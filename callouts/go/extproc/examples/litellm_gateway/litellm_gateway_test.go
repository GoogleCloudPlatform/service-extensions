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

package litellm_gateway

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocfilter "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/testing/protocmp"
)

// newTestService creates a service pointing at a mock LiteLLM server.
func newTestService(litellmURL string) *ExampleCalloutService {
	service := &ExampleCalloutService{
		httpClient: &http.Client{},
		litellmURL: litellmURL,
		litellmKey: "test-key",
	}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.Handlers.RequestBodyHandler = service.HandleRequestBody
	return service
}

func TestHandleRequestHeaders_LLMEndpoint(t *testing.T) {
	service := newTestService("http://localhost:4000")

	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{Key: ":path", RawValue: []byte("/v1/chat/completions")},
			},
		},
	}

	resp, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}
	if resp == nil {
		t.Fatal("HandleRequestHeaders returned nil")
	}

	// Should have x-litellm-routed header and ModeOverride for body buffering.
	want := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*core.HeaderValueOption{
							{
								Header: &core.HeaderValue{
									Key:      "x-litellm-routed",
									RawValue: []byte("true"),
								},
							},
						},
					},
				},
			},
		},
		ModeOverride: &extprocfilter.ProcessingMode{
			RequestBodyMode: extprocfilter.ProcessingMode_BUFFERED,
		},
	}

	if diff := cmp.Diff(want, resp, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() LLM endpoint mismatch (-want +got):\n%s", diff)
	}
}

func TestHandleRequestHeaders_NonLLMEndpoint(t *testing.T) {
	service := newTestService("http://localhost:4000")

	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{Key: ":path", RawValue: []byte("/api/health")},
			},
		},
	}

	resp, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}
	if resp == nil {
		t.Fatal("HandleRequestHeaders returned nil")
	}

	// Should be an empty HeadersResponse (pass-through).
	want := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
	}

	if diff := cmp.Diff(want, resp, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() non-LLM endpoint mismatch (-want +got):\n%s", diff)
	}
}

func TestHandleRequestHeaders_EmptyHeaders(t *testing.T) {
	service := newTestService("http://localhost:4000")

	resp, err := service.HandleRequestHeaders(&extproc.HttpHeaders{})
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}
	if resp == nil {
		t.Fatal("HandleRequestHeaders returned nil")
	}
}

func TestHandleRequestBody_EmptyBody(t *testing.T) {
	service := newTestService("http://localhost:4000")

	resp, err := service.HandleRequestBody(&extproc.HttpBody{})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}
	if resp == nil {
		t.Fatal("HandleRequestBody returned nil")
	}
}

func TestHandleRequestBody_InvalidJSON(t *testing.T) {
	service := newTestService("http://localhost:4000")

	body := &extproc.HttpBody{
		Body: []byte("not json"),
	}

	resp, err := service.HandleRequestBody(body)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Should return ImmediateResponse with BadRequest.
	if resp.GetImmediateResponse() == nil {
		t.Fatal("Expected ImmediateResponse for invalid JSON, got nil")
	}
}

func TestHandleRequestBody_ForwardToLiteLLM(t *testing.T) {
	// Mock LiteLLM server.
	mockResp := map[string]interface{}{
		"id":      "chatcmpl-test",
		"object":  "chat.completion",
		"model":   "gpt-4",
		"choices": []interface{}{},
	}
	mockRespBytes, _ := json.Marshal(mockResp)

	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify auth header.
		if r.Header.Get("Authorization") != "Bearer test-key" {
			t.Errorf("Expected Authorization header 'Bearer test-key', got '%s'", r.Header.Get("Authorization"))
		}
		// Verify content type.
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("Expected Content-Type 'application/json', got '%s'", r.Header.Get("Content-Type"))
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(mockRespBytes)
	}))
	defer mockServer.Close()

	service := newTestService(mockServer.URL)

	reqBody := map[string]interface{}{
		"model":    "gpt-4",
		"messages": []interface{}{map[string]string{"role": "user", "content": "hello"}},
	}
	reqBytes, _ := json.Marshal(reqBody)

	resp, err := service.HandleRequestBody(&extproc.HttpBody{Body: reqBytes})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Should return ImmediateResponse with the LiteLLM response body.
	ir := resp.GetImmediateResponse()
	if ir == nil {
		t.Fatal("Expected ImmediateResponse, got nil")
	}

	if ir.GetStatus().GetCode().Number() != 200 {
		t.Errorf("Expected status 200, got: %d", ir.GetStatus().GetCode().Number())
	}

	if diff := cmp.Diff(mockRespBytes, ir.GetBody()); diff != "" {
		t.Errorf("Body mismatch (-want +got):\n%s", diff)
	}

	// Verify gateway marker header is present.
	foundGateway := false
	for _, h := range ir.GetHeaders().GetSetHeaders() {
		if h.GetHeader().GetKey() == "x-litellm-gateway" {
			foundGateway = true
			if string(h.GetHeader().GetRawValue()) != "true" {
				t.Errorf("Expected x-litellm-gateway=true, got %s", string(h.GetHeader().GetRawValue()))
			}
		}
	}
	if !foundGateway {
		t.Error("Expected x-litellm-gateway header in ImmediateResponse")
	}
}

