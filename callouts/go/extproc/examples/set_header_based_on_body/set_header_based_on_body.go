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
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)

const (
	maxBufferSize = 2 * 1024 * 1024 // 2MB max buffer size
	stateTimeout  = 5 * time.Minute
)

// requestState maintains the state for a single request being processed
type requestState struct {
	buffer             *bytes.Buffer        // Accumulates request body
	responseHeaders    *extproc.HttpHeaders // Stored response headers
	hasTrailers        bool                 // Tracks if trailers were seen
	headersSent        bool                 // Tracks if headers were sent
	waitingForComplete bool                 // Indicates if we're waiting for full body
	lastAccessed       time.Time            // Tracks when state was last accessed
}

// ExampleCalloutService implements the External Processing service for Envoy
type ExampleCalloutService struct {
	extproc.UnimplementedExternalProcessorServer

	contextsMu    sync.RWMutex
	requestsMu    sync.RWMutex
	requestStates map[string]*requestState
	contexts      map[context.Context]string
	cleanupTicker *time.Ticker
	done          chan struct{}
}

// NewExampleCalloutService creates a new instance of the callout service
func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{
		requestStates: make(map[string]*requestState),
		contexts:      make(map[context.Context]string),
		cleanupTicker: time.NewTicker(stateTimeout / 2),
		done:          make(chan struct{}),
	}

	go service.periodicCleanup()
	return service
}

// periodicCleanup removes expired state entries
func (s *ExampleCalloutService) periodicCleanup() {
	for {
		select {
		case <-s.cleanupTicker.C:
			s.cleanupExpiredStates()
		case <-s.done:
			s.cleanupTicker.Stop()
			return
		}
	}
}

// cleanupExpiredStates removes state entries that haven't been accessed recently
func (s *ExampleCalloutService) cleanupExpiredStates() {
	cutoff := time.Now().Add(-stateTimeout)
	s.requestsMu.Lock()
	defer s.requestsMu.Unlock()
	for id, state := range s.requestStates {
		if state.lastAccessed.Before(cutoff) {
			delete(s.requestStates, id)
		}
	}
}

// Close stops the service cleanly
func (s *ExampleCalloutService) Close() {
	close(s.done)
}

// Process handles the bidirectional stream of processing requests from Envoy
func (s *ExampleCalloutService) Process(stream extproc.ExternalProcessor_ProcessServer) error {
	ctx, cancel := context.WithCancel(stream.Context())
	defer cancel()

	var requestID string
	var cleanupOnce sync.Once

	cleanupFunc := func() {
		if requestID != "" {
			s.cleanup(ctx, requestID)
		}
	}
	defer cleanupOnce.Do(cleanupFunc)

	for {
		req, err := stream.Recv()
		if err != nil {
			return err
		}

		if requestID == "" {
			s.contextsMu.RLock()
			requestID = s.contexts[ctx]
			s.contextsMu.RUnlock()
		}

		var resp *extproc.ProcessingResponse
		var respErr error

		switch v := req.Request.(type) {
		case *extproc.ProcessingRequest_RequestHeaders:
			resp, respErr = s.HandleRequestHeaders(ctx, v.RequestHeaders)
		case *extproc.ProcessingRequest_RequestBody:
			resp, respErr = s.HandleRequestBody(ctx, v.RequestBody)
		case *extproc.ProcessingRequest_RequestTrailers:
			resp, respErr = s.HandleRequestTrailers(ctx, v.RequestTrailers)
		case *extproc.ProcessingRequest_ResponseHeaders:
			resp, respErr = s.HandleResponseHeaders(ctx, v.ResponseHeaders)
		case *extproc.ProcessingRequest_ResponseBody:
			resp, respErr = s.HandleResponseBody(ctx, v.ResponseBody)
		case *extproc.ProcessingRequest_ResponseTrailers:
			resp, respErr = s.HandleResponseTrailers(ctx, v.ResponseTrailers)
		default:
			resp = &extproc.ProcessingResponse{
				Response: &extproc.ProcessingResponse_RequestHeaders{
					RequestHeaders: &extproc.HeadersResponse{
						Response: &extproc.CommonResponse{},
					},
				},
			}
		}

		if respErr != nil {
			return respErr
		}

		if resp != nil {
			if err := stream.Send(resp); err != nil {
				return err
			}
		}
	}
}

