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

package utils

import (
	"strings"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	rpcstatus "google.golang.org/genproto/googleapis/rpc/status"
	"google.golang.org/grpc/codes"
)

// AllowRequest creates an allowed response with optional headers.
func AllowRequest(headersToAdd map[string]string) *auth.CheckResponse {
	okResponse := &auth.OkHttpResponse{}

	if headersToAdd != nil {
		for key, value := range headersToAdd {
			headerValue := &core.HeaderValue{
				Key:   key,
				Value: value,
			}
			headerOption := &core.HeaderValueOption{
				Header: headerValue,
			}
			okResponse.Headers = append(okResponse.Headers, headerOption)
		}
	}

	return &auth.CheckResponse{
		Status: &rpcstatus.Status{Code: int32(codes.OK)},
		HttpResponse: &auth.CheckResponse_OkResponse{
			OkResponse: okResponse,
		},
	}
}

// DenyRequest creates a denied response with status, body and headers.
func DenyRequest(statusCode typev3.StatusCode, body string, headers map[string]string) *auth.CheckResponse {
	deniedResponse := &auth.DeniedHttpResponse{
		Status: &typev3.HttpStatus{Code: statusCode},
	}

	if body != "" {
		deniedResponse.Body = body
	}

	if headers != nil {
		for key, value := range headers {
			headerValue := &core.HeaderValue{
				Key:   key,
				Value: value,
			}
			headerOption := &core.HeaderValueOption{
				Header: headerValue,
			}
			deniedResponse.Headers = append(deniedResponse.Headers, headerOption)
		}
	}

	return &auth.CheckResponse{
		HttpResponse: &auth.CheckResponse_DeniedResponse{
			DeniedResponse: deniedResponse,
		},
	}
}

// ExtractHeader extracts a header value from the request.
func ExtractHeader(req *auth.CheckRequest, headerName string) string {
	if req == nil || req.Attributes == nil || req.Attributes.Request == nil || req.Attributes.Request.Http == nil {
		return ""
	}

	httpReq := req.Attributes.Request.Http
	if httpReq.Headers != nil {
		if value, exists := httpReq.Headers[headerName]; exists {
			return value
		}
	}

	return ""
}

// ExtractClientIP extracts the client IP from X-Forwarded-For header.
func ExtractClientIP(req *auth.CheckRequest) string {
	xff := ExtractHeader(req, "x-forwarded-for")
	if xff == "" {
		return ""
	}

	// Get the first IP from the X-Forwarded-For list
	// Handle comma-separated list of IPs
	ips := splitAndTrim(xff, ",")
	if len(ips) > 0 {
		return ips[0]
	}

	return ""
}

func splitAndTrim(s, sep string) []string {
	var result []string
	for _, part := range strings.Split(s, sep) {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}
