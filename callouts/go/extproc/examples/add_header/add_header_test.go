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

package add_header

import (
	"testing"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/assert"
)

func TestHandleRequestHeadersAddHeader(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders request
	headers := &extproc.HttpHeaders{}

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)

	// Assert that no error occurred
	assert.NoError(t, err)

	// Assert that the response is not nil
	assert.NotNil(t, response)

	// Assert that the response contains the correct header
	headerValue := response.GetRequestHeaders().Response.GetHeaderMutation().GetSetHeaders()[0]
	assert.Equal(t, "header-request", headerValue.GetHeader().GetKey())
	assert.Equal(t, "", headerValue.GetHeader().GetValue())
}

func TestHandleResponseHeadersAddHeader(t *testing.T) {
	// Create an instance of ExampleCalloutService
	service := NewExampleCalloutService()

	// Create a sample HttpHeaders response
	headers := &extproc.HttpHeaders{}

	// Call the HandleResponseHeaders method
	response, err := service.HandleResponseHeaders(headers)

	// Assert that no error occurred
	assert.NoError(t, err)

	// Assert that the response is not nil
	assert.NotNil(t, response)

	// Assert that the response contains the correct header
	headerValue := response.GetResponseHeaders().Response.GetHeaderMutation().GetSetHeaders()[0]
	assert.Equal(t, "header-response", headerValue.GetHeader().GetKey())
	assert.Equal(t, "", headerValue.GetHeader().GetValue())
}
