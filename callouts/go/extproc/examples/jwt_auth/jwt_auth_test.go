package jwt_auth

import (
	"io/ioutil"
	"sort"
	"strconv"
	"testing"

	"github.com/dgrijalva/jwt-go"
	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/testing/protocmp"
)

// generateTestJWTToken generates a JWT token for testing purposes.
func generateTestJWTToken(privateKey []byte, claims jwt.MapClaims) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	privateKeyParsed, err := jwt.ParseRSAPrivateKeyFromPEM(privateKey)
	if err != nil {
		return "", err
	}
	return token.SignedString(privateKeyParsed)
}

// sortHeaders sorts headers in-place by their keys.
func sortHeaders(headers []*base.HeaderValueOption) {
	sort.Slice(headers, func(i, j int) bool {
		return headers[i].Header.Key < headers[j].Header.Key
	})
}

// TestHandleRequestHeaders_ValidToken tests the handling of request headers with a valid JWT token.
func TestHandleRequestHeaders_ValidToken(t *testing.T) {
	// Load the test private key
	privateKey, err := ioutil.ReadFile("../../ssl_creds/localhost.key")
	if err != nil {
		t.Fatalf("failed to load private key: %v", err)
	}

	// Create a test JWT token
	claims := jwt.MapClaims{
		"sub":  "1234567890",
		"name": "John Doe",
		"iat":  int64(1720020355),
		"exp":  int64(1820023955),
	}
	tokenString, err := generateTestJWTToken(privateKey, claims)
	if err != nil {
		t.Fatalf("failed to generate test JWT token: %v", err)
	}

	headers := &extproc.HttpHeaders{
		Headers: &base.HeaderMap{
			Headers: []*base.HeaderValue{
				{
					Key:      "Authorization",
					RawValue: []byte("Bearer " + tokenString),
				},
			},
		},
	}

	// Create an instance of ExampleCalloutService with an overridden public key path
	service := NewExampleCalloutServiceWithKeyPath("../../ssl_creds/publickey.pem")

	// Call the HandleRequestHeaders method
	response, err := service.HandleRequestHeaders(headers)
	if err != nil {
		t.Fatalf("HandleRequestHeaders got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleRequestHeaders(): got nil resp, want non-nil")
	}

	// Prepare expected response
	wantResponse := &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: &extproc.HeadersResponse{
				Response: &extproc.CommonResponse{
					ClearRouteCache: true,
					HeaderMutation: &extproc.HeaderMutation{
						SetHeaders: []*base.HeaderValueOption{
							{
								Header: &base.HeaderValue{
									Key:      "decoded-sub",
									RawValue: []byte("1234567890"),
								},
							},
							{
								Header: &base.HeaderValue{
									Key:      "decoded-name",
									RawValue: []byte("John Doe"),
								},
							},
							{
								Header: &base.HeaderValue{
									Key:      "decoded-iat",
									RawValue: []byte(strconv.FormatInt(int64(1720020355), 10)),
								},
							},
							{
								Header: &base.HeaderValue{
									Key:      "decoded-exp",
									RawValue: []byte(strconv.FormatInt(int64(1820023955), 10)),
								},
							},
						},
					},
				},
			},
		},
	}

	// Sort headers for comparison
	sortHeaders(wantResponse.Response.(*extproc.ProcessingResponse_RequestHeaders).RequestHeaders.Response.HeaderMutation.SetHeaders)
	sortHeaders(response.Response.(*extproc.ProcessingResponse_RequestHeaders).RequestHeaders.Response.HeaderMutation.SetHeaders)

	if diff := cmp.Diff(response, wantResponse, protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() mismatch (-want +got):\n%s", diff)
	}
}

// TestHandleRequestHeaders_InvalidToken tests the handling of request headers with an invalid JWT token.
func TestHandleRequestHeaders_InvalidToken(t *testing.T) {
	headers := &extproc.HttpHeaders{
		Headers: &base.HeaderMap{
			Headers: []*base.HeaderValue{
				{
					Key:      "Authorization",
					RawValue: []byte("Bearer invalidtoken"),
				},
			},
		},
	}

	// Create an instance of ExampleCalloutService with a test public key path
	service := NewExampleCalloutServiceWithKeyPath("../../ssl_creds/publickey.pem")
	service.PublicKey = []byte("invalidpublickey")

	// Call the HandleRequestHeaders method
	_, err := service.HandleRequestHeaders(headers)

	// Check if an error occurred
	if err == nil {
		t.Fatal("HandleRequestHeaders() did not return an error, want PermissionDenied error")
	}

	// Create the expected error
	wantErr := status.Errorf(codes.PermissionDenied, "Authorization token is invalid")

	// Compare the actual error with the expected error
	if diff := cmp.Diff(status.Code(err), status.Code(wantErr)); diff != "" {
		t.Errorf("HandleRequestHeaders() error code = %v, want %v, diff: %v", status.Code(err), status.Code(wantErr), diff)
	}

	if diff := cmp.Diff(err.Error(), wantErr.Error(), protocmp.Transform()); diff != "" {
		t.Errorf("HandleRequestHeaders() error message = %v, want %v, diff: %v", err.Error(), wantErr.Error(), diff)
	}
}
