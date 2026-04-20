# LiteLLM Gateway — Service Extensions Callout

A Service Extensions ext_proc callout that acts as a **policy enforcer** on top of a LiteLLM gateway. LiteLLM translates OpenAI-compatible requests to any supported provider (Vertex AI, OpenAI, Anthropic, etc.) while the callout inspects each request at the load balancer, tags it with metadata, and can reject disallowed models before they ever reach the LLM.

This sample uses **Vertex AI** as the LLM provider — everything stays inside Google Cloud, authentication is IAM-based, and no external API keys are needed.

## Architecture

```
  Client
   │ POST /v1/chat/completions  (OpenAI format)
   ▼
  ┌──────────────────────────────────────────────────────┐
  │              Google Cloud ALB                        │
  │                                                      │
  │  ┌──────────┐     ┌─────────────────────┐            │
  │  │ URL Map  │     │  Traffic Extension  │            │
  │  │          │     │                     │            │
  │  │ /v1/* ───┼────►│  Callout (ext_proc) │            │
  │  │ /chat/*  │     │  - inspect request  │            │
  │  │ …        │     │  - enforce policy   │            │
  │  │          │     │  - tag headers      │            │
  │  │          │     │  - allow / reject   │            │
  │  │          │     └──────────┬──────────┘            │
  │  │          │                │ allowed               │
  │  │          │                ▼                       │
  │  │          │     ┌─────────────────────┐            │
  │  │          ├────►│   LiteLLM backend   │            │
  │  │          │     │   (Cloud Run)       │            │
  │  │ default ─┼────►│                     │            │
  │  │          │     │  calls Vertex AI    │            │
  │  │          │     │  using ADC          │            │
  │  │          │     └──────────┬──────────┘            │
  │  └──────────┘                │                       │
  └──────────────────────────────┼───────────────────────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │  Vertex AI   │
                          │  (Gemini,    │
                          │   Claude,    │
                          │   Llama)     │
                          └──────────────┘
```

## How It Works

1. **Client** sends an OpenAI-compatible request (e.g. `POST /v1/chat/completions`) to the load balancer.
2. **URL Map** routes LLM paths (`/v1/*`, `/chat/*`, `/completions`, `/embeddings`) to the LiteLLM Cloud Run backend.
3. **Traffic Extension** intercepts the request and forwards it to the callout via gRPC.
4. **Go callout** inspects the request:
   - Validates the JSON body (rejects with 400 if invalid)
   - Enforces the `ALLOWED_MODELS` allowlist (rejects with 403 if the model is not allowed)
   - Scans prompts for `SEC_KEYWORDS` and tags the request with an `x-sec-keyword` header when matched
   - Returns a `BodyResponse` with header mutations — **the callout does not proxy traffic**
5. **Envoy** forwards the (unchanged) request body plus new headers to the LiteLLM backend.
6. **LiteLLM** translates the OpenAI request to the Vertex AI native format and calls Vertex AI using the Cloud Run service account (ADC).
7. **Response headers phase** — when matched keywords are present, the callout is invoked again and mirrors `x-sec-keyword` onto the response so it's visible to the client.
8. **Response** flows back through the LB to the client.

Non-LLM paths skip the callout entirely and hit the default upstream backend.

### Supported Endpoints

| Path | Type |
|------|------|
| `/v1/chat/completions` | Chat |
| `/v1/completions` | Text completion |
| `/v1/embeddings` | Embeddings |
| `/v1/models` | Model discovery |
| `/chat/completions` | Chat (alias) |
| `/completions` | Text completion (alias) |
| `/embeddings` | Embeddings (alias) |

### Policy features

- **Model allowlist** — set `ALLOWED_MODELS=modelA,modelB`. Requests for any other model get rejected with `403`. Empty (default) allows all models exposed by LiteLLM.
- **Keyword detection** — set `SEC_KEYWORDS=word1,word2`. When a prompt message contains any keyword, the callout adds `x-sec-keyword: word1,word2` to **both** the forwarded request (for upstream logs) **and** the client-facing response (visible in browser devtools).

