__Copyrights and Licences__

Files using Copyright 2023 Google LLC & Apache License Version 2.0:

* [service_callout.py](./extproc/service/callout_server.py) (This is only HTTP layer callouts)
* [network_callout_server.py](./extproc/service/network_callout_server.py) (This is for TCP layer callouts)
* [callout_tools.py](./extproc/service/callout_tools.py)
* [command_line_tools.py](./extproc/service/command_line_tools.py)

Note: This document will focus on two types of callouts: L7 and L4. The interface for each type is different.

# Requirements

* Python 3.11+
* [buf](https://buf.build/docs/introduction)
* [requirements.txt](./requirements.txt)

> [!NOTE]
> All commands are expected to be run from within the `callouts/python` directory.

# L7 HTTP Quick start

The minimal operation of this Python-based ext_proc server requires the `grpcio` python package as well as the protobuf generator tool [buf](https://buf.build/docs/introduction).

The preferred method of installation is through a virtual environment, `venv`. To set up the virtual environment run:

```shell
cd service-extensions/callouts/python
python -m venv env
source env/bin/activate
```

Then the packages can be installed with:

```shell
pip install -r requirements.txt
```

`buf` can be installed from [here](https://buf.build/docs/installation).

The proto library files are generated with `buf` using:

```shell
buf -v generate \
  https://github.com/envoyproxy/envoy.git#subdir=api \
  --path envoy/service/ext_proc/v3/external_processor.proto \
  --include-imports
```

> The default template file `buf.gen.yaml` will not generate `pyright` compatible proto stubs.
> If you plan to develop callouts with a similar type checker and not just build them,
> we suggest you run the command with the alternative development template using
> `--template=buf_dev.gen.yaml`:
>
> ```shell
> buf -v generate \
>  https://github.com/envoyproxy/envoy.git#subdir=api \
>  --path envoy/service/ext_proc/v3/external_processor.proto \
>  --include-imports --template=buf_dev.gen.yaml
> ```
>
> You may need to run `python -m pip uninstall ./protodef` after re-generating the proto files
> to get the linter to update.

The proto files are then installed as a local package:

```shell
python -m pip install ./protodef
```

We install the proto files as a local package to allow for absolute imports within the generated python code.

## Running

Example servers can be started from the `extproc/example/<...>` submodules.
For example the grpc `service_callout_example` server can be started with:

```shell
python -m extproc.example.basic.service_callout_example
```

The server will then run until interrupted, for example, by inputting `Ctrl-C`.

# Examples

Examples for various styles of L7 callout server are located under [extproc/example/](./extproc/example/).

# Developing L7 Callouts

This repository provides the following files to be extended to fit the needs of the user:

* [extproc/service/callout_server.py](extproc/service/callout_server.py) Baseline service callout server.
* [extproc/service/callout_tools.py](extproc/service/callout_tools.py) Common functions used in many callout server codepaths.

## Making a new L7 server

Create a new python script `server.py` and import the `CalloutServer` class from [extproc/service/callout_server.py](extproc/service/callout_server.py)

``` python
from extproc.service.callout_server import CalloutServer
```

Just from importing the server class we can make the server run by creating a new instance and calling the blocking function `run`
:

``` python
if __name__ == '__main__':
  CalloutServer().run()
```

Calling the server like this won't do much besides respond to health checks, for the server to respond to callouts we create a custom class extending `CalloutServer`.

Make a class extending `CalloutServer`.

``` python
class BasicCalloutServer(CalloutServer):
```

There are a few callback methods in `CalloutServer` provided for developers to override:

* `on_request_headers`: Process request headers.
* `on_response_headers`: Process response headers.
* `on_request_body`: Process request body.
* `on_response_body`: Process response body.

These functions correspond to the `oneof` required field in a [ProcessingRequest](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingrequest) and required response field of a [ProcessingResponse](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingresponse).

When a given type of data is received the corresponding function is called on this server.
To hook into that call, override the method, for example in `BasicCalloutServer`:

``` python
class BasicCalloutServer(CalloutServer):
    def on_response_headers(
      self, headers: HttpHeaders,
      context: ServicerContext) -> HeadersResponse:
    ...
```

A few things to note here, we are strongly typing our variables with the expected types. This requires the following imports:

```python
from grpc import ServicerContext
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
```

See [Using the proto files](#using-the-proto-files) for more details.

Each of the callback methods provides the given data type as an input parameter and expect the corresponding response to be returned.
For example `on_response_headers`:

* `headers`: `response_headers` data from [ProcessingRequest](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingrequest).
* `context`: associated grpc data.
* `return`: `response_headers` data from [ProcessingResponse](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#service-ext-proc-v3-processingresponse).

There are methods specified under [extproc/service/callout_tools.py](extproc/service/callout_tools.py) that will help in creating a response to the callout.
Import those with:

``` python
from extproc.service.callout_tools import add_header_mutation
```

With the callout from before we can add the `foo:bar` header mutation on incomming `response_headers` callouts:

``` python
class BasicCalloutServer(CalloutServer):
    def on_response_headers(
      self, headers: HttpHeaders,
      context: ServicerContext) -> HeadersResponse:
        return add_header_mutation(add=[('foo', 'bar')])
```

`add_header_mutation` also has parameters for removing (`remove`) and cache clearing (`clear_route_cache`). See [extproc/service/callout_tools.py](extproc/service/callout_tools.py).

The callout server uses the `logging` module. By default, this means that nothing is logged to the terminal on standard use. We recommend setting the logging level to `INFO` so that normal server operation is visible.

All together that is:

``` python
import logging
from grpc import ServicerContext
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from extproc.service.callout_server import CalloutServer

class BasicCalloutServer(CalloutServer):
  def on_response_headers(
    self, headers: HttpHeaders,
    context: ServicerContext) -> HeadersResponse:
    return add_header_mutation(add=[('foo', 'bar')])

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  BasicCalloutServer().run()
```

Saving to file `server.py` the callout server can be run with:

```shell
python -m server
```

## Additional Details

[CalloutServer](extproc/service/callout_server.py) has many options to customize the security information as well as port settings.
The default `CalloutServer` listens on port `8443` for grpc traffic, `8000` for health checks and `8080` for plaintext traffic. Please see the `CalloutServer` docstring for more information.

The `on_request_headers` and `on_request_body` methods also accept [`ImmediateResponse`](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto#envoy-v3-api-field-service-ext-proc-v3-processingresponse-immediate-response) values as a return value.

[CalloutServer](extproc/service/callout_server.py) also contains a `process` method that can be overridden to work directly on incoming `ProcessingRequest`s.

## Using the proto files

The python classes can be imported using the relative [envoy/api](https://github.com/envoyproxy/envoy/tree/main/api) path:

```python
from envoy.service.ext_proc.v3 import external_processor_pb2
```

For example to import the `HeadersResponse` class:

```python
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
```

# Alternative Install Methods

## Without `venv`

Alternatively, the packages can be installed through the package manager:

```shell
sudo apt-get install python3-grpcio -y
```

And the protobuf library with:

```shell
python -m pip install ./protodef
```

> [!WARNING]
> Installing the `protodef` package to your system outside of a `venv` could cause unintentional side effects.

## Without installing the proto code as a local package

Alternatively, rather than installing through pip, the proto code can be placed in the root of this project and imported directly.

```bash
buf -v generate \
  https://github.com/envoyproxy/envoy.git#subdir=api \
  --path envoy/service/ext_proc/v3/external_processor.proto \
  --include-imports \
  -o out && \
mv ./out/protodef/* .
```

# Tests

Tests require packages from the `requirements.txt` file as well as the `requirements-test.txt` file, installed with:

```shell
pip install -r requirements.txt -r requirements-test.txt
```

All tests can then be run with:

```shell
pytest
```

# Docker

The basic Docker image contains arguments for pointing to and running python modules.
For example, to build
[extproc/example/basic/service_callout_example.py](extproc/example/basic/service_callout_example.py) run:

``` bash
docker build \
  -f ./extproc/example/Dockerfile \
  -t service-callout-example-python \
  --build-arg proto_path=envoy/service/ext_proc/v3/external_processor.proto \
  --build-arg copy_path=extproc/example/basic/ \
  --build-arg run_module=service_callout_example .
```

`--build-arg` specifies the following:

* `copy_path`: Required files to copy to the docker image.
* `run_module`: The python module to run on startup.

The above example makes a copy of `extproc/example/basic/service_callout_example.py`
and sets up the image to run `service_callout_example.py` on startup.

The image can then be run with:

``` bash
docker run -P -it --network host service-callout-example-python:latest
```

In this example, using the `-P` flag tells docker to connect the exposed ports to the local machine's ports.
Setting `--network host` tells docker to connect the image to the `0.0.0.0` or `localhost` ip address.

> [!NOTE]
> The docker image is set up to pass command line arguments to the module when specified.
> This also requires that the example is set up to use command line arguments as well,
> like in [extproc/example/basic/service_callout_example.py](extproc/example/basic/service_callout_example.py)
>
> For example:
>
> ```bash
> docker run -P -it --network host service-callout-example-python:latest \
>   -- --combined_health_check
> ```
>
> Will run the health check for `basic/service_callout_example.py` combined with the main grpc server.

## Examples with unique dependencies

The `cloud_log` and `jwt_auth` examples require additional libraries to function.
For instance, the `cloud_log` example requires the `google-cloud-logging` library.

In this case, we need more than just the python file.
We copy `additional-requirements.txt` along with `service_callout_example.py` by
specifying the folder `extproc/example/cloud_log` as the `copy_path`.

``` bash
docker build \
  -f ./extproc/example/Dockerfile \
  -t service-callout-example-python \
  --build-arg proto_path=envoy/service/ext_proc/v3/external_processor.proto \
  --build-arg copy_path=extproc/example/cloud_log \
  --build-arg run_module=service_callout_example .
```

`./extproc/example/Dockerfile` is set up to detect additional dependencies when present,
and install them.

Both the `cloud_log` and `jwt_auth` examples can be built this way.
If even more configurability is needed, a custom Docker image example is also available.

## Custom Docker Files

If the baseline docker file does not contain the required complexity for a given use case.
A custom image can be created and branched from the common image.
`./extproc/example/Dockerfile` is internally split up into two steps,
a common image step and the example specific image step.

For instance, the `jwt_auth` example requires an additional python library much like `cloud_log`.
We can also accomplish the same goal as the `cloud_log` example through a custom Docker image.
`./extproc/example/jwt_auth/Dockerfile` installs the dependencies as part of the image setup.

To build the `jwt_auth` example we first build the common image:

```shell
docker build \
  -f ./extproc/example/Dockerfile \
  --target service-callout-common-python \
  -t service-callout-common-python .
```

and then the `jwt_auth` image:

```shell
docker build \
  -f ./extproc/example/jwt_auth/Dockerfile \
  -t service-callout-jwt-example-python .
```

# L4 TCP Quick Start

Similar to L7 Quick Start, the minimal operation of this Python-based ext_proc server requires the `grpcio` python package as well as the protobuf generator tool [buf](https://buf.build/docs/introduction).

The preferred method of installation is through a virtual environment, `venv`. To set up the virtual environment run:

```shell
cd service-extensions/callouts/python
python -m venv env
source env/bin/activate
```

Then the packages can be installed with:

```shell
pip install -r requirements.txt
```

`buf` can be installed from [here](https://buf.build/docs/installation).

The network level proto library files are generated with `buf` using:

```shell
buf -v generate \
  https://github.com/envoyproxy/envoy.git#subdir=api \
  --path envoy/service/network_ext_proc/v3/network_external_processor.proto \
  --include-imports
```

> The default template file `buf.gen.yaml` will not generate `pyright` compatible proto stubs.
> If you plan to develop callouts with a similar type checker and not just build them,
> we suggest you run the command with the alternative development template using
> `--template=buf_dev.gen.yaml`:
>
> ```shell
> buf -v generate \
>  https://github.com/envoyproxy/envoy.git#subdir=api \
>  --path envoy/service/network_ext_proc/v3/network_external_processor.proto \
>  --include-imports --template=buf_dev.gen.yaml
> ```
>
> You may need to run `python -m pip uninstall ./protodef` after re-generating the proto files
> to get the linter to update.

The proto files are then installed as a local package:

```shell
python -m pip install ./protodef
```

We install the proto files as a local package to allow for absolute imports within the generated python code.

# Docker with TCP extension

The basic Docker image contains arguments for pointing to and running python modules.
For example, to build
[extproc/l4_example/basic/network_service_callout_example.py](extproc/l4_example/basic/network_service_callout_example.py) run:

``` bash
docker build \
  -f ./extproc/example/Dockerfile \
  -t service-callout-example-network \
  --build-arg proto_path=envoy/service/network_ext_proc/v3/network_external_processor.proto
  --build-arg copy_path=extproc/l4_example/basic/ \
  --build-arg run_module=network_service_callout_example .
```

`--build-arg` specifies the following:

* `copy_path`: Required files to copy to the docker image.
* `run_module`: The python module to run on startup.

The above example makes a copy of `extproc/l4_example/basic/network_service_callout_example.py`
and sets up the image to run `network_service_callout_example.py` on startup.

The image can then be run with:

``` bash
docker run -P -it --network host service-callout-example-network:latest
```
