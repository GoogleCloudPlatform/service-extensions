// Copyright 2024 Google LLC.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"fmt"
	"os"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"service-extensions-samples/extproc/examples/add_body"
	"service-extensions-samples/extproc/examples/add_header"
	"service-extensions-samples/extproc/examples/basic_callout_server"
	"service-extensions-samples/extproc/examples/jwt_auth"
	"service-extensions-samples/extproc/examples/redirect"
	"service-extensions-samples/extproc/internal/server"
)

// ExampleService defines the interface that all example services must implement.
type ExampleService interface {
	extproc.ExternalProcessorServer
}

func main() {
	exampleType := os.Getenv("EXAMPLE_TYPE")

	var customService ExampleService

	switch exampleType {
	case "redirect":
		customService = redirect.NewExampleCalloutService()
	case "add_header":
		customService = add_header.NewExampleCalloutService()
	case "add_body":
		customService = add_body.NewExampleCalloutService()
	case "basic_callout_server":
		customService = basic_callout_server.NewExampleCalloutService()
	case "jwt_auth":
		customService = jwt_auth.NewExampleCalloutService()
	default:
		fmt.Println("Unknown EXAMPLE_TYPE. Please set it to a valid example")
		return
	}

	config := server.Config{
		Address:            "0.0.0.0:8443",
		InsecureAddress:    "0.0.0.0:8181",
		HealthCheckAddress: "0.0.0.0:8000",
		CertFile:           "extproc/ssl_creds/localhost.crt",
		KeyFile:            "extproc/ssl_creds/localhost.key",
	}

	calloutServer := server.NewCalloutServer(config)
	go calloutServer.StartGRPC(customService)
	go calloutServer.StartInsecureGRPC(customService)
	go calloutServer.StartHealthCheck()

	// Block forever or handle signals as needed
	select {}
}
