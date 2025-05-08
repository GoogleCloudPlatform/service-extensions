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

package body_buffering

import (
	"context"
	"testing"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)

// TestHandleRequestHeadersSetupBufferedMode tests that the processing mode is correctly set to BUFFERED
func TestHandleRequestHeadersSetupBufferedMode(t *testing.T) {
	service := NewExampleCalloutService()
	defer service.Close()
	ctx := context.Background()

	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "host",
					Value: "example.com",
				},
			},
		},
	}

	response, err := service.HandleRequestHeaders(ctx, headers)

	if err != nil {
		t.Errorf("HandleRequestHeaders got err: %v", err)
	}

	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Verify mode override is set correctly
	if response.ModeOverride == nil {
		t.Fatalf("Expected ModeOverride to be set, but it was nil")
	}

	if response.ModeOverride.RequestBodyMode != extprocconfig.ProcessingMode_BUFFERED {
		t.Errorf("Expected RequestBodyMode to be BUFFERED, got %v", response.ModeOverride.RequestBodyMode)
	}

	if response.ModeOverride.ResponseBodyMode != extprocconfig.ProcessingMode_BUFFERED {
		t.Errorf("Expected ResponseBodyMode to be BUFFERED, got %v", response.ModeOverride.ResponseBodyMode)
	}
}

// TestRequestBodyBuffering tests that body content is correctly buffered
func TestRequestBodyBuffering(t *testing.T) {
	service := NewExampleCalloutService()
	defer service.Close()
	ctx := context.Background()

	// Set up request headers
	headers := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "host",
					Value: "example.com",
				},
			},
		},
	}

	_, err := service.HandleRequestHeaders(ctx, headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}

	// Get the requestID that was created
	requestID := service.getRequestID(ctx)

	// Send first body chunk (not end of stream)
	body1 := &extproc.HttpBody{
		Body:        []byte("This is the first chunk "),
		EndOfStream: false,
	}

	_, err = service.HandleRequestBody(ctx, body1)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Verify content was buffered
	state, exists := service.getState(requestID)
	if !exists || state.buffer.String() != "This is the first chunk " {
		t.Errorf("Expected buffer to contain first chunk, got: %s", state.buffer.String())
	}

	// Send second body chunk (end of stream)
	body2 := &extproc.HttpBody{
		Body:        []byte("and this is the second chunk."),
		EndOfStream: true,
	}

	_, err = service.HandleRequestBody(ctx, body2)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Verify both chunks were buffered
	state, exists = service.getState(requestID)
	if !exists || state.buffer.String() != "This is the first chunk and this is the second chunk." {
		t.Errorf("Expected buffer to contain both chunks, got: %s", state.buffer.String())
	}
}

// TestFullBodyProcessingWithResponseHeaders tests the complete flow where response headers are delayed
// until the full body is available, and then headers are set based on body content
func TestFullBodyProcessingWithResponseHeaders(t *testing.T) {
	service := NewExampleCalloutService()
	defer service.Close()
	ctx := context.Background()

	// Set up request headers
	reqHeaders := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "host",
					Value: "example.com",
				},
			},
		},
	}

	_, err := service.HandleRequestHeaders(ctx, reqHeaders)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}

	// Send body chunks with error content and JSON format
	body := &extproc.HttpBody{
		Body:        []byte(`{"status": "error", "message": "Something went wrong"}`),
		EndOfStream: true,
	}

	_, err = service.HandleRequestBody(ctx, body)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Set up response headers
	respHeaders := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "content-type",
					Value: "application/json",
				},
			},
		},
	}

	// Now process response headers which should trigger the full processing
	resp, err := service.HandleResponseHeaders(ctx, respHeaders)
	if err != nil {
		t.Fatalf("HandleResponseHeaders got err: %v", err)
	}

	// Check that the response has our body-based headers
	if resp == nil {
		t.Fatalf("HandleResponseHeaders(): got nil resp, want non-nil")
	}

	responseHeaders, ok := resp.Response.(*extproc.ProcessingResponse_ResponseHeaders)
	if !ok {
		t.Fatalf("Expected ResponseHeaders in response, got different type")
	}

	// Check for required header mutations
	headerMutation := responseHeaders.ResponseHeaders.Response.HeaderMutation
	if headerMutation == nil {
		t.Fatalf("Expected HeaderMutation in response, got nil")
	}

	// Create a map of the headers for easier checking
	headerMap := make(map[string]string)
	for _, header := range headerMutation.SetHeaders {
		headerMap[header.Header.Key] = header.Header.Value
	}

	// Check for specific headers we expect based on the JSON error content
	expectedHeaders := map[string]string{
		"x-body-size":      "54", // Updated to match actual size
		"x-body-has-error": "true",
		"x-body-format":    "json",
	}

	for k, v := range expectedHeaders {
		if headerMap[k] != v {
			t.Errorf("Expected header %s=%s, got %s", k, v, headerMap[k])
		}
	}
}

