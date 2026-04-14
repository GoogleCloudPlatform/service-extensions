// Copyright 2026 Google LLC
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
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

const (
	maxKeyHexLength   = 256
	minKeyHexLength   = 32
	maxExpirySeconds  = 86400 // 24 hours
	minExpirySeconds  = 60    // 1 minute
	defaultExpirySecs = 3600
	// Maximum response body size to process (1MB). Larger bodies are passed through
	// unmodified to prevent excessive memory usage and processing time.
	maxBodySize = 1024 * 1024
)

// Pre-compile URL regex to save CPU cycles on every request
var urlPattern = regexp.MustCompile(`(https?://[^\s"'<>]+)`)

type cdnTokenConfig struct {
	decodedKey    []byte
	keyName       string
	expirySeconds int
}

type vmContext struct {
	types.DefaultVMContext
}

type pluginContext struct {
	types.DefaultPluginContext
	config *cdnTokenConfig
}

type httpContext struct {
	types.DefaultHttpContext
	config *cdnTokenConfig
}

func (*vmContext) NewPluginContext(uint32) types.PluginContext {
	return &pluginContext{}
}

func (p *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{
		config: p.config,
	}
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	if pluginConfigurationSize == 0 {
		proxywasm.LogErrorf("Configuration is required")
		return types.OnPluginStartStatusFailed
	}

	configBytes, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogErrorf("Failed to get plugin configuration: %v", err)
		return types.OnPluginStartStatusFailed
	}

	cfg, err := parseConfig(configBytes)
	if err != nil {
		proxywasm.LogErrorf("Configuration error: %v", err)
		return types.OnPluginStartStatusFailed
	}

	p.config = cfg
	proxywasm.LogInfof("CDN Token Generator configured: keyName=%s, expirySeconds=%d", cfg.keyName, cfg.expirySeconds)

	return types.OnPluginStartStatusOK
}

// parseConfig parses the TextPB configuration format directly to avoid heavy proto dependencies
func parseConfig(data []byte) (*cdnTokenConfig, error) {
	cfg := &cdnTokenConfig{
		expirySeconds: defaultExpirySecs,
	}

	var privateKeyHex string
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}

		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"`)

		switch key {
		case "private_key_hex":
			privateKeyHex = val
		case "key_name":
			cfg.keyName = val
		case "expiry_seconds":
			if v, err := strconv.Atoi(val); err == nil {
				cfg.expirySeconds = v
			}
		}
	}

	// Validation
	if privateKeyHex == "" {
		return nil, fmt.Errorf("private_key_hex is required")
	}
	if cfg.keyName == "" {
		return nil, fmt.Errorf("key_name is required")
	}
	if len(privateKeyHex) < minKeyHexLength || len(privateKeyHex) > maxKeyHexLength {
		return nil, fmt.Errorf("private_key_hex length must be between %d and %d", minKeyHexLength, maxKeyHexLength)
	}
	if cfg.expirySeconds < minExpirySeconds || cfg.expirySeconds > maxExpirySeconds {
		return nil, fmt.Errorf("expiry_seconds must be between %d and %d", minExpirySeconds, maxExpirySeconds)
	}

	// Decode hex key once during configuration to save CPU cycles
	decoded, err := hex.DecodeString(privateKeyHex)
	if err != nil {
		return nil, fmt.Errorf("failed to decode private key from hex: %v", err)
	}
	cfg.decodedKey = decoded

	return cfg, nil
}

func (ctx *httpContext) OnHttpResponseBody(numBytes int, endOfStream bool) types.Action {
	// Buffer the response until we have the complete body.
	if !endOfStream {
		return types.ActionPause
	}

	defer func() {
		if err := recover(); err != nil {
			proxywasm.LogErrorf("Panic during body processing: %v", err)
			proxywasm.ResumeHttpResponse()
		}
	}()

	if numBytes == 0 {
		return types.ActionContinue
	}

	// Skip processing for very large bodies to prevent memory issues.
	if numBytes > maxBodySize {
		proxywasm.LogWarnf("Response body too large (%d bytes), skipping URL signing", numBytes)
		return types.ActionContinue
	}

	body, err := proxywasm.GetHttpResponseBody(0, numBytes)
	if err != nil || len(body) == 0 {
		proxywasm.LogErrorf("Failed to read response body: %v", err)
		return types.ActionContinue
	}

	replacements := 0
	modifiedBody := urlPattern.ReplaceAllFunc(body, func(match []byte) []byte {
		replacements++
		return generateSignedUrl(match, ctx.config)
	})

	if replacements > 0 {
		proxywasm.LogInfof("Replaced %d URLs with signed URLs", replacements)
		if err := proxywasm.ReplaceHttpResponseBody(modifiedBody); err != nil {
			proxywasm.LogErrorf("Failed to replace HTTP response body: %v", err)
		}
	}

	return types.ActionContinue
}

// generateSignedUrl creates a signed URL in Media CDN token format.
// See: https://cloud.google.com/media-cdn/docs/generate-tokens
func generateSignedUrl(targetUrl []byte, config *cdnTokenConfig) []byte {
	// Base64 URL-safe encode the URL prefix without padding.
	urlPrefixB64 := base64.RawURLEncoding.EncodeToString(targetUrl)

	// Calculate expiration timestamp.
	expiresAt := time.Now().Unix() + int64(config.expirySeconds)

	// Create the string to sign (Media CDN token format).
	stringToSign := fmt.Sprintf("URLPrefix=%s~Expires=%d~KeyName=%s", urlPrefixB64, expiresAt, config.keyName)

	// Compute HMAC-SHA256 signature
	mac := hmac.New(sha256.New, config.decodedKey)
	mac.Write([]byte(stringToSign))
	hmacResult := mac.Sum(nil)

	// Convert HMAC to hexadecimal string (Media CDN uses hex, not base64).
	hmacHex := hex.EncodeToString(hmacResult)

	// Build final signed URL with Edge-Cache-Token parameter.
	separator := "?"
	if bytes.Contains(targetUrl, []byte("?")) {
		separator = "&"
	}

	finalUrl := fmt.Sprintf("%s%sEdge-Cache-Token=%s~hmac=%s", string(targetUrl), separator, stringToSign, hmacHex)
	return []byte(finalUrl)
}

// [END serviceextensions_plugin_cdn_token_generator]
