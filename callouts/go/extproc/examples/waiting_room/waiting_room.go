// Copyright 2026 Google LLC.
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

package waiting_room

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	envoy_type "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/pkg/utils"
	"google.golang.org/protobuf/types/known/structpb"
)

const (
	WaitingRoomCookieName = "waiting_room_token"

	WaitingRoomWaitTime = 300 // 5 minutes
)

// WaitingRoomCalloutService is a gRPC service that handles waiting room logic.
type WaitingRoomCalloutService struct {
	server.GRPCCalloutService
}

// NewWaitingRoomCalloutService creates a new instance of WaitingRoomCalloutService.
func NewWaitingRoomCalloutService() *WaitingRoomCalloutService {
	service := &WaitingRoomCalloutService{}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.Handlers.ResponseHeadersHandler = service.HandleResponseHeaders
	return service
}

// HandleRequestHeaders processes incoming requests and implements waiting room logic.
func (s *WaitingRoomCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	headerMap := make(map[string]string)
	for _, hv := range headers.GetHeaders().GetHeaders() {
		headerMap[strings.ToLower(hv.GetKey())] = string(hv.GetRawValue())
	}

	// Check if user has a waiting room cookie
	cookieHeader := headerMap["cookie"]
	token, timestamp := extractWaitingRoomCookie(cookieHeader)

	// Determine if user should be allowed through
	if shouldAllowAccess(token, timestamp) {
		// User has valid token and has waited long enough - allow through
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestHeaders{
				RequestHeaders: utils.AddHeaderMutation(
					[]struct{ Key, Value string }{
						{Key: "X-Waiting-Room-Status", Value: "allowed"},
					},
					nil,
					false,
					nil,
				),
			},
		}, nil
	}

	currentTime := time.Now().Unix()

	// Only generate a fresh token for true first-time visitors so the timer doesn't reset.
	var cookieToken string
	var cookieTimestamp int64
	if token != "" && timestamp != 0 {
		// Returning visitor - reuse their existing token and original timestamp
		cookieToken = token
		cookieTimestamp = timestamp
	} else {
		// First visit - issue a new token with the current time
		cookieToken = generateToken()
		cookieTimestamp = currentTime
	}

	cookieValue := fmt.Sprintf("%s=%s:%d; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict",
		WaitingRoomCookieName, cookieToken, cookieTimestamp, WaitingRoomWaitTime*2)

	retryAfter := int64(WaitingRoomWaitTime)
	if cookieTimestamp > 0 {
		elapsed := currentTime - cookieTimestamp
		remaining := int64(WaitingRoomWaitTime) - elapsed
		if remaining > 0 {
			retryAfter = remaining
		} else {
			retryAfter = 0
		}
	}

	metaStruct, err := structpb.NewStruct(map[string]interface{}{
		"waiting_room": map[string]interface{}{
			"redirect":    true,
			"retry_after": retryAfter,
		},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to build dynamic metadata: %w", err)
	}

	waitingRoomHTML := fmt.Sprintf(`<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Waiting Room</title>
<meta http-equiv="refresh" content="%d;url=/">
</head>
<body>
<h1>You are in the waiting room</h1>
<p>Please wait approximately <strong>%d seconds</strong> before you will be admitted.</p>
<p>This page will automatically retry in %d seconds.</p>
</body>
</html>`, retryAfter, retryAfter, retryAfter)

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: &extproc.ImmediateResponse{
				Status: &envoy_type.HttpStatus{
					Code: envoy_type.StatusCode_ServiceUnavailable, // 503
				},
				Headers: &extproc.HeaderMutation{
					SetHeaders: []*core.HeaderValueOption{
						{
							Header: &core.HeaderValue{
								Key:      "Set-Cookie",
								RawValue: []byte(cookieValue),
							},
						},
						{
							Header: &core.HeaderValue{
								Key:      "Retry-After",
								RawValue: []byte(strconv.FormatInt(retryAfter, 10)),
							},
						},
						{
							Header: &core.HeaderValue{
								Key:      "Content-Type",
								RawValue: []byte("text/html; charset=utf-8"),
							},
						},
					},
				},
				Body:    waitingRoomHTML,
				Details: "waiting_room",
			},
		},
		DynamicMetadata: metaStruct,
	}, nil
}

// HandleResponseHeaders adds waiting room headers to responses when redirecting.
func (s *WaitingRoomCalloutService) HandleResponseHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: utils.AddHeaderMutation(
				[]struct{ Key, Value string }{
					{Key: "X-Waiting-Room", Value: "active"},
				},
				nil,
				false,
				nil,
			),
		},
	}, nil
}

// extractWaitingRoomCookie parses the cookie header and extracts the waiting room token and timestamp.
func extractWaitingRoomCookie(cookieHeader string) (token string, timestamp int64) {
	if cookieHeader == "" {
		return "", 0
	}

	cookies := strings.Split(cookieHeader, ";")
	for _, cookie := range cookies {
		cookie = strings.TrimSpace(cookie)
		if strings.HasPrefix(cookie, WaitingRoomCookieName+"=") {
			value := strings.TrimPrefix(cookie, WaitingRoomCookieName+"=")
			parts := strings.Split(value, ":")
			if len(parts) == 2 {
				token = parts[0]
				if ts, err := strconv.ParseInt(parts[1], 10, 64); err == nil {
					timestamp = ts
				}
			}
			break
		}
	}

	return token, timestamp
}

// shouldAllowAccess determines if a user should be allowed to access the origin.
func shouldAllowAccess(token string, timestamp int64) bool {
	// No token means first visit - deny access
	if token == "" || timestamp == 0 {
		return false
	}

	// Check if enough time has elapsed
	currentTime := time.Now().Unix()
	elapsed := currentTime - timestamp

	return elapsed >= WaitingRoomWaitTime
}

// generateToken creates a cryptographically secure random token.
func generateToken() string {
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		// Fallback to timestamp-based token if random generation fails
		return fmt.Sprintf("fallback-%d", time.Now().UnixNano())
	}
	return base64.URLEncoding.EncodeToString(bytes)
}
