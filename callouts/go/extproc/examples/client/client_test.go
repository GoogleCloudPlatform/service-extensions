// Copyright 2024 Google LLC.
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

package main

import (
	"io"
	"log"
	"net"
	"strings"
	"sync"
	"testing"
	"time"

	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/testing/protocmp"
	"service-extensions-samples/extproc/pkg/utils"
)

// testServer implements the extproc.ExternalProcessorServer interface for testing purposes.
type testServer struct {
	extproc.UnimplementedExternalProcessorServer
}

// Process handles incoming gRPC streams and sends appropriate responses.
func (s *testServer) Process(stream extproc.ExternalProcessor_ProcessServer) error {
	for {
		req, err := stream.Recv()
		if err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}

		var response *extproc.ProcessingResponse

		switch {
		case req.GetRequestHeaders() != nil:
			response = &extproc.ProcessingResponse{
				Response: &extproc.ProcessingResponse_RequestHeaders{
					RequestHeaders: &extproc.HeadersResponse{
						Response: &extproc.CommonResponse{
							HeaderMutation: &extproc.HeaderMutation{
								SetHeaders: []*base.HeaderValueOption{
									{
										Header: &base.HeaderValue{
											Key:      "processed-header",
											RawValue: []byte("processed-value"),
										},
									},
								},
							},
						},
					},
				},
			}
		case req.GetRequestBody() != nil:
			response = &extproc.ProcessingResponse{
				Response: &extproc.ProcessingResponse_RequestBody{
					RequestBody: &extproc.BodyResponse{
						Response: &extproc.CommonResponse{
							BodyMutation: &extproc.BodyMutation{
								Mutation: &extproc.BodyMutation_Body{
									Body: []byte("replaced-body"),
								},
							},
						},
					},
				},
			}
		case req.GetResponseHeaders() != nil:
			response = &extproc.ProcessingResponse{
				Response: &extproc.ProcessingResponse_ResponseHeaders{
					ResponseHeaders: &extproc.HeadersResponse{
						Response: &extproc.CommonResponse{
							HeaderMutation: &extproc.HeaderMutation{
								SetHeaders: []*base.HeaderValueOption{
									{
										Header: &base.HeaderValue{
											Key:      "response-processed-header",
											RawValue: []byte("response-processed-value"),
										},
									},
								},
							},
						},
					},
				},
			}
		case req.GetResponseBody() != nil:
			response = &extproc.ProcessingResponse{
				Response: &extproc.ProcessingResponse_ResponseBody{
					ResponseBody: &extproc.BodyResponse{
						Response: &extproc.CommonResponse{
							BodyMutation: &extproc.BodyMutation{
								Mutation: &extproc.BodyMutation_ClearBody{
									ClearBody: true,
								},
							},
						},
					},
				},
			}
		default:
			// Handle empty request
			response = &extproc.ProcessingResponse{}
		}

		if response != nil {
			if err := stream.Send(response); err != nil {
				return err
			}
		}
	}
}

// startTestServer starts the test gRPC server on the given address.
func startTestServer(wg *sync.WaitGroup, address string) {
	lis, err := net.Listen("tcp", address)
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}
	grpcServer := grpc.NewServer()
	extproc.RegisterExternalProcessorServer(grpcServer, &testServer{})
	wg.Done()
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC: %v", err)
	}
}

// TestGRPCCalloutService tests the gRPC callout service by sending predefined requests and comparing the responses with expected values.
func TestGRPCCalloutService(t *testing.T) {
	serverAddress := "localhost:8181"
	var wg sync.WaitGroup
	wg.Add(1)
	go startTestServer(&wg, serverAddress)
	wg.Wait()
	time.Sleep(3 * time.Second) // Ensure the server has enough time to start

	tests := []struct {
		name     string
		requests []*extproc.ProcessingRequest
		expected []*extproc.ProcessingResponse
	}{
		{
			name: "EmptyData",
			requests: []*extproc.ProcessingRequest{
				{},
			},
			expected: []*extproc.ProcessingResponse{
				{},
			},
		},
		{
			name: "BasicCallouts",
			requests: []*extproc.ProcessingRequest{
				{Request: &extproc.ProcessingRequest_RequestBody{RequestBody: &extproc.HttpBody{}}},
				{Request: &extproc.ProcessingRequest_ResponseBody{ResponseBody: &extproc.HttpBody{}}},
				{Request: &extproc.ProcessingRequest_RequestHeaders{RequestHeaders: &extproc.HttpHeaders{}}},
				{Request: &extproc.ProcessingRequest_ResponseHeaders{ResponseHeaders: &extproc.HttpHeaders{}}},
			},
			expected: []*extproc.ProcessingResponse{
				{Response: &extproc.ProcessingResponse_RequestBody{
					RequestBody: utils.AddBodyStringMutation("replaced-body", false),
				}},
				{Response: &extproc.ProcessingResponse_ResponseBody{
					ResponseBody: utils.AddBodyClearMutation(false),
				}},
				{Response: &extproc.ProcessingResponse_RequestHeaders{
					RequestHeaders: utils.AddHeaderMutation([]struct{ Key, Value string }{{Key: "processed-header", Value: "processed-value"}}, nil, false, nil),
				}},
				{Response: &extproc.ProcessingResponse_ResponseHeaders{
					ResponseHeaders: utils.AddHeaderMutation([]struct{ Key, Value string }{{Key: "response-processed-header", Value: "response-processed-value"}}, nil, false, nil),
				}},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Marshal requests to JSON
			var reqJSONStrings []string
			for _, req := range tt.requests {
				reqBytes, err := protojson.Marshal(req)
				if err != nil {
					t.Fatalf("Failed to marshal request to JSON: %v", err)
				}
				reqJSONStrings = append(reqJSONStrings, string(reqBytes))
			}

			// Create a single JSON string from the slice of JSON strings
			jsonData := "[" + strings.Join(reqJSONStrings, ",") + "]"

			// Call makeJSONRequest with the JSON string
			responses, err := makeJSONRequest(serverAddress, false, "", jsonData)
			if err != nil {
				t.Fatalf("Failed to send requests: %v", err)
			}

			if len(responses) != len(tt.expected) {
				t.Fatalf("Expected %d responses, got %d", len(tt.expected), len(responses))
			}

			for i, resp := range responses {
				if diff := cmp.Diff(tt.expected[i], resp, protocmp.Transform()); diff != "" {
					t.Errorf("Response mismatch (-want +got):\n%s", diff)
				}
			}
		})
	}
}
