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

package redirect

import (
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"testing"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/stretchr/testify/assert"
)

func TestHandleRequestHeaders(t *testing.T) {
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

	// Assert that the immediate response status code is 301
	assert.Equal(t, typev3.StatusCode(301), response.GetImmediateResponse().GetStatus().GetCode())

	// Assert that the response contains the correct header
	locationHeader := response.GetImmediateResponse().GetHeaders().GetSetHeaders()[0]
	assert.Equal(t, "Location", locationHeader.GetHeader().GetKey())
	assert.Equal(t, "http://service-extensions.com/redirect", locationHeader.GetHeader().GetValue())
}
