# Agent Breakglass "Kill Switch" & Isolation

A Service Extensions `ext_proc` callout, used as an **authorization
extension**, that gives automated real-time containment for compromised AI
agents. It ingests anomaly findings from three detection sources, evaluates
them through a policy engine, and -- on a match -- marks the agent
`BLOCKED` in a Firestore-backed state store. From that moment, every
subsequent request from that agent is denied at the gateway boundary with
an immediate `403`, without mutating any persistent IAM policy or gateway
routing configuration.

The callout implementation does **not** itself proxy traffic; it only
answers ALLOW/DENY. The load balancer / Agent Gateway enforces the
decision.

## Architecture

```
 Detection Sources                    Customer VPC / Google Cloud
 ┌────────────────┐                                                        │
 │ Vertex Anomaly   │ poll  ┌──────────────────────────────────────────┐   │
 │ Detection        ├──────►│ Ingestion (Cloud Run, FastAPI)            │   │
 ├────────────────┤ push  │  /webhook/scc  /webhook/wiz               │   │
 │ Security Command │──────►│  /poll/anomaly-detection                  │   │
 │ Center (Pub/Sub)  │       │   - Decider: dry_run -> exempt -> severity│   │
 ├────────────────┤ push  │   - Actuator: block Firestore + revoke IAM │   │
 │ Wiz               │──────►│                                            │   │
 └────────────────┘       └───────────────┬────────────────────────────┘   │
                                            │ write                          │
                                            ▼                                │
                                   ┌──────────────────┐                     │
                                   │ Blocked State     │                     │
                                   │ Store (Firestore) │                     │
                                   └────────┬──────────┘                     │
                                            │ read (short-TTL local cache)   │
 Client Agent                               │                                │
  │  HTTPS request                          ▼                                │
  ▼                              ┌────────────────────────────────────┐     │
 Global External Application LB │  Traffic Extension (authz role)      │    │
  ────────────────────────────► │   Callout (ext_proc, Cloud Run)      │    │
   403 if BLOCKED                │    on_request_headers -> ALLOW/DENY  │    │
                                  └───────────────┬──────────────────────┘   │
                                                   │ if ALLOW                 │
                                                   ▼                          │
                                          Vertex AI / Agent Platform          │
                                          / downstream MCP servers            │
```

## How It Works

### Containment (hot path)

1. **Client agent** sends a request through the load balancer / Agent
   Gateway, carrying its identity in `x-agent-id` (or `x-spiffe-id`).
2. **Traffic Extension** (configured with `supported_events =
   ["REQUEST_HEADERS"]` -- the callout never touches the body) streams the
   request headers to the callout.
3. **Callout** (`service_callout_example.py::on_request_headers`) looks up
   the agent ID in the Blocked State Store (Firestore, fronted by a
   short-TTL local cache -- default 5s -- so the hot path rarely makes a
   network call). `BLOCKED` -> returns an `ImmediateResponse` with `403`.
   `ACTIVE` / not found -> returns `None` (pass through).
4. If the state-store lookup itself fails (Firestore outage, network
   partition), the callout **fails closed** by default (`FAIL_OPEN=false`)
   -- the opposite default from the other two examples in this collection,
   because an unreachable kill switch must not silently become a bypass.

### Containment (control plane)

1. A security detector -- **Vertex Anomaly Detection** (polled by Cloud
   Scheduler), **Security Command Center** (Pub/Sub push), or **Wiz**
   (HTTPS webhook) -- reports a finding to the ingestion HTTP app running
   alongside the callout.
2. Each source's adapter (`adapters/vertex_anomaly.py`, `adapters/scc.py`,
   `adapters/wiz.py`) normalizes the vendor-specific payload into a common
   `Finding(agent_id, severity, rationale, source, source_finding_id)`.
3. The **Decider** (`decider.py`) evaluates it: `dry_run` short-circuits
   first (log only, no actuation); then an `exempt_agents` check; then a
   per-source severity threshold (`MIN_SEVERITY_VERTEX_ANOMALY`,
   `MIN_SEVERITY_SCC`, `MIN_SEVERITY_WIZ`). The service is stateless (no
   dedup ledger), so duplicate findings for an already-blocked agent are
   expected -- the Actuator's block is an idempotent upsert.
