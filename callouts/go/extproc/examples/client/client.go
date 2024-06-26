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
	"context"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net"
	"sync"
	"time"

	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/encoding/protojson"
)

// server is an implementation of extproc.ExternalProcessorServer.
type server struct {
	extproc.UnimplementedExternalProcessorServer
}

// Process processes incoming gRPC streams.
func (s *server) Process(stream extproc.ExternalProcessor_ProcessServer) error {
	for {
		req, err := stream.Recv()
		if err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}

		log.Printf("Received request: %v", req)

		// Respond with a dummy ProcessingResponse for demonstration
		response := &extproc.ProcessingResponse{
			Response: &extproc.ProcessingResponse_RequestHeaders{
				RequestHeaders: &extproc.HeadersResponse{},
			},
		}
		if err := stream.Send(response); err != nil {
			return err
		}
	}
}

// startServer starts a gRPC server at the specified address.
func startServer(wg *sync.WaitGroup, address string) {
	lis, err := net.Listen("tcp", address)
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}
	grpcServer := grpc.NewServer()
	extproc.RegisterExternalProcessorServer(grpcServer, &server{})
	log.Printf("Server listening at %v", lis.Addr())
	wg.Done()
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC: %v", err)
	}
}

var (
	tls        = flag.Bool("tls", false, "Connection uses TLS if true, else plain TCP")
	certFile   = flag.String("cert_file", "", "The file containing the CA root cert file")
	serverAddr = flag.String("addr", "localhost:8181", "The server address in the format of host:port")
	dataJSON   = flag.String("data", "", "The JSON string containing the ProcessingRequest data")
)

// makeChannel creates a gRPC client connection to the given address.
func makeChannel(addr string, useTLS bool, certFile string) (*grpc.ClientConn, error) {
	if useTLS {
		creds, err := credentials.NewClientTLSFromFile(certFile, "")
		if err != nil {
			return nil, err
		}
		return grpc.Dial(addr, grpc.WithTransportCredentials(creds))
	}
	return grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

// makeJSONRequest sends ProcessingRequest objects read from a JSON string and receives ProcessingResponse objects.
func makeJSONRequest(address string, useTLS bool, certFile, jsonData string) ([]*extproc.ProcessingResponse, error) {
	conn, err := makeChannel(address, useTLS, certFile)
	if err != nil {
		return nil, err
	}
	defer func(conn *grpc.ClientConn) {
		err := conn.Close()
		if err != nil {

		}
	}(conn)

	client := extproc.NewExternalProcessorClient(conn)

	// Unmarshal the JSON string into a slice of ProcessingRequest
	var rawRequests []map[string]interface{}
	if err := json.Unmarshal([]byte(jsonData), &rawRequests); err != nil {
		return nil, err
	}

	var requests []*extproc.ProcessingRequest
	for _, rawReq := range rawRequests {
		reqBytes, err := json.Marshal(rawReq)
		if err != nil {
			return nil, err
		}
		req := &extproc.ProcessingRequest{}
		if err := protojson.Unmarshal(reqBytes, req); err != nil {
			return nil, err
		}
		requests = append(requests, req)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	stream, err := client.Process(ctx)
	if err != nil {
		return nil, err
	}

	for _, req := range requests {
		if err := stream.Send(req); err != nil {
			return nil, err
		}
		log.Printf("Sent request: %v", req)
	}

	// Close the send direction of the stream to signal the server that all messages have been sent.
	if err := stream.CloseSend(); err != nil {
		return nil, err
	}

	var responses []*extproc.ProcessingResponse
	for {
		resp, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		responses = append(responses, resp)
		log.Printf("Received response: %v", resp)
	}

	return responses, nil
}

func main() {
	flag.Parse()

	if *dataJSON == "" {
		log.Fatal("Data JSON is required")
	}

	var wg sync.WaitGroup
	wg.Add(1)

	// Start the server in a goroutine
	go startServer(&wg, *serverAddr)

	// Wait for the server to start
	wg.Wait()
	time.Sleep(3 * time.Second) // Ensure the server has enough time to start

	responses, err := makeJSONRequest(*serverAddr, *tls, *certFile, *dataJSON)
	if err != nil {
		log.Fatalf("Failed to make JSON request: %v", err)
	}

	for _, resp := range responses {
		respJSON, err := protojson.Marshal(resp)
		if err != nil {
			log.Fatalf("Failed to marshal response to JSON: %v", err)
		}
		log.Printf("Response: %s", string(respJSON))
	}
}
