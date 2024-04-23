=========================================
Introduction
=========================================

Recipes and code samples for `Google Cloud Service Extensions <https://cloud.google.com/service-extensions/docs/overview>`_.

Service Extensions offers two types of extensions:

-   **Plugin extensions**: extensions that let you insert custom code inline in
    the networking data path. You build these plugins by using `WebAssembly (Wasm) <https://webassembly.org/>`_ and
    `Proxy-Wasm ABI <https://github.com/proxy-wasm>`_. Plugin extensions run as
    Wasm modules on a Google-managed sandbox infrastructure similar to a
    serverless infrastructure.

    Media CDN supports plugin extensions.

    Example recipes are found in the ``plugins`` subdirectory.

-   **Callout extensions**: extensions that let you use Cloud Load Balancing to
    make gRPC calls to user-managed services during data processing. You write
    callout extensions against Envoy's external processing gRPC API. Callout
    extensions run as general-purpose gRPC servers on user-managed compute VMs
    and Google Kubernetes Engine Pods on Google Cloud, multicloud, or
    on-premises environments.

    Cloud Load Balancing Application Load Balancers support callout extensions.

All Service Extensions allow you to insert custom code inline in the networking
data path.