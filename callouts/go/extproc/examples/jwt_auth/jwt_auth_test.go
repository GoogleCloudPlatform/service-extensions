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

package jwt_auth

import (
	"io/ioutil"
	"strconv"
	"testing"

	"github.com/dgrijalva/jwt-go"
	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
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
	opts := []cmp.Option{
		protocmp.Transform(),
		protocmp.SortRepeatedFields(&extproc.HeaderMutation{}, "set_headers"),
	}

	if diff := cmp.Diff(response, wantResponse, opts...); diff != "" {
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
	if !cmp.Equal(err, wantErr, cmpopts.EquateErrors()) {
		t.Errorf("HandleRequestHeaders() got err %v, want %v", err, wantErr)
	}
}
