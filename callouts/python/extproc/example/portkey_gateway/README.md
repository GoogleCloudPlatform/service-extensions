# Portkey Gateway

A Service Extensions `ext_proc` callout that fronts a self-hosted **Portkey AI
gateway** to turn a Google Cloud external Application Load Balancer into an
OpenAI-compatible multi-provider gateway. The callout itself does **not** proxy
traffic; it only mutates request and response headers and bodies. Vanilla
OpenAI clients send requests in, the callout rewrites them to provider-native
bytes, and the LB forwards the result to the matching Internet NEG backend
(api.anthropic.com, Vertex AI, Groq, OpenRouter, and so on). Portkey runs as a
**sidecar container** in the same Cloud Run service, no separate deployment.
The callout uses Portkey's `custom_host` feature to intercept the translated
bytes on a loopback port rather than letting Portkey actually call the
provider; the LB owns the outbound connection. Streaming (`stream: true`) is
not supported in this sample and is rejected with HTTP 501.

## Architecture

```
                       x-model-id: anthropic/claude-...
  Client ───────────────────────────────────────────────────────────────┐
   │  POST /v1/chat/completions (OpenAI body, model="provider/...")     │
   ▼                                                                    │
 ┌──────────────────────────────────────────────────────────────────────┴───┐
 │ ┌────────────────────────────┐        ┌────────────────────────────────┐ │
 │ │ URL Map                    │        │ Traffic Extension callout      │ │
 │ │  /v1/* + x-model-id        │  body  │ PortkeyGatewayCallout/Cloud Run│ │
 │ │   prefix match on:         ├───────►│  1. parse model/provider       │ │
 │ │    anthropic/   → BE-A     │◄───────┤  2. mint auth (ADC or API key) │ │
 │ │    groq/        → BE-G     │ headers│  3. call Portkey sidecar at    │ │
 │ │    openrouter/  → BE-O     │ +body  │     localhost:8787 with        │ │
 │ │   /v1/* default → BE-V     │        │     custom_host = :9999        │ │
 │ └──────────┬─────────────────┘        │  4. capture translated bytes   │ │
 │            │ LB forwards              │     POSTed back to :9999       │ │
 │            ▼                          │  5. return as ext_proc body    │ │
 │ ┌────┐ ┌────┐ ┌────┐ ┌────┐           │     and header mutations       │ │
 │ │BE-V│ │BE-A│ │BE-G│ │BE-O│           └────────────────────────────────┘ │
 │ │ NEG│ │ NEG│ │ NEG│ │ NEG│                                              │
 │ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘                                              │
 └───┼──────┼──────┼──────┼─────────────────────────────────────────────────┘
     ▼      ▼      ▼      ▼
  BE-V: {region}-aiplatform.googleapis.com    BE-A: api.anthropic.com
  BE-G: api.groq.com                          BE-O: openrouter.ai

  ─── Portkey sidecar loopback (request phase) ───────────────────────────────
  Callout ──OpenAI body──► Portkey :8787 (custom_host=http://127.0.0.1:9999)
                                │  Portkey translates and POSTs provider bytes
                                ▼
                          Capture server :9999  ──► Callout reads captured bytes
                                                     (returned to LB as mutations)

  ─── Portkey sidecar loopback (response phase) ──────────────────────────────
  LB delivers provider response ──► Callout arms :9998 with provider bytes
  Callout ──original OpenAI body──► Portkey :8787 (custom_host=http://127.0.0.1:9998)
                                          │  Portkey reads replayed provider bytes
                                          ▼
                                    Portkey returns OpenAI-shaped response
                                    Callout returns that to the LB (body mutation)
```

## How It Works

