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

package jwt_auth

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/dgrijalva/jwt-go"
	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// getTestFilePath retorna o caminho absoluto para arquivos de teste
func getTestFilePath(filename string) string {
	return filepath.Join("..", "..", "ssl_creds", filename)
}

// generateTestJWTToken generates a JWT token for testing purposes.
func generateTestJWTToken(privateKey []byte, claims jwt.MapClaims) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	privateKeyParsed, err := jwt.ParseRSAPrivateKeyFromPEM(privateKey)
	if err != nil {
		return "", err
	}
	return token.SignedString(privateKeyParsed)
}

// TestHandleCheck_ValidToken tests the handling of check requests with a valid JWT token.
func TestHandleCheck_ValidToken(t *testing.T) {
	// Load the test private key
	privateKey, err := os.ReadFile(getTestFilePath("localhost.key"))
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

	// Create an instance of JwtAuthServer with the test public key path
	service := NewJwtAuthServerWithKeyPath(getTestFilePath("publickey.pem"))

	req := &authv3.CheckRequest{
		Attributes: &authv3.AttributeContext{
			Request: &authv3.AttributeContext_Request{
				Http: &authv3.AttributeContext_HttpRequest{
					Headers: map[string]string{
						"authorization": "Bearer " + tokenString,
					},
				},
			},
		},
	}

	// Call the HandleCheck method
	response, err := service.HandleCheck(context.Background(), req)
	if err != nil {
		t.Fatalf("HandleCheck got err: %v", err)
	}

	// Check if the response is not nil
	if response == nil {
		t.Fatalf("HandleCheck(): got nil resp, want non-nil")
	}

	// Check if it's an OK response
	if response.GetOkResponse() == nil {
		t.Fatalf("Expected OK response for valid JWT")
	}

	// Prepare expected headers
	expectedHeaders := []struct {
		key   string
		value string
	}{
		{"decoded-sub", "1234567890"},
		{"decoded-name", "John Doe"},
		{"decoded-iat", "1720020355"},
		{"decoded-exp", "1820023955"},
	}

	// Check headers in the OK response
	headers := response.GetOkResponse().Headers
	for _, expected := range expectedHeaders {
		found := false
		for _, h := range headers {
			if h.Header.Key == expected.key && h.Header.Value == expected.value {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("Expected header %s: %s not found", expected.key, expected.value)
		}
	}
}

// TestHandleCheck_InvalidToken tests the handling of check requests with an invalid JWT token.
func TestHandleCheck_InvalidToken(t *testing.T) {
	// Create an instance of JwtAuthServer with a test public key path
	service := NewJwtAuthServerWithKeyPath(getTestFilePath("publickey.pem"))
	// Override the public key to be invalid
	service.PublicKey = []byte("invalidpublickey")

	req := &authv3.CheckRequest{
		Attributes: &authv3.AttributeContext{
			Request: &authv3.AttributeContext_Request{
				Http: &authv3.AttributeContext_HttpRequest{
					Headers: map[string]string{
						"authorization": "Bearer invalidtoken",
					},
				},
			},
		},
	}

	// Call the HandleCheck method
	response, err := service.HandleCheck(context.Background(), req)
	if err != nil {
		t.Fatalf("HandleCheck got err: %v", err)
	}

	// Check if it's a denied response
	if response.GetDeniedResponse() == nil {
		t.Fatalf("Expected denied response for invalid JWT")
	}

	if response.GetDeniedResponse().Status.Code != typev3.StatusCode_Unauthorized {
		t.Errorf("Expected status code Unauthorized, got %v", response.GetDeniedResponse().Status.Code)
	}

	body := response.GetDeniedResponse().Body
	expectedBody := "Authorization token is invalid."
	if body != expectedBody {
		t.Errorf("Expected body %s, got %s", expectedBody, body)
	}
}

// TestHandleCheck_MissingToken tests the handling of check requests without a JWT token.
func TestHandleCheck_MissingToken(t *testing.T) {
	// Use absolute path for the test
	service := NewJwtAuthServerWithKeyPath(getTestFilePath("publickey.pem"))

	req := &authv3.CheckRequest{
		Attributes: &authv3.AttributeContext{
			Request: &authv3.AttributeContext_Request{
				Http: &authv3.AttributeContext_HttpRequest{
					Headers: map[string]string{},
				},
			},
		},
	}

	response, err := service.HandleCheck(context.Background(), req)
	if err != nil {
		t.Fatalf("HandleCheck got err: %v", err)
	}

	if response.GetDeniedResponse() == nil {
		t.Fatalf("Expected denied response for missing JWT")
	}

	if response.GetDeniedResponse().Status.Code != typev3.StatusCode_Unauthorized {
		t.Errorf("Expected status code Unauthorized, got %v", response.GetDeniedResponse().Status.Code)
	}

	body := response.GetDeniedResponse().Body
	expectedBody := "No Authorization token found."
	if body != expectedBody {
		t.Errorf("Expected body %s, got %s", expectedBody, body)
	}
}