// cleanup removes state for a completed request to prevent memory leaks
func (s *ExampleCalloutService) cleanup(ctx context.Context, requestID string) {
	s.contextsMu.Lock()
	delete(s.contexts, ctx)
	s.contextsMu.Unlock()

	s.requestsMu.Lock()
	delete(s.requestStates, requestID)
	s.requestsMu.Unlock()
}

// generateRequestID creates a unique identifier for a request
func generateRequestID() string {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("ts-%x", time.Now().UnixNano())
	}
	return hex.EncodeToString(b)
}

// extractRequestID tries to find a request ID in the headers
func extractRequestID(headers *extproc.HttpHeaders) string {
	if headers == nil || headers.Headers == nil {
		return ""
	}
	for _, header := range headers.Headers.Headers {
		if header != nil && strings.EqualFold(header.Key, "x-request-id") {
			return string(header.Value)
		}
	}
	return ""
}

// getOrCreateRequestID gets an existing request ID or creates a new one
func (s *ExampleCalloutService) getOrCreateRequestID(ctx context.Context, headers *extproc.HttpHeaders) string {
	s.contextsMu.RLock()
	requestID, exists := s.contexts[ctx]
	s.contextsMu.RUnlock()

	if exists {
		s.refreshStateTimestamp(requestID)
		return requestID
	}

	requestID = extractRequestID(headers)
	if requestID == "" {
		requestID = generateRequestID()
	}

	s.contextsMu.Lock()
	s.contexts[ctx] = requestID
	s.contextsMu.Unlock()

	s.requestsMu.Lock()
	s.requestStates[requestID] = &requestState{
		buffer:             new(bytes.Buffer),
		hasTrailers:        false,
		headersSent:        false,
		waitingForComplete: true,
		lastAccessed:       time.Now(),
	}
	s.requestsMu.Unlock()

	return requestID
}

// refreshStateTimestamp updates the last accessed time for a request state
func (s *ExampleCalloutService) refreshStateTimestamp(requestID string) {
	s.requestsMu.Lock()
	if state, exists := s.requestStates[requestID]; exists {
		state.lastAccessed = time.Now()
	}
	s.requestsMu.Unlock()
}

// getRequestID retrieves the request ID associated with a context
func (s *ExampleCalloutService) getRequestID(ctx context.Context) string {
	s.contextsMu.RLock()
	requestID := s.contexts[ctx]
	s.contextsMu.RUnlock()

	if requestID != "" {
		s.refreshStateTimestamp(requestID)
	}

	return requestID
}

// getState safely retrieves the state for a requestID
func (s *ExampleCalloutService) getState(requestID string) (*requestState, bool) {
	if requestID == "" {
		return nil, false
	}
	s.requestsMu.RLock()
	state, exists := s.requestStates[requestID]
	s.requestsMu.RUnlock()
	return state, exists
}

// HandleRequestHeaders processes request headers from Envoy
func (s *ExampleCalloutService) HandleRequestHeaders(ctx context.Context, headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	_ = s.getOrCreateRequestID(ctx, headers)
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{},
			},
		},
		ModeOverride: &extprocconfig.ProcessingMode{
			RequestBodyMode:  extprocconfig.ProcessingMode_BUFFERED,
			ResponseBodyMode: extprocconfig.ProcessingMode_BUFFERED,
		},
	}, nil
}

// HandleRequestBody processes request body chunks from Envoy
func (s *ExampleCalloutService) HandleRequestBody(ctx context.Context, body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	if body == nil {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{
					Response: &extproc.CommonResponse{},
				},
			},
		}, nil
	}

	requestID := s.getRequestID(ctx)
	state, exists := s.getState(requestID)
	if !exists {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{
					Response: &extproc.CommonResponse{},
				},
			},
		}, nil
	}

	s.requestsMu.Lock()
	if state.buffer.Len()+len(body.Body) > maxBufferSize {
		s.requestsMu.Unlock()
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{
					Response: &extproc.CommonResponse{},
				},
			},
		}, nil
	}
	state.buffer.Write(body.Body)
	state.lastAccessed = time.Now()
	canProcessNow := body.EndOfStream
	if canProcessNow {
		state.waitingForComplete = false
	}
	s.requestsMu.Unlock()

	if canProcessNow {
		return s.processCompleteBody(requestID)
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{},
			},
		},
	}, nil
}

