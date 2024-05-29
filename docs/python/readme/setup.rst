Requirements
============

-   Python 3.11+
-   `buf <https://buf.build/docs/introduction>`
-   `requirements.txt <./requirements.txt>`

Quick start
===========

The minimal operation of this Python-based ext_proc server requires the `grpcio` python package as well as the protobuf generator tool `buf <https://buf.build/docs/introduction>`.

The preferred method of installation is through a virtual environment, `venv`. To set up the virtual environment run:

.. code-block:: shell

    python -m venv env
    source env/bin activate

Then the packages can be installed with:

.. code-block:: shell

    pip install -r requirements.txt

And if you want to run tests:

.. code-block:: shell

    pip install -r requirements-test.txt

`buf` can be installed from `here <https://buf.build/docs/installation>`.

The proto library files are generated with `buf` using:

.. code-block:: shell

    buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path envoy/service/ext_proc/v3/external_processor.proto --include-imports

The proto files are then installed as a local package:

.. code-block:: shell

    python -m pip install ./protodef

We install the proto files as a local package to allow for absolute imports within the generated python code.

Running
-------

Example servers can be started from the `extproc/example/<...>` submodules. For example, the grpc `service_callout_example` server can be started with:

.. code-block:: shell

    python -m extproc.example.grpc.service_callout_example

The server will then run until interrupted, for example, by inputting `Ctrl-C`.

Examples
--------

Examples for various styles of callout server are located under `extproc/example/`.

Developing Callouts
===================

This repository provides the following files to be extended to fit the needs of the user:

-   `extproc/service/callout_server.py <extproc/service/callout_server.py>`: Baseline service callout server.
-   `extproc/service/callout_tools.py <extproc/service/callout_tools.py>`: Common functions used in many callout server code paths.

Making a new server
-------------------

Create a new python script `server.py` and import the `CalloutServer` class from `extproc/service/callout_server.py`:

.. code-block:: python

    from extproc.service.callout_server import CalloutServer

Just from importing the server class we can make the server run by creating a new instance and calling the blocking function `run`:

.. code-block:: python

    if __name__ == '__main__':
        CalloutServer().run()

Calling the server like this won't do much besides respond to health checks though. In order for the server to respond to requests, we need to create a custom class extending `CalloutServer`.

Make a class extending `CalloutServer`:

.. code-block:: python

    class BasicCalloutServer(CalloutServer):

There are a few callback methods in `CalloutServer` provided for developers to override:

-   `on_request_headers`: Process request headers.
-   `on_response_headers`: Process response headers.
-   `on_request_body`: Process request body.
-   `on_response_body`: Process response body.

These functions correspond to the `oneof` required field in a `ProcessingRequest` and required response field of a `ProcessingResponse`.

When a given type of data is received, the corresponding function is called on this server. To hook into that call, override the method, for example in `BasicCalloutServer`:

.. code-block:: python

    class BasicCalloutServer(CalloutServer):
        def on_response_headers(
            self, headers: HttpHeaders, context: ServicerContext) -> HeadersResponse:
            ...

A few things to note here, we are strongly typing our variables with the expected types. This requires the following imports:

.. code-block:: python

    from grpc import ServicerContext
    from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
    from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders

See `Using the proto files` for more details.

Each of the callback methods provides the given data type as an input parameter and expects the corresponding response to be returned. For example, `on_response_headers`:

-   `headers`: `response_headers` data from `ProcessingRequest`.
-   `context`: associated grpc data.
-   `return`: `response_headers` data from `ProcessingResponse`.

There are methods specified under `extproc/service/callout_tools.py` that will help in creating a response to the request. Import those with:

.. code-block:: python

    from extproc.service.callout_tools import add_header_mutation

With the callout from before we can add the `foo:bar` header mutation on incoming `response_headers` requests:

.. code-block:: python

    class BasicCalloutServer(CalloutServer):
        def on_response_headers(
            self, headers: HttpHeaders, context: ServicerContext) -> HeadersResponse:
            return add_header_mutation(add=[('foo', 'bar')])

`add_header_mutation` also has parameters for removing (`remove`) and cache clearing (`clear_route_cache`). See `extproc/service/callout_tools.py`.

The callout server uses the `logging` module. By default, this means that nothing is logged to the terminal on standard use. We recommend setting the logging level to `INFO` so that normal server operation is visible.

All together that is:

.. code-block:: python

    import logging
    from grpc import ServicerContext
    from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
    from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
    from extproc.service.callout_server import CalloutServer

    class BasicCalloutServer(CalloutServer):
        def on_response_headers(
            self, headers: HttpHeaders, context: ServicerContext) -> HeadersResponse:
            return add_header_mutation(add=[('foo', 'bar')])

    if __name__ == '__main__':
        logging.basicConfig(level=logging.INFO)
        BasicCalloutServer().run()

Saving to file `server.py`, the callout server can be run with:

.. code-block:: shell

    python -m server

Additional Details
===================

`CalloutServer` has many options to customize the security information as well as port settings. The default `CalloutServer` listens on port `8443` for grpc traffic, `8000` for health checks, and `8080` for insecure traffic. Please see the `CalloutServer` docstring for more information.

The `on_request_headers` and `on_request_body` methods also accept `ImmediateResponse` values as a return value.

`CalloutServer` also contains a `process` method that can be overridden to work directly on incoming `ProcessingRequest` s.

Using the proto files
---------------------

The python classes can be imported using the relative `envoy/api` path:

.. code-block:: python

    from envoy.service.ext_proc.v3 import external_processor_pb2

For example, to import the `HeadersResponse` class:

.. code-block:: python

    from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse

Alternative Install Methods
===========================

Without `venv`
--------------

Alternatively, the packages can be installed through the package manager:

.. code-block:: shell

    sudo apt-get install python3-grpcio -y

And the protobuf library with:

.. code-block:: shell

    python -m pip install ./protodef

WARNING! Installing the `protodef` package to your system outside of a `venv` could cause unintentional side effects. Only do this if you are inside of a self-contained environment or you know what you are doing.

Without installing the proto code as a local package
----------------------------------------------------

Alternatively, rather than installing through pip, the proto code can be placed in the root of this project and imported directly.

.. code-block:: shell

    buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path envoy/service/ext_proc/v3/external_processor.proto --include-imports -o out
    mv ./out/protodef/* .

Tests
=====

Tests can be run with:

.. code-block:: shell

    pytest

Docker
======

Quickstart
----------

The basic docker image contains arguments for pointing to and running python modules. For example, to build `extproc/example/basic_callout_server.py` into a run-able docker image:

.. code-block:: shell

    docker build -f ./extproc/example/Dockerfile -t service-callout-example-python --build-arg copy_path=extproc/example/basic_callout_server.py --build-arg run_module=basic_callout_server .

--build-arg:
* `copy_path`: Path of python files required on the docker image.
* `run_module`: The module to run on startup.

This image will copy `extproc/example/basic_callout_server.py` to the base directory and runs it as `basic_callout_server`.

The image can then be run with:

.. code-block:: shell

    docker run -P -it service-callout-example-python:latest

In this example, using the `-P` flag tells docker to connect the exposed ports to the local machine's ports. Setting