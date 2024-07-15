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

package add_header

import (
	"testing"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

// TestHandleRequestHeadersAddHeader tests the HandleRequestHeaders method of ExampleCalloutService for adding headers.
func TestHandleRequestHeadersAddHeader(t *testing.T) {
	// Create an instance of ExampleCalloutService
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

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleResponseHeadersAddHeader tests the HandleResponseHeaders method of ExampleCalloutService for adding headers.
func TestHandleResponseHeadersAddHeader(t *testing.T) {
	// Create an instance of ExampleCalloutService
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

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseHeaders() mismatch (-want +got):\n%s", diff)
	}
}
