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

package dynamic_forwarding

import (
	"fmt"
	"log"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/pkg/utils"
)

// ExampleCalloutService is a gRPC service that handles header processing.
type ExampleCalloutService struct {
	server.GRPCCalloutService
}

// NewExampleCalloutService creates a new instance of ExampleCalloutService.
func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	return service
}

func extractIpToReturnHeader(headers *extproc.HttpHeaders) (string, error) {
	if headers == nil || headers.Headers == nil {
		return "", fmt.Errorf("no hearder found")
	}
	for _, header := range headers.Headers.Headers {
		if header.Key == "ip-to-return" {
			return string(header.RawValue), nil
		}
	}
	return "", fmt.Errorf("no ip header found")
}

// HandleRequestHeaders handles incoming request headers and adds a dynamic forwarding metadata.
func (s *ExampleCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	var ipToReturn string
	ipFromHeader, err := extractIpToReturnHeader(headers)
	if err != nil {
		ipToReturn = "10.1.10.3" //default backend
	} else {
		ipToReturn = ipFromHeader
	}

	dynamicMetadata, err := utils.AddDynamicForwardingMetadata(ipToReturn, 80)
	if err != nil {
		log.Printf("received error from dynamic metadata builder: %v", err)
		return nil, err
	}
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
                DynamicMetadata: dynamicMetadata,
	}, nil
}
