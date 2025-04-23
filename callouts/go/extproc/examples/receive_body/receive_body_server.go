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

package receive_body

import (
	extprocconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/pkg/utils"
)

// ReceiveBodyCalloutService is a GRPC callout service that conditionally processes request/response bodies based on headers.
type ReceiveBodyCalloutService struct {
	server.GRPCCalloutService
}

// NewReceiveBodyCalloutService creates a new ReceiveBodyCalloutService with initialized handlers.
func NewReceiveBodyCalloutService() *ReceiveBodyCalloutService {
	service := &ReceiveBodyCalloutService{}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.Handlers.RequestBodyHandler = service.HandleRequestBody
	service.Handlers.ResponseHeadersHandler = service.HandleResponseHeaders
	service.Handlers.ResponseBodyHandler = service.HandleResponseBody
	return service
}

// HandleRequestHeaders processes request headers to conditionally enable streaming body processing.
func (s *ReceiveBodyCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	processBody := false

	// Check for X-Process-Request-Body header
	for _, h := range headers.GetHeaders().GetHeaders() {
		if h.GetKey() == "x-process-request-body" && h.GetValue() == "true" {
			processBody = true
			break
		}
	}

	resp := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: utils.AddHeaderMutation(nil, nil, false, nil),
		},
	}

	if processBody {
		resp.ModeOverride = &extprocconfig.ProcessingMode{
			RequestBodyMode: extprocconfig.ProcessingMode_STREAMED,
		}
	}

	return resp, nil
}

// HandleRequestBody processes streamed request body chunks when enabled.
func (s *ReceiveBodyCalloutService) HandleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	processedBody := append(body.GetBody(), []byte("-processed")...)
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: utils.AddBodyStringMutation(string(processedBody), false),
		},
	}, nil
}

// HandleResponseHeaders processes response headers to conditionally enable streaming body processing.
func (s *ReceiveBodyCalloutService) HandleResponseHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	processBody := false

	// Check for X-Process-Response-Body header
	for _, h := range headers.GetHeaders().GetHeaders() {
		if h.GetKey() == "x-process-response-body" && h.GetValue() == "true" {
			processBody = true
			break
		}
	}

	resp := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: utils.AddHeaderMutation(nil, nil, false, nil),
		},
	}

	if processBody {
		resp.ModeOverride = &extprocconfig.ProcessingMode{
			ResponseBodyMode: extprocconfig.ProcessingMode_STREAMED,
		}
	}

	return resp, nil
}

// HandleResponseBody processes streamed response body chunks when enabled.
func (s *ReceiveBodyCalloutService) HandleResponseBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	processedBody := append(body.GetBody(), []byte("-processed")...)
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: utils.AddBodyStringMutation(string(processedBody), false),
		},
	}, nil
}
