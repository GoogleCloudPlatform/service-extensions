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

package add_body

import (
	"testing"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/assert"
)

func TestHandleRequestBody(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpBody request
	body := &extproc.HttpBody{}

	// Call the HandleRequestBody method
	response, err := service.HandleRequestBody(body)

	// Assert that no error occurred
	assert.NoError(t, err)

	// Assert that the response is not nil
	assert.NotNil(t, response)

	// Assert that the response contains the correct body
	bodyValue := response.GetRequestBody().GetResponse()
	assert.Equal(t, "new-body-request", string(bodyValue.GetBodyMutation().GetBody()))
}

func TestHandleResponseBody(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpBody request
	body := &extproc.HttpBody{}

	// Call the HandleRequestBody method
	response, err := service.HandleResponseBody(body)

	// Assert that no error occurred
	assert.NoError(t, err)

	// Assert that the response is not nil
	assert.NotNil(t, response)

	// Assert that the response contains the correct body
	bodyValue := response.GetResponseBody().GetResponse()
	assert.Equal(t, "new-body-response", string(bodyValue.GetBodyMutation().GetBody()))
}
