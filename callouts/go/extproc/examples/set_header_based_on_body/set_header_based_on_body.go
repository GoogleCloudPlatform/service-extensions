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
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	extproctype "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

const (
	maxBufferSize = 2 * 1024 * 1024 // 2MB max buffer size

	// maxStreamedChunkSize is the maximum size of a single body chunk sent back
	// to Envoy. The gRPC max message size is 128 KiB; using 62,000 bytes gives
	// a safety margin for protobuf overhead, matching common Envoy ext_proc
	// implementations.
	maxStreamedChunkSize = 62000
)

// errStopStream signals that processing should end (e.g. after an ImmediateResponse).
var errStopStream = errors.New("stop processing stream")

// ExampleCalloutService implements a stateful External Processing service for Envoy.
//
// It is designed for processing_mode FULL_DUPLEX_STREAMED: it buffers the whole
// request/response body, computes header mutations from the buffered content,
// and only then releases (in this order) the header response, the body (echoed
// back unchanged, chunked to stay below the gRPC message size limit) and the
// trailers. State is stream-local, so no global locks are needed.
//
// In FULL_DUPLEX_STREAMED mode Envoy does NOT forward the body by itself: the
// server must send every byte back in StreamedBodyResponse messages, otherwise
// the body is lost. There is no 1:1 relation between received and sent body
// messages.
type ExampleCalloutService struct {
	extproc.UnimplementedExternalProcessorServer
}

// NewExampleCalloutService creates a new instance of the callout service.
func NewExampleCalloutService() *ExampleCalloutService {
	return &ExampleCalloutService{}
}

// Process handles the bidirectional stream of processing requests from Envoy.
func (s *ExampleCalloutService) Process(stream extproc.ExternalProcessor_ProcessServer) error {
	req := &sideState{isRequest: true}
	resp := &sideState{isRequest: false}

	for {
		msg, err := stream.Recv()
		if err == io.EOF {
			// Safety net: release anything still held when Envoy half-closes.
			if err := req.flush(stream, false); err != nil {
				return err
			}
			return resp.flush(stream, false)
		}
		if err != nil {
			return err
		}

		switch m := msg.Request.(type) {
		case *extproc.ProcessingRequest_RequestHeaders:
			if err := req.onHeaders(stream, m.RequestHeaders.EndOfStream); err != nil {
				return err
			}
		case *extproc.ProcessingRequest_RequestBody:
			if err := req.onBody(stream, m.RequestBody.Body, m.RequestBody.EndOfStream); err != nil {
				if errors.Is(err, errStopStream) {
					return nil
				}
				return err
			}
		case *extproc.ProcessingRequest_RequestTrailers:
			if err := req.onTrailers(stream); err != nil {
				return err
			}
		case *extproc.ProcessingRequest_ResponseHeaders:
			if err := resp.onHeaders(stream, m.ResponseHeaders.EndOfStream); err != nil {
				return err
			}
		case *extproc.ProcessingRequest_ResponseBody:
			if err := resp.onBody(stream, m.ResponseBody.Body, m.ResponseBody.EndOfStream); err != nil {
				if errors.Is(err, errStopStream) {
					return nil
				}
				return err
			}
		case *extproc.ProcessingRequest_ResponseTrailers:
			if err := resp.onTrailers(stream); err != nil {
				return err
			}
		}
	}
}

// sideState tracks the processing state for one direction (request or response).
type sideState struct {
	isRequest bool

	// body holds the buffered body that has not been sent back to Envoy yet.
	body bytes.Buffer

	// truncated is set when the buffer limit is exceeded on the response side.
	// From that point on the buffered bytes have been flushed and every
	// following chunk is passed through untouched.
	truncated bool

	// headersDelayed is true while the header response is being held until the
	// body (or trailers) has been seen.
	headersDelayed bool
}

