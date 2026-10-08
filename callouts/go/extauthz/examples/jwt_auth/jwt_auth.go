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
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extauthz/internal/server"
	"github.com/GoogleCloudPlatform/service-extensions/callouts/go/extauthz/pkg/utils"
	"github.com/dgrijalva/jwt-go"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// JwtAuthServer implements JWT token validation for ext_authz.
type JwtAuthServer struct {
	server.GRPCCalloutService
	PublicKey []byte
}

// NewJwtAuthServerWithKeyPath creates a new instance of JwtAuthServer with the specified public key path.
func NewJwtAuthServerWithKeyPath(keyPath string) *JwtAuthServer {
	service := &JwtAuthServer{}
	service.CheckHandler = service.HandleCheck
	service.LoadPublicKey(keyPath)
	return service
}

// NewJwtAuthServer creates a new instance of JwtAuthServer with the default public key path.
func NewJwtAuthServer() *JwtAuthServer {
	return NewJwtAuthServerWithKeyPath("ssl_creds/publickey.pem")
}

// LoadPublicKey loads the public key from the specified file path.
func (s *JwtAuthServer) LoadPublicKey(path string) {
	key, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("failed to load public key: %v", err)
	}
	s.PublicKey = key
}

// extractJWTToken extracts the JWT token from the request headers.
func (s *JwtAuthServer) extractJWTToken(req *auth.CheckRequest) (string, error) {
	headers := req.GetAttributes().GetRequest().GetHttp().GetHeaders()
	if headers == nil {
		return "", fmt.Errorf("no headers found")
	}
	authHeader, exists := headers["authorization"]
	if !exists {
		return "", fmt.Errorf("no Authorization header found")
	}
	return authHeader, nil
}

// validateJWTToken validates the JWT token using the public key.
func (s *JwtAuthServer) validateJWTToken(tokenString string) (map[string]interface{}, error) {
	tokenString = strings.TrimPrefix(tokenString, "Bearer ")

	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}

		return jwt.ParseRSAPublicKeyFromPEM(s.PublicKey)
	})
	if err != nil {
		return nil, err
	}
	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		return claims, nil
	}
	return nil, fmt.Errorf("invalid token")
}

// HandleCheck processes the authorization check request and validates JWT tokens.
func (s *JwtAuthServer) HandleCheck(ctx context.Context, req *auth.CheckRequest) (*auth.CheckResponse, error) {
	tokenString, err := s.extractJWTToken(req)
	if err != nil {
		return utils.DenyRequest(
			typev3.StatusCode_Unauthorized,
			"No Authorization token found.",
			nil,
		), nil
	}

	claims, err := s.validateJWTToken(tokenString)
	if err != nil {
		return utils.DenyRequest(
			typev3.StatusCode_Unauthorized,
			"Authorization token is invalid.",
			nil,
		), nil
	}

	// Convert claims to headers for upstream
	headers := make(map[string]string)
	for key, value := range claims {
		// Handle special formatting for iat and exp claims
		if key == "iat" || key == "exp" {
			if floatVal, ok := value.(float64); ok {
				intVal := int64(floatVal)
				headers["decoded-"+key] = fmt.Sprintf("%d", intVal)
				continue
			}
		}
		headers["decoded-"+key] = fmt.Sprint(value)
	}

	return utils.AllowRequest(headers), nil
}
