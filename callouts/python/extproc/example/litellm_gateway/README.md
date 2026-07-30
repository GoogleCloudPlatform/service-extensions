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

To try it hands-on, [WALKTHROUGH.md](WALKTHROUGH.md) deploys the gateway and
works through each feature with the exact `curl` and log commands, and the
output to expect.

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
 │   │   x-model-id:            ├────────►│   - LiteLLM: provider detect     │   │
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
   body `{"model": "anthropic/claude-haiku-4-5", "messages": […]}`) plus a
   routing header `x-model-id: anthropic/claude-haiku-4-5` (the model id
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
When the header does carry a known provider prefix and disagrees with the
request body's `model` field, the callout treats the header as authoritative
and overwrites the body's `model` before calling LiteLLM (see "Routing
strategies" under Regional configuration for how the route extension uses
this to change the served model, not just the backend).

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
| Anthropic | `anthropic/claude-haiku-4-5` | `api.anthropic.com` | `ANTHROPIC_API_KEY` env var (Secret Manager) |
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
  -H "x-model-id: anthropic/claude-haiku-4-5" \
  -d '{"model":"anthropic/claude-haiku-4-5","max_tokens":64,"messages":[{"role":"user","content":"Say hi"}]}'

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

## Regional configuration

**[WALKTHROUGH.md](WALKTHROUGH.md) walks through each feature end to end**: what
it demonstrates, the `terraform.tfvars` change that enables it, the `curl` to
send, the response to expect, and the log command that shows it working. The
rest of this section describes the configuration itself.

The `deploy/terraform-regional/` directory contains an alternate Terraform
config, a regional external Application LB, that adds three opt-in features to
the same callout image. Each feature sits behind its own feature flag, and
with all flags off the callout is exactly the original translation-only
gateway (the simple `deploy/terraform/` config sets none of them):

| Feature | Flag (off by default) | When off |
|---------|----------------------|----------|
| Programmable model routing (Route Extension rewrites `x-model-id`; the traffic extension then serves the model the header names) | `router_settings` section in the `GATEWAY_CONFIG` file | No rewrites; the request body's `model` is always served as-is |
| Token budget and rate-limit enforcement (Memorystore for Redis) | `REDIS_HOST` env var | No quota checks; every request passes through unmetered |
| OpenTelemetry tracing (one span per LLM request, OTLP) | `OTEL_EXPORTER_OTLP_ENDPOINT` env var | No spans emitted |

Activate any subset independently: each flag only enables its own feature,
so a deployment can run, say, quota without routing or tracing.

### Regional request path

```
Client POST /v1/chat/completions (x-model-id: anthropic/claude-haiku-4-5)
  |
  v
Regional External Application LB
  |
  +-- Route Extension (runs first, REQUEST_HEADERS only)
  |     callout detects mode=route from per-extension metadata
  |     compute_route() rewrites x-model-id via the strategies enabled by
  |       router_settings (model_alias, tag_based, weighted_split,
  |       simple_shuffle); inert when no GATEWAY_CONFIG router_settings
  |     returns clear_route_cache=true so URL map re-evaluates
  |
  +-- URL map evaluates (possibly rewritten) x-model-id header prefix
  |     anthropic/ -> Anthropic backend
  |     groq/      -> Groq backend
  |     openrouter/-> OpenRouter backend
  |     /v1/*      -> Vertex AI backend (default)
  |     other      -> upstream UI
  |
  +-- Traffic Extension (REQUEST_HEADERS, REQUEST_BODY, RESPONSE_*)
        callout transforms body OpenAI->provider, injects auth
        checks quota (REDIS_HOST set): 401 unknown key, 402 over budget,
          429 rate limit
        starts OTel span (OTEL_EXPORTER_OTLP_ENDPOINT set)
        on response: records token spend, ends span
```

### Feature environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | (none) | Redis host for quota enforcement. Set by Terraform from the Memorystore instance. |
| `REDIS_PORT` | `6379` | Redis port. Set by Terraform. |
| `QUOTA_FAIL_OPEN` | `true` | If `false`, quota backend errors reject the request (503). Default is fail-open. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (none) | OTLP endpoint for trace export, for example a collector you run. Cloud Trace's endpoint does not work directly (it requires an OAuth token the callout does not send); see "Verified on GCP" below. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | OTLP protocol (`grpc` or `http/protobuf`). |
| `OTEL_SERVICE_NAME` | `litellm-gateway` | Service name in trace data. |
| `GATEWAY_CONFIG` | (none) | Path to an optional gateway config YAML (see `config.example.yaml`). Covers `router_settings` (the routing feature flag), `litellm_settings`, and `general_settings`. Absent: routing stays disabled and the other knobs use their defaults. |

### Gateway config file

