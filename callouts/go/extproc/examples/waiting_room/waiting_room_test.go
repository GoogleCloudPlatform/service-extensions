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
	"fmt"
	"strconv"
	"strings"
	"testing"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

// TestHandleRequestHeadersFirstVisit tests the HandleRequestHeaders method when a user visits for the first time (no cookie).
func TestHandleRequestHeadersFirstVisit(t *testing.T) {
	service := NewWaitingRoomCalloutService()

	// No cookie header - first visit
	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:      "host",
					RawValue: []byte("example.com"),
				},
			},
		},
	}

	response, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	immediateResp := response.GetImmediateResponse()
	if immediateResp == nil {
		t.Fatalf("HandleRequestHeaders(): got nil ImmediateResponse for first visit, want non-nil")
	}

	// Verify the HTTP status is 503 Service Unavailable
	if immediateResp.GetStatus().GetCode().Number() != 503 {
		t.Errorf("Expected status 503, got: %d", immediateResp.GetStatus().GetCode().Number())
	}

	// Verify that a Set-Cookie header was added
	found := false
	var retryAfterValue string
	for _, header := range immediateResp.GetHeaders().GetSetHeaders() {
		key := header.GetHeader().GetKey()
		val := string(header.GetHeader().GetRawValue())
		switch key {
		case "Set-Cookie":
			found = true
			// Verify cookie contains the waiting room token name
			if !strings.Contains(val, WaitingRoomCookieName) {
				t.Errorf("Set-Cookie header missing %s, got: %s", WaitingRoomCookieName, val)
			}
			// Verify cookie has security attributes
			if !strings.Contains(val, "HttpOnly") {
				t.Errorf("Set-Cookie header missing HttpOnly attribute, got: %s", val)
			}
			if !strings.Contains(val, "SameSite=Strict") {
				t.Errorf("Set-Cookie header missing SameSite=Strict attribute, got: %s", val)
			}
		case "Retry-After":
			retryAfterValue = val
		}
	}

	if !found {
		t.Errorf("HandleRequestHeaders(): Set-Cookie header not found in ImmediateResponse")
	}
	if retryAfterValue == "" {
		t.Errorf("HandleRequestHeaders(): Retry-After header not found in ImmediateResponse")
	} else {
		ra, err := strconv.ParseInt(retryAfterValue, 10, 64)
		if err != nil || ra <= 0 {
			t.Errorf("Expected positive Retry-After value, got: %s", retryAfterValue)
		}
	}

	// Verify response body contains waiting room HTML
	if !strings.Contains(immediateResp.GetBody(), "waiting room") {
		t.Errorf("Expected ImmediateResponse body to contain waiting room HTML, got: %s", immediateResp.GetBody())
	}

	// Verify dynamic metadata indicates redirect
	if response.GetDynamicMetadata() != nil {
		fields := response.GetDynamicMetadata().GetFields()
		if waitingRoom, ok := fields["waiting_room"]; ok {
			wrFields := waitingRoom.GetStructValue().GetFields()
			if redirect, ok := wrFields["redirect"]; ok {
				if !redirect.GetBoolValue() {
					t.Errorf("Expected redirect to be true for first visit")
				}
			} else {
				t.Errorf("Expected 'redirect' field in waiting_room metadata")
			}
		} else {
			t.Errorf("Expected 'waiting_room' field in dynamic metadata")
		}
	}
}

