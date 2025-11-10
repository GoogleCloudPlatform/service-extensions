// Copyright 2025 Google LLC
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

// [START serviceextensions_plugin_drafting_jwt_token]
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {
	proxywasm.SetVMContext(&vmContext{})
}

type vmContext struct {
	types.DefaultVMContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

type pluginContext struct {
	types.DefaultPluginContext
	secretKey          string
	defaultExpiration  int
	kvStore            map[string]*UserEntitlements
}

// UserEntitlements represents user permissions and roles from KV store
type UserEntitlements struct {
	Plan        string   `json:"plan"`
	Permissions []string `json:"permissions"`
	Roles       []string `json:"roles,omitempty"`
}

// Config represents the plugin configuration
type Config struct {
	SecretKey                string                          `json:"secret_key"`
	DefaultExpirationMinutes int                             `json:"default_expiration_minutes"`
	Data                     map[string]*UserEntitlements    `json:"data"`
}

// JWTHeader represents the JWT header structure
type JWTHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
}

// JWTPayload represents the JWT payload with registered and public claims
type JWTPayload struct {
	Sub         string   `json:"sub"`
	Exp         int64    `json:"exp"`
	Nbf         int64    `json:"nbf"`
	Iat         int64    `json:"iat"`
	Plan        string   `json:"plan,omitempty"`
	Permissions []string `json:"permissions,omitempty"`
	Roles       []string `json:"roles,omitempty"`
}

// TokenResponse represents the token generation response
type TokenResponse struct {
	Token     string `json:"token"`
	ExpiresIn int    `json:"expires_in"`
	TokenType string `json:"token_type"`
}

// VerifyResponse represents the token verification response
type VerifyResponse struct {
	Valid   bool   `json:"valid"`
	Message string `json:"message"`
}

func (ctx *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	// Load plugin configuration
	configData, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogErrorf("failed to get plugin configuration: %v", err)
		return types.OnPluginStartStatusFailed
	}

	var config Config
	if err := json.Unmarshal(configData, &config); err != nil {
		proxywasm.LogErrorf("failed to parse configuration: %v", err)
		return types.OnPluginStartStatusFailed
	}

	// Set default values
	ctx.secretKey = config.SecretKey
	if ctx.secretKey == "" {
		proxywasm.LogWarn("no secret_key configured, using default (INSECURE)")
		ctx.secretKey = "default_secret_key_change_me"
	}

	ctx.defaultExpiration = config.DefaultExpirationMinutes
	if ctx.defaultExpiration == 0 {
		ctx.defaultExpiration = 60
	}

	// Load KV store data
	ctx.kvStore = config.Data
	if ctx.kvStore == nil {
		ctx.kvStore = make(map[string]*UserEntitlements)
	}

	proxywasm.LogInfof("JWT Plugin configured successfully with %d KV store entries", len(ctx.kvStore))
	return types.OnPluginStartStatusOK
}

func (ctx *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{
		contextID: contextID,
		plugin:    ctx,
	}
}

type httpContext struct {
	types.DefaultHttpContext
	contextID uint32
	plugin    *pluginContext
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		proxywasm.LogErrorf("failed to get :path header: %v", err)
		return types.ActionContinue
	}

	method, err := proxywasm.GetHttpRequestHeader(":method")
	if err != nil {
		proxywasm.LogErrorf("failed to get :method header: %v", err)
		return types.ActionContinue
	}

	// Handle token generation endpoint
	if path == "/generate-token" && method == "POST" {
		return ctx.handleGenerateToken()
	}

	// Handle token verification endpoint
	if path == "/verify-token" && method == "GET" {
		return ctx.handleVerifyToken()
	}

	// For other requests, validate token if present
	return ctx.handleProtectedEndpoint()
}

