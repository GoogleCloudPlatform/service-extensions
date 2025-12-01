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

// DefaultConfig returns a default server configuration.
func DefaultConfig() Config {
	return Config{
		Address:            "0.0.0.0:8443",
		InsecureAddress:    "0.0.0.0:8181",
		HealthCheckAddress: "0.0.0.0:8000",
		CertFile:           "../../ssl_creds/localhost.crt",
		KeyFile:            "../../ssl_creds/localhost.key",
		EnableTLS:          true,
	}
}

// InsecureConfig returns a configuration with only the insecure address set.
func InsecureConfig() Config {
	return Config{
		InsecureAddress:      "0.0.0.0:8181",
		HealthCheckAddress:   "0.0.0.0:8000",
		EnableInsecureServer: true,
	}
}

// TestNewCalloutServer tests the creation of a new callout server with a basic configuration.
func TestNewCalloutServer(t *testing.T) {
	// Use a config without TLS to avoid requiring certificates
	config := Config{
		InsecureAddress:      "0.0.0.0:8181",
		HealthCheckAddress:   "0.0.0.0:8000",
		EnableInsecureServer: true,
		EnableTLS:            false,
	}

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
	// Skip this test if TLS certificates are not available
	config := DefaultConfig()
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
	config := InsecureConfig()

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
	config := DefaultConfig()

	calloutServer := NewCalloutServer(config)

	go calloutServer.StartHealthCheck()

	time.Sleep(time.Second)

	resp, err := http.Get("http://0.0.0.0:8000")
	if err != nil {
		t.Fatalf("Failed to get health check: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Health check status = %v, want %v", resp.StatusCode, http.StatusOK)
	}
}
