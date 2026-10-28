# Deploying to a Compute Engine VM

Runs any example in this repo as a callout backend service behind an Application Load Balancer, on a VM you manage.

This guide is language-agnostic: swap the container image for your own (or point `--metadata=startup-script` at your own binary) and everything else — instance group, backend service, extension config — stays the same regardless of whether the callout is written in Python, Go, or Java.

## Prerequisites

```bash
gcloud services enable compute.googleapis.com networkservices.googleapis.com
```

You'll also need an existing Application Load Balancer that [supports traffic/route extensions](https://cloud.google.com/service-extensions/docs/lb-extensions-overview#supported-lbs), and its VPC network/subnet.

## 1. Create the VM

Using one of this repo's published example images (see each example's README for its own image, or build your own with the relevant Dockerfile):

```bash
gcloud compute instances create-with-container callouts-vm \
  --container-image=us-docker.pkg.dev/service-extensions-samples/callouts-source/python-example-jwt-auth:main \
  --network=lb-network \
  --subnet=backend-subnet \
  --zone=us-west1-a \
  --tags=allow-ssh,load-balanced-backend
```

## 2. Add it to an (unmanaged) instance group

```bash
gcloud compute instance-groups unmanaged create callouts-ig \
  --zone=us-west1-a

gcloud compute instance-groups unmanaged add-instances callouts-ig \
  --zone=us-west1-a \
  --instances=callouts-vm
```

## 3. Create the backend service and attach the instance group

```bash
gcloud compute backend-services create l7-ilb-callout-service \
  --load-balancing-scheme=INTERNAL_MANAGED \
  --protocol=GRPC \
  --region=us-west1

gcloud compute backend-services add-backend l7-ilb-callout-service \
  --balancing-mode=UTILIZATION \
  --instance-group=callouts-ig \
  --instance-group-zone=us-west1-a \
  --region=us-west1
```

## 4. Configure the extension

Create `traffic.yaml`:

```yaml
name: traffic-ext
forwardingRules:
  - https://www.googleapis.com/compute/v1/projects/PROJECT_ID/regions/us-west1/forwardingRules/l7-ilb-forwarding-rule
loadBalancingScheme: INTERNAL_MANAGED
extensionChains:
  - name: "chain1"
    matchCondition:
      celExpression: "true"
    extensions:
      - name: "callout-ext"
        authority: example.com
        service: https://www.googleapis.com/compute/v1/projects/PROJECT_ID/regions/us-west1/backendServices/l7-ilb-callout-service
        failOpen: true
        timeout: 0.1s
        supportedEvents:
          - REQUEST_HEADERS
          - RESPONSE_HEADERS
```

Import it:

```bash
gcloud service-extensions lb-traffic-extensions import traffic-ext \
  --source=traffic.yaml \
  --location=us-west1
```

## 5. Verify

```bash
curl -D - -H "host: example.com" FORWARDING_RULE_IP
```

Look for the headers your example adds (e.g. `decoded-<claim>` for `jwt_auth`, `hello: service-extensions` for `basic`).

## Notes

- `failOpen: true` lets traffic through if the callout server is unreachable — set `false` if a failed callout should fail the request instead.
- `supportedEvents` should match what your chosen example actually implements; check its README's "Callback overridden" section. Body events (`REQUEST_BODY`, `RESPONSE_BODY`) add latency — only enable what you use.
- For a route extension instead of a traffic extension (dynamic_forwarding-style routing), use `gcloud service-extensions lb-route-extensions import` instead, and see [Configure route extensions](https://cloud.google.com/service-extensions/docs/configure-route-extensions).
