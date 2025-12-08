# Service Extensions Samples (C++)

This repository contains samples for service extensions using gRPC external
processing in C++. It demonstrates how to set up and run different examples
dynamically using Docker and Docker Compose.

## Copyrights and Licenses

Files using Copyright 2025 Google LLC & Apache License Version 2.0:

* [callout_server.h](./service/callout_server.h)
* [main.cc](./service/main.cc)
* [examples](./examples)

## Requirements

* Clang
* Bazel
* Docker
* Docker Compose

## Quick Start

The minimal operation of this C++ based ext_proc server requires Bazel, Clang and Docker.

### Running Without Docker

You can run the examples directly with Bazel and Clang without using Docker.

### Install Clang

#### For Linux

```sh
sudo apt-get install clang
```

#### For macOS

```
brew install llvm
```

### Install Bazel

The recommended way to install Bazel is from the
[Bazelisk](https://bazel.build/install/bazelisk#installing_bazel) which can manage different Bazel
versions.


### Verify Installation

```
clang --version
bazel --version
docker --version
```

### Set Environment Variable

Set the `EXAMPLE_TYPE` environment variable to the example you want to build and run (e.g `basic`).

#### For Linux/macOS

```sh
export EXAMPLE_TYPE=basic
```

#### For Windows (Command Prompt)

```sh
set EXAMPLE_TYPE=basic
```

#### For Windows (PowerShell)

```sh
$env:EXAMPLE_TYPE="basic"
```

### Build the application

Make sure you have Clang installed and then download and build the dependencies:

>**Note**: Given that on the C++ environment the dependencies should be compiled before linked,
the compiling process may take a while in the first time.

```sh
bazel build --config=clang //examples/${EXAMPLE_TYPE}:custom_callout_server_cpp
```

## Run the Application

```sh
./bazel-bin/examples/${EXAMPLE_TYPE}/custom_callout_server_cpp
```

## Building and Running the Examples with Docker

You can run different examples by setting the `EXAMPLE_TYPE` environment variable and
using Docker Compose.

### Building Basic Example

Running from the [./config](./config)

```sh
EXAMPLE_TYPE=basic docker-compose build
```

### Running Basic Example

Running from the [./config](./config)

```sh
EXAMPLE_TYPE=basic docker-compose up
```

## Running the without Docker

### Set Example Type:

```
export EXAMPLE_TYPE=basic  # Options: basic, jwt_auth, redirect
```

### Build and Run:

```
bazel build --config=clang //examples/${EXAMPLE_TYPE}:custom_callout_server_cpp
./bazel-bin/examples/${EXAMPLE_TYPE}/custom_callout_server_cpp
```

## Running Tests

To run the unit tests, use the following command from the project root:

```sh
bazel test --test_summary=detailed --config=clang //...
```

## Runtime Configuration

Configure the server using these command line flags:

```sh
./custom_callout_server_cpp \
  --server_address=0.0.0.0:443 \      # Secure endpoint (default: 0.0.0.0:443)
  --plaintext_address=0.0.0.0:8080 \  # Plaintext endpoint (default: 0.0.0.0:8080)
  --enable_plaintext=true \           # Whether to enable plaintext gRPC server (default: true)
  --enable_tls=false \                # Whether to enable secure TLS gRPC server (default: false)
  --health_check_port=80 \            # Health check port (default: 80)
  --key_path=/path/to/key.pem \       # SSL private key (default: ssl_creds/privatekey.pem)
  --cert_path=/path/to/cert.pem       # SSL certificate (default: ssl_creds/chain.pem)
```

> **Note**: TLS is disabled by default. To enable TLS, set `--enable_tls=true`.
> For production environments, it is strongly recommended to enable TLS to ensure secure communication.

### Custom Ports and SSL

```
docker run -p 443:443 -p 8080:8080 \
  -e SERVER_ADDRESS=0.0.0.0:443 \
  -v /path/to/ssl:/ssl_creds \
  service-callout-cpp:${EXAMPLE_TYPE}
```

## Developing Callouts

This repository provides the following files to be extended to fit the needs of the user:

[CalloutServer](./service/callout_server.h): Baseline service callout server with dual endpoints (secure/insecure) and health check service.

### Making a New Server

The provided `CalloutServer` class implements the `ExternalProcessor::Service` interface with:
- Insecure (plaintext) endpoint on port 8080 (enabled by default)
- Secure (TLS) endpoint on port 443 (disabled by default, enable with `--enable_tls=true`)
- HTTP health check on port 80
- Configurable via command line flags

### Extend the CalloutServer

To create your custom server, create a new class that inherits from `CalloutServer`.
This allows you to leverage the existing infrastructure for handling gRPC
communication and request processing.  The example below demonstrates this.

```c++
#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "service/callout_server.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

class CustomCalloutServer : public CalloutServer {
public:
  // ... overridden methods ...
};
```

### Override the callback methods

The `CalloutServer` class provides virtual callback methods for different
stages of the _request/response_ lifecycle:
`OnRequestHeader`, `OnResponseHeader`, `OnRequestBody`, and `OnResponseBody`.
Override these methods in your custom class to implement your specific logic
like in the example below.

```c++
// ... your CalloutServer class OnRequestHeader method implementation ...
void OnRequestHeader(ProcessingRequest* request,
                     ProcessingResponse* response) {
  CalloutServer::AddRequestHeader(response, "your-header-key",
                                  "your-header-value");
}
// ...
```

### Run the Server

The server automatically handles:
- Dual gRPC endpoints (secure/insecure)
- Health check service
- Command line configuration

Example minimal setup:
```c++
auto config = CalloutServer::DefaultConfig();
CalloutServer::RunServers(config);
```

An example of how this file can be used together with your custom service
implementation can be found in this bazel [BUILD](./examples/basic/BUILD) file
from the _basic_ example. Where it uses _bazel_ build to link this common core
file during the build process, avoiding code duplication.

## Using the Proto Files

The provided code and this example rely on the Envoy External Processor proto definitions.
These definitions can be found on the [external_processor.proto](https://github.com/envoyproxy/data-plane-api/blob/main/envoy/service/ext_proc/v3/external_processor.proto).

This file defines the structure of the messages exchanged between Envoy and
your external processor. Consult the Envoy documentation for details on how
to generate these files from the `.proto` definitions.