## Quick Start (Local)

### Prerequisites

- Docker and Docker Compose
- `gcloud` CLI
- A GCP project with **Vertex AI API enabled** and Gemini models accessible in your region

### 1. Authenticate for Vertex AI

LiteLLM uses Application Default Credentials to call Vertex AI. Run once on your host:

```bash
gcloud auth application-default login
```

Then set these environment variables so `docker-compose` can find your ADC file and project info:

```bash
# Linux / macOS
export ADC_FILE=$HOME/.config/gcloud/application_default_credentials.json

# Windows (Git Bash / WSL)
export ADC_FILE=$APPDATA/gcloud/application_default_credentials.json

export GCP_PROJECT_ID=your-project-id
export GCP_REGION=us-central1
```

### 2. Configure models

Edit `deploy/litellm_config.yaml`. Models use the `vertex_ai/` provider and read project/region from env vars:

```yaml
model_list:
  - model_name: vertex/gemini-2.5-flash
    litellm_params:
      model: vertex_ai/gemini-2.5-flash
      vertex_project: os.environ/GCP_PROJECT_ID
      vertex_location: os.environ/GCP_REGION
```

### 3. Start the services

```bash
cd deploy
docker-compose up --build
```

This starts three containers:

| Endpoint | Container | Purpose |
|----------|-----------|---------|
| `http://localhost:8000` | Envoy | Simulates the Google Cloud ALB — calls the callout as an ext_proc filter, then routes to LiteLLM. Full chain. |
| `http://localhost:4000` | LiteLLM | Direct access to the LiteLLM proxy (bypasses the callout). |
| `http://localhost:9901` | Envoy admin | Stats, config dump, health. |

Docker-compose mounts your host ADC into the LiteLLM container so it can call Vertex AI with your user credentials.

### 4. Test the full chain via Envoy

The Envoy service is configured with the same ext_proc filter as the Cloud Run deployment, so local testing exercises the full chain (policy enforcement + LiteLLM + Vertex AI):

```bash
# Basic chat completion — goes through the callout
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "vertex/gemini-2.5-flash",
    "messages": [{"role": "user", "content": "What is Service Extensions?"}]
  }' | jq .choices[0].message.content

# Trigger keyword detection (check for x-sec-keyword response header)
curl -is http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"vertex/gemini-2.5-flash","messages":[{"role":"user","content":"tell me about galaxy"}]}' \
  | grep -iE "(HTTP/|x-sec-keyword)"
```

You can also hit LiteLLM directly on `http://localhost:4000` to bypass the policy layer for debugging.

### 5. Try the sample chat UI

```bash
cd sample-ui
npx serve -p 3000 .
```

Open `http://localhost:3000` — it auto-connects to LiteLLM on `localhost:4000` (bypassing the callout). To exercise the full chain instead, open `http://localhost:3000/?api=http://localhost:8000` which routes through Envoy.

## Adding Models

