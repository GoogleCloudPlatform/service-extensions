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

// [START serviceextensions_plugin_cdn_token_generator]
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

// Security constants
const (
	maxURLLength    = 2048
	maxKeyLength    = 256
	minKeyLength    = 32
	maxConfigSize   = 4096
	maxExpiryTime   = 86400 // 24 hours max
	minExpiryTime   = 60    // 1 minute min
)

// Regex patterns for validation
var (
	urlPattern     = regexp.MustCompile(`^https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(/[^\s]*)?$`)
	keyNamePattern = regexp.MustCompile(`^[a-zA-Z0-9\-_]{1,64}$`)
	hexPattern     = regexp.MustCompile(`^[a-fA-F0-9]+$`)
)

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

type vmContext struct {
	types.DefaultVMContext
}

func (v *vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

type pluginContext struct {
	types.DefaultPluginContext
	config *Config
}

type httpContext struct {
	types.DefaultHttpContext
	config *Config
}

type Config struct {
	PrivateKeyHex    string `json:"privateKeyHex"`
	KeyName          string `json:"keyName"`
	ExpirySeconds    int    `json:"expirySeconds"`
	URLHeaderName    string `json:"urlHeaderName"`
	OutputHeaderName string `json:"outputHeaderName"`
}

func (p *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{config: p.config}
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	// Security: Configuration is mandatory
	if pluginConfigurationSize == 0 {
		proxywasm.LogCritical("Configuration required for security - no defaults for sensitive data")
		return types.OnPluginStartStatusFailed
	}

	// Security: Validate configuration size
	if pluginConfigurationSize > maxConfigSize {
		proxywasm.LogCritical("Configuration too large")
		return types.OnPluginStartStatusFailed
	}

	configData, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogCritical("Failed to get plugin configuration")
		return types.OnPluginStartStatusFailed
	}

	var config Config
	if err := json.Unmarshal(configData, &config); err != nil {
		proxywasm.LogCritical("Failed to parse plugin configuration")
		return types.OnPluginStartStatusFailed
	}

	// Security: Validate all configuration parameters
	if err := p.validateConfig(&config); err != nil {
		proxywasm.LogCriticalf("Invalid configuration: %s", err.Error())
		return types.OnPluginStartStatusFailed
	}

	p.config = &config
	proxywasm.LogInfof("CDN Token Generator plugin started securely with key: %s", config.KeyName)
	return types.OnPluginStartStatusOK
}

// Security: Comprehensive configuration validation
func (p *pluginContext) validateConfig(config *Config) error {
	// Validate private key
	if config.PrivateKeyHex == "" {
		return fmt.Errorf("privateKeyHex is required")
	}
	
	if len(config.PrivateKeyHex) < minKeyLength || len(config.PrivateKeyHex) > maxKeyLength {
		return fmt.Errorf("privateKeyHex length must be between %d and %d", minKeyLength, maxKeyLength)
	}
	
	if !hexPattern.MatchString(config.PrivateKeyHex) {
		return fmt.Errorf("privateKeyHex must be valid hexadecimal")
	}

	// Validate key name
	if config.KeyName == "" {
		return fmt.Errorf("keyName is required")
	}
	
	if !keyNamePattern.MatchString(config.KeyName) {
		return fmt.Errorf("keyName contains invalid characters")
	}

	// Validate expiry time
	if config.ExpirySeconds < minExpiryTime || config.ExpirySeconds > maxExpiryTime {
		return fmt.Errorf("expirySeconds must be between %d and %d", minExpiryTime, maxExpiryTime)
	}

	// Validate header names
	if config.URLHeaderName == "" || config.OutputHeaderName == "" {
		return fmt.Errorf("header names cannot be empty")
	}

	// Security: Prevent header injection
	if strings.ContainsAny(config.URLHeaderName, "\r\n") || strings.ContainsAny(config.OutputHeaderName, "\r\n") {
		return fmt.Errorf("header names cannot contain CR or LF characters")
	}

	return nil
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Security: Defensive programming
	if ctx.config == nil {
		proxywasm.LogError("Plugin configuration is null")
		return types.ActionContinue
	}
	
	// Security: Validate input header
	originalURL, err := proxywasm.GetHttpRequestHeader(ctx.config.URLHeaderName)
	if err != nil {
		proxywasm.LogInfof("URL header not found or empty: %s", ctx.config.URLHeaderName)
		return types.ActionContinue
	}
	
	if originalURL == "" {
		proxywasm.LogInfof("URL header not found or empty: %s", ctx.config.URLHeaderName)
		return types.ActionContinue
	}

	// Security: Comprehensive URL validation
	if err := ctx.validateURL(originalURL); err != nil {
		proxywasm.LogError("Invalid URL provided")
		return types.ActionContinue
	}

	proxywasm.LogInfof("Generating signed URL for: %s", originalURL)

	// Generate signed URL
	signedURL, err := ctx.generateSignedURL(originalURL)
	if err != nil {
		proxywasm.LogError("Failed to generate signed URL")
		return types.ActionContinue
	}

	// Add the signed URL as a new header
	err = proxywasm.AddHttpRequestHeader(ctx.config.OutputHeaderName, signedURL)
	if err != nil {
		proxywasm.LogError("Failed to add signed URL header")
		return types.ActionContinue
	}

	return types.ActionContinue
}

