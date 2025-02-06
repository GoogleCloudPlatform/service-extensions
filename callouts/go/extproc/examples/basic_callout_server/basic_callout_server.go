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

package basic_callout_server

import (
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/pkg/utils"
)

// ExampleCalloutService is a GRPC callout service that processes HTTP headers and bodies.
type ExampleCalloutService struct {
	server.GRPCCalloutService
}

// NewExampleCalloutService creates a new ExampleCalloutService with initialized handlers.
func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.Handlers.ResponseHeadersHandler = service.HandleResponseHeaders
	service.Handlers.RequestBodyHandler = service.HandleRequestBody
	service.Handlers.ResponseBodyHandler = service.HandleResponseBody
	return service
}

// HandleRequestHeaders processes the incoming HTTP request headers and adds a new header.
func (s *ExampleCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: utils.AddHeaderMutation([]struct{ Key, Value string }{{Key: "header-request", Value: "Value-request"}}, nil, false, nil),
		},
	}, nil
}

// HandleResponseHeaders processes the outgoing HTTP response headers and adds a new header.
func (s *ExampleCalloutService) HandleResponseHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: utils.AddHeaderMutation([]struct{ Key, Value string }{{Key: "header-response", Value: "Value-response"}}, nil, false, nil),
		},
	}, nil
}

// HandleRequestBody processes the incoming HTTP request body and modifies it.
func (s *ExampleCalloutService) HandleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: utils.AddBodyStringMutation("new-body-request", false),
		},
	}, nil
}

// HandleResponseBody processes the outgoing HTTP response body and modifies it.
func (s *ExampleCalloutService) HandleResponseBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: utils.AddBodyStringMutation("new-body-response", false),
		},
	}, nil
}
