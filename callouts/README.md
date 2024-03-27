__Copyrights and Licences__

Copyright 2024 Google LLC & Apache License Version 2.0

Built off of [envoy](https://github.com/envoyproxy/envoy)
 * [External Processor Reference](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/ext_proc/v3/ext_proc.proto#envoy-v3-api-msg-extensions-filters-http-ext-proc-v3-externalprocessor)
 * [Docs](https://www.envoyproxy.io/docs/envoy/latest)
 * [API](https://www.envoyproxy.io/docs/envoy/latest/api/api)

# Introduction

[Service Extensions](https://cloud.google.com/service-extensions/docs) are external services that are called out to within the filter chain of a load balancer and provide information on requests before reaching backends.

This repository contains software development kits that provide a baseline to start up external services.
 * [Python](./python/README.md)

The development kits are meant to be used as standalone servers where a main library class can be imported and extended to fit a custom callout purpose.