An optional YAML config, modeled on LiteLLM's own `config.yaml`, customizes
routing, telemetry, and quota defaults without a code change. Point
`GATEWAY_CONFIG` at the file:

```bash
export GATEWAY_CONFIG=/path/to/config.yaml
```

See `config.example.yaml` for a complete example. Section names mirror
LiteLLM's config so a reader already familiar with LiteLLM recognizes the
knobs:

| Section | Keys | Consumed by |
|---------|------|-------------|
| `router_settings` | `model_group_alias`, `tag_rules`, `weighted_groups`, `shuffle_groups` | `routing.configure()`. This is the routing feature flag: the strategies ship disabled (empty tables) and this section turns them on. A strategy is active exactly when its table is non-empty. |
| `litellm_settings` | `redact_user_api_key_info` | `telemetry.py`. Omits the hashed virtual key from spans when true, as in LiteLLM. |
| `general_settings` | `quota_fail_open` | `quota.py`. The `QUOTA_FAIL_OPEN` env var wins over this when both are set. |

A deployment without `GATEWAY_CONFIG` set, or a file without
`router_settings`, keeps routing disabled and every other knob at its
default, so the zero-config deployment is the original translation-only
gateway.

### Seeding quota keys

The gateway has no key-management API by design. `seed_keys.py` is the
sample's substitute for LiteLLM's `/key/generate` endpoint, and there are two
ways to run it. Memorystore has a private IP, so both write from inside the
VPC.

**With Terraform (no VPC access needed).** Define the keys in the
`quota_keys` variable (see `deploy/terraform-regional/terraform.tfvars.example`
for a set that exercises every enforcement path), then run the seed job that
config creates:

```bash
terraform apply
gcloud run jobs execute litellm-gateway-seed-keys --region us-central1
```

The job runs `seed_keys.py` from the callout image against the private Redis
with `--replace`, so removing a field from `quota_keys` also removes it from
Redis. Re-run it after any change to `quota_keys`. `terraform output -raw
seed_job_command` prints the exact command.

**By hand, for ad hoc changes.** From a machine with Redis access (a VM or
Cloud Shell inside the VPC):

```bash
cp keys.example.yaml keys.yaml
# Edit keys.yaml: add or adjust key entries.
python seed_keys.py --host $REDIS_HOST --file keys.yaml
```

Every entry always writes a `key` field, even one with no other
fields, so a key with no limits (`vk-unlimited` in `keys.example.yaml`) is
still known to `quota.check()`: it is tracked, never treated as unknown and
blocked.

Each key entry (see `keys.example.yaml`) supports:

| Field | Meaning |
|-------|---------|
| `token_budget` | Tokens allowed per `budget_duration` window. |
| `budget_duration` | Window length: `30s` / `30m` / `30h` / `30d` / `1mo`. |
| `rpm_limit` | Requests allowed per minute. |
| `tpm_limit` | Tokens allowed per minute. |
| `soft_budget` | Warn-only threshold below `token_budget`; logs a warning once spend reaches it, does not block. |
| `expires` | ISO-8601 timestamp; requests after this time are rejected. |
| `models` | Allowlist: exact model ids or `<provider>/*` wildcards. Omit to allow every model. |
| `model_max_budget` | Per-model budget, tracked separately from the key-level budget: `{model: {budget_limit, time_period}}`. |

`quota.check()` returns:

- `401 Unauthorized`: unknown key, or a key whose `expires` timestamp is in
  the past.
- `402 Payment Required`: the key-level `token_budget`, or a `model_max_budget`
  entry for the requested model, is exceeded.
- `403 Forbidden`: the requested model is not in the key's `models` allowlist.
- `429 Too Many Requests`: `rpm_limit` or `tpm_limit` exceeded.
- `503 Service Unavailable`: the quota backend is unreachable and
  `QUOTA_FAIL_OPEN=false` (the default is fail-open, so this is opt-in).

Budget and rate-limit windows are fixed-size buckets, indexed by
`int(time.time()) // window_seconds` and stored in the counter's Redis key
(for example `spend:<key>:<window id>`). Deriving the bucket from the clock
alone keeps enforcement stateless: no window-start timestamp to read and
rewrite (which would be a read-modify-write race between concurrent requests
and across callout instances), every instance computes the same key name
independently, `INCRBY` on it is atomic, and a window rolls over simply by
changing the key name, leaving the old counter to expire on its TTL. That is
also why no reset job is needed.

The trade-off is that windows are a rolling approximation: one resets the
moment its bucket index changes, not on a calendar boundary, and `1mo` is
treated as 30 days. The LiteLLM Proxy instead resets on calendar boundaries
(for example midnight UTC on the 1st for a monthly budget), which is why it
ships a budget rescheduler to zero the counters.

### Response headers

