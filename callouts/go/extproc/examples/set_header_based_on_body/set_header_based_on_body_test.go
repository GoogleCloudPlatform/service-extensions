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

package set_header_based_on_body

import (
	"bytes"
	"io"
	"testing"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	extproctype "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// mockProcessStream simulates Envoy's gRPC stream for testing.
type mockProcessStream struct {
	extproc.ExternalProcessor_ProcessServer
	reqs  []*extproc.ProcessingRequest
	resps []*extproc.ProcessingResponse
}

func (m *mockProcessStream) Recv() (*extproc.ProcessingRequest, error) {
	if len(m.reqs) == 0 {
		return nil, io.EOF
	}
	req := m.reqs[0]
	m.reqs = m.reqs[1:]
	return req, nil
}

func (m *mockProcessStream) Send(resp *extproc.ProcessingResponse) error {
	m.resps = append(m.resps, resp)
	return nil
}

// --- helpers ---------------------------------------------------------------

func reqHeaders(eos bool) *extproc.ProcessingRequest {
	return &extproc.ProcessingRequest{
		Request: &extproc.ProcessingRequest_RequestHeaders{
			RequestHeaders: &extproc.HttpHeaders{EndOfStream: eos},
		},
	}
}

func reqBody(body []byte, eos bool) *extproc.ProcessingRequest {
	return &extproc.ProcessingRequest{
		Request: &extproc.ProcessingRequest_RequestBody{
			RequestBody: &extproc.HttpBody{Body: body, EndOfStream: eos},
		},
	}
}

func reqTrailers() *extproc.ProcessingRequest {
	return &extproc.ProcessingRequest{
		Request: &extproc.ProcessingRequest_RequestTrailers{
			RequestTrailers: &extproc.HttpTrailers{},
		},
	}
}

func respHeaders(eos bool) *extproc.ProcessingRequest {
	return &extproc.ProcessingRequest{
		Request: &extproc.ProcessingRequest_ResponseHeaders{
			ResponseHeaders: &extproc.HttpHeaders{EndOfStream: eos},
		},
	}
}

func respBody(body []byte, eos bool) *extproc.ProcessingRequest {
	return &extproc.ProcessingRequest{
		Request: &extproc.ProcessingRequest_ResponseBody{
			ResponseBody: &extproc.HttpBody{Body: body, EndOfStream: eos},
		},
	}
}

// streamedBodies extracts every StreamedBodyResponse (request or response side)
// in the order they were sent. FULL_DUPLEX_STREAMED requires the body to be
// returned this way, so a body response without it is a test failure.
func streamedBodies(t *testing.T, resps []*extproc.ProcessingResponse) []*extproc.StreamedBodyResponse {
	t.Helper()
	var out []*extproc.StreamedBodyResponse
	for _, r := range resps {
		var br *extproc.BodyResponse
		switch v := r.Response.(type) {
		case *extproc.ProcessingResponse_RequestBody:
			br = v.RequestBody
		case *extproc.ProcessingResponse_ResponseBody:
			br = v.ResponseBody
		default:
			continue
		}
		sr := br.GetResponse().GetBodyMutation().GetStreamedResponse()
		if sr == nil {
			t.Fatalf("body response without streamed_response: the body would be lost in FULL_DUPLEX_STREAMED mode")
		}
		out = append(out, sr)
	}
	return out
}

// checkChunks asserts size limits and that only the last chunk has EOS equal
// to wantLastEOS, and returns the reassembled body.
func checkChunks(t *testing.T, chunks []*extproc.StreamedBodyResponse, wantLastEOS bool) []byte {
	t.Helper()
	var buf bytes.Buffer
	for i, c := range chunks {
		if len(c.Body) > maxStreamedChunkSize {
			t.Errorf("chunk %d has %d bytes, max is %d", i, len(c.Body), maxStreamedChunkSize)
		}
		last := i == len(chunks)-1
		if !last && c.EndOfStream {
			t.Errorf("chunk %d (not last) has end_of_stream=true", i)
		}
		if last && c.EndOfStream != wantLastEOS {
			t.Errorf("last chunk end_of_stream=%v, want %v", c.EndOfStream, wantLastEOS)
		}
		buf.Write(c.Body)
	}
	return buf.Bytes()
}

func headerMapFrom(hm *extproc.HeaderMutation) map[string]string {
	m := make(map[string]string)
	for _, h := range hm.GetSetHeaders() {
		m[h.Header.Key] = h.Header.Value
	}
	return m
}

// --- tests -----------------------------------------------------------------

func TestHeadersOnlyWithEndOfStream(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{reqs: []*extproc.ProcessingRequest{reqHeaders(true)}}

	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) != 1 {
		t.Fatalf("Expected 1 response, got %d", len(mockStream.resps))
	}

	rh, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_RequestHeaders)
	if !ok {
		t.Fatalf("Expected RequestHeaders response")
	}
	if hm := rh.RequestHeaders.Response.HeaderMutation; hm != nil {
		if n := len(hm.SetHeaders); n > 0 {
			t.Errorf("Expected no header mutation for empty body, got %d headers", n)
		}
	}
}

