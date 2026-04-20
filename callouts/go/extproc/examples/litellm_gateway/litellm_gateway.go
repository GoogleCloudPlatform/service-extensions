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
	"io"
	"log"
	"os"
	"strings"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocfilter "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extproc/pkg/utils"
)

// Header names the callout emits.
const (
	headerRouted  = "x-litellm-routed"
	headerPolicy  = "x-litellm-policy"
	headerSecKW   = "x-sec-keyword"
	policyAllowed = "allowed"
)

// llmEndpoints is the set of paths that the callout inspects.
// Requests to other paths pass through unchanged.
var llmEndpoints = map[string]bool{
	"/v1/chat/completions": true,
	"/v1/completions":      true,
	"/v1/embeddings":       true,
	"/v1/models":           true,
	"/chat/completions":    true,
	"/completions":         true,
	"/embeddings":          true,
}

// ExampleCalloutService inspects LLM requests and enforces policies before
// they reach the LiteLLM upstream.
type ExampleCalloutService struct {
	server.GRPCCalloutService

	// secKeywords are lowercased prompt keywords. When any message content
	// contains one, the callout adds an x-sec-keyword header on both the
	// forwarded request and the returned response.
	secKeywords []string

	// allowedModels is the set of model names a client may request. Empty
	// means all models are allowed.
	allowedModels map[string]bool
}

// NewExampleCalloutService creates a new callout configured from environment
// variables:
//
//	SEC_KEYWORDS   comma-separated prompt keywords to tag with x-sec-keyword
//	ALLOWED_MODELS comma-separated model allowlist (empty = allow all)
func NewExampleCalloutService() *ExampleCalloutService {
	service := &ExampleCalloutService{
		secKeywords:   parseCSVLower(os.Getenv("SEC_KEYWORDS")),
		allowedModels: parseCSVSet(os.Getenv("ALLOWED_MODELS")),
	}

	if len(service.secKeywords) > 0 {
		log.Printf("SEC_KEYWORDS enabled: %v", service.secKeywords)
	}
	if len(service.allowedModels) > 0 {
		allowed := make([]string, 0, len(service.allowedModels))
		for m := range service.allowedModels {
			allowed = append(allowed, m)
		}
		log.Printf("ALLOWED_MODELS enabled: %v", allowed)
	}

	return service
}

// Process overrides the framework's default stream loop so we can maintain
// per-stream state. Keywords detected in the request body phase are carried
// over to the response headers phase and mirrored onto the response.
func (s *ExampleCalloutService) Process(stream extproc.ExternalProcessor_ProcessServer) error {
	var matchedKeywords []string

	for {
		req, err := stream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}

		var (
			response   *extproc.ProcessingResponse
			handlerErr error
		)

		switch {
		case req.GetRequestHeaders() != nil:
			response, handlerErr = s.handleRequestHeaders(req.GetRequestHeaders())
		case req.GetRequestBody() != nil:
			response, matchedKeywords, handlerErr = s.handleRequestBody(req.GetRequestBody())
		case req.GetResponseHeaders() != nil:
			response, handlerErr = s.handleResponseHeaders(matchedKeywords)
		default:
			// Phases we don't subscribe to — skip silently.
			continue
		}

		if handlerErr != nil {
			return handlerErr
		}
		if response == nil {
			continue
		}
		if err := stream.Send(response); err != nil {
			return err
		}
	}
}

// handleRequestHeaders inspects the request path. For LLM endpoints it requests
// body buffering AND response headers so we can mirror keywords onto the
// response. For non-LLM endpoints it returns a pass-through.
func (s *ExampleCalloutService) handleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	path, method := "", ""
	for _, h := range headers.GetHeaders().GetHeaders() {
		switch h.GetKey() {
		case ":path":
			path = string(h.GetRawValue())
		case ":method":
			method = string(h.GetRawValue())
		}
	}

	log.Printf("Request %s %s", method, path)

	if !llmEndpoints[path] {
		return passThrough(), nil
	}

	resp := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: utils.AddHeaderMutation(
				[]struct{ Key, Value string }{{Key: headerRouted, Value: "true"}},
				nil, false, nil,
			),
		},
	}

	// For POSTs we need buffered body mode so HandleRequestBody can inspect
	// the JSON payload, and we opt into the response headers phase so we can
	// mirror x-sec-keyword onto the client-facing response.
	// GET /v1/models has no request body, so it flows through with only the
	// marker header.
	if method != "GET" {
		resp.ModeOverride = &extprocfilter.ProcessingMode{
			RequestBodyMode:    extprocfilter.ProcessingMode_BUFFERED,
			ResponseHeaderMode: extprocfilter.ProcessingMode_SEND,
		}
	}
	return resp, nil
}

