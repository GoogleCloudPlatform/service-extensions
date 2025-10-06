// Copyright 2025 Google LLC.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
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

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extauthz/examples/block_ip"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extauthz/internal/server"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
)

// ExampleService defines the interface that all example services must implement.
type ExampleService interface {
	auth.AuthorizationServer
}

func main() {
	exampleType := os.Getenv("EXAMPLE_TYPE")

	var customService ExampleService

	switch exampleType {
	case "block_ip":
		customService = block_ip.NewCalloutServerExample()
	default:
		fmt.Println("Unknown EXAMPLE_TYPE. Please set it to a valid example")
		return
	}

	config := server.Config{
		Address:            "0.0.0.0:443",
		InsecureAddress:    "0.0.0.0:8080",
		HealthCheckAddress: "0.0.0.0:80",
		CertFile:           "ssl_creds/localhost.crt",
		KeyFile:            "ssl_creds/localhost.key",
	}

	calloutServer := server.NewCalloutServer(config)

	// Start servers in goroutines
	go calloutServer.StartGRPC(customService)
	go calloutServer.StartInsecureGRPC(customService)
	go calloutServer.StartHealthCheck()

	fmt.Printf("Started extauthz callout server with example: %s\n", exampleType)
	fmt.Println("Secure gRPC server listening on :443")
	fmt.Println("Insecure gRPC server listening on :8080")
	fmt.Println("Health check server listening on :80")

	// Block forever or handle signals as needed
	select {}
}