func TestHeadersMutatedWhenBodyPresent(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			reqHeaders(false),
			reqBody([]byte(`{"k":"v"}`), true),
		},
	}

	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) < 1 {
		t.Fatalf("Expected at least 1 response, got %d", len(mockStream.resps))
	}

	rh, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_RequestHeaders)
	if !ok {
		t.Fatalf("Expected first response to be RequestHeaders")
	}
	hm := rh.RequestHeaders.Response.HeaderMutation
	if hm == nil || len(hm.SetHeaders) == 0 {
		t.Fatalf("Expected header mutation, got none")
	}
	for _, h := range hm.SetHeaders {
		if h.AppendAction != core.HeaderValueOption_OVERWRITE_IF_EXISTS_OR_ADD {
			t.Errorf("Expected OVERWRITE_IF_EXISTS_OR_ADD for %s, got %v", h.Header.Key, h.AppendAction)
		}
	}
}

// TestFullDuplexProcessing: body split in two chunks, EOS on the last one.
// Headers must come first, and the full body must be echoed back with EOS.
func TestFullDuplexProcessing(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			reqHeaders(false),
			reqBody([]byte(`{"status": `), false),
			reqBody([]byte(`"error"}`), true),
		},
	}

	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) != 2 {
		t.Fatalf("Expected 2 responses (Headers, Body), got %d", len(mockStream.resps))
	}

	rh, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_RequestHeaders)
	if !ok {
		t.Fatalf("Expected first response to be RequestHeaders")
	}
	headerMap := headerMapFrom(rh.RequestHeaders.Response.HeaderMutation)
	expectedHeaders := map[string]string{
		"x-body-size":      "19",
		"x-body-has-error": "true",
		"x-body-format":    "json",
	}
	for k, v := range expectedHeaders {
		if headerMap[k] != v {
			t.Errorf("Expected header %s=%s, got %s", k, v, headerMap[k])
		}
	}

	got := checkChunks(t, streamedBodies(t, mockStream.resps), true)
	if want := `{"status": "error"}`; string(got) != want {
		t.Errorf("Echoed body = %q, want %q", got, want)
	}
}

// TestFullDuplexStreamedWithTrailers simulates FULL_DUPLEX_STREAMED: body chunks
// never carry EOS; the end of the body is signaled by trailers. The body must be
// echoed back WITHOUT end_of_stream (trailers follow).
func TestFullDuplexStreamedWithTrailers(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			reqHeaders(false),
			reqBody([]byte(`<warning>xml</warning>`), false),
			reqTrailers(),
		},
	}

	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) != 3 {
		t.Fatalf("Expected 3 responses (Headers, Body, Trailers), got %d", len(mockStream.resps))
	}

	rh, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_RequestHeaders)
	if !ok {
		t.Fatalf("First response should be RequestHeaders")
	}
	headerMap := headerMapFrom(rh.RequestHeaders.Response.HeaderMutation)
	if headerMap["x-body-has-warning"] != "true" || headerMap["x-body-format"] != "xml" {
		t.Errorf("Unexpected headers: %v", headerMap)
	}

	if _, ok := mockStream.resps[1].Response.(*extproc.ProcessingResponse_RequestBody); !ok {
		t.Errorf("Second response should be RequestBody")
	}
	if _, ok := mockStream.resps[2].Response.(*extproc.ProcessingResponse_RequestTrailers); !ok {
		t.Errorf("Third response should be RequestTrailers")
	}

	got := checkChunks(t, streamedBodies(t, mockStream.resps), false)
	if want := `<warning>xml</warning>`; string(got) != want {
		t.Errorf("Echoed body = %q, want %q", got, want)
	}
}

// TestTrailersWithoutBody: headers held, trailers arrive with no body at all.
func TestTrailersWithoutBody(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{reqHeaders(false), reqTrailers()},
	}
	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) != 2 {
		t.Fatalf("Expected 2 responses (Headers, Trailers), got %d", len(mockStream.resps))
	}
	if _, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_RequestHeaders); !ok {
		t.Errorf("First response should be RequestHeaders")
	}
	if _, ok := mockStream.resps[1].Response.(*extproc.ProcessingResponse_RequestTrailers); !ok {
		t.Errorf("Second response should be RequestTrailers")
	}
}

