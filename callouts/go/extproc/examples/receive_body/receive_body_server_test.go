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
	"testing"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

func TestHandleRequestHeaders_EnableStreaming(t *testing.T) {
	service := NewReceiveBodyCalloutService()
	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{Key: "x-process-request-body", Value: "true"},
			},
		},
	}

	resp, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders error: %v", err)
	}

	if resp.ModeOverride == nil || resp.ModeOverride.RequestBodyMode != extprocconfig.ProcessingMode_STREAMED {
		t.Errorf("Expected STREAMED request body mode, got: %v", resp.ModeOverride)
	}
}

func TestHandleRequestHeaders_NoHeader(t *testing.T) {
	service := NewReceiveBodyCalloutService()
	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{Headers: []*core.HeaderValue{}},
	}

	resp, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders error: %v", err)
	}

	if resp.ModeOverride != nil {
		t.Errorf("Expected no mode override, got: %v", resp.ModeOverride)
	}
}

func TestHandleRequestBody_Processing(t *testing.T) {
	service := NewReceiveBodyCalloutService()
	body := &extproc.HttpBody{Body: []byte("test")}

	resp, err := service.HandleRequestBody(body)
	if err != nil {
		t.Fatalf("HandleRequestBody error: %v", err)
	}

	expected := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					BodyMutation: &extproc.BodyMutation{
						Mutation: &extproc.BodyMutation_Body{
							Body: []byte("test-processed"),
						},
					},
				},
			},
		},
	}

	if diff := cmp.Diff(expected, resp, protocmp.Transform()); diff != "" {
		t.Errorf("Response mismatch (-want +got):\n%s", diff)
	}
}

func TestHandleResponseHeaders_EnableStreaming(t *testing.T) {
	service := NewReceiveBodyCalloutService()
	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{Key: "x-process-response-body", Value: "true"},
			},
		},
	}

	resp, err := service.HandleResponseHeaders(headers)
	if err != nil {
		t.Fatalf("HandleResponseHeaders error: %v", err)
	}

	if resp.ModeOverride == nil || resp.ModeOverride.ResponseBodyMode != extprocconfig.ProcessingMode_STREAMED {
		t.Errorf("Expected STREAMED response body mode, got: %v", resp.ModeOverride)
	}
}

func TestHandleResponseHeaders_NoHeader(t *testing.T) {
	service := NewReceiveBodyCalloutService()
	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{Headers: []*core.HeaderValue{}},
	}

	resp, err := service.HandleResponseHeaders(headers)
	if err != nil {
		t.Fatalf("HandleResponseHeaders error: %v", err)
	}

	if resp.ModeOverride != nil {
		t.Errorf("Expected no mode override, got: %v", resp.ModeOverride)
	}
}

func TestHandleResponseBody_Processing(t *testing.T) {
	service := NewReceiveBodyCalloutService()
	body := &extproc.HttpBody{Body: []byte("response")}

	resp, err := service.HandleResponseBody(body)
	if err != nil {
		t.Fatalf("HandleResponseBody error: %v", err)
	}

	expected := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					BodyMutation: &extproc.BodyMutation{
						Mutation: &extproc.BodyMutation_Body{
							Body: []byte("response-processed"),
						},
					},
				},
			},
		},
	}

	if diff := cmp.Diff(expected, resp, protocmp.Transform()); diff != "" {
		t.Errorf("Response mismatch (-want +got):\n%s", diff)
	}
}
