# LiteLLM Gateway — Service Extensions Callout

An ext_proc (gRPC) callout that intercepts LLM requests at the Google Cloud Application Load Balancer and routes them through [LiteLLM](https://github.com/BerriAI/litellm) to any supported LLM provider (Gemini, Groq, OpenRouter, OpenAI, Anthropic, etc.).

## Architecture

```
                        ┌─────────────────────────────────────────────────┐
                        │           Google Cloud ALB                      │
                        │                                                 │
  Client Request        │   ┌──────────────┐    ┌─────────────────────┐  │
  POST /v1/chat/───────►│   │  URL Map /   │    │  Traffic Extension  │  │
  completions           │   │  Forwarding  │───►│  (Service Ext)      │  │
                        │   └──────────────┘    └────────┬────────────┘  │
                        │                                │               │
                        └────────────────────────────────┼───────────────┘
                                                         │ gRPC ext_proc
                                                         ▼
                                  ┌──────────────────────────────────────┐
                                  │        Cloud Run Service             │
                                  │                                      │
                                  │  ┌────────────┐   ┌──────────────┐  │
                                  │  │ Go Callout │──►│   LiteLLM    │  │
                                  │  │  (ext_proc)│   │   (sidecar)  │  │
                                  │  │  :8080     │   │   :4000      │  │
                                  │  └────────────┘   └──────┬───────┘  │
                                  │                          │          │
                                  └──────────────────────────┼──────────┘
                                                             │ HTTPS
                                                             ▼
                                                    ┌─────────────────┐
                                                    │   LLM Provider  │
                                                    │ (Gemini, Groq,  │
                                                    │  OpenRouter...) │
                                                    └─────────────────┘
```

## How It Works

1. **Client** sends an OpenAI-compatible request (e.g. `POST /v1/chat/completions`) to the load balancer.
2. **Traffic Extension** matches the request path and forwards it to the callout via gRPC.
3. **Go callout** receives request headers — if the path is an LLM endpoint, it requests body buffering (`ModeOverride: BUFFERED`).
4. **Go callout** receives the buffered body, strips `stream: true`, and forwards it to the LiteLLM sidecar.
5. **LiteLLM** translates the request to the target provider's API (Gemini, Groq, etc.) and returns the response.
6. **Go callout** returns an `ImmediateResponse` — the LLM response goes directly to the client, bypassing the upstream origin entirely.

Non-LLM requests pass through unmodified to the upstream origin.

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

### Optional features

- **Keyword detection** — Set `SEC_KEYWORDS` to a comma-separated list. When any message in the request body contains a keyword, the callout adds an `x-sec-keyword` response header with the matched values. Useful for tagging or monitoring sensitive topics.
- **CORS support** — Set `ENABLE_CORS=true` to add CORS headers and handle OPTIONS preflight requests. Required for browser-based clients accessing the API.

## Quick Start (Local)

### Prerequisites

- Docker and Docker Compose
- An API key for at least one LLM provider (e.g. [Gemini](https://aistudio.google.com/apikey))

### 1. Configure models

Edit `deploy/litellm_config.yaml`. Model names use the `provider/model` convention so each model is clearly identified:

```yaml
model_list:
  - model_name: gemini/2.5-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
  - model_name: groq/llama-3.3-70b
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
```

### 2. Set your API keys

Edit `deploy/docker-compose.yml` and replace the placeholder values for `GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENROUTER_API_KEY`.

### 3. Start the services

```bash
cd deploy
docker-compose up --build
```

This starts:
- **Go callout** on port `8080` (gRPC) and `80` (health check)
- **LiteLLM proxy** on port `4000`

### 4. Test it

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-test-master-key" \
  -d '{
    "model": "gemini/2.5-flash",
    "messages": [{"role": "user", "content": "What is Service Extensions?"}]
  }' | jq .choices[0].message.content
```

### 5. Try the sample chat UI

The `sample-ui/` folder contains a lightweight chat interface for interactive testing. Serve it with any static HTTP server:

```bash
cd sample-ui
npx serve -p 3000 .
```

Open `http://localhost:3000` — it auto-connects to LiteLLM on `localhost:4000` and lets you pick any configured model from the dropdown.

## Adding Models

All model configuration lives in `deploy/litellm_config.yaml`. LiteLLM supports [100+ providers](https://docs.litellm.ai/docs/providers). No code changes needed.

Model names use the `provider/model` convention so users can easily tell which provider each model belongs to in the UI (e.g. `gemini/2.5-flash`, `groq/llama-3.3-70b`).

### Providers with free tiers

Useful for testing without paying for credits:

| Provider | Free tier | Env var |
|----------|-----------|---------|
| [Google Gemini](https://aistudio.google.com/apikey) | Yes | `GEMINI_API_KEY` |
| [Groq](https://console.groq.com/keys) | Yes, fast inference | `GROQ_API_KEY` |
| [OpenRouter](https://openrouter.ai/keys) | `:free` models | `OPENROUTER_API_KEY` |

### Add an OpenAI model

```yaml
model_list:
  - model_name: openai/gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
```

Then add `OPENAI_API_KEY` to `docker-compose.yml` (or `terraform.tfvars` for Cloud Run).

### Add an Anthropic model

```yaml
model_list:
  - model_name: anthropic/claude-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ANTHROPIC_API_KEY
```

### Add a load-balanced model (multiple providers)

```yaml
model_list:
  - model_name: fast-chat
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
  - model_name: fast-chat
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
```

Requests to model `fast-chat` will be load-balanced across both providers.

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
| `roles/artifactregistry.admin` | Create repos, push/pull images |
| `roles/serviceusage.serviceUsageAdmin` | Enable required GCP APIs |
| `roles/secretmanager.admin` | Create secrets, manage versions and access |
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
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  networkservices.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com
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

Build the LiteLLM sidecar image (with model config baked in):

```bash
cd extproc/examples/litellm_gateway/deploy

gcloud builds submit \
  --config=cloudbuild-litellm.yaml \
  --project=YOUR_PROJECT_ID .
```

(Optional) Build the sample UI image — needed if you want to serve the chat interface as the upstream application:

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
# Edit terraform.tfvars with your project ID, images, and API keys.
# To serve the chat UI as the upstream, set:
#   upstream_app_image = "us-central1-docker.pkg.dev/YOUR_PROJECT_ID/litellm-gateway/sample-ui:latest"

terraform init
terraform plan
terraform apply
```

### 6. Test the deployment

```bash
# Get the load balancer IP
LB_IP=$(terraform output -raw load_balancer_ip)

# Non-LLM traffic (passes through to upstream)
curl -sk https://$LB_IP/

# LLM traffic (routed through callout → LiteLLM → Gemini)
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini/2.5-flash", "messages": [{"role": "user", "content": "Hello"}]}'

# List available models
curl -sk https://$LB_IP/v1/models
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
| Cloud Run (callout + LiteLLM sidecar) | Processes LLM requests via ext_proc |
| Cloud Run (upstream app) | Handles non-LLM traffic (hello-app or sample-ui) |
| Secret Manager | Stores LLM provider API keys |
| Regional HTTPS Load Balancer | Entry point with self-signed cert |
| Traffic Extension | Routes LLM paths to the callout |

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
│   ├── docker-compose.yml           # Local dev environment
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

| Variable | Default | Description |
|----------|---------|-------------|
| `EXAMPLE_TYPE` | — | Must be `litellm_gateway` |
| `LITELLM_BASE_URL` | `http://localhost:4000` | LiteLLM proxy address |
| `LITELLM_MASTER_KEY` | — | Bearer token for LiteLLM proxy auth (required if LiteLLM is key-protected) |
| `GEMINI_API_KEY` | — | Gemini API key (passed to LiteLLM) |
| `GROQ_API_KEY` | — | Groq API key (optional, free tier) |
| `OPENROUTER_API_KEY` | — | OpenRouter API key (optional, free models) |
| `ENABLE_CORS` | `false` | Set to `true` to add CORS headers and handle OPTIONS preflight (for browser-based access) |
| `SEC_KEYWORDS` | — | Comma-separated keywords to detect in prompts. When found, adds `x-sec-keyword` response header |