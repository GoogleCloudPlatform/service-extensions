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

// [START serviceextensions_plugin_hmac_authcookie]
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

// Replace with your desired secret key.
const secretKey = "your_secret_key"

func main() {}

type vmContext struct{ types.DefaultVMContext }

func (*vmContext) NewPluginContext(uint32) types.PluginContext {
	return &pluginContext{}
}

type pluginContext struct {
	types.DefaultPluginContext
	ipRegex *regexp.Regexp
}

// Regex for matching IPs on format like 127.0.0.1.
func (p *pluginContext) OnPluginStart(int) types.OnPluginStartStatus {
	re, err := regexp.Compile(`^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$`)
	if err != nil {
		proxywasm.LogCriticalf("Failed to compile IP regex: %v", err)
		return types.OnPluginStartStatusFailed
	}
	p.ipRegex = re
	return types.OnPluginStartStatusOK
}

func (p *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{ipRegex: p.ipRegex}
}

type httpContext struct {
	types.DefaultHttpContext
	ipRegex *regexp.Regexp
}

// Validates the HMAC HTTP cookie performing the following steps:
//
//  1. Obtains the client IP address and rejects the request if it is not present.
//  2. Obtains the HTTP cookie and rejects the request if it is not present.
//  3. Verifies that the HMAC hash of the cookie matches its payload, rejecting
//     the request if there is no match.
//  4. Ensures that the client IP address matches the IP in the cookie payload,
//     and that the current time is earlier than the expiration time specified in
//     the cookie payload.
func (ctx *httpContext) OnHttpRequestHeaders(int, bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), -1)
		}
	}()

	clientIP, ok := ctx.getClientIP()
	if !ok {
		ctx.sendResponse(403, "Access forbidden - missing client IP.\n")
		return types.ActionPause
	}

	token, ok := ctx.getAuthCookie()
	if !ok {
		ctx.sendResponse(403, "Access forbidden - missing HMAC cookie.\n")
		return types.ActionPause
	}

	payload, signature, ok := ctx.parseAuthCookie(token)
	if !ok {
		ctx.sendResponse(403, "Access forbidden - invalid HMAC cookie.\n")
		return types.ActionPause
	}

	if !ctx.verifyHMAC(payload, signature) {
		ctx.sendResponse(403, "Access forbidden - invalid HMAC hash.\n")
		return types.ActionPause
	}

	ip, exp, ok := ctx.parsePayload(payload)
	if !ok || ip != clientIP {
		ctx.sendResponse(403, "Access forbidden - invalid client IP.\n")
		return types.ActionPause
	}

	if !ctx.validateExpiration(exp) {
		ctx.sendResponse(403, "Access forbidden - hash expired.\n")
		return types.ActionPause
	}

	return types.ActionContinue
}

// Try to get the client IP from the X-Forwarded-For header.
func (ctx *httpContext) getClientIP() (string, bool) {
	xfwd, err := proxywasm.GetHttpRequestHeader("X-Forwarded-For")
	if err != nil || xfwd == "" {
		proxywasm.LogWarn("Failed to get or empty X-Forwarded-For header")
		return "", false
	}

	for _, ip := range strings.Split(xfwd, ",") {
		ip = strings.TrimSpace(ip)
		if ctx.ipRegex.MatchString(ip) {
			return ip, true
		}
	}
	proxywasm.LogWarn("No valid IP found in X-Forwarded-For header")
	return "", false
}

// Try to get the HMAC auth token from the Cookie header.
func (ctx *httpContext) getAuthCookie() (string, bool) {
	cookies, err := proxywasm.GetHttpRequestHeader("Cookie")
	if err != nil || cookies == "" {
		proxywasm.LogWarn("Failed to get or empty Cookie header")
		return "", false
	}

	for _, c := range strings.Split(cookies, "; ") {
		parts := strings.SplitN(c, "=", 2)
		if len(parts) == 2 && parts[0] == "Authorization" {
			return parts[1], true
		}
	}
	proxywasm.LogWarn("Authorization cookie not found")
	return "", false
}

// Try to parse the authorization cookie in the format
// "base64(payload)" + "." + "base64(HMAC(payload))".
func (ctx *httpContext) parseAuthCookie(token string) (payload, signature string, ok bool) {
	parts := strings.SplitN(token, ".", 2)
	if len(parts) != 2 {
		proxywasm.LogWarn("Invalid cookie format: missing separator")
		return "", "", false
	}

	payloadBytes, err := base64.StdEncoding.DecodeString(parts[0])
	if err != nil {
		proxywasm.LogWarnf("Failed to decode payload: %v", err)
		return "", "", false
	}

	signatureBytes, err := base64.StdEncoding.DecodeString(parts[1])
	if err != nil {
		proxywasm.LogWarnf("Failed to decode signature: %v", err)
		return "", "", false
	}

	return string(payloadBytes), string(signatureBytes), true
}

// Function to compute the HMAC signature.
func (ctx *httpContext) verifyHMAC(payload, signature string) bool {
	h := hmac.New(sha256.New, []byte(secretKey))
	h.Write([]byte(payload))
	computedSignature := fmt.Sprintf("%x", h.Sum(nil))
	return computedSignature == signature
}

// Try to parse the payload into client IP and expiration timestamp.
// The payload is expected to be in the format "client_ip,expiration_timestamp".
func (ctx *httpContext) parsePayload(payload string) (ip, exp string, ok bool) {
	parts := strings.SplitN(payload, ",", 2)
	if len(parts) != 2 {
		proxywasm.LogWarn("Invalid payload format: missing separator")
		return "", "", false
	}
	return parts[0], parts[1], true
}

// Check if the current time is earlier than cookie payload expiration.
func (ctx *httpContext) validateExpiration(exp string) bool {
	timestamp, err := strconv.ParseInt(exp, 10, 64)
	if err != nil {
		proxywasm.LogWarnf("Failed to parse expiration timestamp: %v", err)
		return false
	}
	return time.Now().UnixNano() <= timestamp
}

func (ctx *httpContext) sendResponse(status int, body string) {
	proxywasm.SendHttpResponse(uint32(status), [][2]string{
		{"Content-Type", "text/plain"},
	}, []byte(body), -1)
}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

// [END serviceextensions_plugin_hmac_authcookie]
