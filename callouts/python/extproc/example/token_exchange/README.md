# Token Exchange

A Service Extensions `ext_proc` callout that transparently swaps identity
tokens in-transit, both for external partners calling into Google Cloud
(**inbound**) and for Google Cloud native agents calling third-party APIs
(**outbound**). It replaces static service account keys and hand-rolled
credential-swapping code with a single networking-layer proxy, so client and
backend application code never changes.

The callout implementation does **not** itself proxy traffic; it only
mutates the `Authorization` header. The load balancer forwards the rewritten
request straight to the real destination.

## Architecture

```
INBOUND (external partner -> Vertex AI)

 Azure AD Client                                Customer VPC / Google Cloud
  │ Authorization: Bearer <Azure JWT>                                      │
  ▼                                                                        │
 ┌────────────────────────────────────────────────────────────────────────┐
 │              Global External Application LB                            │
 │                                                                         │
 │   ┌───────────────────┐        ┌────────────────────────────────────┐  │
 │   │ URL Map           │  hdrs  │  Traffic Extension                  │  │
 │   │  default -> Vertex├───────►│   Callout (ext_proc, Cloud Run)     │  │
 │   │                   │◄───────┤   - STS/WIF exchange (Azure->GCP)   │  │
 │   └────────┬──────────┘  hdrs  │   - stamp X-Goog-Authenticated-User-*│ │
 │            │                   └──────────────────────────────────────┘│
 │            ▼                                                           │
 │   ┌──────────────────┐                                                 │
 │   │ Vertex AI backend│                                                 │
 │   │ Internet NEG     │                                                 │
 │   └────────┬─────────┘                                                 │
 └────────────┼────────────────────────────────────────────────────────────┘
              ▼
   {region}-aiplatform.googleapis.com


OUTBOUND (Google Cloud agent -> Salesforce)

 Gemini Agent (Google JWT) -> Agent Gateway -> Traffic Extension -> Callout
   - exchanges the Google JWT for a native Salesforce token via Salesforce's
     OAuth token endpoint (Salesforce trusts https://accounts.google.com as
     a federated identity source)
   -> forwards to api.my.salesforce.com with the native token
```

## How It Works

### Inbound (external partner -> Google Cloud)

1. **Client** authenticates with its own IdP (e.g. Azure AD) and sends a
   request to the load balancer with `Authorization: Bearer <third-party JWT>`.
2. **Traffic Extension** streams the request headers to the callout over
   gRPC (`REQUEST_HEADERS` only -- Token Exchange never subscribes to the
   body).
3. **Callout** (`service_callout_example.py`) extracts the bearer token and
   calls Google's Security Token Service (`POST
   https://sts.googleapis.com/v1/token`), presenting the third-party token
   as `subject_token` and the configured Workload Identity Pool provider as
   `audience`. STS validates the token against the WIF trust relationship
   and returns a federated Google Cloud access token. If
   `TARGET_SERVICE_ACCOUNT` is set, the callout exchanges that federated
   token again via `iamcredentials.googleapis.com:generateAccessToken` to
   impersonate a single, well-known service account.
4. The callout replaces `Authorization` with the Google Cloud access token
   and appends `X-Goog-Authenticated-User-Email`,
   `X-Goog-Authenticated-User-Id`, and `X-Original-User-Groups`, parsed from
   the (already-trusted-by-STS) source token's claims, for downstream audit
   logging.
5. **Load balancer** forwards the rewritten request to the Vertex AI
   backend, which validates the Google Cloud token and enforces IAM.

### Outbound (Google Cloud agent -> third-party API)

1. **Agent** sends a request through the Agent Gateway carrying its own
   Google Cloud-minted identity token (JWT).
2. **Traffic Extension** streams the request headers to the callout.
3. **Callout** extracts the Google JWT and presents it to the target IdP's
   OAuth token endpoint (`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`,
   `assertion=<Google JWT>`). The third-party IdP is configured out-of-band
   to trust Google's OIDC issuer (`https://accounts.google.com`) as a
   federated identity source, and returns a native access token.
4. The callout replaces `Authorization` with the native third-party token.
5. **Load balancer / Agent Gateway** forwards the rewritten request to the
   external service, which authenticates it using its own native token.

### Caching

Both flows cache the exchanged credential, keyed by a SHA-256 hash of the
*source* token (never the raw token itself), with a TTL set to the issued
token's lifetime minus a 60-second safety margin
(`CACHE_SAFETY_MARGIN_SECONDS`). This avoids a synchronous STS/IdP round
trip on every request from a caller reusing the same source token.

### Fail-open

If the exchange fails (STS/IdP unreachable, timeout, malformed token), the
callout passes the request through with its original, unexchanged
credential by default (`FAIL_OPEN=true`) -- IAM on the backend remains
responsible for rejecting invalid credentials, so a callout outage doesn't
become a total system outage. Set `FAIL_OPEN=false` to reject with `401`
instead.

## Deploy to Google Cloud

