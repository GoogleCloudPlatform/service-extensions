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

package waf_server

import (
	"testing"

	extprocconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

// TestHandleRequestHeadersStreaming tests the streaming configuration in RequestHeaders
func TestHandleRequestHeadersStreaming(t *testing.T) {
	// Create an instance of FirewallCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders request
	headers := &extproc.HttpHeaders{}

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Define the expected response
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{},
			},
		},
		ModeOverride: &extprocconfig.ProcessingMode{
			RequestBodyMode: extprocconfig.ProcessingMode_STREAMED,
		},
	}

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleRequestBodyClean tests handling of clean request bodies
func TestHandleRequestBodyClean(t *testing.T) {
	service := NewExampleCalloutService()

	body := &extproc.HttpBody{
		Body: []byte("This is clean content"),
	}

	response, err := service.HandleRequestBody(body)

	if err != nil {
		t.Errorf("HandleRequestBody got err: %v", err)
	}

	// Expect normal processing response for clean content
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{},
			},
		},
	}

	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestBody() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleRequestBodyMalicious tests blocking of malicious request bodies
func TestHandleRequestBodyMalicious(t *testing.T) {
	service := NewExampleCalloutService()

	body := &extproc.HttpBody{
		Body: []byte("This contains MALICIOUS_CONTENT that should be blocked"),
	}

	response, err := service.HandleRequestBody(body)

	if err != nil {
		t.Errorf("HandleRequestBody got err: %v", err)
	}

	// Expect blocking immediate response
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: &extproc.ImmediateResponse{
				Status: &typev3.HttpStatus{
					Code: typev3.StatusCode_Forbidden,
				},
				Body: "Blocked: Detected MALICIOUS_CONTENT",
			},
		},
	}

	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestBody() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleResponseHeadersStreaming tests the streaming configuration in ResponseHeaders
func TestHandleResponseHeadersStreaming(t *testing.T) {
	// Create an instance of FirewallCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders response
	headers := &extproc.HttpHeaders{}

	// Call the HandleResponseHeaders method
	response, err := service.HandleResponseHeaders(headers)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleResponseHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleResponseHeaders(): got nil resp, want non-nil")
	}

	// Define the expected response
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{},
			},
		},
		ModeOverride: &extprocconfig.ProcessingMode{
			ResponseBodyMode: extprocconfig.ProcessingMode_STREAMED,
		},
	}

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseHeaders() mismatch (-want +got):\n%s", diff)
	}
}
