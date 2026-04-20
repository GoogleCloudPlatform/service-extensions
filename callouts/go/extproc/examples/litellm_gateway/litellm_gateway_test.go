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
	"testing"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extprocfilter "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_proc/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	httpstatus "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// --- Test fixtures -----------------------------------------------------------
//
// Test constants.

const (
	// Prompt keywords used by the detector.
	kwSec     = "sec"
	kwLiteLLM = "litellm"

	// Model identifiers used in policy tests.
	modelAllowed    = "vertex/gemini-2.5-flash"
	modelDisallowed = "secret-internal-model"
	modelAnything   = "anything-goes"

	// HTTP paths and methods.
	pathChatCompletions = "/v1/chat/completions"
	pathModels          = "/v1/models"
	pathNonLLM          = "/api/health"
	methodGet           = "GET"
	methodPost          = "POST"

	// Header name constants (headerRouted / headerPolicy / headerSecKW /
	// policyAllowed) are declared in the production file and shared here.

	// Prompts used across tests.
	promptWithBothKeywords = "This request covers sec tagging and the litellm gateway."
	promptWithNoKeywords   = "Tell me a joke"
	promptGeneric          = "hello"
)

// matchedKeywords returns the expected keyword list (in the order the detector
// emits them, which matches s.secKeywords order).
func matchedKeywords() []string { return []string{kwSec, kwLiteLLM} }

// --- Service construction helpers --------------------------------------------

// newTestService constructs an ExampleCalloutService with the given options,
// bypassing environment variable parsing so tests are deterministic.
func newTestService(opts ...func(*ExampleCalloutService)) *ExampleCalloutService {
	service := &ExampleCalloutService{}
	for _, opt := range opts {
		opt(service)
	}
	return service
}

func withKeywords(keywords ...string) func(*ExampleCalloutService) {
	return func(s *ExampleCalloutService) {
		s.secKeywords = keywords
	}
}

func withAllowedModels(models ...string) func(*ExampleCalloutService) {
	return func(s *ExampleCalloutService) {
		s.allowedModels = map[string]bool{}
		for _, m := range models {
			s.allowedModels[m] = true
		}
	}
}

// --- Proto helpers -----------------------------------------------------------

// headerRequest builds an HttpHeaders proto with the given path and method.
func headerRequest(path, method string) *extproc.HttpHeaders {
	return &extproc.HttpHeaders{
		Headers: &core.HeaderMap{
			Headers: []*core.HeaderValue{
				{Key: ":path", RawValue: []byte(path)},
				{Key: ":method", RawValue: []byte(method)},
			},
		},
	}
}

// chatBody marshals a chat-completion request body with a single user message.
func chatBody(t *testing.T, model, content string) []byte {
	t.Helper()
	body, err := json.Marshal(map[string]interface{}{
		"model":    model,
		"messages": []map[string]string{{"role": "user", "content": content}},
	})
	if err != nil {
		t.Fatalf("chatBody marshal: %v", err)
	}
	return body
}

// findHeader searches a slice of HeaderValueOption for a header by key.
func findHeader(headers []*core.HeaderValueOption, key string) (string, bool) {
	for _, h := range headers {
		if h.GetHeader().GetKey() == key {
			return string(h.GetHeader().GetRawValue()), true
		}
	}
	return "", false
}

// --- Header phase ------------------------------------------------------------

func TestHandleRequestHeaders_PostLLMPath(t *testing.T) {
	service := newTestService()

	resp, err := service.handleRequestHeaders(headerRequest(pathChatCompletions, methodPost))
	if err != nil {
		t.Fatalf("handleRequestHeaders got err: %v", err)
	}

	// Must request buffered body mode AND response headers so we can mirror
	// the keyword header onto the response.
	if resp.GetModeOverride() == nil {
		t.Fatal("expected ModeOverride for LLM POST")
	}
	if resp.GetModeOverride().GetRequestBodyMode() != extprocfilter.ProcessingMode_BUFFERED {
		t.Errorf("expected BUFFERED body mode, got %v", resp.GetModeOverride().GetRequestBodyMode())
	}
	if resp.GetModeOverride().GetResponseHeaderMode() != extprocfilter.ProcessingMode_SEND {
		t.Errorf("expected SEND response header mode, got %v", resp.GetModeOverride().GetResponseHeaderMode())
	}

	// Must add the routing marker header.
	mutation := resp.GetRequestHeaders().GetResponse().GetHeaderMutation()
	if mutation == nil {
		t.Fatal("expected HeaderMutation")
	}
	if v, ok := findHeader(mutation.GetSetHeaders(), headerRouted); !ok || v != "true" {
		t.Errorf("expected %s=true, got %q (present=%v)", headerRouted, v, ok)
	}
}

