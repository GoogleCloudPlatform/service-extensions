# Prompt-Amender

A Service Extensions `ext_proc` callout that centralizes prompt governance
for a fleet of AI agents. It intercepts outgoing `generateContent` requests,
matches the caller's identity/host/path against a hot-reloadable YAML
ruleset, and mutates `system_instruction.parts[].text` in flight -- so
organizational safety guardrails, brand voice, and runtime context (caller
SPIFFE ID, host, path) get injected without any change to client agent
code, and without a redeploy when the policy changes.

## Architecture

```
                                     Customer VPC / Google Cloud
 Agent (SPIFFE SVID)                                                       │
  │  mTLS: generateContent                                                 │
  ▼                                                                        │
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         Agent Gateway                                   │
 │                                                                         │
 │   ┌────────────────────────────┐        ┌─────────────────────────┐    │
 │   │ Traffic Extension           │ hdrs   │ Callout (ext_proc,      │    │
 │   │  x-spiffe-id injected by GW ├───────►│ Cloud Run)              │    │
 │   │                              │◄───────┤  - match rule (glob)   │    │
 │   │  match -> BUFFERED body      │ body  │  - mode_override:      │    │
 │   │  no match -> body skipped    │◄──────┤    request_body_mode   │    │
 │   │                              │───────►│  - mutate system_     │    │
 │   └──────────────┬───────────────┘ body  │    instruction.parts[]│    │
 │                  │                        └──────────┬───────────┘    │
 │                  ▼                                    │ HTTPS: Load   │
 │         ┌─────────────────┐                            │ Rules        │
 │         │ Vertex AI /      │                            ▼              │
 │         │ Agent Platform   │                   ┌──────────────────┐   │
 │         └──────────────────┘                   │ Config Source     │   │
 │                                                 │ GCS / Git          │   │
 │                                                 └──────────────────┘   │
 └────────────────────────────────────────────────────────────────────────┘
```

## How It Works

1. **Agent** sends a standard `generateContent` request through the Agent
   Gateway, authenticated via mTLS with its SPIFFE SVID. The gateway
   validates the certificate and injects the caller's SPIFFE ID into a
   trusted `x-spiffe-id` header before invoking the callout.
2. **Header phase** (`on_request_headers`): the callout extracts
   `x-spiffe-id`, `:authority`, and `:path`, and evaluates them against the
   active YAML ruleset using UNIX glob matching (first match wins). It then
   overrides the processing mode for this request:
   `mode_override.request_body_mode = BUFFERED` on a match, or `NONE` on no
   match -- so unmatched traffic (the common case in a multi-tenant
   environment) never pays body-buffering latency.
3. **Body phase** (`on_request_body`, match only): the callout parses the
   buffered JSON body, locates `system_instruction.parts[].text`, and
   applies the matched rule's mutation:

   | Operation | Behavior |
   |-----------|----------|
   | `prepend` | `action.text + "\n\n" + original` |
   | `append` | `original + "\n\n" + action.text` |
   | `replace` | `action.text` |
   | `template` | Jinja2-rendered, with `original_prompt`, `caller_spiffe_id`, `host`, `path` available |

   It re-serializes the payload (preserving `generationConfig`,
   `safetySettings`, and every other field untouched) and returns a
   recalculated `Content-Length`.
4. **Agent Gateway** forwards the mutated request to Vertex AI / Agent
   Platform.

### Hot-reloadable rules

The ruleset is sourced from one of three configurable backends
(`CONFIG_SOURCE`): a static `env` value, a polled `gcs` object (using the
GCS object generation number to detect changes), or a polled `git` branch
(via `git ls-remote`). A background thread performs the poll and executes
an **atomic swap** of the active ruleset -- safe to read from any number of
concurrent request-handling threads without locking. If a newly fetched
configuration fails YAML/Jinja2/semantic validation, the update is
rejected and logged, and the service keeps serving the last-known-good
ruleset; it never crashes on bad config.

### What never gets logged

Per design, the callout's structured logs record only `rule_id`, `op`,
`caller_spiffe_id`, `original_len`, `new_len`, and `latency_ms` -- never
the raw prompt text or rendered template output, to prevent sensitive
context from leaking into operational logs.

### Fail-open

If amendment fails (malformed JSON, missing `system_instruction`, a
template render error, or a body over `MAX_REQUEST_BODY_BYTES`), the
callout passes the request through with its original, unmutated body by
default (`FAIL_OPEN=true`). Set `FAIL_OPEN=false` to reject with `500`
instead.

## Adding / editing rules

Edit `rules.example.yaml` (or your own `rules.yaml`) and upload it to the
configured source:

```bash
# CONFIG_SOURCE=gcs
gsutil cp my-rules.yaml gs://your-project-prompt-amender-rules/rules.yaml

# CONFIG_SOURCE=git
git commit -am "update prompt-amender rules" && git push
```

The callout picks up the change within `POLL_INTERVAL_SECONDS` (default 15s)
-- no redeploy needed.

## Deploy to Google Cloud