When quota is enabled (`REDIS_HOST` set) and the request presented a virtual
key, `on_response_headers` adds:

| Header | Meaning |
|--------|---------|
| `x-litellm-key-spend` | Total tokens spent so far in the key's current `budget_duration` window. |
| `x-ratelimit-remaining-tokens` | `token_budget` minus spend so far. Present only when the key has a `token_budget`. |
| `x-ratelimit-remaining-requests` | `rpm_limit` minus requests so far this minute. Present only when the key has an `rpm_limit`. |
| `x-litellm-call-id` | Per-request UUID, the same value attached to the trace span as `litellm.call_id`. |

As with the LiteLLM Proxy's own usage headers, these values reflect spend
recorded so far: the response that completes the in-flight request carries
headers that do not yet include that request's own usage, since spend is
recorded after the response body is read.

### Telemetry (OpenTelemetry)

Each LLM request emits one span (`llm.request`) with GenAI
semantic-convention attributes:

| Attribute | Meaning |
|-----------|---------|
| `gen_ai.operation.name` | `chat`, `text_completion`, or `embeddings`, from the endpoint path. |
| `gen_ai.system` | Provider (`anthropic`, `vertex_ai`, `groq`, `openrouter`). |
| `gen_ai.request.model` | The resolved model id. |
| `gen_ai.usage.input_tokens` / `.output_tokens` / `.total_tokens` | Token usage from the transformed response. |
| `gen_ai.cost.total_cost` | USD cost via LiteLLM's bundled price map (`litellm.cost_per_token`); omitted when the model is not in the price map. |
| `litellm.call_id` | Per-request UUID; also returned as the `x-litellm-call-id` response header. |
| `user_api_key_hash` | Truncated SHA-256 (16 hex chars) of the virtual key; omitted when no key was supplied or `redact_user_api_key_info` is set. |
| `http.response.status_code` | The status the callout returned for this request. |
| `llm.is_streaming` | Whether the request used SSE streaming. |

### Routing strategies (route extension)

The `routing.py` module implements each feasible LiteLLM routing strategy as
a separate, independently configurable function. `compute_route` composes
the enabled ones. Routing is feature-flagged: the strategies ship disabled
(empty tables), and the `router_settings` section of a `GATEWAY_CONFIG` file
(see "Gateway config file" above) is what turns each one on; a strategy is
active exactly when its table is non-empty. A strategy rewrites the
`x-model-id` routing header, which selects the backend; the URL map then
re-evaluates routing on the rewritten header.

| Strategy (`routing.py`) | LiteLLM feature | Enable with (`router_settings`) | Example |
|---|---|---|---|
| `model_alias_route` | Model aliases / model groups | `model_group_alias` | `x-model-id: cheap` -> `openrouter/openai/gpt-oss-20b:free` |
| `tag_based_route` | Tag-based routing | `tag_rules` | `x-model-id: vertex_ai/gemini-2.5-flash` + `x-tier: premium` -> `vertex_ai/gemini-2.5-pro` |
| `weighted_split_route` | A/B / weighted split | `weighted_groups` | 70/30 split of a model group by a stable hash of `x-request-id` |
| `simple_shuffle_route` | simple-shuffle load balancing | `shuffle_groups` | random member of a model group per request |

A header rewrite changes which **backend** serves the request. The served
**model** normally comes from the request body, but with routing enabled the
traffic extension callout treats `x-model-id` (after any route-extension
rewrite) as authoritative over `body.model` whenever the header carries a
known provider prefix (`vertex_ai/`, `anthropic/`, `groq/`, `openrouter/`)
and differs from the body value: it overwrites the body's `model` field
before handing the request to LiteLLM. This is what makes
`tag_based_route`'s premium upgrade and `weighted_split_route` /
`simple_shuffle_route`'s group picks actually change the served model, not
just the backend. `model_alias_route` resolves an alias (no provider prefix
yet) to a full model id, which then participates in the same override on the
next leg. With routing disabled the override never fires, so the body model
always wins, exactly the original gateway behavior. Point alias and tag
targets at models your project actually has access to.

Each request emits one route-mode log line, for example:

```
Route extension rewrite: x-model-id='cheap' -> 'openrouter/openai/gpt-oss-20b:free'
Route extension: no rewrite for x-model-id='vertex_ai/gemini-2.5-flash'
```

### What stays LB-native

The URL map `header_matches` routing, TLS termination, backend selection, and
the Internet NEG forwarding to provider APIs are all handled by the LB. The
callout only mutates headers and body; it does not proxy traffic.

The route extension adds programmable header rewrites before the URL map
evaluates routing. It runs only on request headers (no body access). The
traffic extension then handles body transformation on both the request and
response legs.

### Deploy the regional config