// TestHandleRequestHeadersWithinWaitPeriod tests the HandleRequestHeaders method when a user has a cookie but hasn't waited long enough.
func TestHandleRequestHeadersWithinWaitPeriod(t *testing.T) {
	service := NewWaitingRoomCalloutService()

	// Cookie with a timestamp from 2 minutes ago (less than the 5-minute wait time)
	recentTimestamp := time.Now().Unix() - 120 // 2 minutes ago
	cookieValue := fmt.Sprintf("%s=test-token-123:%d", WaitingRoomCookieName, recentTimestamp)

	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:      "cookie",
					RawValue: []byte(cookieValue),
				},
				{
					Key:      "host",
					RawValue: []byte("example.com"),
				},
			},
		},
	}

	response, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	immediateResp := response.GetImmediateResponse()
	if immediateResp == nil {
		t.Fatalf("HandleRequestHeaders(): got nil ImmediateResponse for within-wait-period, want non-nil")
	}

	// Verify 503 status
	if immediateResp.GetStatus().GetCode().Number() != 503 {
		t.Errorf("Expected status 503, got: %d", immediateResp.GetStatus().GetCode().Number())
	}

	// (not reset the clock with a new token/timestamp).
	for _, header := range immediateResp.GetHeaders().GetSetHeaders() {
		if header.GetHeader().GetKey() == "Set-Cookie" {
			val := string(header.GetHeader().GetRawValue())
			// The cookie value should contain the original token and timestamp
			if !strings.Contains(val, "test-token-123") {
				t.Errorf("Expected Set-Cookie to preserve original token 'test-token-123', got: %s", val)
			}
			expectedTS := fmt.Sprintf("%d", recentTimestamp)
			if !strings.Contains(val, expectedTS) {
				t.Errorf("Expected Set-Cookie to preserve original timestamp %s, got: %s", expectedTS, val)
			}
		}
	}

	// Verify dynamic metadata shows correct remaining wait time (~3 minutes remaining)
	if response.GetDynamicMetadata() != nil {
		fields := response.GetDynamicMetadata().GetFields()
		if waitingRoom, ok := fields["waiting_room"]; ok {
			wrFields := waitingRoom.GetStructValue().GetFields()
			if retryAfter, ok := wrFields["retry_after"]; ok {
				remaining := retryAfter.GetNumberValue()
				// Should be less than full wait time (300) but greater than 0
				// With a 2-min-old cookie, ~180 seconds remain.
				if remaining <= 0 || remaining >= WaitingRoomWaitTime {
					t.Errorf("Expected retry_after between 0 and %d, got: %f", WaitingRoomWaitTime, remaining)
				}
			} else {
				t.Errorf("Expected 'retry_after' field in waiting_room metadata")
			}
		}
	}

	// Verify Retry-After header is also set correctly
	for _, header := range immediateResp.GetHeaders().GetSetHeaders() {
		if header.GetHeader().GetKey() == "Retry-After" {
			ra, err := strconv.ParseInt(string(header.GetHeader().GetRawValue()), 10, 64)
			if err != nil || ra <= 0 || ra >= WaitingRoomWaitTime {
				t.Errorf("Expected Retry-After between 0 and %d, got: %s", WaitingRoomWaitTime, string(header.GetHeader().GetRawValue()))
			}
		}
	}
}

// TestHandleRequestHeadersAfterWaitPeriod tests the HandleRequestHeaders method when a user has waited long enough.
func TestHandleRequestHeadersAfterWaitPeriod(t *testing.T) {
	service := NewWaitingRoomCalloutService()

	// Cookie with a timestamp from 6 minutes ago (more than the 5-minute wait time)
	oldTimestamp := time.Now().Unix() - (WaitingRoomWaitTime + 60) // 6 minutes ago
	cookieValue := fmt.Sprintf("%s=test-token-456:%d", WaitingRoomCookieName, oldTimestamp)

	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:      "cookie",
					RawValue: []byte(cookieValue),
				},
				{
					Key:      "host",
					RawValue: []byte("example.com"),
				},
			},
		},
	}

	response, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// After the wait period the response is still RequestHeaders (allow-through path is unchanged).
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*core.HeaderValueOption{
							{
								Header: &core.HeaderValue{
									Key:      "X-Waiting-Room-Status",
									RawValue: []byte("allowed"),
								},
							},
						},
					},
				},
			},
		},
	}

	if diff := cmp.Diff(wantResponse, response, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}

	// Also verify via direct accessor
	requestHeaders := response.GetRequestHeaders()
	if requestHeaders == nil {
		t.Fatalf("HandleRequestHeaders(): got nil RequestHeaders for allowed user, want non-nil")
	}
	headerMutation := requestHeaders.GetResponse().GetHeaderMutation()
	if headerMutation == nil {
		t.Fatalf("HandleRequestHeaders(): got nil HeaderMutation for allowed user, want non-nil")
	}

	found := false
	for _, header := range headerMutation.GetSetHeaders() {
		if header.GetHeader().GetKey() == "X-Waiting-Room-Status" {
			found = true
			status := string(header.GetHeader().GetRawValue())
			if status != "allowed" {
				t.Errorf("Expected X-Waiting-Room-Status to be 'allowed', got: %s", status)
			}
		}
	}
	if !found {
		t.Errorf("HandleRequestHeaders(): X-Waiting-Room-Status header not found in response")
	}
}

// TestHandleResponseHeaders tests the HandleResponseHeaders method of WaitingRoomCalloutService.
func TestHandleResponseHeaders(t *testing.T) {
	service := NewWaitingRoomCalloutService()

	headers := &extproc.HttpHeaders{}

	response, err := service.HandleResponseHeaders(headers)
	if err != nil {
		t.Errorf("HandleResponseHeaders got err: %v", err)
	}
	if response == nil {
		t.Fatalf("HandleResponseHeaders(): got nil resp, want non-nil")
	}

	// This path is unchanged - still uses ResponseHeaders mutation.
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*core.HeaderValueOption{
							{
								Header: &core.HeaderValue{
									Key:      "X-Waiting-Room",
									RawValue: []byte("active"),
								},
							},
						},
					},
				},
			},
		},
	}

	if diff := cmp.Diff(wantResponse, response, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseHeaders() mismatch (-want +got):\n%s", diff)
	}
}
