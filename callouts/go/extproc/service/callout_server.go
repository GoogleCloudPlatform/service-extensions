// Copyright 2024 Google LLC.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package callout_server

import (
	"crypto/tls"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/reflection"
	"log"
	"net"
	"net/http"
)

func loadConfig() ServerConfig {
	// Load configuration from environment variables or default
	return ServerConfig{
		Address:              "0.0.0.0:8443",
		InsecureAddress:      "0.0.0.0:8181",
		HealthCheckAddress:   "0.0.0.0:8000",
		CertFile:             "extproc/ssl_creds/localhost.crt",
		KeyFile:              "extproc/ssl_creds/localhost.key",
		EnableInsecureServer: true,
	}
}

type ServerConfig struct {
	Address              string
	InsecureAddress      string
	HealthCheckAddress   string
	CertFile             string
	KeyFile              string
	EnableInsecureServer bool
}

type CalloutServer struct {
	Config ServerConfig
	Cert   tls.Certificate
}

func NewCalloutServer(config ServerConfig) *CalloutServer {
	var cert tls.Certificate
	var err error

	if config.CertFile != "" && config.KeyFile != "" {
		cert, err = tls.LoadX509KeyPair(config.CertFile, config.KeyFile)
		if err != nil {
			log.Fatalf("Failed to load server certificate: %v", err)
		}
	}

	return &CalloutServer{
		Config: config,
		Cert:   cert,
	}
}

func (s *CalloutServer) StartGRPC(service extproc.ExternalProcessorServer) {
	lis, err := net.Listen("tcp", s.Config.Address)
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}
	creds := credentials.NewServerTLSFromCert(&s.Cert)
	grpcServer := grpc.NewServer(grpc.Creds(creds))
	extproc.RegisterExternalProcessorServer(grpcServer, service)
	reflection.Register(grpcServer)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC: %v", err)
	}
}

func (s *CalloutServer) StartHealthCheck() {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	var server *http.Server = &http.Server{
		Addr:    s.Config.HealthCheckAddress,
		Handler: mux,
	}

	log.Fatal(server.ListenAndServe())
}

func (s *CalloutServer) StartInsecureGRPC(service extproc.ExternalProcessorServer) {
	if !s.Config.EnableInsecureServer {
		return
	}
	lis, err := net.Listen("tcp", s.Config.InsecureAddress)
	if err != nil {
		log.Fatalf("Failed to listen on insecure port: %v", err)
	}
	grpcServer := grpc.NewServer() // No TLS credentials
	extproc.RegisterExternalProcessorServer(grpcServer, service)
	reflection.Register(grpcServer)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC on insecure port: %v", err)
	}
}

type RequestHeadersHandler func(*extproc.HttpHeaders) (*extproc.ProcessingResponse, error)
type ResponseHeadersHandler func(*extproc.HttpHeaders) (*extproc.ProcessingResponse, error)
type RequestBodyHandler func(*extproc.HttpBody) (*extproc.ProcessingResponse, error)
type ResponseBodyHandler func(*extproc.HttpBody) (*extproc.ProcessingResponse, error)
type RequestTrailersHandler func(*extproc.HttpTrailers) (*extproc.ProcessingResponse, error)
type ResponseTrailersHandler func(*extproc.HttpTrailers) (*extproc.ProcessingResponse, error)

type HandlerRegistry struct {
	RequestHeadersHandler   RequestHeadersHandler
	ResponseHeadersHandler  ResponseHeadersHandler
	RequestBodyHandler      RequestBodyHandler
	ResponseBodyHandler     ResponseBodyHandler
	RequestTrailersHandler  RequestTrailersHandler
	ResponseTrailersHandler ResponseTrailersHandler
}

type GRPCCalloutService struct {
	extproc.UnimplementedExternalProcessorServer
	Handlers HandlerRegistry
}

func (s *GRPCCalloutService) Process(stream extproc.ExternalProcessor_ProcessServer) error {
	for {
		req, err := stream.Recv()
		if err != nil {
			return err
		}

		var response *extproc.ProcessingResponse
		switch {
		case req.GetRequestHeaders() != nil:
			if s.Handlers.RequestHeadersHandler != nil {
				response, err = s.Handlers.RequestHeadersHandler(req.GetRequestHeaders())
			}
		case req.GetResponseHeaders() != nil:
			if s.Handlers.ResponseHeadersHandler != nil {
				response, err = s.Handlers.ResponseHeadersHandler(req.GetResponseHeaders())
			}
		case req.GetRequestBody() != nil:
			if s.Handlers.RequestBodyHandler != nil {
				response, err = s.Handlers.RequestBodyHandler(req.GetRequestBody())
			}
		case req.GetResponseBody() != nil:
			if s.Handlers.ResponseBodyHandler != nil {
				response, err = s.Handlers.ResponseBodyHandler(req.GetResponseBody())
			}
		case req.GetRequestTrailers() != nil:
			if s.Handlers.RequestTrailersHandler != nil {
				response, err = s.Handlers.RequestTrailersHandler(req.GetRequestTrailers())
			}
		case req.GetResponseTrailers() != nil:
			if s.Handlers.ResponseTrailersHandler != nil {
				response, err = s.Handlers.ResponseTrailersHandler(req.GetResponseTrailers())
			}
		}

		if err != nil {
			return err
		}

		if response != nil {
			if err := stream.Send(response); err != nil {
				return err
			}
		}
	}
}

func (s *GRPCCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
	}, nil
}

func (s *GRPCCalloutService) HandleResponseHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{},
		},
	}, nil
}

func (s *GRPCCalloutService) HandleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{},
		},
	}, nil
}

func (s *GRPCCalloutService) HandleResponseBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: &extproc.BodyResponse{},
		},
	}, nil
}

func (s *GRPCCalloutService) HandleRequestTrailers(trailers *extproc.HttpTrailers) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestTrailers{
			RequestTrailers: &extproc.TrailersResponse{},
		},
	}, nil
}

func (s *GRPCCalloutService) HandleResponseTrailers(trailers *extproc.HttpTrailers) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseTrailers{
			ResponseTrailers: &extproc.TrailersResponse{},
		},
	}, nil
}
