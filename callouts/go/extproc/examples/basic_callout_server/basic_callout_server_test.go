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

package basic_callout_server

import (
	"testing"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)

// TestBasicServerCapabilities tests the basic server capabilities of ExampleCalloutService.
func TestBasicServerCapabilities(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders and HttpBody request
	body := &extproc.HttpBody{}
	headers := &extproc.HttpHeaders{}

	// Call the Headers Handlers
	headersRequest, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}

	headersResponse, err := service.HandleResponseHeaders(headers)
	if err != nil {
		t.Fatalf("HandleResponseHeaders got err: %v", err)
	}

	// Call the Body Handlers
	bodyRequest, err := service.HandleRequestBody(body)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	bodyResponse, err := service.HandleResponseBody(body)
	if err != nil {
		t.Fatalf("HandleResponseBody got err: %v", err)
	}

	// Check if the responses are not nil
	if headersRequest == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}
	if headersResponse == nil {
		t.Fatalf("HandleResponseHeaders(): got nil resp, want non-nil")
	}
	if bodyRequest == nil {
		t.Fatalf("HandleRequestBody(): got nil resp, want non-nil")
	}
	if bodyResponse == nil {
		t.Fatalf("HandleResponseBody(): got nil resp, want non-nil")
	}

	// Check if the headersRequest contains the correct header
	headerRequestMutation := headersRequest.GetRequestHeaders().GetResponse().GetHeaderMutation()
	if headerRequestMutation == nil || len(headerRequestMutation.GetSetHeaders()) == 0 {
		t.Fatalf("HandleRequestHeaders(): header mutation is nil or empty")
	}
	headerRequestValue := headerRequestMutation.GetSetHeaders()[0]
	if got, want := headerRequestValue.GetHeader().GetKey(), "header-request"; got != want {
		t.Errorf("Unexpected header key: got %v, want %v", got, want)
	}
	if got, want := headerRequestValue.GetHeader().GetValue(), ""; got != want {
		t.Errorf("Unexpected header value: got %v, want %v", got, want)
	}

	// Check if the headersResponse contains the correct header
	headerResponseMutation := headersResponse.GetResponseHeaders().GetResponse().GetHeaderMutation()
	if headerResponseMutation == nil || len(headerResponseMutation.GetSetHeaders()) == 0 {
		t.Fatalf("HandleResponseHeaders(): header mutation is nil or empty")
	}
	headerResponseValue := headerResponseMutation.GetSetHeaders()[0]
	if got, want := headerResponseValue.GetHeader().GetKey(), "header-response"; got != want {
		t.Errorf("Unexpected header key: got %v, want %v", got, want)
	}
	if got, want := headerResponseValue.GetHeader().GetValue(), ""; got != want {
		t.Errorf("Unexpected header value: got %v, want %v", got, want)
	}

	// Check if the bodyRequest contains the correct body
	bodyRequestValue := bodyRequest.GetRequestBody().GetResponse()
	if got, want := string(bodyRequestValue.GetBodyMutation().GetBody()), "new-body-request"; got != want {
		t.Errorf("Unexpected request body: got %v, want %v", got, want)
	}

	// Check if the bodyResponse contains the correct body
	bodyResponseValue := bodyResponse.GetResponseBody().GetResponse()
	if got, want := string(bodyResponseValue.GetBodyMutation().GetBody()), "new-body-response"; got != want {
		t.Errorf("Unexpected response body: got %v, want %v", got, want)
	}
}

// TestHandleRequestHeaders_Empty tests handling of empty request headers.
func TestHandleRequestHeaders_Empty(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create an empty HttpHeaders request
	headers := &extproc.HttpHeaders{}

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}
}

// TestHandleResponseHeaders_Empty tests handling of empty response headers.
func TestHandleResponseHeaders_Empty(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create an empty HttpHeaders response
	headers := &extproc.HttpHeaders{}

	// Call the HandleResponseHeaders method
	response, err := service.HandleResponseHeaders(headers)
	if err != nil {
		t.Fatalf("HandleResponseHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleResponseHeaders(): got nil resp, want non-nil")
	}
}

// TestHandleRequestBody_Empty tests handling of an empty request body.
func TestHandleRequestBody_Empty(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create an empty HttpBody request
	body := &extproc.HttpBody{}

	// Call the HandleRequestBody method
	response, err := service.HandleRequestBody(body)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestBody(): got nil resp, want non-nil")
	}
}

// TestHandleResponseBody_Empty tests handling of an empty response body.
func TestHandleResponseBody_Empty(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create an empty HttpBody response
	body := &extproc.HttpBody{}

	// Call the HandleResponseBody method
	response, err := service.HandleResponseBody(body)
	if err != nil {
		t.Fatalf("HandleResponseBody got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleResponseBody(): got nil resp, want non-nil")
	}
}

// TestHandleRequestHeaders_MissingFields tests handling of request headers with missing fields.
func TestHandleRequestHeaders_MissingFields(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a HttpHeaders request with missing fields
	headers := &extproc.HttpHeaders{
		Headers: nil, // Missing Headers
	}

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}
}

// TestHandleRequestBody_MissingFields tests handling of a request body with missing fields.
func TestHandleRequestBody_MissingFields(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a HttpBody request with missing fields
	body := &extproc.HttpBody{
		Body: nil, // Missing Body
	}

	// Call the HandleRequestBody method
	response, err := service.HandleRequestBody(body)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestBody(): got nil resp, want non-nil")
	}
}