4. On a `BLOCK` decision, the **Actuator** (`actuator.py`) runs a two-stage
   pipeline:
   - **Stage 1 -- Gateway egress block (fastest time-to-mitigate):**
     upsert the agent as `BLOCKED` in Firestore. This is what the hot path
     above actually enforces.
   - **Stage 2 -- IAP IAM revocation (defense-in-depth, best-effort):**
     remove the agent principal from `roles/iap.egressor` on every
     resource in `MCP_RESOURCE_LIST`, via a read-modify-write against the
     Cloud Resource Manager IAM API, so a request that somehow bypasses
     the gateway still can't reach protected MCP servers.
5. Every containment attempt writes an immutable structured audit log
   entry (`block_succeeded` / `block_partial_failure`) -- the sole source
   of truth used for manual restoration.

### Manual restoration only

There is **no automated unblock path** anywhere in this callout, to avoid
the risk of an automated "restore" loop undoing a containment before an
incident is actually resolved. The only way to clear a block is the admin
CLI, run out-of-band by an operator who has reviewed the audit log:

```bash
python3 -m extproc.example.agent_breakglass.admin_cli status <agent_id>
python3 -m extproc.example.agent_breakglass.admin_cli unblock <agent_id> --confirm
```

## Deploy to Google Cloud

> [!IMPORTANT]
> There is intentionally **no local-dev path** for this sample. The ext_proc
> chain depends on a real GCLB forwarding rule, a Firestore database, and
> (for Wiz/SCC) real webhook sources, none of which an Envoy stand-in
> replicates faithfully. Deploy to GCP to exercise it.

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated with ADC
- A GCP project with Vertex AI enabled (used here as the demo destination
  the authorization extension guards)

#### IAM roles

Scoped for sample/testing deployments. Use least-privilege equivalents in
production, particularly `roles/resourcemanager.projectIamAdmin` -- narrow
it to the specific MCP resources the Actuator manages.

| Role | Purpose |
|------|---------|
| `roles/compute.admin` | Load balancer, backend services, NEGs |
| `roles/run.admin` | Cloud Run services, revisions, IAM bindings |
| `roles/networkservices.admin` | Service Extensions traffic extension |
| `roles/datastore.owner` | Firestore database creation |
| `roles/pubsub.admin` | SCC push topic/subscription |
| `roles/cloudscheduler.admin` | Anomaly-detection poll job |
| `roles/iam.serviceAccountUser` | Bind the Cloud Run service account |
| `roles/artifactregistry.admin` | Create repos, push/pull images |
| `roles/serviceusage.serviceUsageAdmin` | Enable required GCP APIs |
| `roles/cloudbuild.builds.editor` | Submit Cloud Build jobs |

### 1. Authenticate

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Enable required APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudresourcemanager.googleapis.com \
  cloudscheduler.googleapis.com \
  compute.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  networkservices.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com
```

### 3. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create agent-breakglass \
  --repository-format=docker --location=us-central1
```

### 4. Build and push the callout image

Run from `callouts/python/` (the build context is the package root):

```bash
cd callouts/python
gcloud builds submit \
  --config=extproc/example/agent_breakglass/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID
```

### 5. Configure and apply Terraform

```bash
cd extproc/example/agent_breakglass/deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, region, callout_image, thresholds,
# mcp_resource_list, and (if used) the Wiz webhook secret.
terraform init
terraform plan
terraform apply
```

If Security Command Center is in scope, point its notification config at
the `scc_pubsub_topic` output. If Wiz is in scope, register
`{ingestion_service_url}/webhook/wiz` with your Wiz shared secret.

### 6. Test the deployment

```bash
LB_IP=$(terraform output -raw load_balancer_ip)
INGESTION_URL=$(terraform output -raw ingestion_service_url)

# 1. Confirm a normal request passes through.
curl -sk https://$LB_IP/v1/projects/YOUR_PROJECT/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent \
  -H "x-agent-id: test-agent-1" -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"hi"}]}]}'

# 2. Simulate a Wiz finding above the severity threshold to trigger containment.
curl -s -X POST $INGESTION_URL/webhook/wiz \
  -H "Content-Type: application/json" \
  -H "x-wiz-signature: $(echo -n '{"issue":{"resourceExternalId":"test-agent-1","severity":"HIGH","type":"anomalous-tool-use"}}' | openssl dgst -sha256 -hmac "$WIZ_SECRET" | cut -d' ' -f2)" \
  -d '{"issue":{"resourceExternalId":"test-agent-1","severity":"HIGH","type":"anomalous-tool-use"}}'

# 3. Confirm the same request from step 1 is now denied.
curl -sk -o /dev/null -w "%{http_code}\n" https://$LB_IP/v1/projects/YOUR_PROJECT/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent \
  -H "x-agent-id: test-agent-1" -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"hi"}]}]}'
# -> 403

# 4. Restore.
python3 -m extproc.example.agent_breakglass.admin_cli unblock test-agent-1 --confirm
```

