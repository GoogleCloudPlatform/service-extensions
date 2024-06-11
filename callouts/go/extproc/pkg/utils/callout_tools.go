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
	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/golang/protobuf/proto"
)

// HeaderImmediateResponse creates an ImmediateResponse with the given status code and headers.
// The headers can be appended if appendAction is provided.
func HeaderImmediateResponse(code httpstatus.StatusCode, headers []struct{ Key, Value string }, appendAction *base.HeaderValueOption_HeaderAppendAction) *extproc.ImmediateResponse {
	immediateResponse := &extproc.ImmediateResponse{
		Status: &httpstatus.HttpStatus{
			Code: code,
		},
	}

	if len(headers) > 0 {
		headerMutation := &extproc.HeaderMutation{}
		for _, h := range headers {
			headerValueOption := &base.HeaderValueOption{
				Header: &base.HeaderValue{
					Key:   h.Key,
					Value: h.Value,
				},
			}
			if appendAction != nil {
				headerValueOption.AppendAction = *appendAction
			}
			headerMutation.SetHeaders = append(headerMutation.SetHeaders, headerValueOption)
		}
		immediateResponse.Headers = proto.Clone(headerMutation).(*extproc.HeaderMutation)
	}
	return immediateResponse
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

// AddBodyMutation creates a BodyResponse with the given body content.
// It allows clearing the body and the route cache.
func AddBodyMutation(body string, clearBody bool, clearRouteCache bool) *extproc.BodyResponse {
	bodyMutation := &extproc.BodyMutation{}

	if body != "" {
		bodyMutation.Mutation = &extproc.BodyMutation_Body{
			Body: []byte(body),
		}
	}

	if clearBody {
		bodyMutation.Mutation = &extproc.BodyMutation_ClearBody{
			ClearBody: true,
		}
	}

	bodyResponse := &extproc.BodyResponse{
		Response: &extproc.CommonResponse{
			BodyMutation:    bodyMutation,
			ClearRouteCache: clearRouteCache,
		},
	}

	return bodyResponse
}