func TestHandleRequestHeaders_GetModels(t *testing.T) {
	service := newTestService()

	resp, err := service.handleRequestHeaders(headerRequest(pathModels, methodGet))
	if err != nil {
		t.Fatalf("handleRequestHeaders got err: %v", err)
	}

	// GET /v1/models has no body — must not request body buffering or
	// response header phase.
	if resp.GetModeOverride() != nil {
		t.Errorf("GET %s should not request body buffering", pathModels)
	}

	// Should still add the marker so the LB/logs can see the request was inspected.
	if _, ok := findHeader(resp.GetRequestHeaders().GetResponse().GetHeaderMutation().GetSetHeaders(), headerRouted); !ok {
		t.Errorf("expected %s header on %s response", headerRouted, pathModels)
	}
}

func TestHandleRequestHeaders_NonLLMPathPassesThrough(t *testing.T) {
	service := newTestService()

	resp, err := service.handleRequestHeaders(headerRequest(pathNonLLM, methodGet))
	if err != nil {
		t.Fatalf("handleRequestHeaders got err: %v", err)
	}

	rh := resp.GetRequestHeaders()
	if rh == nil {
		t.Fatal("expected RequestHeaders response")
	}
	if rh.GetResponse() != nil {
		t.Error("non-LLM path should have no header mutations")
	}
	if resp.GetModeOverride() != nil {
		t.Error("non-LLM path should not request body buffering")
	}
}

func TestHandleRequestHeaders_EmptyHeaders(t *testing.T) {
	service := newTestService()

	resp, err := service.handleRequestHeaders(&extproc.HttpHeaders{})
	if err != nil {
		t.Fatalf("handleRequestHeaders got err: %v", err)
	}
	if resp == nil {
		t.Fatal("handleRequestHeaders returned nil")
	}
}

// --- Body phase --------------------------------------------------------------

func TestHandleRequestBody_EmptyBody(t *testing.T) {
	service := newTestService()

	resp, matched, err := service.handleRequestBody(&extproc.HttpBody{})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}
	if resp.GetRequestBody() == nil {
		t.Error("empty body should return a RequestBody pass-through")
	}
	if matched != nil {
		t.Errorf("empty body should match no keywords, got %v", matched)
	}
}

func TestHandleRequestBody_InvalidJSONRejected(t *testing.T) {
	service := newTestService()

	resp, _, err := service.handleRequestBody(&extproc.HttpBody{Body: []byte("not json")})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}

	ir := resp.GetImmediateResponse()
	if ir == nil {
		t.Fatal("expected ImmediateResponse for invalid JSON")
	}
	if ir.GetStatus().GetCode() != httpstatus.StatusCode_BadRequest {
		t.Errorf("expected 400, got %v", ir.GetStatus().GetCode())
	}
}

func TestHandleRequestBody_ValidRequestFlowsThrough(t *testing.T) {
	service := newTestService()

	resp, matched, err := service.handleRequestBody(&extproc.HttpBody{Body: chatBody(t, modelAllowed, promptGeneric)})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}
	if matched != nil {
		t.Errorf("no keywords configured — should match nothing, got %v", matched)
	}

	// Must NOT short-circuit.
	if resp.GetImmediateResponse() != nil {
		t.Fatal("valid request should flow through, not return ImmediateResponse")
	}

	rb := resp.GetRequestBody()
	if rb == nil {
		t.Fatal("expected RequestBody response")
	}

	// Must tag the request with the policy marker.
	mutation := rb.GetResponse().GetHeaderMutation()
	if mutation == nil {
		t.Fatal("expected HeaderMutation")
	}
	if v, ok := findHeader(mutation.GetSetHeaders(), headerPolicy); !ok || v != policyAllowed {
		t.Errorf("expected %s=%s, got %q (present=%v)", headerPolicy, policyAllowed, v, ok)
	}
}

func TestHandleRequestBody_KeywordDetection(t *testing.T) {
	service := newTestService(withKeywords(kwSec, kwLiteLLM))

	resp, matched, err := service.handleRequestBody(&extproc.HttpBody{
		Body: chatBody(t, modelAllowed, promptWithBothKeywords),
	})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}

	// Matched keywords must be returned so the response phase can mirror them.
	want := matchedKeywords()
	if len(matched) != len(want) {
		t.Errorf("expected %d matched keywords, got %v", len(want), matched)
	}

	mutation := resp.GetRequestBody().GetResponse().GetHeaderMutation()
	v, ok := findHeader(mutation.GetSetHeaders(), headerSecKW)
	if !ok {
		t.Fatalf("expected %s header", headerSecKW)
	}
	// Order depends on detection order; accept either permutation.
	if v != kwSec+","+kwLiteLLM && v != kwLiteLLM+","+kwSec {
		t.Errorf("expected %s to contain both keywords, got %q", headerSecKW, v)
	}
}