> [!IMPORTANT]
> There is intentionally **no local-dev path** for this sample. The ext_proc
> chain depends on a real GCLB forwarding rule and a configured Workload
> Identity Federation pool / external IdP trust relationship, neither of
> which an Envoy stand-in replicates faithfully. Deploy to GCP to exercise it.

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated with ADC
- **INBOUND**: a Workload Identity Federation pool + OIDC provider already
  configured to trust your external IdP (e.g. Azure AD)
- **OUTBOUND**: the target third-party IdP configured to trust
  `https://accounts.google.com` as a federated identity source

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
| `roles/serviceusage.serviceUsageAdmin` | Enable required GCP APIs |
| `roles/cloudbuild.builds.editor` | Submit Cloud Build jobs |
| `roles/storage.admin` | Cloud Build source staging bucket |

The callout's own runtime identity needs `roles/aiplatform.user` (or
narrower) on the target project for INBOUND mode when impersonating
`target_service_account`, granted via
`roles/iam.serviceAccountTokenCreator` on that target SA (Terraform does
this for you when `target_service_account` is set).

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
  iamcredentials.googleapis.com \
  networkservices.googleapis.com \
  run.googleapis.com \
  sts.googleapis.com
```

### 3. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create token-exchange \
  --repository-format=docker --location=us-central1
```

### 4. Build and push the callout image

Run from `callouts/python/` (the build context is the package root):

```bash
cd callouts/python
gcloud builds submit \
  --config=extproc/example/token_exchange/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID
```

### 5. Configure and apply Terraform

```bash
cd extproc/example/token_exchange/deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, region, callout_image, mode, and the
# WIF/IdP settings for the direction you're deploying.
terraform init
terraform plan
terraform apply
```

### 6. Test the deployment

```bash
LB_IP=$(terraform output -raw load_balancer_ip)

# INBOUND: present a third-party (e.g. Azure AD) OIDC token
curl -sk https://$LB_IP/v1/projects/YOUR_PROJECT/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent \
  -H "Authorization: Bearer $AZURE_AD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Say hi"}]}]}'
```

### 7. Tear down

```bash
terraform destroy
gcloud artifacts repositories delete token-exchange --location=us-central1 --quiet
gcloud storage rm -r gs://YOUR_PROJECT_ID_cloudbuild/
```

### What gets deployed

| Resource | Purpose |
|----------|---------|
| Cloud Run (callout) | The ext_proc callout, header-only token exchange |
| Global external Application LB | Entry point with a self-signed cert |
| Internet NEG + backend service | The real destination (Vertex AI or the third-party API) |
| Serverless NEG | Cloud Run callout |
| URL map | Forwards everything to the destination backend |
| Traffic Extension | Invokes the callout on `REQUEST_HEADERS` only |

## Testing

```bash
cd callouts/python
pip install -r requirements.txt -r requirements-test.txt \
  -r extproc/example/token_exchange/additional-requirements.txt
python -m pytest extproc/example/token_exchange/tests/test_token_exchange.py -v
```

Pure unit tests: no gRPC server, no network. Covers the SHA-256 cache
keying/TTL and the best-effort JWT claim extraction used for audit headers.

## File structure

```
token_exchange/
├── service_callout_example.py     # ext_proc callout, header-only
├── additional-requirements.txt    # requests
├── cloudbuild.yaml                # Cloud Build config for the callout image
├── Dockerfile                     # Callout container image
├── README.md
├── tests/
│   └── test_token_exchange.py
└── deploy/
    └── terraform/
        ├── main.tf                # LB, NEG, backend, URL map, Traffic Ext
        ├── variables.tf
        └── terraform.tfvars.example
```

## Environment variables (callout)

| Variable | Default | Description |
|----------|---------|-------------|
| `TOKEN_EXCHANGE_MODE` | `INBOUND` | `INBOUND` or `OUTBOUND`. |
| `FAIL_OPEN` | `true` | On exchange failure, pass the original credential through (`true`) or reject with 401 (`false`). |
| `CALLOUT_TIMEOUT_SECONDS` | `10` | Timeout budget for the STS / external IdP HTTP call. |
| `CACHE_SAFETY_MARGIN_SECONDS` | `60` | Subtracted from the issued token's lifetime before caching. |
| `WIF_AUDIENCE` | (none) | Workload Identity Pool provider audience. Required for `INBOUND`. |
| `STS_ENDPOINT` | `https://sts.googleapis.com/v1/token` | Google STS token-exchange endpoint. |
| `REQUESTED_SCOPE` | `https://www.googleapis.com/auth/cloud-platform` | Scope requested on the exchanged GCP token. |
| `TARGET_SERVICE_ACCOUNT` | (none) | If set, impersonate this SA after the STS exchange (`INBOUND`). |
| `EXTERNAL_TOKEN_ENDPOINT` | (none) | Third-party IdP's OAuth token endpoint. Required for `OUTBOUND`. |
| `EXTERNAL_CLIENT_ID` | (none) | Client ID registered with the external IdP, if required. |