1. **Client** sends a standard OpenAI request (`POST /v1/chat/completions`,
   body `{"model": "anthropic/claude-3-5-sonnet-...", "messages": [...]}`)
   plus a routing header `x-model-id: anthropic/claude-3-5-sonnet-...` (the
   same value as the body's `model` field).
2. **URL Map** evaluates `prefix=/v1/` plus a `prefix_match` on the
   `x-model-id` header (`anthropic/`, `groq/`, `openrouter/`) and selects the
   matching backend service (e.g. the Anthropic Internet NEG). `/v1/*`
   requests with no matching prefix fall through to the Vertex AI backend;
   non-LLM paths go to the upstream app.
3. **Traffic Extension** intercepts the request and streams the headers and body
   to the callout over gRPC (`REQUEST_HEADERS`, then `REQUEST_BODY`).
4. **Callout** (`service_callout_example.py`) parses the `model` field to detect
   the provider (`anthropic/claude-…` → `anthropic`), then mints auth: a short-
   lived ADC bearer token for Vertex AI, or reads the provider's `*_API_KEY` env
   var (mounted from Secret Manager) for the others.
5. **Callout** arms the capture server on `:9999`, then sends the OpenAI body to
   the Portkey sidecar at `localhost:8787` with
   `x-portkey-custom-host: http://127.0.0.1:9999` and the provider API key.
6. **Portkey sidecar** translates the OpenAI request to the provider's native
   format and POSTs the translated bytes to `:9999`, where the callout's capture
   server records the path, headers, and body.
7. **Callout** reads the captured bytes and returns them as ext_proc mutations
   (body + header rewrites for `:path`, `:authority`, `content-length`, auth,
   etc.). The LB forwards the provider-native request to the provider Internet
   NEG already selected by the URL map.
8. **Response phase**: the LB delivers the provider's native response to the
   callout. The callout arms `:9998` with those bytes, then calls the Portkey
   sidecar again with `x-portkey-custom-host: http://127.0.0.1:9998`. Portkey
   GETs the replayed bytes from `:9998` and translates them back to the OpenAI
   response shape.
9. **Client** receives a standard OpenAI-format response, same shape regardless
   of which provider served it.

### The `x-model-id` header

The client sends `x-model-id: <provider>/<model_id>` alongside the request, with the same
value as the body's `model` field. This is required because a GCLB URL map
evaluates backend routing rules **before** any ext_proc callout runs, so the
callout cannot influence which backend the LB has already selected. Routing
must therefore be header-driven.

The URL map uses a `prefix_match` on the provider segment of the model id
(for example, `anthropic/` matches `anthropic/claude-3-5-sonnet-...`). Because
the header value is just the body's `model` field, the client does not need
any extra mapping logic. The sample UI sets it automatically from the
selected model; OpenAI-style SDK clients can set it via `default_headers`.
A `/v1/*` request with no matching prefix falls through to the Vertex AI
backend.

### Supported endpoints

| Path | Type |
|------|------|
| `/v1/chat/completions` | Chat |
| `/v1/completions` | Text completion |
| `/v1/embeddings` | Embeddings |

Only `/v1/`-prefixed paths are supported: the URL map's provider route rules
match on the `/v1/` prefix, so a request on an unprefixed path can never
reach a provider backend.

## Providers

The sample ships with four provider backends. The model id
(`provider/model` convention) is what gets sent in both the request body's
`model` field and the routing `x-model-id` header; the URL map's
`prefix_match` picks the backend from the provider segment:

| Provider | Example model id | Upstream | Auth |
|----------|-----------------|----------|------|
| Vertex AI | `vertex_ai/gemini-2.5-flash` | `{region}-aiplatform.googleapis.com` | ADC (Cloud Run service identity, `roles/aiplatform.user`) |
| Anthropic | `anthropic/claude-3-5-sonnet-20241022` | `api.anthropic.com` | `ANTHROPIC_API_KEY` env var (Secret Manager) |
| Groq | `groq/compound-beta` | `api.groq.com` | `GROQ_API_KEY` env var (Secret Manager) |
| OpenRouter | `openrouter/openai/gpt-oss-20b:free` | `openrouter.ai` | `OPENROUTER_API_KEY` env var (Secret Manager) |

The `vertex_ai` prefix selects Google's published models served by the
Vertex AI API (now delivered as part of the Gemini Enterprise agent
platform). The endpoint, IAM role, and Portkey provider id (`vertex-ai`)
keep their existing names.

Anthropic's Messages API requires `max_tokens`, which OpenAI clients usually
omit. The callout fills in a default of 4096 when the field is absent.

### Adding a provider

1. Add a `ProviderSpec` entry to `PROVIDERS` in
   `extproc/example/portkey_gateway/service_callout_example.py`: supply the
   Portkey provider id, the Internet NEG FQDN, and the API-key env var name (or
   `None` for ADC).
2. Add a matching entry to `_STUBS` in `capture_server.py` that reflects the
   provider's response shape (used by the unit test suite).
3. If the provider needs an API key, add a `*_api_key` variable in
   `deploy/terraform/variables.tf` and wire it into the `env` block of the
   callout Cloud Run service in `deploy/terraform/main.tf`.
4. Add the provider FQDN to the Internet NEG and URL-map `header_matches` list
   in `deploy/terraform/main.tf`.

## Deploy to Google Cloud

> [!IMPORTANT]
> There is intentionally **no local-dev path** for this sample. The ext_proc
> chain depends on a real GCLB URL map with `header_matches` routing, which an
> Envoy stand-in does not replicate faithfully. Deploy to GCP to exercise it.

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated with ADC
- A GCP project with Vertex AI enabled and Gemini accessible in your region
- API keys for any non-Vertex providers you want to use

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
| `roles/secretmanager.admin` | Create secrets for provider API keys |
| `roles/serviceusage.serviceUsageAdmin` | Enable required GCP APIs |
| `roles/cloudbuild.builds.editor` | Submit Cloud Build jobs |
| `roles/storage.admin` | Cloud Build source staging bucket |

The callout runs under the project's default compute service account by default
(it carries `roles/editor`, enough for Vertex AI ADC). For tighter scoping,
create an SA with only `roles/aiplatform.user` and set
`var.callout_service_account` to its email.

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
  secretmanager.googleapis.com
```

### 3. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create portkey-gateway \
  --repository-format=docker --location=us-central1
```

### 4. Build and push the callout image

The Portkey sidecar uses the upstream `portkeyai/gateway` image pulled from
Docker Hub, so no separate build is needed for it. Only the callout image
needs to be built (run from `callouts/python/`, the build context is the
package root):

```bash
cd callouts/python
gcloud builds submit \
  --config=extproc/example/portkey_gateway/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID
```

(Optional) Sample chat UI image: serves as the upstream app for non-LLM paths
and lets you exercise the gateway from a browser. It sets the `x-model-id`
header automatically based on the selected model:

```bash
cd extproc/example/portkey_gateway/sample-ui
gcloud builds submit --config=cloudbuild.yaml --project=YOUR_PROJECT_ID
```

If you build the sample UI, set `upstream_app_image` in `terraform.tfvars` to
the resulting image path
(`us-central1-docker.pkg.dev/YOUR_PROJECT_ID/portkey-gateway/sample-ui:latest`)
before running `terraform apply`.

### 5. Configure and apply Terraform

```bash
cd extproc/example/portkey_gateway/deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, region, callout_image, and the
# *_api_key values for the providers you want to use.
terraform init
terraform plan
terraform apply
```

Terraform creates a **multi-container Cloud Run service**: the callout container
plus a `portkeyai/gateway` sidecar. API keys you put in `terraform.tfvars` are
uploaded to Secret Manager and mounted as env vars (`secret_key_ref`). They
never appear as plain values in the console.

### 6. Test the deployment

```bash
LB_IP=$(terraform output -raw load_balancer_ip)

# Vertex AI (no header needed, it's the default backend)
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"vertex_ai/gemini-2.5-flash","messages":[{"role":"user","content":"Say hi"}]}'

# Anthropic
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-model-id: anthropic/claude-3-5-sonnet-20241022" \
  -d '{"model":"anthropic/claude-3-5-sonnet-20241022","max_tokens":64,"messages":[{"role":"user","content":"Say hi"}]}'

# Groq
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-model-id: groq/compound-beta" \
  -d '{"model":"groq/compound-beta","messages":[{"role":"user","content":"Say hi"}]}'

# OpenRouter
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-model-id: openrouter/openai/gpt-oss-20b:free" \
  -d '{"model":"openrouter/openai/gpt-oss-20b:free","messages":[{"role":"user","content":"Say hi"}]}'
```

If you deployed the sample UI as upstream, open `https://$LB_IP/` in a browser
(accept the self-signed cert). It sets the `x-model-id` header for you based
on the model you pick.

To see the LB pick a different backend per request, enable logging on the
backend services (Terraform sets `log_config { enable = true }`) and query:

```bash
gcloud logging read 'resource.type="http_load_balancer"' \
  --project=YOUR_PROJECT_ID --limit=10 --freshness=5m \
  --format="value(timestamp,httpRequest.requestUrl,httpRequest.status,resource.labels.backend_service_name)"
```

### 7. Tear down

```bash
terraform destroy
gcloud artifacts repositories delete portkey-gateway --location=us-central1 --quiet
gcloud storage rm -r gs://YOUR_PROJECT_ID_cloudbuild/
```

### What gets deployed

| Resource | Purpose |
|----------|---------|
| Cloud Run (callout + sidecar) | Multi-container service: the ext_proc callout and the `portkeyai/gateway` sidecar |
| Global external Application LB | Entry point with a self-signed cert |
| Internet NEGs (×4) + backend services | Vertex AI, Anthropic, Groq, OpenRouter |
| Serverless NEG | Cloud Run callout |
| URL map | `header_matches` routing to provider backends; default → Vertex AI |
| Traffic Extension | Invokes the callout for LLM paths |
| Secret Manager secrets | Provider API keys (only the non-empty ones) |

## Testing

```bash
cd callouts/python
pip install -r requirements.txt -r requirements-test.txt \
  -r extproc/example/portkey_gateway/additional-requirements.txt
python -m pytest extproc/tests/portkey_gateway_test.py -v
```

The suite is pure unit tests: no gRPC server, no live Portkey sidecar, no
GCP credentials required. It covers provider detection, Vertex ADC token
minting (patched), capture-server arm/take/disarm mechanics, the request-side
and response-side loopback paths, streaming rejection (HTTP 501), and full
end-to-end ext_proc phase sequences for all four providers.

## File structure

```
portkey_gateway/
├── service_callout_example.py      # ext_proc callout + provider registry + Vertex ADC auth
├── capture_server.py               # Loopback capture servers (:9999 and :9998) + stub responses
├── portkey_client.py               # Async HTTP client wrapping the Portkey sidecar
├── additional-requirements.txt     # httpx, aiohttp, google-auth, requests
├── cloudbuild.yaml                 # Cloud Build config for the callout image
├── Dockerfile                      # Callout container image
├── README.md
├── deploy/
│   └── terraform/
│       ├── main.tf                 # LB, NEGs, backends, URL map, Traffic Ext,
│       │                           # multi-container Cloud Run, secrets
│       ├── variables.tf
│       └── terraform.tfvars.example
└── sample-ui/                      # Optional chat UI; sets x-model-id per model
    ├── index.html
    ├── Dockerfile
    └── cloudbuild.yaml
```

(Unit tests live at `extproc/tests/portkey_gateway_test.py`.)

## Environment variables (callout)

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | (none) | Required for Vertex AI; used to build the Vertex URL and passed to the Portkey sidecar as `x-portkey-vertex-project-id`. |
| `GCP_REGION` | `us-central1` | Vertex AI region; also determines the Internet NEG FQDN (`{region}-aiplatform.googleapis.com`). |
| `PORTKEY_BASE_URL` | `http://127.0.0.1:8787` | URL of the Portkey sidecar. Change only if you run Portkey on a different port or host. |
| `CAPTURE_REQUEST_PORT` | `9999` | Port the callout's request capture server listens on. |
| `CAPTURE_RESPONSE_PORT` | `9998` | Port the callout's response capture server listens on. |
| `ANTHROPIC_API_KEY` | (none) | API key for Anthropic requests. Mounted from Secret Manager. |
| `GROQ_API_KEY` | (none) | API key for Groq requests. Mounted from Secret Manager. |
| `OPENROUTER_API_KEY` | (none) | API key for OpenRouter requests. Mounted from Secret Manager. |
