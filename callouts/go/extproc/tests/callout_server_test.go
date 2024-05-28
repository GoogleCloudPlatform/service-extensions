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
	"service-extensions-samples/extproc/examples/basic_callout_server"
	"service-extensions-samples/extproc/internal/server"
	"testing"
	"time"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
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

func TestBasicServerCapabilities(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := basic_callout_server.NewExampleCalloutService()

	// Create a sample HttpHeaders and HttpBody request
	body := &extproc.HttpBody{}
	headers := &extproc.HttpHeaders{}

	// Call the Headers Handlers
	headersRequest, err := service.HandleRequestHeaders(headers)
	headersResponse, err := service.HandleResponseHeaders(headers)

	// Call the Body Handlers
	bodyRequest, err := service.HandleRequestBody(body)
	bodyResponse, err := service.HandleResponseBody(body)

	// Assert that no error occurred
	assert.NoError(t, err)

	// Assert that the response is not nil
	assert.NotNil(t, headersRequest)
	assert.NotNil(t, headersResponse)
	assert.NotNil(t, bodyRequest)
	assert.NotNil(t, bodyResponse)

	// Assert that the response contains the correct header
	headerRequestValue := headersRequest.GetRequestHeaders().Response.GetHeaderMutation().GetSetHeaders()[0]
	assert.Equal(t, "header-request", headerRequestValue.GetHeader().GetKey())
	assert.Equal(t, "", headerRequestValue.GetHeader().GetValue())

	// Assert that the response contains the correct header
	headerResponseValue := headersResponse.GetResponseHeaders().Response.GetHeaderMutation().GetSetHeaders()[0]
	assert.Equal(t, "header-response", headerResponseValue.GetHeader().GetKey())
	assert.Equal(t, "", headerResponseValue.GetHeader().GetValue())

	// Assert that the response contains the correct body
	bodyRequestValue := bodyRequest.GetRequestBody().GetResponse()
	assert.Equal(t, "new-body-request", string(bodyRequestValue.GetBodyMutation().GetBody()))

	// Assert that the response contains the correct body
	bodyResponseValue := bodyResponse.GetResponseBody().GetResponse()
	assert.Equal(t, "new-body-response", string(bodyResponseValue.GetBodyMutation().GetBody()))
}
