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

// [START serviceextensions_plugin_hmac_token_validation]
package main

import (
	"crypto/hmac"
	"crypto/md5"
	"encoding/hex"
	"fmt"
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

type vmContext struct {
	types.DefaultVMContext
}

type pluginContext struct {
	types.DefaultPluginContext
	secretKey            string
	tokenValiditySeconds int64
}

// HTTPContext handles individual HTTP requests with HMAC validation
type httpContext struct {
	types.DefaultHttpContext
	secretKey            string
	tokenValiditySeconds int64
}

// Creates a new plugin context with default configuration
func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{
		secretKey:            "your-secret-key", // Replace with your actual secret key
		tokenValiditySeconds: 300,               // Default token validity (5 minutes)
	}
}

// Creates a new HTTP context for each request
func (p *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{
		secretKey:            p.secretKey,
		tokenValiditySeconds: p.tokenValiditySeconds,
	}
}

// Handles incoming HTTP request headers and performs HMAC validation
// The validation follows these steps:
// 1. Check for Authorization header presence
// 2. Verify the HMAC scheme format
// 3. Parse timestamp and HMAC from token
// 4. Validate timestamp format
// 5. Check token expiration
// 6. Verify required headers (:method, :path)
// 7. Compute and compare HMAC signatures
func (h *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Recovery handler for unexpected panics
	defer func() {
		if r := recover(); r != nil {
			proxywasm.SendHttpResponse(500, nil, []byte(fmt.Sprintf("Internal server error: %v", r)), -1)
		}
	}()

	// 1. Check Authorization header exists
	authHeader, err := proxywasm.GetHttpRequestHeader("authorization")
	if err != nil || authHeader == "" {
		proxywasm.SendHttpResponse(401, [][2]string{{"WWW-Authenticate", `HMAC realm="api"`}}, []byte("Missing Authorization header"), -1)
		return types.ActionPause
	}

	// 2. Verify Authorization scheme
	if len(authHeader) < 5 || !strings.EqualFold(authHeader[:5], "HMAC ") {
		proxywasm.SendHttpResponse(400, nil, []byte("Invalid Authorization scheme. Use 'HMAC'"), -1)
		return types.ActionPause
	}

	// 3. Split token into timestamp and HMAC
	token := authHeader[5:]
	parts := strings.SplitN(token, ":", 2)
	if len(parts) != 2 {
		proxywasm.SendHttpResponse(400, nil, []byte("Invalid token format: expected 'timestamp:hmac'"), -1)
		return types.ActionPause
	}

	timestampStr, providedHmac := parts[0], parts[1]

	// 4. Validate timestamp format
	timestamp, err := strconv.ParseInt(timestampStr, 10, 64)
	if err != nil {
		proxywasm.SendHttpResponse(400, nil, []byte("Invalid timestamp"), -1)
		return types.ActionPause
	}

	// 5. Check token expiration
	currentTime := time.Now().Unix()
	if currentTime-timestamp > h.tokenValiditySeconds {
		proxywasm.SendHttpResponse(403, nil, []byte("Token expired"), -1)
		return types.ActionPause
	}

	// 6. Get required headers
	method, err := proxywasm.GetHttpRequestHeader(":method")
	if err != nil || method == "" {
		proxywasm.SendHttpResponse(400, nil, []byte("Missing :method header"), -1)
		return types.ActionPause
	}

	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil || path == "" {
		proxywasm.SendHttpResponse(400, nil, []byte("Missing :path header"), -1)
		return types.ActionPause
	}

	// 7. Compute and validate HMAC
	message := fmt.Sprintf("%s:%s:%s", method, path, timestampStr)
	computedHmac := computeHmacMd5(message, h.secretKey)

	proxywasm.LogDebugf("HMAC validation: method=%s path=%s timestamp=%s received=%s expected=%s",
		method, path, timestampStr, providedHmac, computedHmac)

	if computedHmac != providedHmac {
		clientIP, _ := proxywasm.GetHttpRequestHeader("x-forwarded-for")
		proxywasm.LogWarnf("Invalid HMAC from %s", clientIP)
		proxywasm.SendHttpResponse(403, nil, []byte("Invalid HMAC"), -1)
		return types.ActionPause
	}

	proxywasm.LogInfof("Valid HMAC for path: %s", path)
	return types.ActionContinue
}

// computeHmacMd5 generates an HMAC-MD5 signature for the given message and key
// Returns the signature as a lowercase hexadecimal string
func computeHmacMd5(message, key string) string {
	mac := hmac.New(md5.New, []byte(key))
	mac.Write([]byte(message))
	return hex.EncodeToString(mac.Sum(nil))
}

// [END serviceextensions_plugin_hmac_token_validation]