All model configuration lives in `deploy/litellm_config.yaml`. LiteLLM supports [100+ providers](https://docs.litellm.ai/docs/providers) — no code changes needed.

Model names use the `provider/model` convention so users can see which provider they are using in the UI dropdown.

### Add a Gemini model

```yaml
model_list:
  - model_name: vertex/gemini-2.5-flash
    litellm_params:
      model: vertex_ai/gemini-2.5-flash
      vertex_project: os.environ/GCP_PROJECT_ID
      vertex_location: os.environ/GCP_REGION
```

### Third-party models via Vertex AI Model Garden

The sample config ships with three widely-used Model-as-a-Service (MaaS) partner models alongside Gemini. Each one must be enabled first in [Model Garden](https://console.cloud.google.com/vertex-ai/model-garden), and most are region-specific.

| Model | Family | License | Region (sample) |
|-------|--------|---------|-----------------|
| Llama 3.3 70B | Meta | Llama Community License (open weights) | `us-central1` |
| Qwen 3 235B Instruct | Alibaba | Apache 2.0 | `us-central1` |
| Mistral Small 2503 | Mistral AI | Mistral Research License | `us-central1` |

```yaml
- model_name: vertex/llama-3.3-70b
  litellm_params:
    model: vertex_ai/meta/llama-3.3-70b-instruct-maas
    vertex_project: os.environ/GCP_PROJECT_ID
    vertex_location: us-central1
```

### Self-deployed Vertex AI endpoints

For models that aren't available as MaaS — Gemma, DeepSeek, fine-tuned variants, custom models from Hugging Face — you deploy them yourself to a dedicated Vertex AI endpoint and point LiteLLM at the endpoint ID.

**Steps:**

1. In the Console → Vertex AI → Model Garden, click **Deploy model** on the model you want. Vertex creates an Endpoint backed by GPU VMs.
2. Copy the numeric endpoint ID from the endpoint details page.
3. Add it to `litellm_config.yaml` and rebuild the LiteLLM image:

```yaml
- model_name: vertex/my-self-hosted-model
  litellm_params:
    model: vertex_ai/openai/ENDPOINT_ID_HERE
    vertex_project: os.environ/GCP_PROJECT_ID
    vertex_location: us-central1
```

Everything else (callout, load balancer, traffic extension, policies) stays the same — only the LiteLLM entry changes.

### Mix providers in a single load-balanced model

```yaml
model_list:
  - model_name: fast-chat
    litellm_params:
      model: vertex_ai/gemini-2.5-flash
      vertex_project: os.environ/GCP_PROJECT_ID
      vertex_location: us-central1
  - model_name: fast-chat
    litellm_params:
      model: vertex_ai/meta/llama-3.3-70b-instruct-maas
      vertex_project: os.environ/GCP_PROJECT_ID
      vertex_location: us-central1
```

Requests to model `fast-chat` are load-balanced across both providers.

## Deploy to Google Cloud (Cloud Run)

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated with application default credentials
- Go >= 1.24 (for building the callout image)

#### IAM Roles

The following roles are scoped for **sample/testing deployments**. For production, apply the principle of least privilege with more granular permissions.

| Role | Purpose |
|------|---------|
| `roles/compute.admin` | VPC, subnets, load balancer, backend services, NEGs |
| `roles/run.admin` | Cloud Run services, revisions, IAM bindings |
| `roles/networkservices.admin` | Service Extensions traffic policies |
| `roles/iam.serviceAccountUser` | Bind service accounts to Cloud Run |
| `roles/iam.serviceAccountAdmin` | Create the LiteLLM service account |
| `roles/artifactregistry.admin` | Create repos, push/pull images |
| `roles/serviceusage.serviceUsageAdmin` | Enable required GCP APIs |
| `roles/aiplatform.user` (on the LiteLLM SA) | LiteLLM calls Vertex AI |
| `roles/cloudbuild.builds.editor` | Submit Cloud Build jobs |
| `roles/storage.admin` | Cloud Build source staging bucket |

> **Production note:** Replace admin roles with granular equivalents (e.g. `compute.networkAdmin` + `compute.loadBalancerAdmin` instead of `compute.admin`, `run.developer` instead of `run.admin`).

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
  run.googleapis.com
```

### 3. Create Artifact Registry repository

```bash
gcloud artifacts repositories create litellm-gateway \
  --repository-format=docker \
  --location=us-central1
```

### 4. Build and push images

Build the Go callout image (from the `callouts/go` directory):

```bash
cd callouts/go

gcloud builds submit \
  --config=extproc/examples/litellm_gateway/deploy/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID .
```

Build the LiteLLM image (with model config baked in):

```bash
cd extproc/examples/litellm_gateway/deploy

gcloud builds submit \
  --config=cloudbuild-litellm.yaml \
  --project=YOUR_PROJECT_ID .
```

(Optional) Build the sample UI image if you want the chat interface as the upstream application:

```bash
cd ../sample-ui

gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=YOUR_PROJECT_ID .
```

### 5. Deploy with Terraform

```bash
cd ../deploy/terraform

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project ID, images, and optional policy settings.

terraform init
terraform plan
terraform apply
```

Terraform creates:
- A dedicated service account for LiteLLM with `roles/aiplatform.user`
- Two Cloud Run services: `litellm-gateway-callout` (policy) and `litellm-gateway-litellm` (LLM gateway)
- A URL map that routes LLM paths to the LiteLLM backend
- A Service Extensions traffic extension that invokes the callout for LLM paths

### 6. Test the deployment

```bash
# Get the load balancer IP
LB_IP=$(terraform output -raw load_balancer_ip)

# Non-LLM traffic (passes through to upstream)
curl -sk https://$LB_IP/

# LLM traffic (LB → traffic extension → callout → LiteLLM → Vertex AI)
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "vertex/gemini-2.5-flash", "messages": [{"role": "user", "content": "Hello"}]}'

# List available models
curl -sk https://$LB_IP/v1/models

# Try a disallowed model (if allowed_models is set, this returns 403)
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "some-other-model", "messages": [{"role": "user", "content": "Hi"}]}'
```

If you deployed the sample UI as upstream, open `https://$LB_IP/` in a browser (accept the self-signed cert) to use the chat interface directly through the ALB.

