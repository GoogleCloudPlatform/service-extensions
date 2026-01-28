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

package block_ip

import (
	"context"
	"testing"

	attrv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// TestCheck_BlockedIP tests that requests from blocked IPs are denied.
func TestCheck_BlockedIP(t *testing.T) {
	service := NewCalloutServerExample()

	req := &auth.CheckRequest{
		Attributes: &attrv3.AttributeContext{
			Request: &attrv3.AttributeContext_Request{
				Http: &attrv3.AttributeContext_HttpRequest{
					Headers: map[string]string{
						"x-forwarded-for": "10.0.0.1,192.168.1.1",
					},
				},
			},
		},
	}

	response, err := service.Check(context.Background(), req)
	if err != nil {
		t.Errorf("Check got err: %v", err)
	}

	if response.GetDeniedResponse() == nil {
		t.Fatalf("Expected denied response for blocked IP")
	}

	if response.GetDeniedResponse().Status.Code != typev3.StatusCode_Forbidden {
		t.Errorf("Expected status code Forbidden, got %v", response.GetDeniedResponse().Status.Code)
	}

	headers := response.GetDeniedResponse().Headers
	if len(headers) == 0 || headers[0].Header.Key != "x-client-ip-allowed" || headers[0].Header.Value != "false" {
		t.Errorf("Expected x-client-ip-allowed: false header")
	}
}

// TestCheck_AllowedIP tests that requests from allowed IPs are permitted.
func TestCheck_AllowedIP(t *testing.T) {
	service := NewCalloutServerExample()

	req := &auth.CheckRequest{
		Attributes: &attrv3.AttributeContext{
			Request: &attrv3.AttributeContext_Request{
				Http: &attrv3.AttributeContext_HttpRequest{
					Headers: map[string]string{
						"x-forwarded-for": "192.168.1.1,10.0.0.1",
					},
				},
			},
		},
	}

	response, err := service.Check(context.Background(), req)
	if err != nil {
		t.Errorf("Check got err: %v", err)
	}

	if response.GetOkResponse() == nil {
		t.Fatalf("Expected OK response for allowed IP")
	}

	headers := response.GetOkResponse().Headers
	if len(headers) == 0 || headers[0].Header.Key != "x-client-ip-allowed" || headers[0].Header.Value != "true" {
		t.Errorf("Expected x-client-ip-allowed: true header")
	}
}

// TestCheck_MissingXFF tests that requests without x-forwarded-for header are denied.
func TestCheck_MissingXFF(t *testing.T) {
	service := NewCalloutServerExample()

	req := &auth.CheckRequest{
		Attributes: &attrv3.AttributeContext{
			Request: &attrv3.AttributeContext_Request{
				Http: &attrv3.AttributeContext_HttpRequest{
					Headers: map[string]string{},
				},
			},
		},
	}

	response, err := service.Check(context.Background(), req)
	if err != nil {
		t.Errorf("Check got err: %v", err)
	}

	if response.GetDeniedResponse() == nil {
		t.Fatalf("Expected denied response for missing X-Forwarded-For")
	}
}

// TestCheck_InvalidIP tests that requests with invalid IPs are denied.
func TestCheck_InvalidIP(t *testing.T) {
	service := NewCalloutServerExample()

	req := &auth.CheckRequest{
		Attributes: &attrv3.AttributeContext{
			Request: &attrv3.AttributeContext_Request{
				Http: &attrv3.AttributeContext_HttpRequest{
					Headers: map[string]string{
						"x-forwarded-for": "invalid-ip-address",
					},
				},
			},
		},
	}

	response, err := service.Check(context.Background(), req)
	if err != nil {
		t.Errorf("Check got err: %v", err)
	}

	if response.GetDeniedResponse() == nil {
		t.Fatalf("Expected denied response for invalid IP")
	}
}
