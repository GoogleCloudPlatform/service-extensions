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

package dynamic_forwarding

import (
	"testing"

	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	structpb "google.golang.org/protobuf/types/known/structpb"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

// TestHandleRequestHeaders_deafultEndpoint tests the HandleRequestHeaders method of ExampleCalloutService for adding dynamic metadata.
func TestHandleRequestHeaders_defaultEndpoint(t *testing.T) {
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
	expectedDynamicMetadata, err := structpb.NewStruct(map[string]any{
		"com.google.envoy.dynamic_forwarding.selected_endpoints": map[string]any{
			"primary": "10.1.10.3:80",
                },
	})

	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
		DynamicMetadata: expectedDynamicMetadata,
	}

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}
}


// TestHandleRequestHeaders_endpointInHeader tests the HandleRequestHeaders method of ExampleCalloutService for adding dynamic metadata.
func TestHandleRequestHeaders_endpointInHeader(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders request
	headers := &extproc.HttpHeaders{
		Headers: &base.HeaderMap{
			Headers: []*base.HeaderValue{
				{
					Key:      "ip-to-return",
					RawValue: []byte("10.1.10.10"),
				},
			},
		},
	}
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
	expectedDynamicMetadata, err := structpb.NewStruct(map[string]any{
		"com.google.envoy.dynamic_forwarding.selected_endpoints": map[string]any{
			"primary": "10.1.10.10:80",
                },
	})

	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
		DynamicMetadata: expectedDynamicMetadata,
	}

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}
}
