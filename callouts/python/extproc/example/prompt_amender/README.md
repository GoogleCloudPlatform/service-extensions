# Prompt-Amender

A Service Extensions `ext_proc` callout that centralizes prompt governance
for a fleet of AI agents. It intercepts outgoing `generateContent` requests,
matches the caller's identity/host/path against a hot-reloadable YAML
ruleset, and mutates `systemInstruction.parts[].text` in flight -- so
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
   buffered JSON body, locates `systemInstruction.parts[].text` (accepting
   the legacy `system_instruction` spelling too -- see "Governance can't
   be opted out of" below), and applies the matched rule's mutation:

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

If amendment fails (malformed JSON, a template render error, or a body
over `MAX_REQUEST_BODY_BYTES`), the callout passes the request through
with its original, unmutated body by default (`FAIL_OPEN=true`). Set
`FAIL_OPEN=false` to reject with `500` instead. Note that a *missing*
system instruction is no longer a failure case: if a matched request has
none, the callout inserts one rather than skip governance -- see
"Governance can't be opted out of" below.

### Governance can't be opted out of

The callout accepts both the canonical proto3 JSON field name
`systemInstruction` and the snake_case `system_instruction` some clients
send -- recognizing only one would silently skip governance for whichever
spelling it doesn't know, and `systemInstruction` is what real Vertex/
Gemini SDK traffic actually sends. If a matched request has no system
instruction at all, the callout inserts an empty one and applies the
rule's mutation to it, rather than treating the absence as a pass-through:
a client should not be able to bypass a matched policy by simply omitting
the field.

### Identity headers must come from a trusted gateway

Rule selectors match on `x-spiffe-id`, and the whole design assumes that
header is trustworthy -- i.e. injected by an Agent Gateway *after* it has
validated the caller's mTLS SVID, never accepted verbatim from the raw
client. **The Terraform in this example ships a standalone demo load
balancer with no such gateway in front of it.** To keep the demo from
being a trivial identity spoof, `deploy/terraform/main.tf` strips any
client-supplied `x-spiffe-id` at the URL map before the callout ever sees
it (`header_action.request_headers_to_remove`). That also means the demo
curl commands below, which set `x-spiffe-id` directly, only exercise rule
matching because nothing downstream of the URL map re-injects a verified
identity -- there is no real identity being asserted in this topology. If
you deploy this behind a real Agent Gateway (or any proxy that terminates
mTLS and injects the header itself), confirm your gateway's header
injection happens *after* the point where this stripping rule (or your
own equivalent) removes anything the client sent -- ordering between URL
map header actions and extension invocation is deployment-specific and
worth verifying directly rather than assuming.

### `mode_override` reliability on the request path

This is the first example in this collection to rely on `mode_override`
for the *request* body mode (the litellm_gateway example only uses it on
the *response* side). Envoy only honors `mode_override` when
`allow_mode_override` is enabled on the extension. `on_request_body`
doesn't assume the override was actually honored: if the gateway sends a
body despite a no-match header decision, the callout passes it through
unmutated rather than treating it as an error. Still, verify on a real
deployment that unmatched traffic is actually skipping body delivery
(check Cloud Run request logs for body-bearing calls with no matching
rule) before relying on the fast path for latency budgeting -- if it
isn't honored in your topology, keep `REQUEST_BODY` in `supported_events`
(already the case here) and the no-op pass-through in `on_request_body`
covers you either way.

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
-- no redeploy needed. Rules come from GCS/git, i.e. semi-trusted config
rather than application code: `template` actions render through a
`jinja2.sandbox.SandboxedEnvironment`, not a plain `Environment`, so a
`rules.yaml` writer can't achieve code execution in the callout via
template injection (e.g. `{{ ''.__class__.__mro__[1].__subclasses__() }}`).

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

The shipped Terraform strips any client-supplied `x-spiffe-id` at the URL
map (see "Identity headers must come from a trusted gateway" above), so
there's no way to assert an identity from a plain curl against this demo
topology -- that's intentional. To exercise rule matching end-to-end
without standing up a full mTLS-terminating gateway, temporarily comment
out the `header_action` block in `deploy/terraform/main.tf` and re-apply,
then:

```bash
LB_IP=$(terraform output -raw load_balancer_ip)

curl -sk https://$LB_IP/v1/projects/YOUR_PROJECT/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent \
  -H "x-spiffe-id: principalSet://agents.global.org-123456789012.system.id.goog/support/agent-1" \
  -H "Content-Type: application/json" \
  -d '{"systemInstruction":{"parts":[{"text":"You are a customer support assistant."}]},"contents":[{"role":"user","parts":[{"text":"What is the refund policy?"}]}]}'
```

The response should reflect the brand-safety guardrail injected by
`support-safety-inject` in `rules.example.yaml`. Put the `header_action`
back before treating this as anything other than a local smoke test --
production traffic must only ever have `x-spiffe-id` set by a component
that has actually verified the caller.

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
python -m pytest extproc/tests/prompt_amender_test.py -v
```

The test file lives in the shared `extproc/tests/` tree (flat
`prompt_amender_test.py` naming), not under `extproc/example/
prompt_amender/`, so it's picked up by CI's `pytest extproc/tests/` the
same way every other example's tests are. If `requirements-test.txt`
doesn't already carry PyYAML and Jinja2 (some of the other examples don't
need them), add:

```text
PyYAML==6.0.1
Jinja2==3.1.4
```

Pure unit tests: no gRPC server, no network. Covers selector glob matching
(including `spiffe://` vs `principalSet://` scheme normalization), all
four mutation operations, the Jinja2 sandbox rejecting an SSTI payload,
and ruleset validation (rejecting rules with no selectors, duplicate IDs,
and invalid Jinja2 syntax).

## File structure

```
prompt_amender/
├── service_callout_example.py     # ext_proc callout, header+body mutation
├── rule_engine.py                 # selector matching + mutation operations
├── config_sources.py              # env/GCS/git rule sourcing + hot reload
├── logging_utils.py               # structured JSON logging (never logs raw prompts)
├── metrics.py                     # OTEL counters/histogram
├── rules.example.yaml
├── additional-requirements.txt    # PyYAML, Jinja2, google-cloud-storage, opentelemetry-api
├── cloudbuild.yaml
├── Dockerfile
├── README.md
└── deploy/
    └── terraform/
        ├── main.tf                # LB, GCS bucket, backend, URL map, Traffic Ext
        ├── variables.tf
        └── terraform.tfvars.example

extproc/tests/
└── prompt_amender_test.py         # pure unit tests -- shared tree, not per-example
```

## Environment variables (callout)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Level for the structured JSON logger. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (none) | If set, registers real OTEL SDK providers so `prompt_amender_*` metrics and the `prompt_amender.amend` span actually export via OTLP; unset means the API's no-op default stays in place (calls succeed, nothing is exported). |
| `FAIL_OPEN` | `true` | On amendment failure, pass the request through unmodified (`true`) or reject with 500 (`false`). |
| `MAX_REQUEST_BODY_BYTES` | `4194304` | Body size limit before amendment is aborted. |
| `CONFIG_SOURCE` | `gcs` | `env`, `gcs`, or `git`. |
| `CONFIG_VALUE` | (none) | Raw YAML, used when `CONFIG_SOURCE=env`. |
| `GCS_RULES_URI` | (none) | `gs://bucket/rules.yaml`, used when `CONFIG_SOURCE=gcs`. |
| `GIT_REPO_URL` / `GIT_BRANCH` / `GIT_RULES_PATH` | (none) / `main` / `rules.yaml` | Used when `CONFIG_SOURCE=git`. |
| `POLL_INTERVAL_SECONDS` | `15` | How often to check the config source for changes. |