> [!IMPORTANT]
> There is intentionally **no local-dev path** for this sample. The ext_proc
> chain depends on a real GCLB forwarding rule and (for `x-spiffe-id`) an
> Agent Gateway performing mTLS/SVID validation, neither of which an Envoy
> stand-in replicates faithfully. Deploy to GCP to exercise it.

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated with ADC
- A GCP project with Vertex AI enabled

#### IAM roles

Scoped for sample/testing deployments. Use least-privilege equivalents in
production.

| Role | Purpose |
|------|---------|
| `roles/compute.admin` | Load balancer, backend services, NEGs |
| `roles/run.admin` | Cloud Run services, revisions, IAM bindings |
| `roles/networkservices.admin` | Service Extensions traffic extension |
| `roles/iam.serviceAccountUser` | Bind the Cloud Run service account |
| `roles/artifactregistry.admin` | Create repos, push/pull images |
| `roles/storage.admin` | Rules bucket + Cloud Build source staging bucket |
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
  compute.googleapis.com \
  iam.googleapis.com \
  networkservices.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com
```

### 3. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create prompt-amender \
  --repository-format=docker --location=us-central1
```

### 4. Build and push the callout image

Run from `callouts/python/` (the build context is the package root):

```bash
cd callouts/python
gcloud builds submit \
  --config=extproc/example/prompt_amender/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID
```

### 5. Configure and apply Terraform

```bash
cd extproc/example/prompt_amender/deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, region, callout_image.
terraform init
terraform plan
terraform apply
```

This seeds the rules bucket with `rules.example.yaml` when `config_source = gcs`.

### 6. Test the deployment

```bash
LB_IP=$(terraform output -raw load_balancer_ip)

curl -sk https://$LB_IP/v1/projects/YOUR_PROJECT/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent \
  -H "x-spiffe-id: principalSet://agents.global.org-123456789012.system.id.goog/support/agent-1" \
  -H "Content-Type: application/json" \
  -d '{"system_instruction":{"parts":[{"text":"You are a customer support assistant."}]},"contents":[{"role":"user","parts":[{"text":"What is the refund policy?"}]}]}'
```

The response should reflect the brand-safety guardrail injected by
`support-safety-inject` in `rules.example.yaml`.

### 7. Tear down

```bash
terraform destroy
gcloud artifacts repositories delete prompt-amender --location=us-central1 --quiet
gcloud storage rm -r gs://YOUR_PROJECT_ID_cloudbuild/
```

### What gets deployed

| Resource | Purpose |
|----------|---------|
| Cloud Run (callout) | The ext_proc callout, header+body mutation |
| GCS bucket | `rules.yaml`, polled for hot reload (when `config_source = gcs`) |
| Global external Application LB | Entry point with a self-signed cert |
| Internet NEG + backend service | Vertex AI |
| Serverless NEG | Cloud Run callout |
| URL map | Forwards everything to the Vertex AI backend |
| Traffic Extension | Invokes the callout on `REQUEST_HEADERS`, `REQUEST_BODY` |

## Testing

```bash
cd callouts/python
pip install -r requirements.txt -r requirements-test.txt \
  -r extproc/example/prompt_amender/additional-requirements.txt
python -m pytest extproc/example/prompt_amender/tests/test_rule_engine.py -v
```

Pure unit tests: no gRPC server, no network. Covers selector glob matching,
all four mutation operations, and ruleset validation (rejecting rules with
no selectors, duplicate IDs, and invalid Jinja2 syntax).

## File structure

```
prompt_amender/
├── service_callout_example.py     # ext_proc callout, header+body mutation
├── rule_engine.py                 # selector matching + mutation operations
├── config_sources.py              # env/GCS/git rule sourcing + hot reload
├── rules.example.yaml
├── additional-requirements.txt    # PyYAML, Jinja2, google-cloud-storage, GitPython
├── cloudbuild.yaml
├── Dockerfile
├── README.md
├── tests/
│   └── test_rule_engine.py
└── deploy/
    └── terraform/
        ├── main.tf                # LB, GCS bucket, backend, URL map, Traffic Ext
        ├── variables.tf
        └── terraform.tfvars.example
```

## Environment variables (callout)

| Variable | Default | Description |
|----------|---------|-------------|
| `FAIL_OPEN` | `true` | On amendment failure, pass the request through unmodified (`true`) or reject with 500 (`false`). |
| `MAX_REQUEST_BODY_BYTES` | `4194304` | Body size limit before amendment is aborted. |
| `CONFIG_SOURCE` | `gcs` | `env`, `gcs`, or `git`. |
| `CONFIG_VALUE` | (none) | Raw YAML, used when `CONFIG_SOURCE=env`. |
| `GCS_RULES_URI` | (none) | `gs://bucket/rules.yaml`, used when `CONFIG_SOURCE=gcs`. |
| `GIT_REPO_URL` / `GIT_BRANCH` / `GIT_RULES_PATH` | (none) / `main` / `rules.yaml` | Used when `CONFIG_SOURCE=git`. |
| `POLL_INTERVAL_SECONDS` | `15` | How often to check the config source for changes. |
