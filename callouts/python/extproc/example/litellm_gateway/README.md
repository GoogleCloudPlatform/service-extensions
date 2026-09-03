# LiteLLM Gateway

A Service Extensions `ext_proc` callout that turns a Google Cloud external
Application Load Balancer into an **OpenAI-compatible multi-provider gateway**.
The load balancer routes each request to the right provider backend (Vertex AI,
Anthropic, Groq, OpenRouter, …); the callout runs **LiteLLM in-process** to
translate the OpenAI request/response to/from each provider's native format and
to inject the right auth.

The callout implementation does **not** itself proxy traffic, it only mutates
headers and the body. The load balancer forwards the rewritten request straight
to the provider via an Internet NEG backend.

## Architecture

```
                              x-model-id: anthropic/claude-...
 Client  ────────────────────────────────────────────────────────────────────────┐
  │  POST /v1/chat/completions   (OpenAI body, model="anthropic/claude…")        │
  ▼                                                                              │
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │                    Global External Application LB                             │
 │                                                                               │
 │   ┌──────────────────────────┐         ┌──────────────────────────────────┐   │
 │   │ URL Map                  │         │  Traffic Extension               │   │
 │   │  /v1/* + header          │  body   │   Callout (ext_proc, Cloud Run)  │   │
 │   │   x-v2-target-provider:  ├────────►│   - LiteLLM: provider detect     │   │
 │   │     anthropic → BE-A     │◄────────┤   - LiteLLM: OpenAI→provider body│   │
 │   │     groq      → BE-G     │ headers │   - inject auth (ADC / API key)  │   │
 │   │     openrouter→ BE-O     │  + body │   - rewrite :path / :authority   │   │
 │   │   /v1/*  (default)→ BE-V │         └──────────────────────────────────┘   │
 │   │   default → upstream UI  │                                                │
 │   └────────┬─────────────────┘                                                │
 │            │  LB forwards to the matched backend                              │
 │            ▼                                                                  │
 │   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐  │
 │   │ BE-V Vertex │ │ BE-A Anthr. │ │ BE-G Groq   │ │ BE-O OpenR. │ │upstream│  │
 │   │ Internet NEG│ │ Internet NEG│ │ Internet NEG│ │ Internet NEG│ │ UI app │  │
 │   └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └────────┘  │
 └──────────┼───────────────┼───────────────┼───────────────┼────────────────────┘
            ▼               ▼               ▼               ▼
   {region}-aiplatform  api.anthropic.com  api.groq.com   openrouter.ai
   .googleapis.com
```

On the response, the LB invokes the callout again; LiteLLM transforms the
provider's response back to OpenAI format (or, for streaming, parses each SSE
chunk and re-emits it as an OpenAI `chat.completion.chunk`).

## How It Works

1. **Client** sends a standard OpenAI request (`POST /v1/chat/completions`,
   body `{"model": "anthropic/claude-3-5-sonnet-…", "messages": […]}`) plus a
   routing header `x-model-id: anthropic/claude-3-5-sonnet-…` (the model id
   verbatim).
2. **URL Map** evaluates `prefix=/v1/` + a `prefix_match` on `x-model-id`
   (e.g. `anthropic/`) and selects the matching backend service (e.g. the
   Anthropic Internet NEG). `/v1/*` requests with no matching header fall
   through to the Vertex AI backend; non-LLM paths go to the upstream UI app.
3. **Traffic Extension** intercepts the request and streams the headers and
   body to the callout over gRPC (`REQUEST_HEADERS`, then `REQUEST_BODY`).
4. **Callout** (`service_callout_example.py`) hands the body to LiteLLM:
   - `litellm.get_llm_provider(model)` resolves the provider (`anthropic`).
   - The provider's `Config` class produces the request body in the provider's
     native format (`config.transform_request(...)`), the target URL
     (`config.get_complete_url(...)`), and the auth headers
     (`config.validate_environment(...)`). For Vertex AI the bearer token is
     minted from the Cloud Run service identity (ADC); for the others the API
     key comes from a Secret Manager-backed env var.
   - The callout returns a `BodyResponse` with the transformed body plus header
     mutations: `:path`, `:authority`/`host`, the auth header(s),
     `content-length`, `accept-encoding: identity`, a `user-agent`, and
     `x-litellm-*` provenance markers. **No `clear_route_cache`**: routing was
     already decided by the URL map.
5. **Load balancer** forwards the rewritten request to the chosen backend's
   Internet NEG, which connects to the provider's API.
