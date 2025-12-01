// Copyright 2024 Google LLC.
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

package server

import (
	"fmt"
	"net/http"
	"testing"
	"time"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/mock"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
)

// MockExternalProcessorServer is a mock implementation of the ExternalProcessorServer.
type MockExternalProcessorServer struct {
	extproc.UnimplementedExternalProcessorServer
	mock.Mock
}

// NewCalloutServerTestConfig returns a configuration for TestNewCalloutServer.
func NewCalloutServerTestConfig() Config {
	return Config{
		InsecureAddress:      "0.0.0.0:18181",
		HealthCheckAddress:   "0.0.0.0:18000",
		EnableInsecureServer: true,
		EnableTLS:            false,
	}
}

// StartGRPCTestConfig returns a configuration for TestStartGRPC.
func StartGRPCTestConfig() Config {
	return Config{
		Address:            "0.0.0.0:18443",
		InsecureAddress:    "0.0.0.0:18182",
		HealthCheckAddress: "0.0.0.0:18001",
		CertFile:           "../../ssl_creds/localhost.crt",
		KeyFile:            "../../ssl_creds/localhost.key",
		EnableTLS:          true,
	}
}

// StartInsecureGRPCTestConfig returns a configuration for TestStartInsecureGRPC.
func StartInsecureGRPCTestConfig() Config {
	return Config{
		InsecureAddress:      "0.0.0.0:18183",
		HealthCheckAddress:   "0.0.0.0:18002",
		EnableInsecureServer: true,
	}
}

// StartHealthCheckTestConfig returns a configuration for TestStartHealthCheck.
func StartHealthCheckTestConfig() Config {
	return Config{
		InsecureAddress:      "0.0.0.0:18184",
		HealthCheckAddress:   "0.0.0.0:18003",
		EnableInsecureServer: true,
	}
}

// TestNewCalloutServer tests the creation of a new callout server with a basic configuration.
func TestNewCalloutServer(t *testing.T) {
	config := NewCalloutServerTestConfig()

	calloutServer := NewCalloutServer(config)
	if calloutServer == nil {
		t.Fatalf("NewCalloutServer() = nil, want non-nil")
	}
	if calloutServer.Config != config {
		t.Errorf("NewCalloutServer() config = %v, want %v", calloutServer.Config, config)
	}
}

// TestStartGRPC tests the start of the gRPC server with TLS.
func TestStartGRPC(t *testing.T) {
	config := StartGRPCTestConfig()

	// Skip this test if TLS certificates are not available
	if config.CertFile == "" || config.KeyFile == "" {
		t.Skip("Skipping TLS test: certificates not configured")
	}

	calloutServer := NewCalloutServer(config)
	mockService := &MockExternalProcessorServer{}

	go func() {
		defer func() {
			if r := recover(); r != nil {
				t.Errorf("Panic recovered: %v", r)
			}
		}()
		calloutServer.StartGRPC(mockService)
	}()

	time.Sleep(1 * time.Second)

	conn, err := grpc.Dial(config.Address, grpc.WithTransportCredentials(credentials.NewClientTLSFromCert(nil, "")))
	if err != nil {
		t.Fatalf("Failed to dial: %v", err)
	}
	defer func(conn *grpc.ClientConn) {
		err := conn.Close()
		if err != nil {
			t.Errorf("Failed to close connection: %v", err)
		}
	}(conn)
}

// TestStartInsecureGRPC tests the start of the insecure gRPC server.
func TestStartInsecureGRPC(t *testing.T) {
	config := StartInsecureGRPCTestConfig()

	calloutServer := NewCalloutServer(config)
	mockService := &MockExternalProcessorServer{}

	go func() {
		defer func() {
			if r := recover(); r != nil {
				t.Errorf("Panic recovered: %v", r)
			}
		}()
		calloutServer.StartInsecureGRPC(mockService)
	}()

	time.Sleep(1 * time.Second)

	conn, err := grpc.Dial(config.InsecureAddress, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("Failed to dial: %v", err)
	}
	defer func(conn *grpc.ClientConn) {
		err := conn.Close()
		if err != nil {
			t.Errorf("Failed to close connection: %v", err)
		}
	}(conn)
}

// TestStartHealthCheck tests the start of the health check server.
func TestStartHealthCheck(t *testing.T) {
	config := StartHealthCheckTestConfig()

	calloutServer := NewCalloutServer(config)

	go calloutServer.StartHealthCheck()

	time.Sleep(time.Second)

	resp, err := http.Get(fmt.Sprintf("http://%s", config.HealthCheckAddress))
	if err != nil {
		t.Fatalf("Failed to get health check: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Health check status = %v, want %v", resp.StatusCode, http.StatusOK)
	}
}
