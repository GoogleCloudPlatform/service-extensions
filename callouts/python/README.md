
__Copyrights and Licences__

Files using Copyright 2023 Google LLC & Apache License Version 2.0:
* service_callout.py contains service callout server code
* test_server.py contains code to test the service_callout.py

Built off of [envoy](https://github.com/envoyproxy/envoy)
 * [External Processor Reference](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/ext_proc/v3/ext_proc.proto#envoy-v3-api-msg-extensions-filters-http-ext-proc-v3-externalprocessor)
 * [Docs](https://www.envoyproxy.io/docs/envoy/latest)
 * [API](https://www.envoyproxy.io/docs/envoy/latest/api/api)

# Quick start 

The minimal operation of this server requires the `grpcio` python package as well as the protobuf generator tool [buf](https://buf.build/docs/introduction).


The prefered method of installation is through a virtual enviornment, `venv`. To set up the virtual enviornment run:

```
python -m venv env
source env/bin activate
```

Then the packages can be installed with:

```
pip install -r requirements.txt
```

And if you want to run tests:

```
pip install -r requirements-test.txt
```

`buf` can be installed from [here](https://buf.build/docs/installation).

The proto library files are generated with `buf` using: 

```
buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path envoy/service/ext_proc/v3/external_processor.proto --include-imports
```

The proto files are then installed as a local package:

```
python -m pip install ./protodef
```

We install the proto files as a local package to allow for absolute imports within the generated python code.

## Running
Example servers can be started from the `extproc/example/<...>` submodules. 
For example the grpc `service_callout_example` server can be started with:

```
python -m extproc.example.grpc.service_callout_example
```

The server will then run until interupted, for example, by inputing `Ctrl-C`. 

# Developing Callouts

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
```
sudo apt-get install python3-grpcio -y
```

And the protobuf library with:

```
python -m pip install ./protodef
```

### WARNING!
Installing the `protodef` package to your system outside of a `venv` could cause unintentional side effects. Only do this if you are inside of a self contained enviornment or you know what you are doing.

## Without installing the proto code as a local package

Alternatively, rather than installing through pip, the proto code can be placed in the root of this project and imported directly.

```
buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path envoy/service/ext_proc/v3/external_processor.proto --include-imports -o .
```

# Tests

Tests can be run with:
```
pytest
```

# Building Docker

Because there is a lot of shared setup between images, docker files are built in two steps.
First we build the shared image:

```
docker build -f ./extproc/example/common/Dockerfile -t service-callout-common-python .
```

Then to build an example docker image, call `docker build -f <path> -t <image> .` 
where `<path>` is the path to the Dockerfile within the desired example submodule, 
and `<image>` is the desired docker image name.

For example, to build the example grpc server with image name `service-callout-example-python` run:
```
docker build -f ./extproc/example/grpc/Dockerfile -t service-callout-example-python .
```

Run the image with:

```
docker run --network host -P service-callout-example-python
```

In this example, using the `-P` flag tells docker to connect the exposed ports to the local machine's ports. 
Setting `--network host` tells docker to connect the image to the `0.0.0.0` or `localhost` ip address.
