__Copyrights and Licences__

Copyright 2024 Google LLC & Apache License Version 2.0

Built off of [envoy](https://github.com/envoyproxy/envoy)
 * [External Processor Reference](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/ext_proc/v3/ext_proc.proto#envoy-v3-api-msg-extensions-filters-http-ext-proc-v3-externalprocessor)
 * [Docs](https://www.envoyproxy.io/docs/envoy/latest)
 * [API](https://www.envoyproxy.io/docs/envoy/latest/api/api)

# Introduction

[Callout-based Service Extensions](https://cloud.google.com/service-extensions/docs/overview) let you use Cloud Load Balancing to make gRPC calls to user-managed services during data processing. You write callout extensions against Envoy's external processing gRPC API. Callout extensions run as general-purpose gRPC servers on user-managed compute VMs and Google Kubernetes Engine Pods on Google Cloud, multicloud, or on-premises environments.

This repository contains SDKs that will simplify your extension development.
 * [Python](./python/README.md)
