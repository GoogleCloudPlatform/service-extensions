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

package redirect

import (
	"testing"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/google/go-cmp/cmp"
)

// TestHandleRequestHeaders tests the HandleRequestHeaders method to ensure it correctly processes
// HTTP request headers and returns an immediate response with a 301 status code and a Location header.
func TestHandleRequestHeaders(t *testing.T) {
	// Create an instance of ExampleCalloutService.
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders request.
	headers := &extproc.HttpHeaders{}

	// Call the HandleRequestHeaders method.
	response, err := service.HandleRequestHeaders(headers)

	// Check if any error occurred.
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	// Check if the response is not nil.
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Check if the immediate response status code is 301.
	statusCode := response.GetImmediateResponse().GetStatus().GetCode()
	if diff := cmp.Diff(statusCode, typev3.StatusCode(301)); diff != "" {
		t.Errorf("Unexpected status code mismatch (-want +got):\n%s", diff)
	}

	// Check if the response contains the correct header.
	headersMutation := response.GetImmediateResponse().GetHeaders().GetSetHeaders()
	if len(headersMutation) == 0 {
		t.Fatalf("HandleRequestHeaders(): no headers found in response")
	}

	locationHeader := headersMutation[0]

	expectedKey := "Location"
	expectedValue := "http://service-extensions.com/redirect"

	if diff := cmp.Diff(locationHeader.GetHeader().GetKey(), expectedKey); diff != "" {
		t.Errorf("Unexpected header key mismatch (-want +got):\n%s", diff)
	}

	if diff := cmp.Diff(string(locationHeader.GetHeader().GetRawValue()), expectedValue); diff != "" {
		t.Errorf("Unexpected header value mismatch (-want +got):\n%s", diff)
	}
}