// TestBodyChunkedToMaxSize ensures a large body is echoed back in chunks that
// respect the gRPC message size budget, reassembling to the original bytes.
func TestBodyChunkedToMaxSize(t *testing.T) {
	body := make([]byte, 3*maxStreamedChunkSize+10)
	for i := range body {
		body[i] = byte('a' + i%26)
	}

	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			reqHeaders(false),
			reqBody(body[:100000], false),
			reqBody(body[100000:], true),
		},
	}
	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}

	chunks := streamedBodies(t, mockStream.resps)
	if len(chunks) != 4 {
		t.Errorf("Expected 4 chunks, got %d", len(chunks))
	}
	if got := checkChunks(t, chunks, true); !bytes.Equal(got, body) {
		t.Errorf("Reassembled body differs from original (got %d bytes, want %d)", len(got), len(body))
	}
	if _, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_RequestHeaders); !ok {
		t.Errorf("Headers must be sent before any body chunk")
	}
}

// TestEmptyBodyWithEndOfStream: Envoy sends an empty last chunk with EOS; we
// must answer with an empty chunk carrying EOS so the stream terminates.
func TestEmptyBodyWithEndOfStream(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{reqHeaders(false), reqBody(nil, true)},
	}
	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	chunks := streamedBodies(t, mockStream.resps)
	if len(chunks) != 1 || !chunks[0].EndOfStream || len(chunks[0].Body) != 0 {
		t.Fatalf("Expected a single empty chunk with EOS, got %v", chunks)
	}
}

// TestRequestBodyTooLarge: exceeding the buffer on the request side rejects with 413.
func TestRequestBodyTooLarge(t *testing.T) {
	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			reqHeaders(false),
			reqBody(make([]byte, maxBufferSize+1), true),
		},
	}
	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) != 1 {
		t.Fatalf("Expected only the ImmediateResponse, got %d responses", len(mockStream.resps))
	}
	ir, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_ImmediateResponse)
	if !ok {
		t.Fatalf("Expected ImmediateResponse")
	}
	if code := ir.ImmediateResponse.Status.Code; code != extproctype.StatusCode_PayloadTooLarge {
		t.Errorf("Status = %v, want PayloadTooLarge", code)
	}
}

// TestResponseTruncationFlag ensures that exceeding maxBufferSize on the response
// side does NOT replace the upstream response with an ImmediateResponse; the
// truncation is flagged via header and the body is still delivered intact.
func TestResponseTruncationFlag(t *testing.T) {
	service := NewExampleCalloutService()
	largeChunk := bytes.Repeat([]byte("a"), maxBufferSize+1)

	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			respHeaders(false),
			respBody(largeChunk, true),
		},
	}
	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}
	if len(mockStream.resps) < 2 {
		t.Fatalf("Expected at least 2 responses, got %d", len(mockStream.resps))
	}

	rh, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_ResponseHeaders)
	if !ok {
		t.Fatalf("Expected first response to be ResponseHeaders")
	}
	hm := rh.ResponseHeaders.Response.HeaderMutation
	if hm == nil {
		t.Fatalf("Expected header mutation, got none")
	}
	if headerMapFrom(hm)["x-body-truncated"] != "true" {
		t.Errorf("Expected x-body-truncated: true header, not found")
	}

	got := checkChunks(t, streamedBodies(t, mockStream.resps), true)
	if !bytes.Equal(got, largeChunk) {
		t.Errorf("Body not delivered intact (got %d bytes, want %d)", len(got), len(largeChunk))
	}
}

// TestResponseTruncationAfterBuffering: the first chunk fits in the buffer, the
// second overflows it. The buffered prefix must be flushed (after the headers)
// and the overflowing chunk passed through, preserving byte order.
func TestResponseTruncationAfterBuffering(t *testing.T) {
	first := bytes.Repeat([]byte("x"), maxBufferSize/2)
	second := bytes.Repeat([]byte("y"), maxBufferSize)
	want := append(append([]byte{}, first...), second...)

	service := NewExampleCalloutService()
	mockStream := &mockProcessStream{
		reqs: []*extproc.ProcessingRequest{
			respHeaders(false),
			respBody(first, false),
			respBody(second, true),
		},
	}
	if err := service.Process(mockStream); err != nil {
		t.Fatalf("Process() returned unexpected error: %v", err)
	}

	rh, ok := mockStream.resps[0].Response.(*extproc.ProcessingResponse_ResponseHeaders)
	if !ok {
		t.Fatalf("Expected first response to be ResponseHeaders")
	}
	if headerMapFrom(rh.ResponseHeaders.Response.HeaderMutation)["x-body-truncated"] != "true" {
		t.Errorf("Expected x-body-truncated: true")
	}
	if got := checkChunks(t, streamedBodies(t, mockStream.resps), true); !bytes.Equal(got, want) {
		t.Errorf("Body differs from original (got %d bytes, want %d)", len(got), len(want))
	}
}
