# Token Exchange Callout

This callout server swaps the bearer token of an incoming request for one the
backend accepts, and rewrites the `Authorization` header before the request is
forwarded. For example, clients sign in with an external identity provider such
as Entra ID, but the backend only takes Google access tokens: the callout
exchanges one for the other through Workload Identity Federation, so neither
the client nor the backend has to change. Use this callout when the backend
expects credentials from a different issuer than the one the client
authenticates with.

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The `on_request_headers` callback reads the bearer token from the
   `Authorization` header. If there is none, the request passes through
   unchanged, or is rejected with `401` in fail-closed mode.
3. The token is exchanged, depending on `TOKEN_EXCHANGE_MODE`:
   - **inbound**: an external JWT is sent to the Google Security Token Service
     (STS) as the subject token of a Workload Identity Federation exchange, and
     a Google access token comes back.
   - **outbound**: the token is sent to the [RFC 8693](https://datatracker.ietf.org/doc/html/rfc8693)
     token endpoint in `OUTBOUND_TOKEN_URL`, with the optional client
     credentials, and the endpoint's token comes back.
4. The exchanged token is cached in memory, keyed by the SHA-256 hash of the
   original token, and reused until 60 seconds before it expires. Responses
   without `expires_in` are not cached.
5. `Authorization` is replaced with the exchanged token. In inbound mode the
   callout preserves the original token in `x-goog-agent-user-authorization`
   (for downstream runtimes such as Agent Engine) and copies the
   `email` (or `preferred_username`), `sub` and `groups` claims of the
   original JWT into the `x-goog-authenticated-user-email`,
   `x-goog-authenticated-user-id` and `x-original-user-groups` headers. Any
   of these headers the token has no claim for is removed, so a client
   cannot supply its own values. The claims are read without signature
   verification, because STS already validated the token during the
   exchange.
6. If the exchange fails, the request passes through with the original token,
   or is rejected with `403` when `TOKEN_EXCHANGE_FAIL_CLOSED=true`. In inbound
   mode the identity headers are removed on every pass-through as well.

The callout does not validate token signatures itself. Validation is left to
the token endpoint that performs the exchange.

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Exchanges the bearer token, rewrites `Authorization`, and sets or removes the identity headers. Returns an `ImmediateResponse` instead when the request is rejected in fail-closed mode. |

## Configuration

The callout server is configured with environment variables.

| Variable | Description |
|---|---|
| `TOKEN_EXCHANGE_MODE` | `inbound` (default) or `outbound`. |
| `TOKEN_EXCHANGE_FAIL_CLOSED` | `true` to reject requests that were not exchanged. Defaults to `false`. |
| `WIF_PROJECT_NUMBER` | Project number of the workload identity pool. Required in inbound mode. |
| `WIF_POOL_ID` | Workload identity pool ID. Required in inbound mode. |
| `WIF_PROVIDER_ID` | Workload identity pool provider ID. Required in inbound mode. |
| `WIF_SCOPE` | Space separated OAuth scopes of the Google access token. Defaults to `https://www.googleapis.com/auth/cloud-platform`. |
| `OUTBOUND_TOKEN_URL` | Token endpoint of the external identity provider. Required in outbound mode. |
| `OUTBOUND_CLIENT_ID` | OAuth client ID sent to the token endpoint. Optional. |
| `OUTBOUND_CLIENT_SECRET` | OAuth client secret sent to the token endpoint. Optional. |

The identity headers reuse the names that Identity-Aware Proxy sets, but not
its format: the email header carries the plain claim value, and the id header
carries the `sub` claim of the external identity provider. `groups` is joined
with commas.

## Run

```bash
cd callouts/python
pip install -r requirements.txt \
  -r extproc/example/token_exchange/additional-requirements.txt
export TOKEN_EXCHANGE_MODE=inbound
export WIF_PROJECT_NUMBER=123456789012
export WIF_POOL_ID=my-pool
export WIF_PROVIDER_ID=my-provider
python -m extproc.example.token_exchange.service_callout_example \
  --disable_tls --plaintext_address 0.0.0.0:8080 \
  --health_check_address 0.0.0.0:8000
```

The health check listens on port 80 by default, which needs root on Linux and
macOS. `--health_check_address` moves it to an unprivileged port.

## Test

```bash
cd callouts/python
pytest extproc/tests/token_exchange_test.py
```

The tests call the callout directly with synthetic requests and mock the HTTP
calls to STS and the token endpoint, so they need no network access.

## Deploy to Google Cloud

The Terraform configuration in [`deploy/terraform`](deploy/terraform) deploys
the callout server to Cloud Run and attaches it as a traffic extension to a
global external Application Load Balancer. It also deploys an echo backend, so
the mutated request headers can be inspected. For deploying a regional external
HTTPS Application Load Balancer fronting Agent Engine via Private Service
Connect (PSC), see
[`deploy/terraform_agent_engine`](deploy/terraform_agent_engine/README.md).

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0, with
  the Google provider >= 7.7.0 (resolved by `terraform init`)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- A Google Cloud project with billing enabled
- For inbound mode, an external OpenID Connect identity provider whose tokens
  the callout should accept
- For outbound mode, an RFC 8693 token endpoint

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
  secretmanager.googleapis.com \
  sts.googleapis.com
```

### 3. Create the Artifact Registry repository

`cloudbuild.yaml` pushes to a repository named `token-exchange` in
`us-central1`.

```bash
gcloud artifacts repositories create token-exchange \
  --repository-format=docker --location=us-central1
```

### 4. Build and push the image

Run from `callouts/python`, because the build context is the package root:

```bash
cd callouts/python
gcloud builds submit \
  --config extproc/example/token_exchange/cloudbuild.yaml .
```

### 5. Create the workload identity pool (inbound mode)

Create a pool and an OpenID Connect provider for the external identity
provider. The issuer and audience below are the ones for an Entra ID tenant;
see [Configure Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation-with-other-providers)
for other providers.

```bash
gcloud iam workload-identity-pools create my-pool --location=global
gcloud iam workload-identity-pools providers create-oidc my-provider \
  --workload-identity-pool=my-pool --location=global \
  --issuer-uri="https://login.microsoftonline.com/TENANT_ID/v2.0" \
  --allowed-audiences="APP_CLIENT_ID" \
  --attribute-mapping="google.subject=assertion.sub"
```

The access token that STS returns only carries the permissions granted to the
federated identity. Grant the roles the backend expects to
`principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/my-pool/*`
or to individual subjects.

### 6. Create the client secret (outbound mode)

The client secret is read from Secret Manager at container start. Create it
outside of Terraform, so that its value never ends up in the Terraform state:

```bash
printf '%s' "$CLIENT_SECRET" | gcloud secrets create \
  token-exchange-client-secret --data-file=-
```

Terraform grants the callout's service account
`roles/secretmanager.secretAccessor` on this secret only. Cloud Run resolves
the secret version when an instance starts, so pin
`outbound_client_secret_version` to a version number rather than `latest`
when the secret is rotated.

### 7. Configure and apply Terraform

```bash
cd callouts/python/extproc/example/token_exchange/deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, project_number, region, image_uri,
# token_exchange_mode, and the wif_* or outbound_* values for that mode.
terraform init
terraform apply
```

| Variable | Description |
|---|---|
| `project_id`, `project_number`, `region` | Target project and region. |
| `image_uri` | The image pushed in step 4. |
| `token_exchange_mode` | `INBOUND` or `OUTBOUND`. |
| `wif_pool_id`, `wif_provider_id` | The pool and provider from step 5. |
| `outbound_token_url`, `outbound_client_id` | The token endpoint and client ID for outbound mode. |
| `outbound_client_secret_id`, `outbound_client_secret_version` | The secret from step 6 and the version to expose. |
| `fail_closed` | Sets `TOKEN_EXCHANGE_FAIL_CLOSED` on the callout and `fail_open = false` on the traffic extension. |

The traffic extension starts taking effect a few minutes after the apply.
Until then, requests reach the echo backend unchanged.

### 8. Test the deployment

`$TOKEN` is a JWT issued by the identity provider behind the pool (inbound) or
the token the outbound endpoint accepts as subject token (outbound). The echo
backend returns the request headers it received.

```bash
LB_IP=$(terraform output -raw load_balancer_ip)

# The Authorization header should now carry the exchanged token, and in
# inbound mode the identity headers should be present.
curl -s "http://$LB_IP/headers" -H "Authorization: Bearer $TOKEN"

# Identity headers sent by the client are overwritten or removed.
curl -s "http://$LB_IP/headers" -H "Authorization: Bearer $TOKEN" \
  -H "x-original-user-groups: admin"

# With fail_closed = true, a request without a token gets 401 and a
# request with a token that cannot be exchanged gets 403.
curl -s -o /dev/null -w '%{http_code}\n' "http://$LB_IP/headers"
```

### 9. Tear down

```bash
terraform destroy
gcloud artifacts repositories delete token-exchange --location=us-central1
gcloud iam workload-identity-pools delete my-pool --location=global
gcloud secrets delete token-exchange-client-secret
```

### What gets deployed

| Resource | Purpose |
|---|---|
| Cloud Run service `token-exchange-ext-proc` | The callout server, running as its own service account. |
| Cloud Run service `token-exchange-echo-backend` | An echo backend (`go-httpbin`) that returns the request headers. |
| Serverless NEGs and backend services | Connect both services to the load balancer. |
| Global forwarding rule, HTTP proxy, URL map, IP address | A verification load balancer on port 80. |
| Traffic extension `token-exchange-traffic-ext` | Sends request headers to the callout, with a 10 second timeout. |
| Secret Manager IAM binding | Read access to the client secret for the callout's service account, outbound mode only. |

### Invoker access
> [!IMPORTANT]
> Both Cloud Run services allow unauthenticated invocation (`allUsers`). The
> callout has to, because Service Extensions calls it without an identity token
> and the [callouts documentation](https://cloud.google.com/service-extensions/docs/callouts-overview)
> requires a Cloud Run callout backend to allow unauthenticated access. The echo
> backend needs it because the load balancer does not authenticate to Cloud Run
> backends either.

> Both services have their ingress limited to internal traffic and Cloud Load
> Balancing, and their default `run.app` URL turned off, so they cannot be
> reached directly from the internet. Any load balancer in the project can still
> route to them, so keep this in mind outside of a test project.