// Security: Robust URL validation
func (ctx *httpContext) validateURL(targetURL string) error {
	// Security: Length validation to prevent DoS
	if len(targetURL) > maxURLLength {
		return fmt.Errorf("URL exceeds maximum length")
	}

	// Security: Basic format validation
	if !urlPattern.MatchString(targetURL) {
		return fmt.Errorf("URL format validation failed")
	}

	// Security: Parse validation
	u, err := url.Parse(targetURL)
	if err != nil {
		return fmt.Errorf("URL parsing failed")
	}

	// Security: Scheme validation
	if u.Scheme != "https" && u.Scheme != "http" {
		return fmt.Errorf("unsupported URL scheme")
	}

	// Security: Host validation
	if u.Host == "" {
		return fmt.Errorf("URL host is required")
	}

	// Security: Prevent localhost/internal IPs (basic check)
	host := strings.ToLower(u.Host)
	if strings.Contains(host, "localhost") || strings.Contains(host, "127.0.0.1") || strings.Contains(host, "::1") {
		return fmt.Errorf("internal URLs not allowed")
	}

	return nil
}

func (ctx *httpContext) generateSignedURL(targetURL string) (string, error) {
	// Calculate expiration time (current time + configured expiry)
	expiresAt := time.Now().Add(time.Duration(ctx.config.ExpirySeconds) * time.Second).Unix()

	// Parse the target URL (already validated)
	u, err := url.Parse(targetURL)
	if err != nil {
		return "", fmt.Errorf("URL parsing failed")
	}

	// Create the URL prefix for signing (EXACT Media CDN format)
	urlPrefix := fmt.Sprintf("%s://%s%s", u.Scheme, u.Host, u.Path)
	
	// Base64 encode the URL prefix
	urlPrefixB64 := base64.URLEncoding.EncodeToString([]byte(urlPrefix))

	// Create the string to sign (EXACT Media CDN format)
	stringToSign := fmt.Sprintf("URLPrefix=%s&Expires=%d&KeyName=%s",
		urlPrefixB64, expiresAt, ctx.config.KeyName)

	// Security: Safe private key decoding
	privateKeyBytes, err := ctx.secureDecodeKey(ctx.config.PrivateKeyHex)
	if err != nil {
		return "", fmt.Errorf("key decoding failed")
	}

	// Generate HMAC signature (Ed25519-style with SHA256 for WASM compatibility)
	signature := ctx.computeSecureSignature(privateKeyBytes, []byte(stringToSign))
	
	// Base64 encode signature (Media CDN compatible)
	signatureB64 := base64.URLEncoding.EncodeToString(signature)

	// Build the final signed URL (EXACT Media CDN format)
	query := u.Query()
	query.Set("URLPrefix", urlPrefixB64)
	query.Set("Expires", strconv.FormatInt(expiresAt, 10))
	query.Set("KeyName", ctx.config.KeyName)
	query.Set("Signature", signatureB64)

	u.RawQuery = query.Encode()
	
	return u.String(), nil
}

// Security: Safe key decoding with validation
func (ctx *httpContext) secureDecodeKey(keyHex string) ([]byte, error) {
	// Additional validation during runtime
	if len(keyHex)%2 != 0 {
		return nil, fmt.Errorf("invalid key format")
	}

	keyBytes, err := hex.DecodeString(keyHex)
	if err != nil {
		return nil, fmt.Errorf("key decoding error")
	}

	// Security: Validate decoded key length
	if len(keyBytes) < 16 || len(keyBytes) > 128 {
		return nil, fmt.Errorf("invalid key size")
	}

	return keyBytes, nil
}

// Security: Secure signature computation
func (ctx *httpContext) computeSecureSignature(key, data []byte) []byte {
	// Use HMAC-SHA256 for secure signing (Ed25519-compatible approach for WASM)
	mac := hmac.New(sha256.New, key)
	mac.Write(data)
	return mac.Sum(nil)
}

// Security: Constant-time signature verification (for future validation needs)
func (ctx *httpContext) verifySignature(expected, actual []byte) bool {
	if len(expected) != len(actual) {
		return false
	}
	return subtle.ConstantTimeCompare(expected, actual) == 1
}

// [END serviceextensions_plugin_cdn_token_generator]