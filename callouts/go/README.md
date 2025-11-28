# Service Extensions Samples (Go)

This repository contains samples for service extensions using gRPC external processing in Go. It demonstrates how to set up and run different examples dynamically using Docker and Docker Compose.

## Copyrights and Licenses

Files using Copyright 2024 Google LLC & Apache License Version 2.0:
* [callout_server.go](./extproc/internal/server/callout_server.go)
* [callout_tools.go](./extproc/pkg/utils/callout_tools.go)

## Requirements

* Go 1.23+
* Docker
* Docker Compose

## Quick Start

The minimal operation of this Go-based ext_proc server requires Go and Docker.

### Running Without Docker

You can run the examples directly with Go without using Docker.

### Install Dependencies

Make sure you have Go installed and then download the dependencies:

```sh
go mod download
```
### Set Environment Variable

Set the EXAMPLE_TYPE environment variable to the example you want to run (e.g ``redirect``).

#### For Linux/macOS:

```sh
export EXAMPLE_TYPE=redirect
```
#### For Windows (Command Prompt):

```sh
set EXAMPLE_TYPE=redirect
```

#### For Windows (PowerShell):

```sh
$env:EXAMPLE_TYPE="redirect"
```

## Run the Application:

#### Run the main Go file:

```sh
go run ./extproc/cmd/example/main.go
```

## Building and Running the Examples with Docker
You can run different examples by setting the EXAMPLE_TYPE environment variable and using Docker Compose.

### Building Redirect Example
Running from the ./extproc/config/
```sh
EXAMPLE_TYPE=redirect docker-compose build
```

### Running Redirect Example
Running from the ./extproc/config/
```sh
EXAMPLE_TYPE=redirect docker-compose up
```

## Running Tests
To run the unit tests, use the following command from the project root:

```sh
go test ./...
```

## Developing Callouts
This repository provides the following files to be extended to fit the needs of the user:

[CalloutServer](extproc/internal/server/callout_server.go): Baseline service callout server.

[CalloutTools](extproc/pkg/utils/callout_tools.go): Common functions used in many callout server code paths.

### Making a New Server

Create a new Go file server.go and import the ``CalloutServer`` class from extproc/internal/server/callout_server.go:

```go
import (
    "service-extensions/extproc/internal/server"
)
```
### Extend the CalloutServer:

Create a custom class extending ``CalloutServer``:

```go
type CustomCalloutServer struct {
    server.GRPCCalloutService
}
```

Add the handler you are going to override for your custom processing  (e.g: Request Headers):
```go

func NewExampleCalloutService() *CustomCalloutServer {
    service := &CustomCalloutServer{}
    service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
    return service
}
```
### Override the callback methods:

Override the callback methods in ``CalloutServer`` to process headers and bodies:

```go
func (s *CustomCalloutServer) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
    // Custom processing logic
    return &extproc.ProcessingResponse{}, nil
}
```

### Run the Server:

Create an instance of your custom server and call the run method:

```go
func main() {
    server := &CustomCalloutServer{}
    calloutServer := service.NewCalloutServer(config)
    go calloutServer.StartGRPC(server)
    go calloutServer.StartInsecureGRPC(server)
    go calloutServer.StartHealthCheck()

    select {}
}
```
## Additional Details
The ``CalloutServer`` class has many options to customize the security information as well as port settings. The default CalloutServer listens on port 8080 for plaintext traffic and 80 for health checks.

TLS is disabled by default. To enable TLS, set ``EnableTLS`` to ``true`` in the ``Config`` struct.
When enabled, the secure server listens on port 443 by default.

> For production environments, it is strongly recommended to enable TLS to ensure secure communication.

## Using the Proto Files
The Go classes can be imported using the relative envoy/api path:

```go
import (
    "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)
```
