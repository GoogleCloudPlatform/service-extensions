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
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"

	"service-extensions-samples/extproc/internal/server"
	"service-extensions-samples/extproc/pkg/utils"
)

// ExampleCalloutService represents the callout service used to handle
// HTTP request headers and provide an immediate redirection response.
type ExampleCalloutService struct {
	server.GRPCCalloutService
}

// NewExampleCalloutService creates a new instance of ExampleCalloutService
// and assigns the HandleRequestHeaders method to the RequestHeadersHandler.
func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	return service
}

// HandleRequestHeaders handles the HTTP request headers and returns a
// ProcessingResponse with an immediate redirection response.
func (s *ExampleCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: utils.HeaderImmediateResponse(301, []struct{ Key, Value string }{{Key: "Location", Value: "http://service-extensions.com/redirect"}}, nil),
		},
	}, nil
}
