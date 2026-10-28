# Deploying multicloud or on-premises

Runs a callout server outside Google Cloud entirely — another cloud provider, or your own data center — and wires it into Cloud Load Balancing as a **hybrid connectivity NEG** backend.

This is the deployment path the top-level README refers to as "multicloud or on-premises environments." It's the least turnkey of the three guides in this directory, because it depends on your own network connectivity back to Google Cloud — but the load balancer and extension configuration on the Google Cloud side is otherwise the same shape as the [GCE guide](gce.md).

## Prerequisites

- Your callout server (any language in this repo) is already reachable at a fixed `IP:port` from your Google Cloud VPC — over **Cloud VPN**, **Cloud Interconnect** (dedicated or partner), or a **Router appliance VM**. Setting up that connectivity is outside the scope of this guide; see [Hybrid connectivity NEGs](https://cloud.google.com/load-balancing/docs/hybrid) for the options.
- `compute.googleapis.com` and `networkservices.googleapis.com` enabled, same as the GCE guide.

## 1. Create a hybrid connectivity NEG

```bash
gcloud compute network-endpoint-groups create callout-hybrid-neg \
  --network-endpoint-type=non-gcp-private-ip-port \
  --zone=us-west1-a \
  --network=lb-network \
  --subnet=backend-subnet

gcloud compute network-endpoint-groups update callout-hybrid-neg \
  --zone=us-west1-a \
  --add-endpoint="ip=10.100.0.5,port=443"
```

`10.100.0.5` is your callout server's address as reachable through the hybrid connection — not a public IP.

## 2. Create the backend service and attach the NEG

```bash
gcloud compute backend-services create l7-ilb-callout-service \
  --load-balancing-scheme=INTERNAL_MANAGED \
  --protocol=GRPC \
  --region=us-west1

gcloud compute backend-services add-backend l7-ilb-callout-service \
  --network-endpoint-group=callout-hybrid-neg \
  --network-endpoint-group-zone=us-west1-a \
  --region=us-west1
```

## 3. Configure the extension

Identical to the [GCE guide, step 4](gce.md#4-configure-the-extension) — the extension config points at the backend service, and doesn't know or care whether that backend service resolves to a GCP instance group or a hybrid NEG.

## Health checks

Google Cloud's health checker needs to reach your callout server the same way client traffic does — through the same VPN/Interconnect path. Confirm the health check port is reachable from your VPC before debugging anything else; a NEG with no healthy endpoints is the most common failure mode here.

## Notes

- Latency and reliability now depend on your hybrid connection, not Google's network — budget accordingly, especially if you enable body-processing events, which are more sensitive to added round-trip time.
- If your callout runs in another public cloud with its own outbound connectivity, the same hybrid NEG approach applies; only the "how do I reach it" mechanics differ from an on-prem data center.
