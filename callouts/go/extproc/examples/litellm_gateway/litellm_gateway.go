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
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocfilter "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/pkg/utils"
)

// llmEndpoints maps supported LLM API paths to their LiteLLM endpoint.
var llmEndpoints = map[string]string{
	"/v1/chat/completions": "/v1/chat/completions",
	"/v1/completions":      "/v1/completions",
	"/v1/embeddings":       "/v1/embeddings",
	"/v1/models":           "/v1/models",
	"/chat/completions":    "/v1/chat/completions",
	"/completions":         "/v1/completions",
	"/embeddings":          "/v1/embeddings",
}

// corsHeaders returns CORS headers when ENABLE_CORS is set, or nil otherwise.
func (s *ExampleCalloutService) corsHeaders() []*core.HeaderValueOption {
	if !s.enableCORS {
		return nil
	}
	return []*core.HeaderValueOption{
		{Header: &core.HeaderValue{Key: "access-control-allow-origin", RawValue: []byte("*")}},
		{Header: &core.HeaderValue{Key: "access-control-allow-methods", RawValue: []byte("GET, POST, OPTIONS")}},
		{Header: &core.HeaderValue{Key: "access-control-allow-headers", RawValue: []byte("content-type, authorization")}},
	}
}

// ExampleCalloutService is a gRPC callout service that routes LLM requests through LiteLLM.
type ExampleCalloutService struct {
	server.GRPCCalloutService
	httpClient  *http.Client
	litellmURL  string
	litellmKey  string
	enableCORS  bool
	secKeywords []string // Keywords to detect in prompts — adds x-sec-keyword header when found.
}

// NewExampleCalloutService creates a new LiteLLM gateway callout service.
func NewExampleCalloutService() *ExampleCalloutService {
	litellmURL := os.Getenv("LITELLM_BASE_URL")
	if litellmURL == "" {
		litellmURL = "http://localhost:4000"
	}
	litellmKey := os.Getenv("LITELLM_MASTER_KEY")
	enableCORS := os.Getenv("ENABLE_CORS") == "true"

	var secKeywords []string
	if kw := os.Getenv("SEC_KEYWORDS"); kw != "" {
		for _, k := range strings.Split(kw, ",") {
			if trimmed := strings.TrimSpace(k); trimmed != "" {
				secKeywords = append(secKeywords, strings.ToLower(trimmed))
			}
		}
		log.Printf("SEC_KEYWORDS enabled: %v", secKeywords)
	}

	service := &ExampleCalloutService{
		httpClient: &http.Client{
			// The Service Extensions traffic extension timeout is 10s.
			// This timeout is set higher to allow for local testing without the ALB.
			// In production behind the ALB, Envoy will terminate the ext_proc stream
			// at the extension timeout, regardless of this value.
			Timeout: 120 * time.Second,
		},
		litellmURL:  strings.TrimRight(litellmURL, "/"),
		litellmKey:  litellmKey,
		enableCORS:  enableCORS,
		secKeywords: secKeywords,
	}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.Handlers.RequestBodyHandler = service.HandleRequestBody
	return service
}

// HandleRequestHeaders checks if the request path is an LLM endpoint.
func (s *ExampleCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	path := ""
	method := ""
	for _, h := range headers.GetHeaders().GetHeaders() {
		switch h.GetKey() {
		case ":path":
			path = string(h.GetRawValue())
		case ":method":
			method = string(h.GetRawValue())
		}
	}

	log.Printf("Request %s %s", method, path)

	// Handle CORS preflight for browser access (requires ENABLE_CORS=true).
	if s.enableCORS && method == "OPTIONS" {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: &extproc.ImmediateResponse{
					Status: &httpstatus.HttpStatus{Code: httpstatus.StatusCode_NoContent},
					Headers: &extproc.HeaderMutation{
						SetHeaders: s.corsHeaders(),
					},
				},
			},
		}, nil
	}

	// Handle GET /v1/models — proxy directly from headers phase (no body needed).
	if path == "/v1/models" && method == "GET" {
		return s.handleModelsRequest()
	}

	if _, isLLM := llmEndpoints[path]; !isLLM {
		// Not an LLM endpoint — pass through unmodified.
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestHeaders{
				RequestHeaders: &extproc.HeadersResponse{},
			},
		}, nil
	}

	// LLM endpoint — add marker header and request body buffering.
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: utils.AddHeaderMutation(
				[]struct{ Key, Value string }{
					{Key: "x-litellm-routed", Value: "true"},
				},
				nil, false, nil,
			),
		},
		ModeOverride: &extprocfilter.ProcessingMode{
			RequestBodyMode: extprocfilter.ProcessingMode_BUFFERED,
		},
	}, nil
}

// handleModelsRequest proxies GET /v1/models to LiteLLM and returns the result.
func (s *ExampleCalloutService) handleModelsRequest() (*extproc.ProcessingResponse, error) {
	url := s.litellmURL + "/v1/models"

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create models request: %w", err)
	}
	if s.litellmKey != "" {
		req.Header.Set("Authorization", "Bearer "+s.litellmKey)
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		log.Printf("Failed to fetch models from LiteLLM: %v", err)
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: utils.HeaderImmediateResponse(
					httpstatus.StatusCode_ServiceUnavailable, nil, nil, nil,
				),
			},
		}, nil
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read models response: %w", err)
	}

	responseHeaders := append(s.corsHeaders(),
		&core.HeaderValueOption{
			Header: &core.HeaderValue{Key: "content-type", RawValue: []byte("application/json")},
		},
		&core.HeaderValueOption{
			Header: &core.HeaderValue{Key: "x-litellm-gateway", RawValue: []byte("true")},
		},
	)

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: &extproc.ImmediateResponse{
				Status: &httpstatus.HttpStatus{
					Code: httpstatus.StatusCode(resp.StatusCode),
				},
				Headers: &extproc.HeaderMutation{
					SetHeaders: responseHeaders,
				},
				Body: string(body),
			},
		},
	}, nil
}