// onHeaders holds the header response until body/trailers arrive, unless Envoy
// signals end-of-stream (no body will follow).
func (s *sideState) onHeaders(stream extproc.ExternalProcessor_ProcessServer, eos bool) error {
	if eos {
		return s.sendHeadersResponse(stream)
	}
	s.headersDelayed = true
	return nil
}

// onBody buffers the chunk and releases everything once the end of the body is
// known. In FULL_DUPLEX_STREAMED mode, chunks carry no EOS when trailers
// follow; in that case onTrailers drives the flush.
func (s *sideState) onBody(stream extproc.ExternalProcessor_ProcessServer, chunk []byte, eos bool) error {
	// Already past the limit: pass the data through untouched.
	if s.truncated {
		return s.sendBodyChunks(stream, chunk, eos)
	}

	if s.body.Len()+len(chunk) > maxBufferSize {
		if s.isRequest {
			if err := sendImmediateResponse(stream, extproctype.StatusCode_PayloadTooLarge, "request_body_buffer_exceeded"); err != nil {
				return err
			}
			return errStopStream
		}
		// Response side: never replace the upstream response with an error.
		// Release headers (flagged as truncated) and the buffered prefix, then
		// stream the rest through without buffering.
		s.truncated = true
		if err := s.flush(stream, false); err != nil {
			return err
		}
		return s.sendBodyChunks(stream, chunk, eos)
	}

	s.body.Write(chunk)
	if eos {
		return s.flush(stream, true)
	}
	return nil
}

// onTrailers releases pending state (the body ends here, so its last chunk is
// sent without end_of_stream), then forwards the trailers.
func (s *sideState) onTrailers(stream extproc.ExternalProcessor_ProcessServer) error {
	if err := s.flush(stream, false); err != nil {
		return err
	}

	var resp *extproc.ProcessingResponse
	if s.isRequest {
		resp = &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestTrailers{
				RequestTrailers: &extproc.TrailersResponse{},
			},
		}
	} else {
		resp = &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ResponseTrailers{
				ResponseTrailers: &extproc.TrailersResponse{},
			},
		}
	}
	return stream.Send(resp)
}

// flush releases the delayed header response followed by the buffered body,
// preserving the Headers -> Body -> Trailers order expected by Envoy.
// bodyEOS is true only when Envoy itself marked the last body chunk as EOS
// (i.e. no trailers follow).
func (s *sideState) flush(stream extproc.ExternalProcessor_ProcessServer, bodyEOS bool) error {
	if s.headersDelayed {
		if err := s.sendHeadersResponse(stream); err != nil {
			return err
		}
		s.headersDelayed = false
	}

	if s.body.Len() == 0 && !bodyEOS {
		return nil
	}
	err := s.sendBodyChunks(stream, s.body.Bytes(), bodyEOS)
	s.body.Reset()
	return err
}

// sendBodyChunks sends data back to Envoy split in chunks of at most
// maxStreamedChunkSize. Only the last chunk carries eos. An empty body with
// eos=true is still sent as a single empty chunk so Envoy sees the end of stream.
func (s *sideState) sendBodyChunks(stream extproc.ExternalProcessor_ProcessServer, data []byte, eos bool) error {
	if len(data) == 0 {
		if eos {
			return s.sendStreamedBody(stream, nil, true)
		}
		return nil
	}
	for len(data) > 0 {
		n := len(data)
		if n > maxStreamedChunkSize {
			n = maxStreamedChunkSize
		}
		last := n == len(data)
		if err := s.sendStreamedBody(stream, data[:n], eos && last); err != nil {
			return err
		}
		data = data[n:]
	}
	return nil
}

