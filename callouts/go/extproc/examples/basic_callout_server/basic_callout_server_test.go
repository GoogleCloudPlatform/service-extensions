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

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
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

	wantHeadersRequest := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*core.HeaderValueOption{
							{
								Header: &core.HeaderValue{
									Key:      "header-request",
									RawValue: []byte("Value-request"),
								},
							},
						},
					},
				},
			},
		},
	}

	wantHeadersResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*core.HeaderValueOption{
							{
								Header: &core.HeaderValue{
									Key:      "header-response",
									RawValue: []byte("Value-response"),
								},
							},
						},
					},
				},
			},
		},
	}

	wantBodyRequest := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					BodyMutation: &extproc.BodyMutation{
						Mutation: &extproc.BodyMutation_Body{
							Body: []byte("new-body-request"),
						},
					},
				},
			},
		},
	}

	wantBodyResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					BodyMutation: &extproc.BodyMutation{
						Mutation: &extproc.BodyMutation_Body{
							Body: []byte("new-body-response"),
						},
					},
				},
			},
		},
	}

	// Compare the entire proto messages for headers request
	if diff := cmp.Diff(headersRequest, wantHeadersRequest, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}

	// Compare the entire proto messages for headers response
	if diff := cmp.Diff(headersResponse, wantHeadersResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseHeaders() mismatch (-want +got):\n%s", diff)
	}

	// Compare the entire proto messages for body request
	if diff := cmp.Diff(bodyRequest, wantBodyRequest, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestBody() mismatch (-want +got):\n%s", diff)
	}

	// Compare the entire proto messages for body response
	if diff := cmp.Diff(bodyResponse, wantBodyResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseBody() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleRequestHeaders tests handling of various HttpHeaders request scenarios.
func TestHandleRequestHeaders(t *testing.T) {
	// Define test cases
	tests := []struct {
		name    string
		headers *extproc.HttpHeaders
	}{
		{
			name:    "Empty Request Headers",
			headers: &extproc.HttpHeaders{},
		},
		{
			name:    "Missing Fields in Request Headers",
			headers: &extproc.HttpHeaders{Headers: nil},
		},
	}

	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Call the HandleRequestHeaders method
			response, err := service.HandleRequestHeaders(tt.headers)
			if err != nil {
				t.Fatalf("HandleRequestHeaders got err: %v", err)
			}
			if response == nil {
				t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
			}
		})
	}
}

// TestHandleRequestBody tests handling of various HttpBody request scenarios.
func TestHandleRequestBody(t *testing.T) {
	// Define test cases
	tests := []struct {
		name string
		body *extproc.HttpBody
	}{
		{
			name: "Empty Request Body",
			body: &extproc.HttpBody{},
		},
		{
			name: "Missing Fields in Request Body",
			body: &extproc.HttpBody{Body: nil},
		},
	}

	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Call the HandleRequestBody method
			response, err := service.HandleRequestBody(tt.body)
			if err != nil {
				t.Fatalf("HandleRequestBody got err: %v", err)
			}
			if response == nil {
				t.Fatalf("HandleRequestBody(): got nil resp, want non-nil")
			}
		})
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
