# Token Exchange Gateway for Agent Runtime

This Terraform module provisions a **Token Exchange Gateway** using a Regional
External HTTPS Application Load Balancer (ALB), an Envoy Service Extension
(`ext_proc`) on Cloud Run, and a Private Service Connect (PSC) NEG targeting
Agent Engine (`${REGION}-aiplatform.googleapis.com`).

It enables client applications authenticating through third-party Identity
Providers (e.g., Microsoft Entra ID, Okta) to pass their raw identity tokens
downstream to Agent Runtime containers without being rejected at the Google
Cloud Front End (GFE) edge.

---

## How It Works

1. A Regional External **Application Load Balancer (ALB)** intercepts incoming
   client traffic on `REQUEST_HEADERS` and triggers the `ext_proc` gRPC service
   extension.
2. The **service extension** exchanges the incoming third-party JWT for a
   federated Google Cloud STS access token using Workload Identity Federation
   (WIF). It replaces `Authorization` with the Google token, preserves the
   original JWT in `x-goog-agent-user-authorization`, and injects audit
   identity headers.
3. The ALB forwards the mutated request via a **Private Service Connect (PSC)
   NEG** to the regional Agent Engine endpoint.
4. **Agent Engine** authenticates the Google token, reverse-swaps
   `x-goog-agent-user-authorization` back into the standard `Authorization`
   header, and delivers the original user JWT to the agent container.

---

## Prerequisites

- Workload Identity Pool and OIDC Provider configured for your third-party IdP.
- Workload Identity Pool granted `roles/aiplatform.user` on the project.
- Built `token_exchange` callout image uploaded to Artifact Registry.
- Existing VPC network in the target project.

---

## Deploy

```bash
cp terraform.tfvars.example terraform.tfvars
# Populate project_id, project_number, region, wif_pool_id, wif_provider_id, and ext_proc_image_uri

terraform init
terraform apply

export GATEWAY_IP=$(terraform output -raw gateway_ip)
```

---

## Verify

```bash
curl -k -i -X POST \
  -H "Authorization: Bearer ${THIRD_PARTY_JWT}" \
  -H "Host: ${REGION}-aiplatform.googleapis.com" \
  -H "Content-Type: application/json" \
  "https://${GATEWAY_IP}/v1beta1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${ENGINE_ID}:query" \
  -d '{"input": {"input": "test-gateway"}}'
```

---

## Expected Behavior

| Scenario | Description |
|---|---|
| **Direct call to Agent Engine with third-party JWT** | Rejected at GFE edge with `401 Unauthorized`. |
| **Call via Token Exchange Gateway with third-party JWT** | Gateway swaps `Authorization` for a Google STS token and sets `x-goog-agent-user-authorization`; Agent Engine restores the third-party JWT to `Authorization` for the container (`200 OK`). |
