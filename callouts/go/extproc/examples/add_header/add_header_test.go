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

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
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

	// Check if the response contains the correct header
	headerMutation := response.GetRequestHeaders().GetResponse().GetHeaderMutation()
	if headerMutation == nil || len(headerMutation.GetSetHeaders()) == 0 {
		t.Fatalf("HandleRequestHeaders(): got nil or empty HeaderMutation")
	}

	expectedKey := "header-request"
	expectedValue := "Value-request"
	headerValue := headerMutation.GetSetHeaders()[0]

	if diff := cmp.Diff(headerValue.GetHeader().GetKey(), expectedKey); diff != "" {
		t.Errorf("Unexpected header key mismatch (-want +got):\n%s", diff)
	}

	if diff := cmp.Diff(string(headerValue.GetHeader().GetRawValue()), expectedValue); diff != "" {
		t.Errorf("Unexpected header value mismatch (-want +got):\n%s", diff)
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

	// Check if the response contains the correct header
	headerMutation := response.GetResponseHeaders().GetResponse().GetHeaderMutation()
	if headerMutation == nil || len(headerMutation.GetSetHeaders()) == 0 {
		t.Fatalf("HandleResponseHeaders(): got nil or empty HeaderMutation")
	}

	expectedKey := "header-response"
	expectedValue := "Value-response"
	headerValue := headerMutation.GetSetHeaders()[0]

	if diff := cmp.Diff(headerValue.GetHeader().GetKey(), expectedKey); diff != "" {
		t.Errorf("Unexpected header key mismatch (-want +got):\n%s", diff)
	}

	if diff := cmp.Diff(string(headerValue.GetHeader().GetRawValue()), expectedValue); diff != "" {
		t.Errorf("Unexpected header value mismatch (-want +got):\n%s", diff)
	}
}