// detectKeywords scans messages for configured keywords and returns matched ones.
func (s *ExampleCalloutService) detectKeywords(reqMap map[string]interface{}) []string {
	if len(s.secKeywords) == 0 {
		return nil
	}

	messages, ok := reqMap["messages"].([]interface{})
	if !ok {
		return nil
	}

	var matched []string
	seen := map[string]bool{}

	for _, msg := range messages {
		m, ok := msg.(map[string]interface{})
		if !ok {
			continue
		}
		content, _ := m["content"].(string)
		lower := strings.ToLower(content)
		for _, kw := range s.secKeywords {
			if !seen[kw] && strings.Contains(lower, kw) {
				matched = append(matched, kw)
				seen[kw] = true
			}
		}
	}

	return matched
}

// HandleRequestBody forwards the LLM request body to LiteLLM and replaces it with the response.
func (s *ExampleCalloutService) HandleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	rawBody := body.GetBody()
	if len(rawBody) == 0 {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{},
			},
		}, nil
	}

	// Parse JSON body.
	var reqMap map[string]interface{}
	if err := json.Unmarshal(rawBody, &reqMap); err != nil {
		log.Printf("Invalid JSON body: %v", err)
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: utils.HeaderImmediateResponse(
					httpstatus.StatusCode_BadRequest, nil, nil, nil,
				),
			},
		}, nil
	}

	// Force non-streaming — ImmediateResponse cannot carry SSE chunks.
	reqMap["stream"] = false
	delete(reqMap, "stream_options")

	modifiedBody, err := json.Marshal(reqMap)
	if err != nil {
		log.Printf("Failed to marshal modified body: %v", err)
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: utils.HeaderImmediateResponse(
					httpstatus.StatusCode_InternalServerError, nil, nil, nil,
				),
			},
		}, nil
	}

	// Determine the LiteLLM endpoint from the request body structure.
	// The header phase already validated this is an LLM path.
	endpoint := "/v1/chat/completions"
	if _, hasInput := reqMap["input"]; hasInput {
		endpoint = "/v1/embeddings"
	} else if _, hasPrompt := reqMap["prompt"]; hasPrompt {
		if _, hasMessages := reqMap["messages"]; !hasMessages {
			endpoint = "/v1/completions"
		}
	}

	// Detect keywords in the prompt for security/demo tagging.
	matchedKeywords := s.detectKeywords(reqMap)
	if len(matchedKeywords) > 0 {
		log.Printf("SEC keywords detected: %v", matchedKeywords)
	}

	// Forward to LiteLLM.
	litellmResp, statusCode, err := s.forwardToLiteLLM(endpoint, modifiedBody)
	if err != nil {
		log.Printf("LiteLLM error: %v", err)
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: utils.HeaderImmediateResponse(
					httpstatus.StatusCode_ServiceUnavailable, nil, nil, nil,
				),
			},
		}, nil
	}

	// Map HTTP status to envoy status code.
	// Verify the code is a known enum value; fall back to BadGateway for unknown codes.
	envoyStatus := httpstatus.StatusCode(statusCode)
	if _, valid := httpstatus.StatusCode_name[int32(statusCode)]; !valid {
		envoyStatus = httpstatus.StatusCode_BadGateway
	}

	// Build response headers.
	responseHeaders := append(s.corsHeaders(),
		&core.HeaderValueOption{
			Header: &core.HeaderValue{Key: "content-type", RawValue: []byte("application/json")},
		},
		&core.HeaderValueOption{
			Header: &core.HeaderValue{Key: "x-litellm-gateway", RawValue: []byte("true")},
		},
	)
	if len(matchedKeywords) > 0 {
		responseHeaders = append(responseHeaders, &core.HeaderValueOption{
			Header: &core.HeaderValue{
				Key:      "x-sec-keyword",
				RawValue: []byte(strings.Join(matchedKeywords, ",")),
			},
		})
	}

	// Return LiteLLM response directly to the client via ImmediateResponse.
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: &extproc.ImmediateResponse{
				Status: &httpstatus.HttpStatus{
					Code: envoyStatus,
				},
				Headers: &extproc.HeaderMutation{
					SetHeaders: responseHeaders,
				},
				Body: string(litellmResp),
			},
		},
	}, nil
}

// forwardToLiteLLM sends the request body to the LiteLLM proxy and returns the response body and HTTP status.
// For client errors (4xx), the response body is returned so the caller can pass the error details to the client.
// For network errors, it returns a nil body and a non-nil error.
func (s *ExampleCalloutService) forwardToLiteLLM(endpoint string, body []byte) ([]byte, int, error) {
	url := s.litellmURL + endpoint

	req, err := http.NewRequest("POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, 0, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if s.litellmKey != "" {
		req.Header.Set("Authorization", "Bearer "+s.litellmKey)
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to reach LiteLLM: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to read LiteLLM response: %w", err)
	}

	if resp.StatusCode >= 500 {
		return nil, 0, fmt.Errorf("LiteLLM returned status %d: %s", resp.StatusCode, string(respBody))
	}

	return respBody, resp.StatusCode, nil
}