func (ctx *httpContext) handleGenerateToken() types.Action {
	// Get user_id from header
	userID, err := proxywasm.GetHttpRequestHeader("x-user-id")
	if err != nil || userID == "" {
		ctx.sendJSONResponse(400, map[string]string{
			"error": "Missing x-user-id header",
		})
		return types.ActionPause
	}

	// Get optional expiration override
	expirationMinutes := ctx.plugin.defaultExpiration
	if expHeader, err := proxywasm.GetHttpRequestHeader("x-expiration-minutes"); err == nil && expHeader != "" {
		var exp int
		if _, err := fmt.Sscanf(expHeader, "%d", &exp); err == nil {
			expirationMinutes = exp
		}
	}

	// Generate JWT
	token, err := ctx.generateJWT(userID, expirationMinutes)
	if err != nil {
		proxywasm.LogErrorf("failed to generate JWT: %v", err)
		ctx.sendJSONResponse(500, map[string]string{
			"error": "Failed to generate token",
		})
		return types.ActionPause
	}

	// Send response
	response := TokenResponse{
		Token:     token,
		ExpiresIn: expirationMinutes * 60,
		TokenType: "Bearer",
	}

	ctx.sendJSONResponse(200, response)
	return types.ActionPause
}

func (ctx *httpContext) handleVerifyToken() types.Action {
	// Get Authorization header
	authHeader, err := proxywasm.GetHttpRequestHeader("authorization")
	if err != nil || authHeader == "" {
		ctx.sendJSONResponse(401, VerifyResponse{
			Valid:   false,
			Message: "Missing Authorization header",
		})
		return types.ActionPause
	}

	// Extract Bearer token
	if !strings.HasPrefix(authHeader, "Bearer ") {
		ctx.sendJSONResponse(401, VerifyResponse{
			Valid:   false,
			Message: "Invalid Authorization format",
		})
		return types.ActionPause
	}

	token := strings.TrimPrefix(authHeader, "Bearer ")

	// Verify token
	if err := ctx.verifyJWT(token); err != nil {
		ctx.sendJSONResponse(401, VerifyResponse{
			Valid:   false,
			Message: err.Error(),
		})
		return types.ActionPause
	}

	ctx.sendJSONResponse(200, VerifyResponse{
		Valid:   true,
		Message: "Token is valid",
	})
	return types.ActionPause
}

func (ctx *httpContext) handleProtectedEndpoint() types.Action {
	// Get Authorization header
	authHeader, err := proxywasm.GetHttpRequestHeader("authorization")
	if err != nil || authHeader == "" {
		// No token present, allow request to continue
		return types.ActionContinue
	}

	// Check if it's a Bearer token
	if !strings.HasPrefix(authHeader, "Bearer ") {
		return types.ActionContinue
	}

	token := strings.TrimPrefix(authHeader, "Bearer ")

	// Verify token
	if err := ctx.verifyJWT(token); err != nil {
		ctx.sendTextResponse(401, fmt.Sprintf("Unauthorized: %s", err.Error()))
		return types.ActionPause
	}

	// Extract payload and add headers for downstream services
	parts := strings.Split(token, ".")
	if len(parts) == 3 {
		if payload, err := ctx.decodePayload(parts[1]); err == nil {
			if payload.Sub != "" {
				proxywasm.AddHttpRequestHeader("x-jwt-user", payload.Sub)
			}
			if payload.Plan != "" {
				proxywasm.AddHttpRequestHeader("x-jwt-plan", payload.Plan)
			}
		}
	}

	return types.ActionContinue
}

func (ctx *httpContext) generateJWT(userID string, expirationMinutes int) (string, error) {
	now := time.Now().Unix()
	exp := now + int64(expirationMinutes*60)

	// Create JWT header
	header := JWTHeader{
		Alg: "HS256",
		Typ: "JWT",
	}

	// Get user entitlements from KV store
	entitlements := ctx.getUserEntitlements(userID)

	// Create JWT payload with registered and public claims
	payload := JWTPayload{
		Sub:         userID,
		Exp:         exp,
		Nbf:         now,
		Iat:         now,
		Plan:        entitlements.Plan,
		Permissions: entitlements.Permissions,
		Roles:       entitlements.Roles,
	}

	// Encode header
	headerJSON, err := json.Marshal(header)
	if err != nil {
		return "", fmt.Errorf("failed to marshal header: %w", err)
	}
	headerEncoded := base64URLEncode(headerJSON)

	// Encode payload
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal payload: %w", err)
	}
	payloadEncoded := base64URLEncode(payloadJSON)

	// Create signature
	signingInput := headerEncoded + "." + payloadEncoded
	signature := ctx.hmacSHA256(ctx.plugin.secretKey, signingInput)
	signatureEncoded := base64URLEncode(signature)

	// Assemble final JWT
	return signingInput + "." + signatureEncoded, nil
}