// sendStreamedBody emits a single streamed body chunk.
func (s *sideState) sendStreamedBody(stream extproc.ExternalProcessor_ProcessServer, chunk []byte, eos bool) error {
	common := &extproc.CommonResponse{
		BodyMutation: &extproc.BodyMutation{
			Mutation: &extproc.BodyMutation_StreamedResponse{
				StreamedResponse: &extproc.StreamedBodyResponse{
					Body:        chunk,
					EndOfStream: eos,
				},
			},
		},
	}

	var resp *extproc.ProcessingResponse
	if s.isRequest {
		resp = &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestBody{
				RequestBody: &extproc.BodyResponse{Response: common},
			},
		}
	} else {
		resp = &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ResponseBody{
				ResponseBody: &extproc.BodyResponse{Response: common},
			},
		}
	}
	return stream.Send(resp)
}

// sendHeadersResponse computes header mutations based on buffered body and dispatches the response.
// When the response body exceeded the buffer limit, the analysis only covers
// the buffered prefix and x-body-truncated is set.
func (s *sideState) sendHeadersResponse(stream extproc.ExternalProcessor_ProcessServer) error {
	var mutation *extproc.HeaderMutation
	if s.body.Len() > 0 || s.truncated {
		headers := analyzeBodyAndCreateHeaders(s.body.String())
		if s.truncated {
			headers["x-body-truncated"] = "true"
		}
		mutation = &extproc.HeaderMutation{SetHeaders: convertToEnvoyHeaders(headers)}
	}

	var resp *extproc.ProcessingResponse
	if s.isRequest {
		resp = &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestHeaders{
				RequestHeaders: &extproc.HeadersResponse{
					Response: &extproc.CommonResponse{HeaderMutation: mutation},
				},
			},
		}
	} else {
		resp = &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_ResponseHeaders{
				ResponseHeaders: &extproc.HeadersResponse{
					Response: &extproc.CommonResponse{HeaderMutation: mutation},
				},
			},
		}
	}
	return stream.Send(resp)
}

// sendImmediateResponse cleanly rejects the request when safety limits are breached.
func sendImmediateResponse(stream extproc.ExternalProcessor_ProcessServer, code extproctype.StatusCode, details string) error {
	resp := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: &extproc.ImmediateResponse{
				Status:  &extproctype.HttpStatus{Code: code},
				Details: details,
			},
		},
	}
	return stream.Send(resp)
}

// analyzeBodyAndCreateHeaders determines new header states via body string inspection.
func analyzeBodyAndCreateHeaders(bodyContent string) map[string]string {
	headers := make(map[string]string)
	headers["x-body-size"] = fmt.Sprintf("%d", len(bodyContent))

	lower := strings.ToLower(bodyContent)
	if strings.Contains(lower, "error") {
		headers["x-body-has-error"] = "true"
	}
	if strings.Contains(lower, "warning") {
		headers["x-body-has-warning"] = "true"
	}

	trimmedBody := strings.TrimSpace(bodyContent)
	if (strings.HasPrefix(trimmedBody, "{") && strings.HasSuffix(trimmedBody, "}")) ||
		(strings.HasPrefix(trimmedBody, "[") && strings.HasSuffix(trimmedBody, "]")) {
		headers["x-body-format"] = "json"
	} else if strings.HasPrefix(trimmedBody, "<") && strings.HasSuffix(trimmedBody, ">") {
		headers["x-body-format"] = "xml"
	} else {
		headers["x-body-format"] = "text"
	}

	return headers
}

// convertToEnvoyHeaders transforms standard map pairs into the structured protobuf type
// using the explicit OVERWRITE_IF_EXISTS_OR_ADD action to prevent duplicates.
// Keys are sorted so the output is deterministic.
func convertToEnvoyHeaders(headers map[string]string) []*core.HeaderValueOption {
	keys := make([]string, 0, len(headers))
	for k := range headers {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	result := make([]*core.HeaderValueOption, 0, len(keys))
	for _, key := range keys {
		result = append(result, &core.HeaderValueOption{
			Header: &core.HeaderValue{
				Key:   key,
				Value: headers[key],
			},
			AppendAction: core.HeaderValueOption_OVERWRITE_IF_EXISTS_OR_ADD,
		})
	}
	return result
}
