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

package waf_server

import (
	"bytes"
	"sync"

	extprocconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
)

// ExampleCalloutService implements a streaming application firewall that inspects body content
// across chunk boundaries and can immediately terminate requests that contain malicious content.
type ExampleCalloutService struct {
	server.GRPCCalloutService

	// Mutex to protect the buffered content maps
	mu sync.Mutex

	// Maps to store partial content being processed across chunks
	requestBuffers  map[string]*bytes.Buffer
	responseBuffers map[string]*bytes.Buffer

	// Forbidden patterns that trigger immediate termination
	forbiddenPatterns [][]byte
}

// NewExampleCalloutService creates a new ExampleCalloutService with initialized handlers.
//
// In production environments, this would be enhanced to:
// 1. Load forbidden patterns from an external configuration source (file, database, or security service)
// 2. Support regular expressions and more sophisticated pattern matching
// 3. Include severity levels and configurable actions per pattern
// 4. Implement periodic updates of security rules without service restart
// 5. Integrate with security information and event management (SIEM) systems
// 6. Support categorization of threats (SQL injection, XSS, command injection, etc.)
// 7. Include pattern versioning and rule testing capabilities
//
// The current implementation uses a simplified approach with hardcoded patterns
// suitable for demonstration purposes only.
func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{
		requestBuffers:  make(map[string]*bytes.Buffer),
		responseBuffers: make(map[string]*bytes.Buffer),
		forbiddenPatterns: [][]byte{
			[]byte("MALICIOUS_CONTENT"),
			[]byte("SQL_INJECTION"),
			[]byte("XSS_ATTACK"),
		},
	}

	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.Handlers.RequestBodyHandler = service.HandleRequestBody
	service.Handlers.ResponseHeadersHandler = service.HandleResponseHeaders
	service.Handlers.ResponseBodyHandler = service.HandleResponseBody
	return service
}

// HandleRequestHeaders configures the processing mode to stream request bodies.
func (s *ExampleCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	// Extract a request ID from headers for tracking chunks
	var requestID string
	for _, h := range headers.GetHeaders().GetHeaders() {
		if h.GetKey() == "x-request-id" {
			requestID = h.GetValue()
			break
		}
	}

	// Initialize buffer for this request if we have an ID
	if requestID != "" {
		s.mu.Lock()
		s.requestBuffers[requestID] = &bytes.Buffer{}
		s.mu.Unlock()
	}

	// Configure streaming mode for request body processing
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{},
			},
		},
		ModeOverride: &extprocconfig.ProcessingMode{
			RequestBodyMode: extprocconfig.ProcessingMode_STREAMED,
		},
	}, nil
}

// HandleRequestBody inspects streaming request body chunks for malicious content.
func (s *ExampleCalloutService) HandleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	// Extract request ID if available
	requestID := ""
	// HttpBody doesn't have GetTrailers method directly - need to access it differently
	// For now we'll just try to extract from body metadata if needed

	// Process the body chunk
	if malicious, reason := s.inspectBodyChunk(body.GetBody(), requestID, true); malicious {
		// Clean up resources when malicious content is found
		if requestID != "" {
			s.CleanupRequestBuffer(requestID)
		}

		// Return immediate response to block the request
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: &extproc.ImmediateResponse{
					Status: &typev3.HttpStatus{
						Code: typev3.StatusCode_Forbidden,
					},
					Body: "Blocked: " + reason,
				},
			},
		}, nil
	}

	// If this is the end of the stream, clean up
	if body.GetEndOfStream() && requestID != "" {
		s.CleanupRequestBuffer(requestID)
	}

	// ACK the body chunk to continue processing
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{},
			},
		},
	}, nil
}