// processCompleteBody handles the complete body and generates response headers
func (s *ExampleCalloutService) processCompleteBody(requestID string) (*extproc.ProcessingResponse, error) {
	s.requestsMu.Lock()
	defer s.requestsMu.Unlock()
	state, exists := s.requestStates[requestID]
	if !exists {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{
					Response: &extproc.CommonResponse{},
				},
			},
		}, nil
	}

	bodyContent := state.buffer.String()
	state.waitingForComplete = false
	state.headersSent = true
	state.lastAccessed = time.Now()

	additionalHeaders := analyzeBodyAndCreateHeaders(bodyContent)
	headerMutation := &extproc.HeaderMutation{
		SetHeaders: convertToEnvoyHeaders(additionalHeaders),
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: headerMutation,
				},
			},
		},
	}, nil
}

// HandleRequestTrailers processes request trailers from Envoy
func (s *ExampleCalloutService) HandleRequestTrailers(ctx context.Context, trailers *extproc.HttpTrailers) (*extproc.ProcessingResponse, error) {
	requestID := s.getRequestID(ctx)
	state, exists := s.getState(requestID)
	if !exists {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestTrailers{
				RequestTrailers: &extproc.TrailersResponse{
					HeaderMutation: &extproc.HeaderMutation{},
				},
			},
		}, nil
	}

	s.requestsMu.Lock()
	state.hasTrailers = true
	state.lastAccessed = time.Now()
	canProcessNow := state.waitingForComplete && state.responseHeaders != nil
	s.requestsMu.Unlock()

	if canProcessNow {
		return s.processCompleteBody(requestID)
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestTrailers{
			RequestTrailers: &extproc.TrailersResponse{
				HeaderMutation: &extproc.HeaderMutation{},
			},
		},
	}, nil
}

// HandleResponseHeaders processes response headers from Envoy
func (s *ExampleCalloutService) HandleResponseHeaders(ctx context.Context, headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	if headers == nil {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ResponseHeaders{
				ResponseHeaders: &extproc.HeadersResponse{
					Response: &extproc.CommonResponse{},
				},
			},
		}, nil
	}

	requestID := s.getRequestID(ctx)
	state, exists := s.getState(requestID)
	if !exists {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ResponseHeaders{
				ResponseHeaders: &extproc.HeadersResponse{
					Response: &extproc.CommonResponse{},
				},
			},
		}, nil
	}

	s.requestsMu.Lock()
	state.responseHeaders = headers
	state.lastAccessed = time.Now()
	s.requestsMu.Unlock()

	if !state.waitingForComplete && state.buffer.Len() > 0 {
		return s.processCompleteBody(requestID)
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{},
			},
		},
	}, nil
}

// HandleResponseBody processes response body chunks from Envoy
func (s *ExampleCalloutService) HandleResponseBody(ctx context.Context, body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{},
			},
		},
	}, nil
}

// HandleResponseTrailers processes response trailers from Envoy
func (s *ExampleCalloutService) HandleResponseTrailers(ctx context.Context, trailers *extproc.HttpTrailers) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseTrailers{
			ResponseTrailers: &extproc.TrailersResponse{
				HeaderMutation: &extproc.HeaderMutation{},
			},
		},
	}, nil
}

// analyzeBodyAndCreateHeaders processes the full request body and generates headers based on its content
func analyzeBodyAndCreateHeaders(bodyContent string) map[string]string {
	headers := make(map[string]string)
	headers["x-body-size"] = fmt.Sprintf("%d", len(bodyContent))
	if strings.Contains(strings.ToLower(bodyContent), "error") {
		headers["x-body-has-error"] = "true"
	}
	if strings.Contains(strings.ToLower(bodyContent), "warning") {
		headers["x-body-has-warning"] = "true"
	}
	if strings.HasPrefix(strings.TrimSpace(bodyContent), "{") &&
		strings.HasSuffix(strings.TrimSpace(bodyContent), "}") {
		headers["x-body-format"] = "json"
	} else if strings.HasPrefix(strings.TrimSpace(bodyContent), "<") &&
		strings.HasSuffix(strings.TrimSpace(bodyContent), ">") {
		headers["x-body-format"] = "xml"
	} else {
		headers["x-body-format"] = "text"
	}
	return headers
}

// convertToEnvoyHeaders converts a map of header key/values to Envoy's HeaderValueOption format
func convertToEnvoyHeaders(headers map[string]string) []*core.HeaderValueOption {
	var result []*core.HeaderValueOption
	for key, value := range headers {
		result = append(result, &core.HeaderValueOption{
			Header: &core.HeaderValue{
				Key:   key,
				Value: value,
			},
		})
	}
	return result
}