// handleRequestBody enforces policies on the buffered request body:
//
//  1. Reject invalid JSON with 400.
//  2. Reject disallowed models with 403 (if ALLOWED_MODELS is set).
//  3. Tag requests containing configured keywords with x-sec-keyword on the
//     forwarded request. The matched keyword list is returned so the response
//     phase can mirror it.
func (s *ExampleCalloutService) handleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, []string, error) {
	rawBody := body.GetBody()
	if len(rawBody) == 0 {
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{},
			},
		}, nil, nil
	}

	var reqMap map[string]interface{}
	if err := json.Unmarshal(rawBody, &reqMap); err != nil {
		log.Printf("Invalid JSON body: %v", err)
		return immediateError(httpstatus.StatusCode_BadRequest), nil, nil
	}

	// Model allowlist enforcement.
	if len(s.allowedModels) > 0 {
		model, _ := reqMap["model"].(string)
		if !s.allowedModels[model] {
			log.Printf("Rejected disallowed model: %q", model)
			return immediateError(httpstatus.StatusCode_Forbidden), nil, nil
		}
	}

	// Keyword detection.
	matched := s.detectKeywords(reqMap)
	if len(matched) > 0 {
		log.Printf("SEC keywords detected: %v", matched)
	}

	// Build header mutations for the forwarded request.
	setHeaders := []*core.HeaderValueOption{
		{Header: &core.HeaderValue{Key: headerPolicy, RawValue: []byte(policyAllowed)}},
	}
	if len(matched) > 0 {
		setHeaders = append(setHeaders, &core.HeaderValueOption{
			Header: &core.HeaderValue{
				Key:      headerSecKW,
				RawValue: []byte(strings.Join(matched, ",")),
			},
		})
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: setHeaders,
					},
				},
			},
		},
	}, matched, nil
}

// handleResponseHeaders mirrors the x-sec-keyword header onto the response so
// clients can see which keywords matched without needing access to logs.
func (s *ExampleCalloutService) handleResponseHeaders(matchedKeywords []string) (*extproc.ProcessingResponse, error) {
	if len(matchedKeywords) == 0 {
		// Nothing to tag — just acknowledge the phase.
		return &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ResponseHeaders{
				ResponseHeaders: &extproc.HeadersResponse{},
			},
		}, nil
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*core.HeaderValueOption{
							{
								Header: &core.HeaderValue{
									Key:      headerSecKW,
									RawValue: []byte(strings.Join(matchedKeywords, ",")),
								},
							},
						},
					},
				},
			},
		},
	}, nil
}

// detectKeywords scans the `messages` array in the request body for any of the
// configured keywords. Matching is case-insensitive.
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

// passThrough returns a no-op RequestHeaders response so non-LLM traffic is
// unaffected by the callout.
func passThrough() *extproc.ProcessingResponse {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
	}
}

// immediateError short-circuits the request with the given HTTP status code
// and an empty body. Used to reject invalid or disallowed requests.
func immediateError(code httpstatus.StatusCode) *extproc.ProcessingResponse {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: utils.HeaderImmediateResponse(code, nil, nil, nil),
		},
	}
}

// splitCSV splits a comma-separated list and trims whitespace around each
// non-empty element. Returns nil for empty input.
func splitCSV(csv string) []string {
	if csv == "" {
		return nil
	}
	var out []string
	for _, item := range strings.Split(csv, ",") {
		if t := strings.TrimSpace(item); t != "" {
			out = append(out, t)
		}
	}
	return out
}

// parseCSVLower splits a comma-separated list, trims whitespace, and lowercases
// each element. Empty input returns nil.
func parseCSVLower(csv string) []string {
	items := splitCSV(csv)
	for i, v := range items {
		items[i] = strings.ToLower(v)
	}
	return items
}

// parseCSVSet splits a comma-separated list into a lookup set. Empty input
// returns nil (which callers should treat as "allow all").
func parseCSVSet(csv string) map[string]bool {
	items := splitCSV(csv)
	if items == nil {
		return nil
	}
	set := make(map[string]bool, len(items))
	for _, v := range items {
		set[v] = true
	}
	return set
}