func (ctx *httpContext) verifyJWT(token string) error {
	// Split token into parts
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return fmt.Errorf("invalid token format")
	}

	// Verify signature
	signingInput := parts[0] + "." + parts[1]
	expectedSignature := ctx.hmacSHA256(ctx.plugin.secretKey, signingInput)
	expectedSignatureEncoded := base64URLEncode(expectedSignature)

	if parts[2] != expectedSignatureEncoded {
		return fmt.Errorf("invalid signature")
	}

	// Decode and verify payload
	payload, err := ctx.decodePayload(parts[1])
	if err != nil {
		return fmt.Errorf("token verification failed: %w", err)
	}

	// Verify expiration
	now := time.Now().Unix()
	if payload.Exp < now {
		return fmt.Errorf("token expired")
	}

	// Verify not-before
	if payload.Nbf > now {
		return fmt.Errorf("token not yet valid")
	}

	return nil
}

func (ctx *httpContext) decodePayload(encodedPayload string) (*JWTPayload, error) {
	payloadJSON, err := base64URLDecode(encodedPayload)
	if err != nil {
		return nil, fmt.Errorf("failed to decode payload: %w", err)
	}

	var payload JWTPayload
	if err := json.Unmarshal(payloadJSON, &payload); err != nil {
		return nil, fmt.Errorf("failed to unmarshal payload: %w", err)
	}

	return &payload, nil
}

func (ctx *httpContext) getUserEntitlements(userID string) *UserEntitlements {
	if entitlements, ok := ctx.plugin.kvStore[userID]; ok {
		return entitlements
	}

	// Return default/free tier if user not found
	return &UserEntitlements{
		Plan:        "free",
		Permissions: []string{},
	}
}

func (ctx *httpContext) hmacSHA256(key, data string) []byte {
	h := hmac.New(sha256.New, []byte(key))
	h.Write([]byte(data))
	return h.Sum(nil)
}

func (ctx *httpContext) sendJSONResponse(statusCode uint32, data interface{}) {
	body, err := json.Marshal(data)
	if err != nil {
		proxywasm.LogErrorf("failed to marshal response: %v", err)
		body = []byte(`{"error":"internal server error"}`)
		statusCode = 500
	}

	if err := proxywasm.SendHttpResponse(statusCode, [][2]string{
		{"content-type", "application/json"},
	}, body, -1); err != nil {
		proxywasm.LogErrorf("failed to send response: %v", err)
	}
}

func (ctx *httpContext) sendTextResponse(statusCode uint32, message string) {
	if err := proxywasm.SendHttpResponse(statusCode, [][2]string{
		{"content-type", "text/plain"},
	}, []byte(message), -1); err != nil {
		proxywasm.LogErrorf("failed to send response: %v", err)
	}
}

// base64URLEncode encodes bytes to base64 URL-safe format
func base64URLEncode(data []byte) string {
	encoded := base64.StdEncoding.EncodeToString(data)
	encoded = strings.ReplaceAll(encoded, "+", "-")
	encoded = strings.ReplaceAll(encoded, "/", "_")
	encoded = strings.TrimRight(encoded, "=")
	return encoded
}

// base64URLDecode decodes base64 URL-safe format to bytes
func base64URLDecode(data string) ([]byte, error) {
	data = strings.ReplaceAll(data, "-", "+")
	data = strings.ReplaceAll(data, "_", "/")

	// Add padding if needed
	switch len(data) % 4 {
	case 2:
		data += "=="
	case 3:
		data += "="
	}

	return base64.StdEncoding.DecodeString(data)
}
// [END serviceextensions_plugin_drafting_jwt_token]