### 7. Tear down

```bash
# Destroy infrastructure
terraform destroy

# Delete container images
gcloud artifacts repositories delete litellm-gateway \
  --location=us-central1 --quiet

# Delete Cloud Build staging bucket
gcloud storage rm -r gs://YOUR_PROJECT_ID_cloudbuild/
```

### What gets deployed

| Resource | Purpose |
|----------|---------|
| VPC + subnets (main + proxy-only) | Network for the regional external LB |
| Service account `litellm-gateway-sa` | Identity for LiteLLM, has `aiplatform.user` |
| Cloud Run (callout) | Policy enforcer invoked by the traffic extension |
| Cloud Run (litellm) | LiteLLM proxy, calls Vertex AI via ADC |
| Cloud Run (upstream app) | Handles non-LLM traffic (hello-app or sample-ui) |
| Regional HTTPS Load Balancer | Entry point with self-signed cert |
| URL Map | Routes LLM paths to LiteLLM, rest to upstream |
| Traffic Extension | Calls the callout for LLM paths |

## Testing

```bash
cd callouts/go
go test ./extproc/examples/litellm_gateway/ -v
```

## File Structure

```
litellm_gateway/
├── litellm_gateway.go              # ext_proc callout implementation
├── litellm_gateway_test.go         # Unit tests
├── README.md
├── deploy/
│   ├── Dockerfile                   # Local build (pre-built binary)
│   ├── Dockerfile.cloudrun          # Cloud Run build (from source)
│   ├── Dockerfile.litellm           # Custom LiteLLM image with config
│   ├── docker-compose.yml           # Local dev environment (Envoy + callout + LiteLLM)
│   ├── envoy.yaml                   # Envoy config for local ext_proc chain
│   ├── litellm_config.yaml          # LiteLLM model configuration
│   ├── cloudbuild.yaml              # Cloud Build for callout
│   ├── cloudbuild-litellm.yaml      # Cloud Build for LiteLLM
│   └── terraform/
│       ├── main.tf                  # Infrastructure
│       ├── variables.tf             # Terraform variables
│       └── terraform.tfvars.example # Example config
└── sample-ui/
    ├── index.html                   # Chat interface for interactive testing
    ├── Dockerfile                   # Nginx container for Cloud Run deployment
    └── cloudbuild.yaml              # Cloud Build config
```

## Environment Variables

### Callout

| Variable | Default | Description |
|----------|---------|-------------|
| `EXAMPLE_TYPE` | — | Must be `litellm_gateway` |
| `SEC_KEYWORDS` | — | Comma-separated keywords to detect in prompts. When found, adds `x-sec-keyword` header to the forwarded request |
| `ALLOWED_MODELS` | — | Comma-separated model allowlist. Empty means all models allowed. Disallowed models get rejected with 403 |

### LiteLLM

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | — | GCP project used by `vertex_ai/` models in `litellm_config.yaml` |
| `GCP_REGION` | `us-central1` | Vertex AI region |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to ADC JSON (local dev only; Cloud Run uses the service account automatically) |