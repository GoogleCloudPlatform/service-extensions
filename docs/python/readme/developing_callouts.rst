.. _developing_callouts:

Developing Callouts
===================

This repository provides the following files to be extended:

* :ref:`CalloutServer <callout_server>`: Baseline service callout server.
* :ref:`CalloutTools <callout_tools>`: Common functions for callout servers.

Creating a New Server
---------------------

1. **Create a New Server Script**:

    Create ``server.py`` and import the ``CalloutServer`` class:

    .. code-block:: python

        from extproc.service.callout_server import CalloutServer

    Just from importing the server class we can make the server run by creating a new instance and calling the blocking function ``run``:

    .. code-block:: python

        if __name__ == '__main__':
            CalloutServer().run()

2. **Extend CalloutServer**:

    Calling the server like this won't do much besides respond to health checks. For the server to respond to callouts, we create a custom class extending ``CalloutServer``.

    Make a class extending ``CalloutServer``:

    .. code-block:: python

        class BasicCalloutServer(CalloutServer):
            def on_response_headers(self, headers: HttpHeaders, context: ServicerContext) -> HeadersResponse:
                ...

    There are a few callback methods in ``CalloutServer`` provided for developers to override:

    * ``on_request_headers``: Process request headers.
    * ``on_response_headers``: Process response headers.
    * ``on_request_body``: Process request body.
    * ``on_response_body``: Process response body.

    These functions correspond to the ``oneof`` required field in a `ProcessingRequest <https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingrequest>`_ and required response field of a `ProcessingResponse <https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingresponse>`_.

3. **Add Required Imports**:

    A few things to note here: we are strongly typing our variables with the expected types. This requires the following imports:

    .. code-block:: python

        from grpc import ServicerContext
        from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse, HttpHeaders

    See `Using the proto files`_ for more details.

    Each of the callback methods provides the given data type as an input parameter and expects the corresponding response to be returned. For example ``on_response_headers``:

    * ``headers``: ``response_headers`` data from `ProcessingRequest <https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingrequest>`_.
    * ``context``: associated grpc data.
    * ``return``: ``response_headers`` data from `ProcessingResponse <https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingresponse>`_.

    There are methods specified under :ref:`CalloutTools <callout_tools>` that will help in creating a response to the callout. Import those with:

    .. code-block:: python

        from extproc.service.callout_tools import add_header_mutation

4. **Implement Callbacks**:

    With the callout from before, we can add the ``foo:bar`` header mutation on incoming ``response_headers`` callouts:

    .. code-block:: python

        class BasicCalloutServer(CalloutServer):
            def on_response_headers(self, headers: HttpHeaders, context: ServicerContext) -> HeadersResponse:
                return add_header_mutation(add=[('foo', 'bar')])

    ``add_header_mutation`` also has parameters for removing (`remove`) and cache clearing (`clear_route_cache`). See :ref:`CalloutTools <callout_tools>` .

5. **Enable Logging**:

    The callout server uses the ``logging`` module. By default, this means that nothing is logged to the terminal on standard use. We recommend setting the logging level to ``INFO`` so that normal server operation is visible.

    .. code-block:: python

        import logging

        if __name__ == '__main__':
            logging.basicConfig(level=logging.INFO)
            BasicCalloutServer().run()

6. **Complete Example**:

    .. code-block:: python

        import logging
        from grpc import ServicerContext
        from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
        from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
        from extproc.service.callout_server import CalloutServer
        from extproc.service.callout_tools import add_header_mutation

        class BasicCalloutServer(CalloutServer):
            def on_response_headers(self, headers: HttpHeaders, context: ServicerContext) -> HeadersResponse:
                return add_header_mutation(add=[('foo', 'bar')])

        if __name__ == '__main__':
            logging.basicConfig(level=logging.INFO)
            BasicCalloutServer().run()

Additional Details
------------------

:ref:`CalloutServer <callout_server>` has many options to customize the security information as well as port settings. The default ``CalloutServer`` listens on port ``8443`` for grpc traffic, ``8000`` for health checks, and ``8080`` for plaintext traffic. Please see the ``CalloutServer`` docstring for more information.

The ``on_request_headers`` and ``on_request_body`` methods also accept `ImmediateResponse <https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#envoy-v3-api-field-service-ext-proc-v3-processingresponse-immediate-response>`_ values as a return value.

:ref:`CalloutServer <callout_server>` also contains a ``process`` method that can be overridden to work directly on incoming ``ProcessingRequest``.

.. _using_the_proto_files:

Using the Proto Files
---------------------

Import proto classes using the relative `envoy/api <https://github.com/envoyproxy/envoy/tree/main/api>`_ path:

.. code-block:: python

    from envoy.service.ext_proc.v3 import external_processor_pb2

For example, to import the ``HeadersResponse`` class:

.. code-block:: python

    from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse