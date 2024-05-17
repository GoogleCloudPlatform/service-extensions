# Service Extensions Samples (Go)

This repository contains sample service extensions using gRPC external processing in Go. It demonstrates how to set up and run different examples dynamically using Docker and Docker Compose.

## Copyrights and Licenses

Files using Copyright 2024 Google LLC & Apache License Version 2.0:
* [callout_server.go](./extproc/service/callout_server.go)
* [callout_tools.go](./extproc/utils/callout_tools.go)

## Requirements

* Go 1.22+
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

Set the EXAMPLE_TYPE environment variable to the example you want to run (redirect or another_example).

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
go run ./extproc/example/main.go
```
   
## Building and Running the Examples with Docker
You can run different examples by setting the EXAMPLE_TYPE environment variable and using Docker Compose.

### Building and Running the Redirect Example
```sh
docker-compose up --build redirect
```

### Building and Running Another Example
```sh
docker-compose up --build another_example
```

### Available Examples

#### Redirect Example (redirect)

This example demonstrates how to handle request headers and issue a redirect.
Defined in extproc/example/redirect/service_callout_example.go.

#### Another Example (another_example)

This example shows another type of request handling with a different redirect URL.
Defined in extproc/example/another_example/service_callout_example.go.

## Running Tests
To run the unit tests, use the following command from the project root:

```sh
go test ./...
```

## Developing Callouts
This repository provides the following files to be extended to fit the needs of the user:

[CalloutServer](extproc/service/callout_server.go): Baseline service callout server.

[CalloutTools](extproc/utils/callout_tools.go): Common functions used in many callout server code paths.

### Making a New Server

Create a new Go file server.go and import the CalloutServer class from extproc/service/callout_server.go:

```go
import (
    "service-extensions-samples/extproc/service"
)
```
### Extend the CalloutServer:

Create a custom class extending CalloutServer:

```go
type CustomCalloutServer struct {
    service.GRPCCalloutService
}
```
### Override the callback methods:

Override the callback methods in CalloutServer to process headers and bodies:

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
The CalloutServer class has many options to customize the security information as well as port settings. The default CalloutServer listens on port 8443 for gRPC traffic, 8000 for health checks, and 8080 for insecure traffic. Please see the CalloutServer docstring for more information.

## Using the Proto Files
The Go classes can be imported using the relative envoy/api path:

```go
import (
    "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)
```

# Docker
## Quickstart
The basic Docker image contains arguments for building and running Go modules. For example, to build and run the RedirectCalloutService:

```sh
docker-compose up --build redirect
```