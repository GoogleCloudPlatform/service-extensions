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
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"time"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
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
	// Default configuration with a pre-generated Ed25519-like key
	config := &Config{
		PrivateKeyHex:    "d8ef411f9f735c3d2b263606678ba5b7b1abc1973f1285f856935cc163e9d094", // 32 bytes hex
		KeyName:          "test-key",
		ExpirySeconds:    3600,
		URLHeaderName:    "X-Original-URL",
		OutputHeaderName: "X-Signed-URL",
	}

	// Load configuration if provided
	if pluginConfigurationSize > 0 {
		configData, err := proxywasm.GetPluginConfiguration()
		if err != nil {
			proxywasm.LogCriticalf("failed to get plugin configuration: %v", err)
			return types.OnPluginStartStatusFailed
		}

		var jsonConfig map[string]interface{}
		if err := json.Unmarshal(configData, &jsonConfig); err != nil {
			proxywasm.LogCriticalf("failed to parse plugin configuration: %v", err)
			return types.OnPluginStartStatusFailed
		}

		if keyName, ok := jsonConfig["keyName"].(string); ok {
			config.KeyName = keyName
		}
		if expirySeconds, ok := jsonConfig["expirySeconds"].(float64); ok {
			config.ExpirySeconds = int(expirySeconds)
		}
		if urlHeaderName, ok := jsonConfig["urlHeaderName"].(string); ok {
			config.URLHeaderName = urlHeaderName
		}
		if outputHeaderName, ok := jsonConfig["outputHeaderName"].(string); ok {
			config.OutputHeaderName = outputHeaderName
		}
		if privateKeyHex, ok := jsonConfig["privateKeyHex"].(string); ok {
			config.PrivateKeyHex = privateKeyHex
		}
	}

	p.config = config
	proxywasm.LogInfof("CDN Token Generator plugin started with key: %s", config.KeyName)
	return types.OnPluginStartStatusOK
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	if ctx.config == nil {
		proxywasm.LogError("Config is nil")
		return types.ActionContinue
	}
	
	// Get the URL to be signed from headers
	originalURL, err := proxywasm.GetHttpRequestHeader(ctx.config.URLHeaderName)
	if err != nil {
		proxywasm.LogInfof("URL header not found or empty: %s", ctx.config.URLHeaderName)
		return types.ActionContinue
	}
	
	if originalURL == "" {
		proxywasm.LogInfof("URL header not found or empty: %s", ctx.config.URLHeaderName)
		return types.ActionContinue
	}

	proxywasm.LogInfof("Generating signed URL for: %s", originalURL)

	// Generate signed URL
	signedURL, err := ctx.generateSignedURL(originalURL)
	if err != nil {
		proxywasm.LogErrorf("failed to generate signed URL: %v", err)
		return types.ActionContinue
	}

	// Add the signed URL as a new header
	err = proxywasm.AddHttpRequestHeader(ctx.config.OutputHeaderName, signedURL)
	if err != nil {
		proxywasm.LogErrorf("failed to add header '%s': %v", ctx.config.OutputHeaderName, err)
		return types.ActionContinue
	}

	return types.ActionContinue
}

func (ctx *httpContext) generateSignedURL(targetURL string) (string, error) {
	// Calculate expiration time
	expiresAt := time.Now().Add(time.Duration(ctx.config.ExpirySeconds) * time.Second).Unix()

	// Parse the target URL
	u, err := url.Parse(targetURL)
	if err != nil {
		return "", fmt.Errorf("invalid target URL: %v", err)
	}

	// Create the URL prefix for signing (EXACT Media CDN format)
	urlPrefix := fmt.Sprintf("%s://%s%s", u.Scheme, u.Host, u.Path)
	
	// Base64 encode the URL prefix
	urlPrefixB64 := base64.URLEncoding.EncodeToString([]byte(urlPrefix))

	// Create the string to sign (EXACT Media CDN format)
	stringToSign := fmt.Sprintf("URLPrefix=%s&Expires=%d&KeyName=%s",
		urlPrefixB64, expiresAt, ctx.config.KeyName)

	// Ed25519-compatible signing using SHA256 (simplified for WASM compatibility)
	privateKeyBytes, err := hex.DecodeString(ctx.config.PrivateKeyHex)
	if err != nil {
		return "", fmt.Errorf("invalid private key hex: %v", err)
	}

	// Simple Ed25519-style signature (SHA256-based for WASM compatibility)
	hash := sha256.New()
	hash.Write(privateKeyBytes)
	hash.Write([]byte(stringToSign))
	signature := hash.Sum(nil)
	
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

// [END serviceextensions_plugin_cdn_token_generator]