func TestHandleRequestBody_NoKeywordsNoHeader(t *testing.T) {
	service := newTestService(withKeywords(kwSec))

	resp, matched, err := service.handleRequestBody(&extproc.HttpBody{
		Body: chatBody(t, modelAllowed, promptWithNoKeywords),
	})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}
	if matched != nil {
		t.Errorf("expected no matches, got %v", matched)
	}

	mutation := resp.GetRequestBody().GetResponse().GetHeaderMutation()
	if _, ok := findHeader(mutation.GetSetHeaders(), headerSecKW); ok {
		t.Errorf("%s should not be set when no keywords match", headerSecKW)
	}
}

func TestHandleRequestBody_AllowedModelPassesThrough(t *testing.T) {
	service := newTestService(withAllowedModels(modelAllowed))

	resp, _, err := service.handleRequestBody(&extproc.HttpBody{
		Body: chatBody(t, modelAllowed, promptGeneric),
	})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}
	if resp.GetImmediateResponse() != nil {
		t.Error("allowed model should flow through")
	}
}

func TestHandleRequestBody_DisallowedModelRejected(t *testing.T) {
	service := newTestService(withAllowedModels(modelAllowed))

	resp, _, err := service.handleRequestBody(&extproc.HttpBody{
		Body: chatBody(t, modelDisallowed, promptGeneric),
	})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}

	ir := resp.GetImmediateResponse()
	if ir == nil {
		t.Fatal("expected ImmediateResponse for disallowed model")
	}
	if ir.GetStatus().GetCode() != httpstatus.StatusCode_Forbidden {
		t.Errorf("expected 403, got %v", ir.GetStatus().GetCode())
	}
}

func TestHandleRequestBody_AllowlistEmptyAllowsAny(t *testing.T) {
	// No allowlist configured — any model should pass.
	service := newTestService()

	resp, _, err := service.handleRequestBody(&extproc.HttpBody{
		Body: chatBody(t, modelAnything, promptGeneric),
	})
	if err != nil {
		t.Fatalf("handleRequestBody got err: %v", err)
	}
	if resp.GetImmediateResponse() != nil {
		t.Error("empty allowlist should accept any model")
	}
}

// --- Response header phase ---------------------------------------------------

func TestHandleResponseHeaders_WithMatchedKeywords(t *testing.T) {
	service := newTestService()

	resp, err := service.handleResponseHeaders(matchedKeywords())
	if err != nil {
		t.Fatalf("handleResponseHeaders got err: %v", err)
	}

	rh := resp.GetResponseHeaders()
	if rh == nil {
		t.Fatal("expected ResponseHeaders response")
	}
	mutation := rh.GetResponse().GetHeaderMutation()
	if mutation == nil {
		t.Fatal("expected HeaderMutation on response")
	}
	v, ok := findHeader(mutation.GetSetHeaders(), headerSecKW)
	if !ok {
		t.Fatalf("expected %s on response", headerSecKW)
	}
	want := kwSec + "," + kwLiteLLM
	if v != want {
		t.Errorf("expected %s=%s, got %q", headerSecKW, want, v)
	}
}

func TestHandleResponseHeaders_NoKeywordsNoHeader(t *testing.T) {
	service := newTestService()

	resp, err := service.handleResponseHeaders(nil)
	if err != nil {
		t.Fatalf("handleResponseHeaders got err: %v", err)
	}

	rh := resp.GetResponseHeaders()
	if rh == nil {
		t.Fatal("expected ResponseHeaders response")
	}
	if rh.GetResponse() != nil {
		t.Error("no keywords should mean no response mutation")
	}
}

// --- Parser helpers ----------------------------------------------------------

func TestParseCSVLower(t *testing.T) {
	cases := []struct {
		in   string
		want []string
	}{
		{"", nil},
		{"SEC, LiteLLM", []string{kwSec, kwLiteLLM}},
		{"  one  , two,three ", []string{"one", "two", "three"}},
		{",,,", nil},
	}
	for _, c := range cases {
		got := parseCSVLower(c.in)
		if len(got) != len(c.want) {
			t.Errorf("parseCSVLower(%q) len=%d, want %d", c.in, len(got), len(c.want))
			continue
		}
		for i, v := range got {
			if v != c.want[i] {
				t.Errorf("parseCSVLower(%q)[%d]=%q, want %q", c.in, i, v, c.want[i])
			}
		}
	}
}

func TestParseCSVSet(t *testing.T) {
	set := parseCSVSet("a, b ,c")
	if len(set) != 3 || !set["a"] || !set["b"] || !set["c"] {
		t.Errorf("parseCSVSet got %v", set)
	}
	if parseCSVSet("") != nil {
		t.Error("parseCSVSet(\"\") should return nil")
	}
}