```bash
cd deploy/terraform-regional
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, region, callout_image, api keys,
# and optionally otel_exporter_otlp_endpoint and redis_tier.
terraform init
terraform plan
terraform apply
```

After apply, seed quota keys and test:

```bash
LB_IP=$(terraform output -raw load_balancer_ip)
REDIS_HOST=$(terraform output -raw redis_host)

# Seed keys (see "Seeding quota keys" above).
cp keys.example.yaml keys.yaml
python seed_keys.py --host $REDIS_HOST --file keys.yaml

# Test with a valid key.
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer vk-demo" \
  -H "x-model-id: anthropic/claude-haiku-4-5" \
  -d '{"model":"anthropic/claude-haiku-4-5","messages":[{"role":"user","content":"Say hi"}]}'

# Model alias via route extension: x-model-id is an alias, body is the real
# model. The route extension rewrites the header so the URL map routes to the
# alias target's backend.
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer vk-demo" \
  -H "x-model-id: cheap" \
  -d '{"model":"openrouter/openai/gpt-oss-20b:free","messages":[{"role":"user","content":"Say hi"}]}'

# Tag-based routing: a premium tag upgrades a Vertex request flash -> pro.
curl -sk -X POST https://$LB_IP/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer vk-demo" \
  -H "x-model-id: vertex_ai/gemini-2.5-flash" \
  -H "x-tier: premium" \
  -d '{"model":"vertex_ai/gemini-2.5-pro","messages":[{"role":"user","content":"Say hi"}]}'
```

### Tear down (regional)

```bash
cd deploy/terraform-regional
terraform destroy
```

## Testing

```bash
cd callouts/python
pip install -r requirements.txt -r requirements-test.txt \
  -r extproc/example/litellm_gateway/additional-requirements.txt
python -m pytest extproc/tests/ -k litellm -v
```

The suite is pure unit tests: no gRPC server, no network. `litellm_gateway_test.py`
covers the SSE parser, the OpenAI to Vertex body fallback, the ext_proc phase
handlers (header filtering, body rewriting, response transformation, streaming
chunk handling), and a real end-to-end pass through LiteLLM's Anthropic config
(which works offline); the Vertex ADC token mint is patched out.
`litellm_gateway_quota_test.py`, `litellm_gateway_telemetry_test.py`,
`litellm_gateway_routing_test.py`, `litellm_gateway_config_test.py`, and
`litellm_gateway_seed_keys_test.py` cover, respectively, `quota.py` (fakeredis,
no real Redis), `telemetry.py` (an in-memory OTel exporter), `routing.py`,
`gateway_config.py`, and `seed_keys.py`.

## File structure

```
litellm_gateway/
├── service_callout_example.py     # ext_proc callout, LiteLLM in-process
├── telemetry.py                   # OpenTelemetry span helpers (env-gated)
├── quota.py                       # Redis token budget + rate-limit (env-gated)
├── routing.py                     # Route extension rule logic (pure function)
├── gateway_config.py              # Optional YAML config loader (GATEWAY_CONFIG)
├── config.example.yaml            # Example gateway config file
├── seed_keys.py                   # Seeds virtual keys into Redis from keys.yaml
├── keys.example.yaml              # Example virtual-key definitions
├── additional-requirements.txt    # litellm, httpx, google-cloud-aiplatform, otel, redis
├── cloudbuild.yaml                # Cloud Build config for the callout image
├── Dockerfile                     # Callout container image
├── README.md
├── WALKTHROUGH.md                 # Hands-on walkthrough of every feature
├── deploy/
│   ├── terraform/                 # Simple global LB (no Redis, no OTel, no route ext)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── terraform.tfvars.example
│   └── terraform-regional/        # Regional LB + Memorystore + route extension + OTel
│       ├── main.tf
│       ├── variables.tf
│       └── terraform.tfvars.example
└── sample-ui/
    ├── index.html                 # Chat UI; sets x-model-id per model
    ├── Dockerfile
    └── cloudbuild.yaml
```

(Unit tests live at `extproc/tests/litellm_gateway_*_test.py`.)

## Environment variables (callout)

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | (none) | Required for Vertex AI requests (used to build the Vertex URL and for ADC). |
| `GCP_REGION` | `us-central1` | Vertex AI region; also the Internet-NEG FQDN (`{region}-aiplatform.googleapis.com`). |
| `ANTHROPIC_API_KEY` | (none) | Picked up by LiteLLM for `anthropic/*` models. Set via Secret Manager. |
| `GROQ_API_KEY` | (none) | Picked up by LiteLLM for `groq/*` models. |
| `OPENROUTER_API_KEY` | (none) | Picked up by LiteLLM for `openrouter/*` models. |
| `<PROVIDER>_API_KEY` | (none) | Generic pattern: any provider you add reads `<PROVIDER>_API_KEY`. |