### 7. Tear down

```bash
terraform destroy
gcloud artifacts repositories delete agent-breakglass --location=us-central1 --quiet
gcloud storage rm -r gs://YOUR_PROJECT_ID_cloudbuild/
```

### What gets deployed

| Resource | Purpose |
|----------|---------|
| Cloud Run (callout) | The ext_proc authorization callout, hot-path ALLOW/DENY |
| Cloud Run (ingestion) | FastAPI app for the three finding sources -- same image, different port |
| Firestore database | Blocked State Store |
| Pub/Sub topic + push subscription | SCC finding delivery |
| Cloud Scheduler job | Vertex Anomaly Detection poll trigger (optional) |
| Global external Application LB | Entry point with a self-signed cert |
| Internet NEG + backend service | Vertex AI (demo destination) |
| Serverless NEG | Cloud Run callout |
| Traffic Extension | Invokes the callout on `REQUEST_HEADERS` only |

## Testing

```bash
cd callouts/python
pip install -r requirements.txt -r requirements-test.txt \
  -r extproc/example/agent_breakglass/additional-requirements.txt
python -m pytest extproc/tests/agent_breakglass_test.py -v
```

The test file lives in the shared `extproc/tests/` tree (flat
`agent_breakglass_test.py` naming), not under `extproc/example/
agent_breakglass/`, so it's picked up by CI's `pytest extproc/tests/` the
same way every other example's tests are.

Pure unit tests: no gRPC server, no Firestore, no network. Covers the
Decider's dry-run/exemption/severity-threshold logic.

## File structure

```
agent_breakglass/
├── service_callout_example.py     # ext_proc callout: hot-path ALLOW/DENY + boots ingestion
├── __init__.py
├── decider.py                     # dry_run -> exempt_agents -> severity threshold
├── actuator.py                    # stage 1: Firestore block; stage 2: IAP IAM revocation; audit log
├── findings.py                    # Finding contract + Blocked State Store (Firestore)
├── ingestion.py                   # FastAPI app: /webhook/scc, /webhook/wiz, /poll/anomaly-detection
├── admin_cli.py                   # manual-only restoration (`unblock --confirm`)
├── adapters/
│   ├── __init__.py
│   ├── vertex_anomaly.py
│   ├── scc.py
│   └── wiz.py
├── additional-requirements.txt    # google-cloud-firestore, google-auth, fastapi, uvicorn
├── cloudbuild.yaml
├── Dockerfile
├── README.md
└── deploy/
    └── terraform/
        ├── main.tf                # Firestore, Cloud Run x2, Pub/Sub, Scheduler, LB, Traffic Ext
        ├── variables.tf
        └── terraform.tfvars.example

extproc/tests/
└── agent_breakglass_test.py       # pure unit tests -- shared tree, not per-example
```

## Environment variables (callout / ingestion)

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | (required) | Project hosting Firestore and the IAM resources. |
| `FAIL_OPEN` | `false` | On state-store lookup failure, allow (`true`) or deny (`false`, recommended). |
| `DRY_RUN` | `false` | Log intended containment without actually blocking. |
| `EXEMPT_AGENTS` | (none) | Comma-separated agent IDs never blocked. |
| `MIN_SEVERITY_VERTEX_ANOMALY` / `_SCC` / `_WIZ` | `70` / `60` / `60` | Per-source severity threshold (0-100). |
| `FIRESTORE_COLLECTION` | `breakglass_blocked_agents` | Blocked State Store collection name. |
| `STATE_CACHE_TTL_SECONDS` | `5` | Local cache TTL in front of Firestore on the hot path. |
| `MCP_RESOURCE_LIST` | (none) | Comma-separated Resource Manager resource names for IAM revocation. |
| `IAP_EGRESSOR_ROLE` | `roles/iap.egressor` | Role removed on containment (stage 2). |
| `VERTEX_ANOMALY_POLL_ENDPOINT` | (none) | Enables `/poll/anomaly-detection` when set. |
| `WIZ_WEBHOOK_SHARED_SECRET` | (none) | HMAC secret for verifying Wiz webhook signatures. |
| `INGESTION_HTTP_PORT` | `8090` | Port the FastAPI ingestion app listens on. |
