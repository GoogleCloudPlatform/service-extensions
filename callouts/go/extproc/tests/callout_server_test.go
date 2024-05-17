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

package tests

import (
	"net/http"
	"testing"
	"time"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	server "service-extensions-samples/extproc/service"
)

type MockExternalProcessorServer struct {
	extproc.UnimplementedExternalProcessorServer
	mock.Mock
}

func TestNewCalloutServer(t *testing.T) {
	config := DefaultConfig()

	calloutServer := server.NewCalloutServer(config)
	assert.NotNil(t, calloutServer)
	assert.Equal(t, config, calloutServer.Config)
}

func TestStartGRPC(t *testing.T) {
	config := DefaultConfig()

	calloutServer := server.NewCalloutServer(config)
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
	assert.NoError(t, err)
	defer func(conn *grpc.ClientConn) {
		err := conn.Close()
		if err != nil {
			t.Errorf("Failed to close connection: %v", err)
		}
	}(conn)
}

func TestStartInsecureGRPC(t *testing.T) {
	config := InsecureConfig()

	calloutServer := server.NewCalloutServer(config)
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
	assert.NoError(t, err)
	defer func(conn *grpc.ClientConn) {
		err := conn.Close()
		if err != nil {
			t.Errorf("Failed to close connection: %v", err)
		}
	}(conn)
}

func TestStartHealthCheck(t *testing.T) {
	config := DefaultConfig()

	calloutServer := server.NewCalloutServer(config)

	go func() {
		defer func() {
			if r := recover(); r != nil {
				t.Errorf("Panic recovered: %v", r)
			}
		}()
		calloutServer.StartHealthCheck()
	}()

	time.Sleep(1 * time.Second)

	resp, err := http.Get("http://0.0.0.0:8000")
	assert.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
}
