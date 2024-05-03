package main
 
import (
	"crypto/tls"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/reflection"
	"log"
	"net"
	"net/http"
	"os"
)
 
func main() {
 
	dir, err := os.Getwd()
	if err != nil {
		log.Fatal(err)
	}
	log.Println("Current working directory:", dir)
 
	config := loadConfig()
	server := NewCalloutServer(config)
	go server.StartGRPC()
	go server.StartInsecureGRPC()
	go server.StartHealthCheck()
	// Block forever or handle signals as needed
	select {}
}
 
func loadConfig() ServerConfig {
	// Load configuration from environment variables or default
	return ServerConfig{
		Address:              "0.0.0.0:8443",
		InsecureAddress:      "0.0.0.0:8181",
		HealthCheckAddress:   "0.0.0.0:8000",
		CertFile: 			  "extproc/ssl_creds/localhost.crt",
		KeyFile:              "extproc/ssl_creds/localhost.key",
		SecureHealthCheck:    true,
		EnableInsecureServer: true,
	}
}
 
type ServerConfig struct {
	Address              string
	InsecureAddress      string
	HealthCheckAddress   string
	CertFile             string
	KeyFile              string
	SecureHealthCheck    bool
	CombinedHealthCheck  bool
	EnableInsecureServer bool
}
 
type CalloutServer struct {
	Config ServerConfig
	Cert   tls.Certificate
}
 
func NewCalloutServer(config ServerConfig) *CalloutServer {
	cert, err := tls.LoadX509KeyPair(config.CertFile, config.KeyFile)
	if err != nil {
		log.Fatalf("Failed to load server certificate: %v", err)
	}
	return &CalloutServer{
		Config: config,
		Cert:   cert,
	}
}
 
func (s *CalloutServer) StartGRPC() {
	lis, err := net.Listen("tcp", s.Config.Address)
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}
	creds := credentials.NewServerTLSFromCert(&s.Cert)
	grpcServer := grpc.NewServer(grpc.Creds(creds))
	extproc.RegisterExternalProcessorServer(grpcServer, &GRPCCalloutService{})
	reflection.Register(grpcServer)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC: %v", err)
	}
}
 
func (s *CalloutServer) StartHealthCheck() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
 
	var server *http.Server = &http.Server{
		Addr:    s.Config.HealthCheckAddress,
		Handler: mux,
	}
 
	if s.Config.SecureHealthCheck {
		server.TLSConfig = &tls.Config{Certificates: []tls.Certificate{s.Cert}}
		log.Fatal(server.ListenAndServeTLS("", "")) // Use the same cert as gRPC
	} else {
		log.Fatal(server.ListenAndServe())
	}
}
 
func (s *CalloutServer) StartInsecureGRPC() {
	if !s.Config.EnableInsecureServer {
		return
	}
	lis, err := net.Listen("tcp", s.Config.InsecureAddress)
	if err != nil {
		log.Fatalf("Failed to listen on insecure port: %v", err)
	}
	grpcServer := grpc.NewServer() // No TLS credentials
	extproc.RegisterExternalProcessorServer(grpcServer, &GRPCCalloutService{})
	reflection.Register(grpcServer)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC on insecure port: %v", err)
	}
}
 
type GRPCCalloutService struct {
	extproc.UnimplementedExternalProcessorServer
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
			response, err = s.handleRequestHeaders(req.GetRequestHeaders())
		case req.GetResponseHeaders() != nil:
			response, err = s.handleResponseHeaders(req.GetResponseHeaders())
		case req.GetRequestBody() != nil:
			response, err = s.handleRequestBody(req.GetRequestBody())
		case req.GetResponseBody() != nil:
			response, err = s.handleResponseBody(req.GetResponseBody())
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
 
func (s *GRPCCalloutService) handleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{},
		},
	}, nil
}
 
func (s *GRPCCalloutService) handleResponseHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseHeaders{
			ResponseHeaders: &extproc.HeadersResponse{},
		},
	}, nil
}
 
func (s *GRPCCalloutService) handleRequestBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestBody{
			RequestBody: &extproc.BodyResponse{},
		},
	}, nil
}
 
func (s *GRPCCalloutService) handleResponseBody(body *extproc.HttpBody) (*extproc.ProcessingResponse, error) {
	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_ResponseBody{
			ResponseBody: &extproc.BodyResponse{},
		},
	}, nil
}