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
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"time"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {
    proxywasm.LogInfof("CDN Token Generator main() called")
}

func init() {
    proxywasm.LogInfof("CDN Token Generator init() called")
    proxywasm.SetVMContext(&vmContext{})
}

type vmContext struct {
    types.DefaultVMContext
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
    PrivateKey       []byte `json:"privateKey"` 
    KeyName          string `json:"keyName"`
    ExpirySeconds    int    `json:"expirySeconds"`
    URLHeaderName    string `json:"urlHeaderName"`
    OutputHeaderName string `json:"outputHeaderName"`
}

func (v *vmContext) NewPluginContext(uint32) types.PluginContext {
    proxywasm.LogInfof("NewPluginContext called")
    return &pluginContext{}
}

func (p *pluginContext) NewHttpContext(uint32) types.HttpContext {
    proxywasm.LogInfof("NewHttpContext called with config: %+v", p.config)
    return &httpContext{config: p.config}
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
    proxywasm.LogInfof("OnPluginStart called with config size: %d", pluginConfigurationSize)
    
    // Default configuration
    config := &Config{
        KeyName:          "test-key",
        ExpirySeconds:    3600,
        URLHeaderName:    "X-Original-URL",
        OutputHeaderName: "X-Signed-URL",
    }

    // Load configuration if provided
    if pluginConfigurationSize > 0 {
        proxywasm.LogInfof("Loading plugin configuration...")
        configData, err := proxywasm.GetPluginConfiguration()
        if err != nil {
            proxywasm.LogCriticalf("failed to get plugin configuration: %v", err)
            return types.OnPluginStartStatusFailed
        }
        
        proxywasm.LogInfof("Got config data: %s", string(configData))

        var jsonConfig map[string]interface{}
        if err := json.Unmarshal(configData, &jsonConfig); err != nil {
            proxywasm.LogCriticalf("failed to parse plugin configuration: %v", err)
            return types.OnPluginStartStatusFailed
        }

        if keyName, ok := jsonConfig["keyName"].(string); ok {
            config.KeyName = keyName
            proxywasm.LogInfof("Set keyName to: %s", keyName)
        }
        if expirySeconds, ok := jsonConfig["expirySeconds"].(float64); ok {
            config.ExpirySeconds = int(expirySeconds)
            proxywasm.LogInfof("Set expirySeconds to: %d", int(expirySeconds))
        }
        if urlHeaderName, ok := jsonConfig["urlHeaderName"].(string); ok {
            config.URLHeaderName = urlHeaderName
            proxywasm.LogInfof("Set urlHeaderName to: %s", urlHeaderName)
        }
        if outputHeaderName, ok := jsonConfig["outputHeaderName"].(string); ok {
            config.OutputHeaderName = outputHeaderName
            proxywasm.LogInfof("Set outputHeaderName to: %s", outputHeaderName)
        }
        if privateKeyStr, ok := jsonConfig["privateKey"].(string); ok {
            privateKeyBytes, err := base64.StdEncoding.DecodeString(privateKeyStr)
            if err != nil {
                proxywasm.LogCriticalf("failed to decode private key: %v", err)
                return types.OnPluginStartStatusFailed
            }
            config.PrivateKey = privateKeyBytes
            proxywasm.LogInfof("Successfully loaded private key (%d bytes)", len(privateKeyBytes))
        }
    }

    // Generate a default key if none provided
    if len(config.PrivateKey) == 0 {
        proxywasm.LogInfof("Generating default Ed25519 key...")
        _, privateKey, err := ed25519.GenerateKey(nil)
        if err != nil {
            proxywasm.LogCriticalf("failed to generate Ed25519 key: %v", err)
            return types.OnPluginStartStatusFailed
        }
        config.PrivateKey = privateKey
        proxywasm.LogInfof("Generated default key (%d bytes)", len(privateKey))
    }

    p.config = config
    proxywasm.LogInfof("CDN Token Generator plugin started with key: %s", config.KeyName)
    proxywasm.LogInfof("Config: URLHeader=%s, OutputHeader=%s, Expiry=%d", 
        config.URLHeaderName, config.OutputHeaderName, config.ExpirySeconds)
    return types.OnPluginStartStatusOK
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
    proxywasm.LogInfof("=== OnHttpRequestHeaders START ===")
    proxywasm.LogInfof("Headers count: %d, endOfStream: %v", numHeaders, endOfStream)
    
    if ctx.config == nil {
        proxywasm.LogErrorf("ERROR: Config is nil in OnHttpRequestHeaders")
        return types.ActionContinue
    }
    
    proxywasm.LogInfof("Config loaded: URLHeader='%s', OutputHeader='%s'", 
        ctx.config.URLHeaderName, ctx.config.OutputHeaderName)
    
    // Debug: List all headers
    headers, err := proxywasm.GetHttpRequestHeaders()
    if err != nil {
        proxywasm.LogErrorf("Failed to get all headers: %v", err)
    } else {
        proxywasm.LogInfof("All request headers:")
        for _, header := range headers {
            proxywasm.LogInfof("  %s: %s", header[0], header[1])
        }
    }
    
    // Get the URL to be signed from headers
    originalURL, err := proxywasm.GetHttpRequestHeader(ctx.config.URLHeaderName)
    if err != nil {
        proxywasm.LogErrorf("Error getting header '%s': %v", ctx.config.URLHeaderName, err)
        return types.ActionContinue
    }
    
    if originalURL == "" {
        proxywasm.LogInfof("URL header not found or empty: %s", ctx.config.URLHeaderName)
        return types.ActionContinue
    }

    proxywasm.LogInfof("Found URL to sign: %s", originalURL)
    proxywasm.LogInfof("Generating signed URL for: %s", originalURL)

    // Generate signed URL
    signedURL, err := ctx.generateSignedURL(originalURL)
    if err != nil {
        proxywasm.LogErrorf("failed to generate signed URL: %v", err)
        return types.ActionContinue
    }

    proxywasm.LogInfof("Generated signed URL: %s", signedURL)
    proxywasm.LogInfof("Adding header '%s' with value: %s", ctx.config.OutputHeaderName, signedURL)

    // Add the signed URL as a new header
    err = proxywasm.AddHttpRequestHeader(ctx.config.OutputHeaderName, signedURL)
    if err != nil {
        proxywasm.LogErrorf("FAILED to add header '%s': %v", ctx.config.OutputHeaderName, err)
        return types.ActionContinue
    }

    proxywasm.LogInfof("SUCCESS: Added header '%s'", ctx.config.OutputHeaderName)
    proxywasm.LogInfof("=== OnHttpRequestHeaders END ===")
    return types.ActionContinue
}

