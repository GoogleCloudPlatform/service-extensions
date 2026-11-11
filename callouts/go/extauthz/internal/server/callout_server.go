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

package server

import (
	"context"
	"crypto/tls"
	"log"
	"net"
	"net/http"

	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	rpcstatus "google.golang.org/genproto/googleapis/rpc/status"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/reflection"
)

// Config holds the server configuration parameters.
type Config struct {
	Address            string
	InsecureAddress    string
	HealthCheckAddress string
	CertFile           string
	KeyFile            string
}

// CalloutServer represents a server that handles extauthz callouts.
type CalloutServer struct {
	Config Config
	Cert   tls.Certificate
}

// NewCalloutServer creates a new CalloutServer with the given configuration.
func NewCalloutServer(config Config) *CalloutServer {
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

// StartGRPC starts the gRPC server with the specified service.
func (s *CalloutServer) StartGRPC(service auth.AuthorizationServer) {
	lis, err := net.Listen("tcp", s.Config.Address)
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	var opts []grpc.ServerOption
	if s.Cert.Certificate != nil {
		creds := credentials.NewServerTLSFromCert(&s.Cert)
		opts = append(opts, grpc.Creds(creds))
	}

	grpcServer := grpc.NewServer(opts...)
	auth.RegisterAuthorizationServer(grpcServer, service)
	reflection.Register(grpcServer)

	log.Printf("Starting secure gRPC server on %s", s.Config.Address)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC: %v", err)
	}
}

// StartInsecureGRPC starts the gRPC server without TLS.
func (s *CalloutServer) StartInsecureGRPC(service auth.AuthorizationServer) {
	lis, err := net.Listen("tcp", s.Config.InsecureAddress)
	if err != nil {
		log.Fatalf("Failed to listen on insecure port: %v", err)
	}

	grpcServer := grpc.NewServer()
	auth.RegisterAuthorizationServer(grpcServer, service)
	reflection.Register(grpcServer)

	log.Printf("Starting insecure gRPC server on %s", s.Config.InsecureAddress)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC on insecure port: %v", err)
	}
}

// StartHealthCheck starts a health check server.
func (s *CalloutServer) StartHealthCheck() {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

	server := &http.Server{
		Addr:    s.Config.HealthCheckAddress,
		Handler: mux,
	}

	log.Printf("Starting health check server on %s", s.Config.HealthCheckAddress)
	log.Fatal(server.ListenAndServe())
}

// CheckHandler defines the function signature for authorization check handlers
type CheckHandler func(context.Context, *auth.CheckRequest) (*auth.CheckResponse, error)

// GRPCCalloutService implements the gRPC AuthorizationServer.
type GRPCCalloutService struct {
	auth.UnimplementedAuthorizationServer
	CheckHandler CheckHandler
}

// Check processes incoming auth check requests.
func (s *GRPCCalloutService) Check(ctx context.Context, req *auth.CheckRequest) (*auth.CheckResponse, error) {
	if s.CheckHandler != nil {
		return s.CheckHandler(ctx, req)
	}
	return &auth.CheckResponse{
		Status: &rpcstatus.Status{Code: int32(codes.OK)},
	}, nil
}
