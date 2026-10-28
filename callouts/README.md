# Callout extensions

[Callout-based Service Extensions](https://cloud.google.com/service-extensions/docs/overview) let you use Cloud Load Balancing to make gRPC calls to a service you run — to inspect and mutate traffic in flight. Callout extensions run as general-purpose gRPC servers on your own infrastructure: a Compute Engine VM, a GKE Gateway, or your own multicloud/on-premises environment.

This directory has SDKs and examples in **Python**, **Go**, and **Java**. Start with what you're building — language and deployment target are the next question, not the first one.

## Start with what you're building

| Use case | Examples | Languages |
|---|---|---|
| [Header manipulation](#header-manipulation) | Rewrite, add, or strip headers per request or response | Python · Go · Java |
| [Body manipulation](#body-manipulation) | Replace, append, or clear request and response bodies | Python · Go · Java |
| [Routing & traffic](#routing--traffic) | Redirects and dynamic, header-driven backend forwarding | Python · Go · Java |
| [Authentication & authorization](#authentication--authorization) | Validate tokens, block by policy — via `ext_proc` or `ext_authz` | Python · Go · Java |
| [Cookie management](#cookie-management) | Conditionally set cookies on the response path | Python |
| [Observability](#observability) | Log request and authorization decisions to Cloud Logging | Python |
| [AI / LLM gateway](#ai--llm-gateway) | A full gateway callout, with its own Terraform deploy | Python |
| [Network-layer (L4)](#network-layer-l4) | Raw TCP processing, below the HTTP layer | Python |

Every example above is indexed by use case in **[CATALOG.md](CATALOG.md)** — the fastest way to browse all of them without knowing the folder layout first. The table below is the same information laid out per language, for when you already know which SDK you're using.

### Header manipulation
Python: [add_header](python/extproc/example/add_header/), [update_header](python/extproc/example/update_header/), [normalize_header](python/extproc/example/normalize_header/) · Go: [add_header](go/extproc/examples/add_header/) · Java: [AddHeader](java/service-callout/src/main/java/example/AddHeader/)

### Body manipulation
Python: [add_body](python/extproc/example/add_body/), [add_custom_response](python/extproc/example/add_custom_response/) · Go: [add_body](go/extproc/examples/add_body/) · Java: [AddBody](java/service-callout/src/main/java/example/AddBody/)

### Routing & traffic
Python: [redirect](python/extproc/example/redirect/), [dynamic_forwarding](python/extproc/example/dynamic_forwarding/) · Go: [redirect](go/extproc/examples/redirect/), [dynamic_forwarding](go/extproc/examples/dynamic_forwarding/) · Java: [Redirect](java/service-callout/src/main/java/example/Redirect/) *(dynamic_forwarding: Python & Go only)*

### Authentication & authorization
Python: [jwt_auth](python/extproc/example/jwt_auth/) (`ext_proc`), [block_ip](python/extauthz/example/block_ip/) (`ext_authz`) · Go: [jwt_auth](go/extproc/examples/jwt_auth/) · Java: [JwtAuth](java/service-callout/src/main/java/example/JwtAuth/)

### Cookie management
Python: [set_cookie](python/extproc/example/set_cookie/)

### Observability
Python: [cloud_log](python/extproc/example/cloud_log/)

### AI / LLM gateway
Python: [litellm_gateway](python/extproc/example/litellm_gateway/) — ships its own [Terraform config](python/extproc/example/litellm_gateway/deploy/)

### Network-layer (L4)
Python: [network_basic](python/extproc/l4_example/network_basic/)

## Capability matrix

| Capability | Python | Go | Java |
|---|:---:|:---:|:---:|
| `ext_proc` · HTTP (L7) | ✓ | ✓ | ✓ |
| `ext_proc` · TCP (L4) | ✓ | – | – |
| `ext_authz` | ✓ | – | – |

Go and Java cover L7 `ext_proc` today; `ext_authz` and L4 support for those languages is tracked as a roadmap item, not hidden.

## Deploying a callout server

Every example above runs the same way regardless of what it does: as a gRPC server your load balancer calls into. See **[deploy/](deploy/)** for platform guides:

- [deploy/gce.md](deploy/gce.md) — Compute Engine VM
- [deploy/gke.md](deploy/gke.md) — GKE Gateway (GA as of April 2026)
- [deploy/multicloud-onprem.md](deploy/multicloud-onprem.md) — multicloud and on-premises

## Per-language quick starts

- [python/README.md](python/README.md) — requirements, proto generation, running examples, Docker
- [go/README.md](go/README.md) — requirements, running examples, Docker Compose
- [java/service-callout/README.md](java/service-callout/README.md) — requirements, Maven/Gradle build, Docker

## License

Files in this directory are Copyright Google LLC, licensed under Apache License 2.0. See individual language directories for specific file attributions.
