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

package utils

import (
	"fmt"

	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"
        structpb "google.golang.org/protobuf/types/known/structpb"
	"github.com/golang/protobuf/proto"
)

const DYNAMIC_FORWARDING_METADATA_NAMESPACE string = "com.google.envoy.dynamic_forwarding.selected_endpoints"

// HeaderImmediateResponse creates an ImmediateResponse with the given status code, headers to add, and headers to remove.
// The headers can be appended if appendAction is provided.
func HeaderImmediateResponse(code httpstatus.StatusCode, addHeaders []struct{ Key, Value string }, removeHeaders []string, appendAction *base.HeaderValueOption_HeaderAppendAction) *extproc.ImmediateResponse {
	headerMutation := AddHeaderMutation(addHeaders, removeHeaders, false, appendAction)
	return &extproc.ImmediateResponse{
		Status: &httpstatus.HttpStatus{
			Code: code,
		},
		Headers: proto.Clone(headerMutation.Response.HeaderMutation).(*extproc.HeaderMutation),
	}
}

// AddHeaderMutation creates a HeadersResponse with the given headers to add and remove.
// It also allows clearing the route cache and setting an append action for the headers.
func AddHeaderMutation(add []struct{ Key, Value string }, remove []string, clearRouteCache bool, appendAction *base.HeaderValueOption_HeaderAppendAction) *extproc.HeadersResponse {
	headerMutation := &extproc.HeaderMutation{}

	if add != nil {
		for _, kv := range add {
			headerValueOption := &base.HeaderValueOption{
				Header: &base.HeaderValue{
					Key:      kv.Key,
					RawValue: []byte(kv.Value),
				},
			}
			if appendAction != nil {
				headerValueOption.AppendAction = *appendAction
			}
			headerMutation.SetHeaders = append(headerMutation.SetHeaders, headerValueOption)
		}
	}

	if remove != nil {
		headerMutation.RemoveHeaders = append(headerMutation.RemoveHeaders, remove...)
	}

	headersResponse := &extproc.HeadersResponse{
		Response: &extproc.CommonResponse{
			HeaderMutation:  headerMutation,
			ClearRouteCache: clearRouteCache,
		},
	}

	if clearRouteCache {
		headersResponse.Response.ClearRouteCache = true
	}

	return headersResponse
}

// AddBodyStringMutation creates a BodyResponse with the given body content.
// It allows clearing the route cache.
func AddBodyStringMutation(body string, clearRouteCache bool) *extproc.BodyResponse {
	bodyMutation := &extproc.BodyMutation{
		Mutation: &extproc.BodyMutation_Body{
			Body: []byte(body),
		},
	}

	bodyResponse := &extproc.BodyResponse{
		Response: &extproc.CommonResponse{
			BodyMutation:    bodyMutation,
			ClearRouteCache: clearRouteCache,
		},
	}

	return bodyResponse
}

// AddBodyClearMutation creates a BodyResponse that clears the body.
// It allows clearing the route cache.
func AddBodyClearMutation(clearRouteCache bool) *extproc.BodyResponse {
	bodyMutation := &extproc.BodyMutation{
		Mutation: &extproc.BodyMutation_ClearBody{
			ClearBody: true,
		},
	}

	bodyResponse := &extproc.BodyResponse{
		Response: &extproc.CommonResponse{
			BodyMutation:    bodyMutation,
			ClearRouteCache: clearRouteCache,
		},
	}

	return bodyResponse
}

// AddDynamicForwardingMetadata creates a Struct with expected Dynamic Forwarding
// key and format with provided ip and port.
func AddDynamicForwardingMetadata(ipAddress string, portNumber int) (*structpb.Struct, error) {
	formatedEndpoint := fmt.Sprintf("%s:%d", ipAddress, portNumber)
	return structpb.NewStruct(map[string]any{
		DYNAMIC_FORWARDING_METADATA_NAMESPACE: map[string]any{
			"primary": formatedEndpoint,
		},
	})
}