func TestHandleRequestBody_StreamingStripped(t *testing.T) {
	var receivedBody map[string]interface{}

	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedBody)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"id":"test"}`))
	}))
	defer mockServer.Close()

	service := newTestService(mockServer.URL)

	reqBody := map[string]interface{}{
		"model":          "gpt-4",
		"messages":       []interface{}{},
		"stream":         true,
		"stream_options": map[string]interface{}{"include_usage": true},
	}
	reqBytes, _ := json.Marshal(reqBody)

	resp, err := service.HandleRequestBody(&extproc.HttpBody{Body: reqBytes})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Verify stream was set to false.
	if stream, ok := receivedBody["stream"]; ok {
		if stream != false {
			t.Errorf("Expected stream=false, got %v", stream)
		}
	}

	// Verify stream_options was removed.
	if _, ok := receivedBody["stream_options"]; ok {
		t.Error("Expected stream_options to be removed, but it was present")
	}

	// Should return ImmediateResponse.
	if resp.GetImmediateResponse() == nil {
		t.Fatal("Expected ImmediateResponse, got nil")
	}
}

func TestHandleRequestBody_StreamAlwaysSetFalse(t *testing.T) {
	var receivedBody map[string]interface{}

	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedBody)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"id":"test"}`))
	}))
	defer mockServer.Close()

	service := newTestService(mockServer.URL)

	// Request without explicit stream field — should still get stream=false.
	reqBody := map[string]interface{}{
		"model":    "gpt-4",
		"messages": []interface{}{},
	}
	reqBytes, _ := json.Marshal(reqBody)

	_, err := service.HandleRequestBody(&extproc.HttpBody{Body: reqBytes})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	if stream, ok := receivedBody["stream"]; !ok {
		t.Error("Expected stream field to be set, but it was absent")
	} else if stream != false {
		t.Errorf("Expected stream=false, got %v", stream)
	}
}

func TestHandleRequestBody_LiteLLM4xxPassedThrough(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"error":{"message":"Invalid model name","type":"invalid_request_error"}}`))
	}))
	defer mockServer.Close()

	service := newTestService(mockServer.URL)

	reqBody := map[string]interface{}{
		"model":    "nonexistent",
		"messages": []interface{}{},
	}
	reqBytes, _ := json.Marshal(reqBody)

	resp, err := service.HandleRequestBody(&extproc.HttpBody{Body: reqBytes})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	ir := resp.GetImmediateResponse()
	if ir == nil {
		t.Fatal("Expected ImmediateResponse, got nil")
	}

	// Should pass through the 400 status, not convert to 503.
	if ir.GetStatus().GetCode().Number() != 400 {
		t.Errorf("Expected status 400, got %d", ir.GetStatus().GetCode().Number())
	}

	// Should contain the error message from LiteLLM.
	if len(ir.GetBody()) == 0 {
		t.Error("Expected error body from LiteLLM, got empty")
	}
}

func TestHandleRequestBody_LiteLLM429PassedThrough(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		w.Write([]byte(`{"error":{"message":"Rate limit exceeded","type":"rate_limit_error"}}`))
	}))
	defer mockServer.Close()

	service := newTestService(mockServer.URL)

	reqBody := map[string]interface{}{
		"model":    "gpt-4",
		"messages": []interface{}{},
	}
	reqBytes, _ := json.Marshal(reqBody)

	resp, err := service.HandleRequestBody(&extproc.HttpBody{Body: reqBytes})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	ir := resp.GetImmediateResponse()
	if ir == nil {
		t.Fatal("Expected ImmediateResponse, got nil")
	}

	if ir.GetStatus().GetCode().Number() != 429 {
		t.Errorf("Expected status 429, got %d", ir.GetStatus().GetCode().Number())
	}

	if len(ir.GetBody()) == 0 {
		t.Error("Expected error body from LiteLLM, got empty")
	}
}

func TestHandleRequestBody_LiteLLMUnavailable(t *testing.T) {
	// Point to a non-existent server.
	service := newTestService("http://localhost:19999")

	reqBody := map[string]interface{}{
		"model":    "gpt-4",
		"messages": []interface{}{},
	}
	reqBytes, _ := json.Marshal(reqBody)

	resp, err := service.HandleRequestBody(&extproc.HttpBody{Body: reqBytes})
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Should return ImmediateResponse with ServiceUnavailable.
	if resp.GetImmediateResponse() == nil {
		t.Fatal("Expected ImmediateResponse for unavailable LiteLLM, got nil")
	}
}
