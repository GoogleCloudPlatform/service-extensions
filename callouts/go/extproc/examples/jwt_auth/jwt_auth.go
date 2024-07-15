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
	"fmt"
	"io/ioutil"
	"log"
	"strings"

	"github.com/GoogleCloudPlatform/service-extensions-samples/callouts/go/extproc/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions-samples/callouts/go/extproc/pkg/utils"
	"github.com/dgrijalva/jwt-go"
	extproc "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ExampleCalloutService implements JWT authentication by processing request headers.
type ExampleCalloutService struct {
	server.GRPCCalloutService
	PublicKey []byte
}

// NewExampleCalloutServiceWithKeyPath creates a new instance of ExampleCalloutService with the specified public key path.
func NewExampleCalloutServiceWithKeyPath(keyPath string) *ExampleCalloutService {
	service := &ExampleCalloutService{}
	service.Handlers.RequestHeadersHandler = service.HandleRequestHeaders
	service.LoadPublicKey(keyPath)
	return service
}

// NewExampleCalloutService creates a new instance of ExampleCalloutService with the default public key path.
func NewExampleCalloutService() *ExampleCalloutService {
	return NewExampleCalloutServiceWithKeyPath("./extproc/ssl_creds/publickey.pem")
}

// LoadPublicKey loads the public key from the specified file path.
func (s *ExampleCalloutService) LoadPublicKey(path string) {
	key, err := ioutil.ReadFile(path)
	if err != nil {
		log.Fatalf("failed to load public key: %v", err)
	}
	s.PublicKey = key
}

// extractJWTToken extracts the JWT token from the request headers.
func extractJWTToken(headers *extproc.HttpHeaders) (string, error) {
	for _, header := range headers.Headers.Headers {
		if header.Key == "Authorization" {
			return string(header.RawValue), nil
		}
	}
	return "", fmt.Errorf("no Authorization header found")
}

// validateJWTToken validates the JWT token using the public key.
func validateJWTToken(key []byte, headers *extproc.HttpHeaders) (map[string]interface{}, error) {
	tokenString, err := extractJWTToken(headers)

	if err != nil {
		return nil, err
	}

	if strings.HasPrefix(tokenString, "Bearer ") {
		tokenString = strings.TrimPrefix(tokenString, "Bearer ")
	}

	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}

		return jwt.ParseRSAPublicKeyFromPEM(key)
	})
	if err != nil {
		return nil, err
	}
	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		return claims, nil
	}
	return nil, fmt.Errorf("invalid token")
}

// HandleRequestHeaders processes the request headers, validates the JWT token, and adds decoded claims to the headers.
func (s *ExampleCalloutService) HandleRequestHeaders(headers *extproc.HttpHeaders) (*extproc.ProcessingResponse, error) {
	claims, err := validateJWTToken(s.PublicKey, headers)
	if err != nil {
		return nil, status.Errorf(codes.PermissionDenied, "Authorization token is invalid")
	}

	var decodedItems []struct{ Key, Value string }
	for key, value := range claims {
		if key == "iat" || key == "exp" {
			// Ensure iat and exp are formatted as integers without scientific notation
			if floatVal, ok := value.(float64); ok {
				intVal := int64(floatVal)
				decodedItems = append(decodedItems, struct{ Key, Value string }{Key: "decoded-" + key, Value: fmt.Sprintf("%d", intVal)})
				continue
			}
		}
		decodedItems = append(decodedItems, struct{ Key, Value string }{Key: "decoded-" + key, Value: fmt.Sprint(value)})
	}

	return &extproc.ProcessingResponse{
		Response: &extproc.ProcessingResponse_RequestHeaders{
			RequestHeaders: utils.AddHeaderMutation(decodedItems, nil, true, nil),
		},
	}, nil
}