// TestFullDuplexWithTrailers tests the case where trailers are present
func TestFullDuplexWithTrailers(t *testing.T) {
	service := NewExampleCalloutService()
	defer service.Close()
	ctx := context.Background()

	// Set up request headers
	reqHeaders := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "host",
					Value: "example.com",
				},
			},
		},
	}

	_, err := service.HandleRequestHeaders(ctx, reqHeaders)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}

	// Send body chunks without end_of_stream
	body := &extproc.HttpBody{
		Body:        []byte(`<warning>This is an XML document with a warning</warning>`),
		EndOfStream: false, // Not end of stream because trailers follow
	}

	_, err = service.HandleRequestBody(ctx, body)
	if err != nil {
		t.Fatalf("HandleRequestBody got err: %v", err)
	}

	// Set up response headers (but these won't trigger processing yet)
	respHeaders := &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "content-type",
					Value: "application/xml",
				},
			},
		},
	}

	// Process response headers
	_, err = service.HandleResponseHeaders(ctx, respHeaders)
	if err != nil {
		t.Fatalf("HandleResponseHeaders got err: %v", err)
	}

	// Now send trailers which should trigger processing
	trailers := &extproc.HttpTrailers{
		Trailers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{
					Key:   "x-checksum",
					Value: "abc123",
				},
			},
		},
	}

	finalResp, err := service.HandleRequestTrailers(ctx, trailers)
	if err != nil {
		t.Fatalf("HandleRequestTrailers got err: %v", err)
	}

	// Check that the response has our body-based headers
	if finalResp == nil {
		t.Fatalf("HandleRequestTrailers(): got nil resp, want non-nil")
	}

	responseHeaders, ok := finalResp.Response.(*extproc.ProcessingResponse_ResponseHeaders)
	if !ok {
		t.Fatalf("Expected ResponseHeaders in response, got different type")
	}

	// Check for required header mutations
	headerMutation := responseHeaders.ResponseHeaders.Response.HeaderMutation
	if headerMutation == nil {
		t.Fatalf("Expected HeaderMutation in response, got nil")
	}

	// Create a map of the headers for easier checking
	headerMap := make(map[string]string)
	for _, header := range headerMutation.SetHeaders {
		headerMap[header.Header.Key] = header.Header.Value
	}

	// Check for specific headers we expect based on the XML warning content
	expectedHeaders := map[string]string{
		"x-body-size":        "57", // Updated to match actual size
		"x-body-has-warning": "true",
		"x-body-format":      "xml",
	}

	for k, v := range expectedHeaders {
		if headerMap[k] != v {
			t.Errorf("Expected header %s=%s, got %s", k, v, headerMap[k])
		}
	}
}

// TestAnalyzeBodyAndCreateHeaders validates the header creation logic
func TestAnalyzeBodyAndCreateHeaders(t *testing.T) {
	testCases := []struct {
		name        string
		bodyContent string
		expected    map[string]string
	}{
		{
			name:        "JSON with error",
			bodyContent: `{"status": "error", "message": "Something went wrong"}`,
			expected: map[string]string{
				"x-body-size":      "54", // Updated to match actual size
				"x-body-has-error": "true",
				"x-body-format":    "json",
			},
		},
		{
			name:        "XML with warning",
			bodyContent: `<warning>This is a warning message</warning>`,
			expected: map[string]string{
				"x-body-size":        "44", // Updated to match actual size
				"x-body-has-warning": "true",
				"x-body-format":      "xml",
			},
		},
		{
			name:        "Plain text",
			bodyContent: "This is just plain text",
			expected: map[string]string{
				"x-body-size":   "23", // Updated to match actual size
				"x-body-format": "text",
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			headers := analyzeBodyAndCreateHeaders(tc.bodyContent)

			// Check all expected headers exist with correct values
			for k, v := range tc.expected {
				if headers[k] != v {
					t.Errorf("Expected header %s=%s, got %s", k, v, headers[k])
				}
			}

			// Check no unexpected headers
			for k := range headers {
				if _, exists := tc.expected[k]; !exists {
					t.Errorf("Unexpected header found: %s=%s", k, headers[k])
				}
			}
		})
	}
}