func (ctx *httpContext) generateSignedURL(targetURL string) (string, error) {
    proxywasm.LogInfof("generateSignedURL: Starting for %s", targetURL)
    
    // Calculate expiration time
    expiresAt := time.Now().Add(time.Duration(ctx.config.ExpirySeconds) * time.Second).Unix()

    // Parse the target URL
    u, err := url.Parse(targetURL)
    if err != nil {
        return "", fmt.Errorf("invalid target URL: %v", err)
    }

    // Create the URL prefix for signing
    urlPrefix := fmt.Sprintf("%s://%s%s", u.Scheme, u.Host, u.Path)
    
    // Base64 encode the URL prefix
    urlPrefixB64 := base64.URLEncoding.EncodeToString([]byte(urlPrefix))

    // Create the string to sign
    stringToSign := fmt.Sprintf("URLPrefix=%s&Expires=%d&KeyName=%s",
        urlPrefixB64, expiresAt, ctx.config.KeyName)

    // Sign the string using Ed25519
    privateKey := ed25519.PrivateKey(ctx.config.PrivateKey)
    signature := ed25519.Sign(privateKey, []byte(stringToSign))
    signatureB64 := base64.URLEncoding.EncodeToString(signature)

    // Build the final signed URL
    query := u.Query()
    query.Set("URLPrefix", urlPrefixB64)
    query.Set("Expires", strconv.FormatInt(expiresAt, 10))
    query.Set("KeyName", ctx.config.KeyName)
    query.Set("Signature", signatureB64)

    u.RawQuery = query.Encode()
    
    proxywasm.LogInfof("generateSignedURL: Result %s", u.String())
    return u.String(), nil
}

// [END serviceextensions_plugin_cdn_token_generator]