6. **Response phase**: the LB invokes the callout again
   (`RESPONSE_HEADERS`, `RESPONSE_BODY`). The callout drops the upstream
   `content-length` (stale after the transform) and, on the body, runs the
   provider `Config`'s `transform_response(...)` to produce an OpenAI
   `chat.completion`. For streaming responses it parses each SSE event with the
   provider's chunk iterator and re-emits an OpenAI `chat.completion.chunk`,
   appending `data: [DONE]\n\n` at the end.
7. **Client** receives a standard OpenAI response with the same shape
   regardless of which provider served it.

### The `x-model-id` header

The client includes `x-model-id: <provider>/<model>` as a request header,
and the URL map prefix-matches the leading `<provider>/` segment to
pick the backend, so no client-side mapping is needed. The sample UI sets the
header automatically from the selected model; OpenAI-style SDK clients can set
it via `default_headers` (client-level) or `extra_headers` (per call).
A `/v1/*` request with no `x-model-id` header, or one whose prefix does not
match Anthropic, Groq, or OpenRouter, falls through to the Vertex AI backend.

### Supported endpoints

| Path | Type |
|------|------|
| `/v1/chat/completions` | Chat |
| `/v1/completions` | Text completion |
| `/v1/embeddings` | Embeddings |
| `/v1/models` | Model discovery |
| `/chat/completions` | Chat (alias) |
| `/completions` | Text completion (alias) |
| `/embeddings` | Embeddings (alias) |

## Providers

The sample ships with four provider backends. The model id follows the LiteLLM
convention `<provider>/<model>`. The `x-model-id` header carries that same
string verbatim, and the URL map prefix-matches on the leading `<provider>/`
segment to pick the backend.

| Provider | Example model id | Upstream | Auth |
|----------|------------------|----------|------|
| Vertex AI | `vertex_ai/gemini-2.5-flash` | `{region}-aiplatform.googleapis.com` | ADC (Cloud Run service identity, `roles/aiplatform.user`) |
| Anthropic | `anthropic/claude-3-5-sonnet-20241022` | `api.anthropic.com` | `ANTHROPIC_API_KEY` env var (Secret Manager) |
| Groq | `groq/compound-beta` | `api.groq.com` | `GROQ_API_KEY` env var (Secret Manager) |
| OpenRouter | `openrouter/openai/gpt-oss-20b:free` | `openrouter.ai` | `OPENROUTER_API_KEY` env var (Secret Manager) |

Vertex AI is the default backend: a request with no `x-model-id` header (or one
whose provider prefix is none of the three above) falls through to Vertex.

LiteLLM owns the actual translation, so adding a provider that LiteLLM already
supports needs no callout code change. See below.

### Adding a provider

1. Add the provider's FQDN to `local.third_party_providers` in
   `deploy/terraform/main.tf`. This creates an Internet NEG + backend service
   and a URL-map `header_matches` rule for it.
2. If the provider needs an API key, add a `*_api_key` variable
   (`deploy/terraform/variables.tf`), wire it into the dynamic `env` block of
   the callout Cloud Run service, and set it in `terraform.tfvars`. The callout
   reads it as `<PROVIDER>_API_KEY` automatically.
3. If LiteLLM's `Config` class for the provider exposes `transform_request`
   directly (most do; only Vertex Gemini needs the small built-in fallback),
   nothing else changes.

## Deploy to Google Cloud

> [!IMPORTANT]
> There is intentionally **no local-dev path** for this sample. The ext_proc
> chain depends on a real GCLB URL map with `header_matches` routing, which an
> Envoy stand-in doesn't replicate faithfully. Deploy to GCP to exercise it.

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
gcloud artifacts repositories create litellm-gateway \
  --repository-format=docker --location=us-central1
```

### 4. Build and push images

Callout image (run from `callouts/python/`, since the build context is the
package root):

```bash
cd callouts/python
gcloud builds submit \
  --config=extproc/example/litellm_gateway/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID
```

(Optional) Sample chat UI image. Serves as the upstream app for non-LLM paths
and lets you exercise the gateway from a browser:

```bash
cd extproc/example/litellm_gateway/sample-ui
gcloud builds submit --config=cloudbuild.yaml --project=YOUR_PROJECT_ID
```

### 5. Configure and apply Terraform

```bash
cd ../deploy/terraform     # from sample-ui/, or just cd into deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, region, callout_image, optional
# upstream_app_image, and the *_api_key values for the providers you want.
terraform init
terraform plan
terraform apply
```

API keys you put in `terraform.tfvars` are uploaded to Secret Manager and
mounted into the callout Cloud Run service as env vars (`secret_key_ref`). They
never appear as plain env values in the console.

### 6. Test the deployment

```bash
LB_IP=$(terraform output -raw load_balancer_ip)

