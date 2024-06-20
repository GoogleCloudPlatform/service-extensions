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
	"regexp"
	"testing"
	"time"

	"github.com/dgrijalva/jwt-go"
	base "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
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
	now := time.Now().Unix()
	claims := jwt.MapClaims{
		"sub":  "1234567890",
		"name": "John Doe",
		"iat":  now,
		"exp":  now + 3600,
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

	// Prepare expected decoded items excluding iat and exp
	expectedItems := []struct{ Key, Value string }{
		{"decoded-sub", "1234567890"},
		{"decoded-name", "John Doe"},
	}

	// Validate the response headers
	requestHeaders := response.GetRequestHeaders().GetResponse()
	for _, item := range expectedItems {
		found := false
		for _, header := range requestHeaders.GetHeaderMutation().GetSetHeaders() {
			if header.GetHeader().GetKey() == item.Key && string(header.GetHeader().GetRawValue()) == item.Value {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("header %s: %s not found in response", item.Key, item.Value)
		}
	}

	// Validate iat and exp separately using regex patterns
	iatPattern := regexp.MustCompile(`^\d+(\.\d+)?(e[+\-]?\d+)?$`)
	expPattern := regexp.MustCompile(`^\d+(\.\d+)?(e[+\-]?\d+)?$`)

	iatFound := false
	expFound := false
	for _, header := range requestHeaders.GetHeaderMutation().GetSetHeaders() {
		key := header.GetHeader().GetKey()
		value := string(header.GetHeader().GetRawValue())
		if key == "decoded-iat" {
			if !iatPattern.MatchString(value) {
				t.Errorf("decoded-iat value %s does not match expected pattern", value)
			}
			iatFound = true
		}
		if key == "decoded-exp" {
			if !expPattern.MatchString(value) {
				t.Errorf("decoded-exp value %s does not match expected pattern", value)
			}
			expFound = true
		}
	}

	if !iatFound {
		t.Error("header decoded-iat not found or mismatched in response")
	}
	if !expFound {
		t.Error("header decoded-exp not found or mismatched in response")
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

	if diff := cmp.Diff(err.Error(), wantErr.Error()); diff != "" {
		t.Errorf("HandleRequestHeaders() error message = %v, want %v, diff: %v", err.Error(), wantErr.Error(), diff)
	}
}
