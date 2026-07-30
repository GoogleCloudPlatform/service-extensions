# LiteLLM Gateway walkthrough

Hands-on walkthrough of every feature, using the regional deployment
(`deploy/terraform-regional/`). Deploy once, then work through the scenarios in
any order: each one says what it demonstrates, what to change, what to send, and
what to look for in the logs. Everything runs through `curl`; the sample UI is
not used.

Every command below was run against a live deployment and the outputs are
copied from that run.

## Contents

1. [Setup](#1-setup)
2. [Scenario 1: multi-provider gateway](#scenario-1-multi-provider-gateway)
3. [Scenario 2: quota, budgets and rate limits](#scenario-2-quota-budgets-and-rate-limits)
4. [Scenario 3: routing by model alias](#scenario-3-routing-by-model-alias)
5. [Scenario 4: routing by tag](#scenario-4-routing-by-tag)
6. [Scenario 5: A/B weighted split](#scenario-5-ab-weighted-split)
7. [Scenario 6: simple-shuffle](#scenario-6-simple-shuffle)
8. [Scenario 7: OpenTelemetry tracing](#scenario-7-opentelemetry-tracing)
9. [Teardown](#teardown)

Scenarios 1 and 2 need no routing configuration. Scenarios 3 to 6 each set one
section of the same `gateway_config` variable, so run them one at a time or
combine them.

---

## 1. Setup

### 1.1 Build the callout image

From `callouts/python/`, replacing `YOUR_PROJECT_ID` with your project:

```bash
gcloud artifacts repositories create litellm-gateway \
  --repository-format=docker --location=us-central1 \
  --project=YOUR_PROJECT_ID
gcloud builds submit --config=extproc/example/litellm_gateway/cloudbuild.yaml \
  --project=YOUR_PROJECT_ID
```

The `us-central1` location here is the image registry's region, independent
of the `region` tfvar used for the deployment itself. If you change `region`,
keep these two consistent (or leave both at `us-central1`).

### 1.2 Configure and deploy

From `deploy/terraform-regional/`:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`: set `project_id`, `callout_image`, and the API keys of
the providers you want (`anthropic_api_key`, `groq_api_key`,
`openrouter_api_key`). Vertex AI needs no key, it uses the Cloud Run service
identity. Then:

```bash
terraform init
terraform apply
export LB=$(terraform output -raw load_balancer_ip)
```

The load balancer uses a self-signed certificate, so `curl` needs `-k`.

**Wait for the load balancer before testing.** A newly created regional
forwarding rule and its extensions take a few minutes to become routable. Until
then requests return `404` from the load balancer even though the callout is
healthy. Poll until a request succeeds:

```bash
until curl -sk -o /dev/null -w "%{http_code}\n" -X POST https://$LB/v1/chat/completions \
  -H "Content-Type: application/json" -H "x-model-id: vertex_ai/gemini-2.5-flash" \
  -d '{"model":"vertex_ai/gemini-2.5-flash","max_tokens":24,"messages":[{"role":"user","content":"hi"}]}' \
  | grep -q 200; do sleep 15; done; echo ready
```

### 1.3 Where quota keys come from

Memorystore has a private IP, so keys are written from inside the VPC. Define
them in the `quota_keys` variable in `terraform.tfvars`, then run the seed job.
`terraform.tfvars.example` ships a commented set that exercises every
enforcement path; uncomment it to follow scenario 2 exactly.

```bash
terraform apply    # updates the secret holding the keys
gcloud run jobs execute litellm-gateway-seed-keys --region us-central1
```

Re-run the job after any change to `quota_keys`. It runs with `--replace`, so
removing a field from a key also removes it from Redis. For ad hoc changes
without Terraform, `seed_keys.py` can be run by hand from a machine inside the
VPC; see the README's "Seeding quota keys" section.

Quota is opt-in per request: a request with no `Authorization` header is never
metered, so leaving `quota_keys` empty (the default) keeps the gateway open.

### 1.4 Where routing configuration comes from

The `gateway_config` variable in `terraform.tfvars` is mounted into the callout
as its config file. Routing strategies live under `router_settings`, and a
strategy is active exactly when its table is non-empty. Empty (the default)
means no rewrites at all.

Changing `gateway_config` and running `terraform apply` updates the secret and
rolls a new callout revision, so the new config is serving within about half a
minute. No image rebuild is needed.

### 1.5 Reading the logs

Every scenario checks the callout's own logs. Define this helper once and the
scenarios below become one-liners:

```bash
logs() {  # logs <substring> [limit]
  gcloud logging read \
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"litellm-gateway-callout\" AND \"$1\"" \
    --limit "${2:-10}" --freshness 10m --format 'value(textPayload)'
}
```

Keep the filter on one line as above. Some shells, Git Bash on Windows in
particular, mangle a filter string that spans multiple lines.

---

## Scenario 1: multi-provider gateway

**What it shows.** One OpenAI-compatible endpoint in front of four providers.
The client always speaks the OpenAI format; the load balancer picks the backend
from the `x-model-id` header, and the callout translates the request and
response to and from each provider's native format.

**Setup.** None beyond section 1. Leave `gateway_config` and `quota_keys` at
their defaults.

**Run.** The model id goes in the header (for routing) and in the body (for the
provider call):

```bash
for M in vertex_ai/gemini-2.5-flash anthropic/claude-haiku-4-5 \
         groq/compound-beta openrouter/openai/gpt-oss-20b:free; do
  echo "== $M"
  curl -sk -X POST https://$LB/v1/chat/completions \
    -H "Content-Type: application/json" -H "x-model-id: $M" \
    -d "{\"model\": \"$M\", \"max_tokens\": 24,
         \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}" \
    | python -c "import json,sys; print(json.load(sys.stdin)['model'])"
done
```

**Expect.** Each provider answers with its own model id:

```
== vertex_ai/gemini-2.5-flash
gemini-2.5-flash
== anthropic/claude-haiku-4-5
claude-haiku-4-5-20251001
== groq/compound-beta
groq/compound
== openrouter/openai/gpt-oss-20b:free
openai/gpt-oss-20b:free
```

**Logs.** The callout records the host and path it rewrote each request to:

```bash
logs "Routing :authority" 8
```

```
INFO:root:Routing :authority=us-central1-aiplatform.googleapis.com :path=/v1/projects/PROJECT/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent (provider=vertex_ai, streaming=False)
INFO:root:Routing :authority=api.anthropic.com :path=/v1/messages (provider=anthropic, streaming=False)
INFO:root:Routing :authority=api.groq.com :path=/openai/v1/chat/completions (provider=groq, streaming=False)
INFO:root:Routing :authority=openrouter.ai :path=/api/v1/chat/completions (provider=openrouter, streaming=False)
```

---

## Scenario 2: quota, budgets and rate limits

**What it shows.** Virtual keys with token budgets, per-model budgets, request
and token rate limits, model allowlists, and expiry. Enforcement is two phase:
the request leg checks before the upstream call, the response leg records the
real token usage.

**Setup.** Uncomment the `quota_keys` block in `terraform.tfvars`, then:

```bash
terraform apply
gcloud run jobs execute litellm-gateway-seed-keys --region us-central1
```

The job logs what it wrote:

```
INFO:root:Seeded key 99b46eb86b815a60 (4 fields)
INFO:root:Seeded key 50d5b48458c9f8f1 (4 fields)
INFO:root:Seeded key f0b2b5a779bd6ed7 (2 fields)
INFO:root:Seeded key 1020c39a7e99a6ee (4 fields)
INFO:root:Seeded key 21705f4bcc57d552 (2 fields)
INFO:root:Done: 5 keys seeded.
```

Each hash is a truncated SHA-256 of the virtual key (matching the
`user_api_key_hash` shown in scenario 7); the raw key is never logged.

**Run.** A helper keeps the examples short:

```bash
call() {  # call <key> <model>
  curl -sk -o /dev/null -w "%{http_code}\n" -X POST https://$LB/v1/chat/completions \
    -H "Content-Type: application/json" -H "Authorization: Bearer $1" \
    -H "x-model-id: $2" \
    -d "{\"model\": \"$2\", \"max_tokens\": 24,
         \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}"
}
V=vertex_ai/gemini-2.5-flash
A=anthropic/claude-haiku-4-5

call vk-demo    $V     # within budget
call vk-expired $V     # key expired
call vk-allow   $A     # model outside the key's allowlist
call vk-allow   $V     # model inside the allowlist
call vk-tpm     $V     # first call of the minute
call vk-tpm     $V     # second call of the minute
call not-a-key  $V     # unknown key
```

**Expect.**

```
200    vk-demo, within budget
401    vk-expired
403    vk-allow with an Anthropic model (its allowlist is vertex_ai/*)
200    vk-allow with a Vertex model
200    vk-tpm, first call
429    vk-tpm, second call in the same minute (tpm_limit 10)
401    unknown key
```

A request with no key at all is not metered, which is what makes quota safe to
enable on an existing deployment:

```bash
curl -sk -o /dev/null -w "%{http_code}\n" -X POST https://$LB/v1/chat/completions \
  -H "Content-Type: application/json" -H "x-model-id: $V" \
  -d "{\"model\": \"$V\", \"max_tokens\": 24,
       \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}"
```

```
200
```

Per-model budgets take a few calls. `vk-model-budget` allows 30 tokens per day
on `anthropic/claude-haiku-4-5` and each answer costs more than that, so the
third call is rejected while other models on the same key keep working:

```bash
call vk-model-budget $A   # 200
call vk-model-budget $A   # 200
call vk-model-budget $A   # 402, this model's budget is spent
call vk-model-budget $V   # 200, a different model is unaffected
```

Successful responses carry the usage headers:

```bash
curl -sk -D - -o /dev/null -X POST https://$LB/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer vk-demo" \
  -H "x-model-id: $V" \
  -d "{\"model\": \"$V\", \"max_tokens\": 24,
       \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}" \
  | grep -i "x-litellm-\|x-ratelimit-"
```

```
x-litellm-key-spend: 21
x-ratelimit-remaining-tokens: 99979
x-ratelimit-remaining-requests: 58
x-litellm-call-id: 0f882c1b-f984-4216-85fa-5e3507c266d8
```

`x-litellm-key-spend` reflects usage recorded before this request, so it lags
the response in flight, the same behavior as the LiteLLM Proxy.

**Logs.** One line per rejection, with the reason:

```bash
logs "Quota reject" 10
```

```
INFO:root:Quota reject (401): key expired
INFO:root:Quota reject (401): unknown key
INFO:root:Quota reject (402): model budget exceeded
INFO:root:Quota reject (403): model not allowed for key
INFO:root:Quota reject (429): tpm exceeded
```

---

## Scenario 3: routing by model alias

**What it shows.** The client asks for a friendly name and the route extension
resolves it to a real model id before the load balancer picks a backend. The URL
map alone cannot do this, it can only prefix-match, so this is the clearest
demonstration of programmable routing.

**Setup.** In `terraform.tfvars`:

```hcl
gateway_config = {
  router_settings = {
    model_group_alias = {
      fast  = "vertex_ai/gemini-2.5-flash"
      smart = "anthropic/claude-haiku-4-5"
      cheap = "openrouter/openai/gpt-oss-20b:free"
    }
  }
}
```

```bash
terraform apply
```

**Run.** The alias goes in the header; the body names the model it resolves to:

```bash
curl -sk -X POST https://$LB/v1/chat/completions \
  -H "Content-Type: application/json" -H "x-model-id: cheap" \
  -d '{"model": "openrouter/openai/gpt-oss-20b:free", "max_tokens": 24,
       "messages": [{"role": "user", "content": "hi"}]}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['model'])"
```

**Expect.**

```
openai/gpt-oss-20b:free
```

An alias carries no provider prefix, so without the route extension the URL map
would fall through to the Vertex backend and the call would fail. A successful
OpenRouter answer proves the header was rewritten and the route recomputed.

**Logs.**

```bash
logs "Route extension" 5
```

```
INFO:root:Route extension rewrite: x-model-id='cheap' -> 'openrouter/openai/gpt-oss-20b:free'
```

---

## Scenario 4: routing by tag

**What it shows.** A separate header selects a different model within the same
provider, the usual "premium tier gets the better model" case. It also shows the
served model changing, not just the backend: the callout treats the rewritten
`x-model-id` as authoritative over the body's `model` field.

**Setup.** In `terraform.tfvars`:

```hcl
gateway_config = {
  router_settings = {
    tag_rules = [
      {
        provider_prefix = "vertex_ai/"
        tag             = "premium"
        target          = "vertex_ai/gemini-2.5-pro"
      },
    ]
  }
}
```

```bash
terraform apply
```

**Run.** Same body both times, only the tag header differs:

```bash
for TIER in "" "premium"; do
  echo -n "x-tier '${TIER}': "
  curl -sk -X POST https://$LB/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "x-model-id: vertex_ai/gemini-2.5-flash" \
    ${TIER:+-H "x-tier: $TIER"} \
    -d '{"model": "vertex_ai/gemini-2.5-flash", "max_tokens": 24,
         "messages": [{"role": "user", "content": "hi"}]}' \
    | python -c "import json,sys; print(json.load(sys.stdin)['model'])"
done
```

**Expect.** The premium request is answered by the upgraded model even though
the body asked for flash:

```
x-tier '': gemini-2.5-flash
x-tier 'premium': gemini-2.5-pro
```

**Logs.** Both halves are visible: the route extension rewrites the header, then
the traffic extension overrides the body model to match.

```bash
gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"litellm-gateway-callout\" AND (\"Route extension\" OR \"overrides body model\")" \
  --limit 6 --freshness 10m --format 'value(textPayload)'
```

```
INFO:root:x-model-id overrides body model: 'vertex_ai/gemini-2.5-flash' -> 'vertex_ai/gemini-2.5-pro'
INFO:root:Route extension rewrite: x-model-id='vertex_ai/gemini-2.5-flash' -> 'vertex_ai/gemini-2.5-pro'
INFO:root:Route extension: no rewrite for x-model-id='vertex_ai/gemini-2.5-flash'
```

The last line is the untagged request: no tag means no rewrite.

---

## Scenario 5: A/B weighted split

**What it shows.** Traffic split across members of a model group by weight. The
choice is a stable hash of `x-request-id`, so the same request id always lands
on the same member, which keeps retries consistent.

**Setup.** In `terraform.tfvars`:

```hcl
gateway_config = {
  router_settings = {
    weighted_groups = {
      "vertex_ai/gemini-2.5-flash" = [
        { model = "vertex_ai/gemini-2.5-flash", weight = 70 },
        { model = "vertex_ai/gemini-2.5-pro", weight = 30 },
      ]
    }
  }
}
```

```bash
terraform apply
```

**Run.** Vary the request id and count what answers:

```bash
for i in $(seq 1 10); do
  curl -sk -X POST https://$LB/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "x-model-id: vertex_ai/gemini-2.5-flash" \
    -H "x-request-id: req-$i" \
    -d '{"model": "vertex_ai/gemini-2.5-flash", "max_tokens": 24,
         "messages": [{"role": "user", "content": "hi"}]}' \
    | python -c "import json,sys; print(json.load(sys.stdin)['model'])"
done | sort | uniq -c
```

**Expect.** Roughly the configured ratio. Exact counts vary with the sample:

```
      6 gemini-2.5-flash
      4 gemini-2.5-pro
```

Repeating the same `x-request-id` always returns the same member.

**Logs.** Only requests landing on the minority member are rewritten; the rest
are logged as no rewrite, which is what a 70/30 split looks like:

```bash
logs "Route extension" 12
```

```
INFO:root:Route extension rewrite: x-model-id='vertex_ai/gemini-2.5-flash' -> 'vertex_ai/gemini-2.5-pro'
INFO:root:Route extension: no rewrite for x-model-id='vertex_ai/gemini-2.5-flash'
```

---

## Scenario 6: simple-shuffle

**What it shows.** A group name that is not a model id at all. Each request
picks a random member, the simplest form of load balancing across equivalent
deployments.

**Setup.** In `terraform.tfvars`:

```hcl
gateway_config = {
  router_settings = {
    shuffle_groups = {
      "vertex-shuffle" = [
        "vertex_ai/gemini-2.5-flash",
        "vertex_ai/gemini-2.5-pro",
      ]
    }
  }
}
```

```bash
terraform apply
```

**Run.**

```bash
for i in $(seq 1 6); do
  curl -sk -X POST https://$LB/v1/chat/completions \
    -H "Content-Type: application/json" -H "x-model-id: vertex-shuffle" \
    -d '{"model": "vertex_ai/gemini-2.5-flash", "max_tokens": 24,
         "messages": [{"role": "user", "content": "hi"}]}' \
    | python -c "import json,sys; print(json.load(sys.stdin)['model'])"
done | sort | uniq -c
```

**Expect.** Both members appear, in no fixed order:

```
      3 gemini-2.5-flash
      3 gemini-2.5-pro
```

**Logs.** Every request is rewritten, since `vertex-shuffle` is never a real
model id:

```bash
logs "vertex-shuffle" 8
```

```
INFO:root:Route extension rewrite: x-model-id='vertex-shuffle' -> 'vertex_ai/gemini-2.5-flash'
INFO:root:Route extension rewrite: x-model-id='vertex-shuffle' -> 'vertex_ai/gemini-2.5-pro'
```

---

## Scenario 7: OpenTelemetry tracing

**What it shows.** One span per request with GenAI semantic-convention
attributes: provider, model, token usage, cost in USD, a call id that also comes
back as a response header, and a hashed virtual key. The raw key never appears.

**Setup.** Spans are exported over OTLP, so this scenario needs a collector.
Google Cloud Trace cannot be used as a direct OTLP target: its ingest endpoint
requires an OAuth token the callout does not send and answers `403 Forbidden`.
Run a collector inside the VPC instead:

```bash
gcloud compute firewall-rules create litellm-gateway-allow-otlp \
  --network litellm-gateway-vpc --allow tcp:4317 --source-ranges 10.10.0.0/24
gcloud compute firewall-rules create litellm-gateway-allow-iap-ssh \
  --network litellm-gateway-vpc --allow tcp:22 --source-ranges 35.235.240.0/20
gcloud compute instances create otel-collector \
  --zone us-central1-a --machine-type e2-small \
  --network litellm-gateway-vpc --subnet litellm-gateway-subnet \
  --image-family debian-12 --image-project debian-cloud \
  --format 'value(networkInterfaces[0].networkIP)'
```

The last command prints the collector's internal IP, `10.10.0.2` in this
example. On the VM, run a collector that listens on `:4317` and prints what it
receives:

```bash
gcloud compute ssh otel-collector --tunnel-through-iap --zone us-central1-a
# then, on the VM:
curl -sL -o /tmp/o.tgz https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.116.1/otelcol-contrib_0.116.1_linux_amd64.tar.gz
tar -xzf /tmp/o.tgz -C /tmp otelcol-contrib
cat > /tmp/col.yaml <<'YAML'
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
YAML
nohup /tmp/otelcol-contrib --config /tmp/col.yaml > /tmp/collector.log 2>&1 &
```

Then point the gateway at it, in `terraform.tfvars`:

```hcl
otel_exporter_otlp_endpoint = "http://10.10.0.2:4317"
```

```bash
terraform apply
```

**Run.** Any request produces a span:

```bash
curl -sk -o /dev/null -X POST https://$LB/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer vk-demo" \
  -H "x-model-id: anthropic/claude-haiku-4-5" \
  -d '{"model": "anthropic/claude-haiku-4-5", "max_tokens": 24,
       "messages": [{"role": "user", "content": "hi"}]}'
```

**Expect.** On the VM, the collector prints the span:

```bash
grep -E "llm.request|gen_ai\.|litellm\.call_id|user_api_key_hash" /tmp/collector.log | tail -12
```

```
    Name           : llm.request
     -> gen_ai.operation.name: Str(chat)
     -> gen_ai.system: Str(anthropic)
     -> gen_ai.request.model: Str(claude-haiku-4-5)
     -> gen_ai.usage.input_tokens: Int(8)
     -> gen_ai.usage.output_tokens: Int(21)
     -> gen_ai.usage.total_tokens: Int(29)
     -> gen_ai.cost.total_cost: Double(0.00011300000000000001)
     -> litellm.call_id: Str(0e03a76a-ef55-46e3-a494-27a9f94981ad)
     -> user_api_key_hash: Str(99b46eb86b815a60)
     -> http.response.status_code: Int(200)
     -> llm.is_streaming: Bool(false)
```

The cost comes from LiteLLM's bundled price map, so no separate pricing table is
needed. `litellm.call_id` matches the `x-litellm-call-id` response header, which
is how a trace is tied back to a specific response.

**Logs.** The callout says at startup where it exports to, and the exporter
reports failures in the same stream:

```bash
logs "OpenTelemetry" 3
```

```
INFO:root:OpenTelemetry enabled (grpc) exporting to http://10.10.0.2:4317
```

If the endpoint is unreachable or rejects the spans, the failure appears here
too, for example `Failed to export traces to 10.10.0.2:4317, error code:
StatusCode.DEADLINE_EXCEEDED` or, for Cloud Trace, `Failed to export span batch
code: 403, reason: Forbidden`.

To turn tracing off again, clear `otel_exporter_otlp_endpoint` and re-apply.

---

## Teardown

From `deploy/terraform-regional/`:

```bash
terraform destroy
```

If scenario 7 was run, remove its extra resources too:

```bash
gcloud compute instances delete otel-collector --zone us-central1-a
gcloud compute firewall-rules delete litellm-gateway-allow-otlp
gcloud compute firewall-rules delete litellm-gateway-allow-iap-ssh
```

A Cloud Run Direct VPC egress reservation can hold the subnet for a few minutes
after the services are gone. If `destroy` reports the subnet is still in use,
wait and run it again.

Optionally remove the image repository as well:

```bash
gcloud artifacts repositories delete litellm-gateway --location=us-central1
```
