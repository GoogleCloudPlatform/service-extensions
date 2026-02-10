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
	// Create an instance of WaitingRoomCalloutService
	service := NewWaitingRoomCalloutService()

	// Create a sample HttpHeaders request with no cookie
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

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Verify that a Set-Cookie header was added
	requestHeaders := response.GetRequestHeaders()
	if requestHeaders == nil {
		t.Fatalf("HandleRequestHeaders(): got nil RequestHeaders, want non-nil")
	}

	headerMutation := requestHeaders.GetResponse().GetHeaderMutation()
	if headerMutation == nil {
		t.Fatalf("HandleRequestHeaders(): got nil HeaderMutation, want non-nil")
	}

	// Check that Set-Cookie header exists
	found := false
	for _, header := range headerMutation.GetSetHeaders() {
		if header.GetHeader().GetKey() == "Set-Cookie" {
			found = true
			cookieValue := string(header.GetHeader().GetRawValue())
			
			// Verify cookie contains the waiting room token name
			if !strings.Contains(cookieValue, WaitingRoomCookieName) {
				t.Errorf("Set-Cookie header missing waiting_room_token, got: %s", cookieValue)
			}
			
			// Verify cookie has security attributes
			if !strings.Contains(cookieValue, "HttpOnly") {
				t.Errorf("Set-Cookie header missing HttpOnly attribute, got: %s", cookieValue)
			}
			if !strings.Contains(cookieValue, "SameSite=Strict") {
				t.Errorf("Set-Cookie header missing SameSite=Strict attribute, got: %s", cookieValue)
			}
		}
	}

	if !found {
		t.Errorf("HandleRequestHeaders(): Set-Cookie header not found in response")
	}

	// Verify that dynamic metadata indicates redirect
	if response.GetDynamicMetadata() != nil {
		fields := response.GetDynamicMetadata().GetFields()
		if waitingRoom, ok := fields["waiting_room"]; ok {
			wrFields := waitingRoom.GetStructValue().GetFields()
			if redirect, ok := wrFields["redirect"]; ok {
				if !redirect.GetBoolValue() {
					t.Errorf("Expected redirect to be true for first visit")
				}
			}
		}
	}
}

// TestHandleRequestHeadersWithinWaitPeriod tests the HandleRequestHeaders method when a user has a cookie but hasn't waited long enough.
func TestHandleRequestHeadersWithinWaitPeriod(t *testing.T) {
	// Create an instance of WaitingRoomCalloutService
	service := NewWaitingRoomCalloutService()

	// Create a cookie with a timestamp from 2 minutes ago (less than the 5-minute wait time)
	recentTimestamp := time.Now().Unix() - 120 // 2 minutes ago
	cookieValue := fmt.Sprintf("%s=test-token-123:%d", WaitingRoomCookieName, recentTimestamp)

	// Create a sample HttpHeaders request with the cookie
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

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Verify that a new Set-Cookie header was added (user still waiting)
	requestHeaders := response.GetRequestHeaders()
	if requestHeaders == nil {
		t.Fatalf("HandleRequestHeaders(): got nil RequestHeaders, want non-nil")
	}

	headerMutation := requestHeaders.GetResponse().GetHeaderMutation()
	if headerMutation == nil {
		t.Fatalf("HandleRequestHeaders(): got nil HeaderMutation, want non-nil")
	}

	// Verify dynamic metadata shows remaining wait time
	if response.GetDynamicMetadata() != nil {
		fields := response.GetDynamicMetadata().GetFields()
		if waitingRoom, ok := fields["waiting_room"]; ok {
			wrFields := waitingRoom.GetStructValue().GetFields()
			if retryAfter, ok := wrFields["retry_after"]; ok {
				remaining := retryAfter.GetNumberValue()
				// Should be less than full wait time but greater than 0
				if remaining <= 0 || remaining >= WaitingRoomWaitTime {
					t.Errorf("Expected retry_after between 0 and %d, got: %f", WaitingRoomWaitTime, remaining)
				}
			}
		}
	}
}

// TestHandleRequestHeadersAfterWaitPeriod tests the HandleRequestHeaders method when a user has waited long enough.
func TestHandleRequestHeadersAfterWaitPeriod(t *testing.T) {
	// Create an instance of WaitingRoomCalloutService
	service := NewWaitingRoomCalloutService()

	// Create a cookie with a timestamp from 6 minutes ago (more than the 5-minute wait time)
	oldTimestamp := time.Now().Unix() - (WaitingRoomWaitTime + 60) // 6 minutes ago
	cookieValue := fmt.Sprintf("%s=test-token-456:%d", WaitingRoomCookieName, oldTimestamp)

	// Create a sample HttpHeaders request with the cookie
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

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Define the expected response - user should be allowed through
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

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}

	// Verify that X-Waiting-Room-Status header is set to "allowed"
	requestHeaders := response.GetRequestHeaders()
	if requestHeaders == nil {
		t.Fatalf("HandleRequestHeaders(): got nil RequestHeaders, want non-nil")
	}

	headerMutation := requestHeaders.GetResponse().GetHeaderMutation()
	if headerMutation == nil {
		t.Fatalf("HandleRequestHeaders(): got nil HeaderMutation, want non-nil")
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
	// Create an instance of WaitingRoomCalloutService
	service := NewWaitingRoomCalloutService()

	// Create a sample HttpHeaders response
	headers := &extproc.HttpHeaders{}

	// Call the HandleResponseHeaders method
	response, err := service.HandleResponseHeaders(headers)

	// Check if any error occurred
	if err != nil {
		t.Errorf("HandleResponseHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleResponseHeaders(): got nil resp, want non-nil")
	}

	// Define the expected response
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

	// Compare the entire proto messages
	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleResponseHeaders() mismatch (-want +got):\n%s", diff)
	}
}
