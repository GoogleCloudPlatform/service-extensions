# Google Cloud Service Extensions Samples

Recipes and code samples for
[Google Cloud Service Extensions](https://cloud.google.com/service-extensions/docs/overview).

Service Extensions offers two types of extensions:

*   **Plugin extensions**: extensions that let you insert custom code inline in
    the networking data path. You build these plugins by using
    [WebAssembly (Wasm)](https://webassembly.org/) and
    [Proxy-Wasm ABI](https://github.com/proxy-wasm). Plugin extensions run as
    Wasm modules on a Google-managed sandbox infrastructure similar to a
    serverless infrastructure.

    Media CDN supports plugin extensions.

    Example recipes are found in the [`plugins` subdirectory](plugins/).

*   **Callout extensions**: extensions that let you use Cloud Load Balancing to
    make gRPC calls to user-managed services during data processing. You write
    callout extensions against Envoy's external processing gRPC API. Callout
    extensions run as general-purpose gRPC servers on user-managed compute VMs
    and Google Kubernetes Engine Pods on Google Cloud, multicloud, or
    on-premises environments.

    Cloud Load Balancing Application Load Balancers support callout extensions.

All Service Extensions allow you to insert custom code inline in the networking
data path.

# License

All recipes and samples within this repository are provided under the
[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) license. Please see
the [LICENSE](/LICENSE) file for more detailed terms and conditions.

# Code of Conduct

For our code of conduct, see [Code of Conduct](/docs/CODE_OF_CONDUCT.md).

# Contributing

Contributions welcome! See the [Contributing Guide](/docs/CONTRIBUTING.md).
