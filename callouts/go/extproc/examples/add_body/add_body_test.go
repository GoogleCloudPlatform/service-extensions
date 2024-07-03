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

package add_body

import (
	"testing"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

// TestHandleRequestBody tests the HandleRequestBody method of ExampleCalloutService.
func TestHandleRequestBody(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpBody request
	body := &extproc.HttpBody{}

	// Call the HandleRequestBody method
	response, err := service.HandleRequestBody(body)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleRequestBody got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleRequestBody(): got nil resp, want non-nil")
	}

	// Define the expected response
	wantResponse := &extproc.ProcessingResponse{
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

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestBody() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleResponseBody tests the HandleResponseBody method of ExampleCalloutService.
func TestHandleResponseBody(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpBody request
	body := &extproc.HttpBody{}

	// Call the HandleResponseBody method
	response, err := service.HandleResponseBody(body)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleResponseBody got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleResponseBody(): got nil resp, want non-nil")
	}

	// Define the expected response
	wantResponse := &extproc.ProcessingResponse{
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

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseBody() mismatch (-want +got):\n%s", diff)
	}
}