// HandleResponseHeaders configures the processing mode to stream response bodies.
func (s *ExampleCalloutService) HandleResponseHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	// Extract a request ID from headers for tracking chunks
	var requestID string
	for _, h := range headers.GetHeaders().GetHeaders() {
		if h.GetKey() == "x-request-id" {
			requestID = h.GetValue()
			break
		}
	}

	// Initialize buffer for this response if we have an ID
	if requestID != "" {
		s.mu.Lock()
		s.responseBuffers[requestID] = &bytes.Buffer{}
		s.mu.Unlock()
	}

	// Configure streaming mode for response body processing
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{},
			},
		},
		ModeOverride: &extprocconfig.ProcessingMode{
			ResponseBodyMode: extprocconfig.ProcessingMode_STREAMED,
		},
	}, nil
}

// HandleResponseBody inspects streaming response body chunks for malicious content.
func (s *ExampleCalloutService) HandleResponseBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	// Extract request ID if available
	requestID := ""
	// HttpBody doesn't have GetTrailers method directly

	// Process the body chunk
	if malicious, reason := s.inspectBodyChunk(body.GetBody(), requestID, false); malicious {
		// Clean up resources when malicious content is found
		if requestID != "" {
			s.CleanupResponseBuffer(requestID)
		}

		// Return immediate response to block the response
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: &extproc.ImmediateResponse{
					Status: &typev3.HttpStatus{
						Code: typev3.StatusCode_BadGateway,
					},
					Body: "Blocked: " + reason,
				},
			},
		}, nil
	}

	// If this is the end of the stream, clean up
	if body.GetEndOfStream() && requestID != "" {
		s.CleanupResponseBuffer(requestID)
	}

	// ACK the body chunk to continue processing
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{},
			},
		},
	}, nil
}

// inspectBodyChunk processes a body chunk, combining it with previously buffered content
// to check for patterns that might span across chunk boundaries.
func (s *ExampleCalloutService) inspectBodyChunk(chunk []byte, requestID string, isRequest bool) (bool, string) {
	if len(chunk) == 0 {
		return false, ""
	}

	var buffer *bytes.Buffer

	// If we have a request ID, use the buffered approach
	if requestID != "" {
		s.mu.Lock()
		defer s.mu.Unlock()

		var ok bool
		if isRequest {
			buffer, ok = s.requestBuffers[requestID]
		} else {
			buffer, ok = s.responseBuffers[requestID]
		}

		if !ok {
			// Buffer not found, create one
			buffer = &bytes.Buffer{}
			if isRequest {
				s.requestBuffers[requestID] = buffer
			} else {
				s.responseBuffers[requestID] = buffer
			}
		}

		// Write the current chunk to our buffer
		buffer.Write(chunk)

		// Check for malicious patterns in the accumulated buffer
		content := buffer.Bytes()
		for _, pattern := range s.forbiddenPatterns {
			if bytes.Contains(content, pattern) {
				return true, "Detected " + string(pattern)
			}
		}

		// If the buffer is getting too large, trim it
		// Keep only the last part that might contain a partial pattern
		const maxBufferSize = 8192
		if buffer.Len() > maxBufferSize {
			// Keep the last 1KB which might contain a partial pattern
			const keepSize = 1024
			if buffer.Len() > keepSize {
				newBuf := buffer.Bytes()[buffer.Len()-keepSize:]
				buffer.Reset()
				buffer.Write(newBuf)
			}
		}
	} else {
		// Simple mode without buffering across chunks
		// Check for malicious patterns in this chunk only
		for _, pattern := range s.forbiddenPatterns {
			if bytes.Contains(chunk, pattern) {
				return true, "Detected " + string(pattern)
			}
		}
	}

	// No malicious content found
	return false, ""
}

// CleanupRequestBuffer removes a request buffer when processing is complete.
func (s *ExampleCalloutService) CleanupRequestBuffer(requestID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.requestBuffers, requestID)
}

// CleanupResponseBuffer removes a response buffer when processing is complete.
func (s *ExampleCalloutService) CleanupResponseBuffer(requestID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.responseBuffers, requestID)
}
