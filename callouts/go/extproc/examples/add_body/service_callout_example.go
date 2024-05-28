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
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"service-extensions-samples/extproc/internal/server"
	"service-extensions-samples/extproc/pkg/utils"
)

type ExampleCalloutService struct {
	server.GRPCCalloutService
}

func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{}
	service.Handlers.RequestBodyHandler = service.HandleRequestBody
	service.Handlers.ResponseBodyHandler = service.HandleResponseBody
	return service
}

func (s *ExampleCalloutService) HandleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: utils.AddBodyMutation(
				"new-body-request",
				false,
				false,
			),
		},
	}, nil
}

func (s *ExampleCalloutService) HandleResponseBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: utils.AddBodyMutation(
				"new-body-response",
				false,
				false,
			),
		},
	}, nil
}