# Vertex AI: no header needed (it's the default backend)
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"vertex_ai/gemini-2.5-flash","messages":[{"role":"user","content":"Say hi"}]}'

# Anthropic / Groq / OpenRouter: set x-model-id to the model id verbatim
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-model-id: anthropic/claude-3-5-sonnet-20241022" \
  -d '{"model":"anthropic/claude-3-5-sonnet-20241022","max_tokens":64,"messages":[{"role":"user","content":"Say hi"}]}'

curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-model-id: groq/compound-beta" \
  -d '{"model":"groq/compound-beta","messages":[{"role":"user","content":"Say hi"}]}'

curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-model-id: openrouter/openai/gpt-oss-20b:free" \
  -d '{"model":"openrouter/openai/gpt-oss-20b:free","messages":[{"role":"user","content":"Say hi"}]}'

# Streaming (SSE)
curl -skN -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"vertex_ai/gemini-2.5-flash","stream":true,"messages":[{"role":"user","content":"Count to 5"}]}'
```

If you deployed the sample UI as upstream, open `https://$LB_IP/` in a browser
(accept the self-signed cert). It sets the `x-model-id` header for you based
on the model you pick.

To see the LB pick a different backend per request, enable logging on the
backend services (the Terraform sets `log_config { enable = true }`) and query:

```bash
gcloud logging read 'resource.type="http_load_balancer"' \
  --project=YOUR_PROJECT_ID --limit=10 --freshness=5m \
  --format="value(timestamp,httpRequest.requestUrl,httpRequest.status,resource.labels.backend_service_name)"
```

### 7. Tear down

```bash
terraform destroy
gcloud artifacts repositories delete litellm-gateway --location=us-central1 --quiet
gcloud storage rm -r gs://YOUR_PROJECT_ID_cloudbuild/
```

### What gets deployed

| Resource | Purpose |
|----------|---------|
| Cloud Run (callout) | The ext_proc callout, LiteLLM in-process |
| Cloud Run (upstream) | Handles non-LLM traffic (hello-app or the sample UI) |
| Global external Application LB | Entry point with a self-signed cert |
| Internet NEGs (×4) + backend services | Vertex AI, Anthropic, Groq, OpenRouter |
| Serverless NEGs (×2) | Cloud Run callout + upstream |
| URL map | `header_matches` routing to provider backends; default → upstream |
| Traffic Extension | Invokes the callout for LLM paths |
| Secret Manager secrets | Provider API keys (only the non-empty ones) |

## Testing

```bash
cd callouts/python
pip install -r requirements.txt -r requirements-test.txt \
  -r extproc/example/litellm_gateway/additional-requirements.txt
python -m pytest extproc/tests/litellm_gateway_test.py -v
```

The suite is pure unit tests: no gRPC server, no network. It covers the SSE
parser, the OpenAI to Vertex body fallback, the ext_proc phase handlers (header
filtering, body rewriting, response transformation, streaming chunk handling),
and a real end-to-end pass through LiteLLM's Anthropic config (which works
offline). The Vertex ADC token mint is patched out.

## File structure

```
litellm_gateway/
├── service_callout_example.py     # ext_proc callout, LiteLLM in-process
├── additional-requirements.txt    # litellm, httpx, google-cloud-aiplatform
├── cloudbuild.yaml                # Cloud Build config for the callout image
├── Dockerfile                     # Callout container image
├── README.md
├── deploy/
│   └── terraform/
│       ├── main.tf                # LB, NEGs, backends, URL map, Traffic Ext, secrets
│       ├── variables.tf
│       └── terraform.tfvars.example
└── sample-ui/
    ├── index.html                 # Chat UI; sets x-model-id per model
    ├── Dockerfile
    └── cloudbuild.yaml
```

(Unit tests live at `extproc/tests/litellm_gateway_test.py`.)

## Environment variables (callout)

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | (none) | Required for Vertex AI requests (used to build the Vertex URL and for ADC). |
| `GCP_REGION` | `us-central1` | Vertex AI region; also the Internet-NEG FQDN (`{region}-aiplatform.googleapis.com`). |
| `ANTHROPIC_API_KEY` | (none) | Picked up by LiteLLM for `anthropic/*` models. Set via Secret Manager. |
| `GROQ_API_KEY` | (none) | Picked up by LiteLLM for `groq/*` models. |
| `OPENROUTER_API_KEY` | (none) | Picked up by LiteLLM for `openrouter/*` models. |
| `<PROVIDER>_API_KEY` | (none) | Generic pattern: any provider you add reads `<PROVIDER>_API_KEY`. |
