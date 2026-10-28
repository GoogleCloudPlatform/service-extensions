# Deploying to GKE Gateway

Runs a callout as a Kubernetes Deployment/Service behind a GKE Gateway, using the `GCPTrafficExtension` resource (general availability as of April 2026).

This is language-agnostic: the manifests below just point at a container image and a Service — swap in your own Python, Go, or Java image and the Gateway/extension wiring is identical.

## Prerequisites

- A GKE cluster running a [Gateway](https://cloud.google.com/kubernetes-engine/docs/concepts/gateway-api) (`gke-l7-regional-external-managed`, `gke-l7-rilb`, or `gke-l7-global-external-managed`, depending on the extension type — see restrictions below).
- **GKE callout backends must serve gRPC over HTTP/2 with end-to-end TLS.** Generate a certificate (e.g. with `mkcert`) and load it as a Kubernetes Secret before you start — a plaintext callout server will not work here, unlike the GCE guide.

```bash
mkcert internal
kubectl create secret tls callout-tls-secret \
  --cert=internal.pem \
  --key=internal-key.pem \
  --namespace=<your-gateway-namespace>
```

## 1. Deploy the callout as a Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: callout-deployment
  namespace: <your-gateway-namespace>
spec:
  replicas: 2
  selector:
    matchLabels: { app: callout }
  template:
    metadata:
      labels: { app: callout }
    spec:
      containers:
        - name: callout
          image: us-docker.pkg.dev/service-extensions-samples/callouts-source/python-example-jwt-auth:main
          ports:
            - name: grpc
              containerPort: 443
            - name: health
              containerPort: 80
          volumeMounts:
            - name: tls
              mountPath: /etc/callout/tls
      volumes:
        - name: tls
          secret: { secretName: callout-tls-secret }
---
apiVersion: v1
kind: Service
metadata:
  name: callout-service
  namespace: <your-gateway-namespace>
spec:
  selector: { app: callout }
  ports:
    - name: grpc
      port: 443
      targetPort: grpc
      protocol: TCP
      appProtocol: HTTP2   # required -- tells the Gateway controller to speak HTTP/2 to this backend
    - name: health
      port: 80
      targetPort: health
```

## 2. Attach a GCPTrafficExtension to your Gateway

```yaml
apiVersion: networking.gke.io/v1
kind: GCPTrafficExtension
metadata:
  name: callout-traffic-extension
  namespace: <your-gateway-namespace>   # must match the Gateway's namespace
spec:
  targetRefs:
    - group: "gateway.networking.k8s.io"
      kind: Gateway
      name: <your-gateway-name>
  extensionChains:
    - name: chain1
      matchCondition:
        celExpressions:
          - "true"
      extensions:
        - name: callout-ext
          backendRef:
            name: callout-service
            port: 443
          timeout: 0.1s
          supportedEvents:
            - RequestHeaders
            - ResponseHeaders
```

```bash
kubectl apply -f callout-deployment.yaml
kubectl apply -f callout-extension.yaml
```

## Which extension type?

| | `GCPTrafficExtension` | `GCPRoutingExtension` |
|---|---|---|
| Use for | Header/body manipulation (`add_header`, `jwt_auth`, …) | Routing decisions (`dynamic_forwarding`) |
| Max extensions per chain | 3 | 1 |
| Affects backend selection? | No | Yes |
| Supported Gateway classes | regional + global external, regional internal | regional external, regional internal only (not global) |

## Notes

- Per-message timeout must be between 10ms and 1s for both extension types.
- A `GCPTrafficExtensionSpec` / `GCPRoutingExtensionSpec` can hold up to 5 extension chains.
- The Gateway, the `GCPTrafficExtension`, and the callout's `Service` must all live in the same namespace.
- Full reference: [Customize GKE Gateway traffic using Service Extensions](https://cloud.google.com/kubernetes-engine/docs/how-to/configure-gke-service-extensions).
