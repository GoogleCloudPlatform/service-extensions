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

// [START serviceextensions_plugin_jwt_auth]
package main

import (
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"net/url"

	jwt "github.com/golang-jwt/jwt/v5"
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
	publicKey *rsa.PublicKey
}

type httpContext struct {
	types.DefaultHttpContext
	publicKey *rsa.PublicKey
}

func (*vmContext) NewPluginContext(uint32) types.PluginContext {
	return &pluginContext{}
}

func (p *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{publicKey: p.publicKey}
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	config, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogCriticalf("failed to get config: %v", err)
		return types.OnPluginStartStatusFailed
	}

	block, _ := pem.Decode(config)
	if block == nil {
		proxywasm.LogCritical("failed to decode PEM block")
		return types.OnPluginStartStatusFailed
	}

	var pub interface{}
	pub, err = x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		pub, err = x509.ParsePKCS1PublicKey(block.Bytes)
		if err != nil {
			proxywasm.LogCriticalf("failed to parse public key: %v", err)
			return types.OnPluginStartStatusFailed
		}
	}

	rsaPub, ok := pub.(*rsa.PublicKey)
	if !ok {
		proxywasm.LogCritical("public key is not RSA")
		return types.OnPluginStartStatusFailed
	}

	p.publicKey = rsaPub
	return types.OnPluginStartStatusOK
}

func (ctx *httpContext) OnHttpRequestHeaders(int, bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	// Get the ":path" header
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil || path == "" {
		proxywasm.LogWarn("Access forbidden - missing :path header.")
		ctx.sendResponse(403, "Access forbidden - missing :path header.\n")
		return types.ActionPause
	}

	// Parse the URL
	u, err := url.ParseRequestURI(path)
	if err != nil {
		proxywasm.LogWarn("Access forbidden - invalid URL.")
		ctx.sendResponse(403, "Access forbidden - invalid URL.\n")
		return types.ActionPause
	}

	// Extract the JWT from the query parameters
	query := u.Query()
	jwtToken := query.Get("jwt")
	if jwtToken == "" {
		proxywasm.LogWarn("WARN: Access forbidden - missing token.")
		ctx.sendResponse(403, "Access forbidden - missing token.\n")
		return types.ActionPause
	}

	// Check token structure without validating claims
	parser := jwt.NewParser(jwt.WithoutClaimsValidation())
	_, _, err = parser.ParseUnverified(jwtToken, jwt.MapClaims{})
	if err != nil {
		proxywasm.LogWarn("WARN: Access forbidden - invalid token.")
		ctx.sendResponse(403, "Access forbidden - invalid token.\n")
		return types.ActionPause
	}

	// Validate the token (signature and claims)
	token, err := jwt.Parse(jwtToken, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return ctx.publicKey, nil
	})
	if err != nil || !token.Valid {
		proxywasm.LogWarn("WARN: Access forbidden.")
		ctx.sendResponse(403, "Access forbidden.\n")
		return types.ActionPause
	}

	// Strip the "jwt" parameter from the URL
	query.Del("jwt")
	u.RawQuery = query.Encode()
	if err := proxywasm.ReplaceHttpRequestHeader(":path", u.String()); err != nil {
		proxywasm.LogError("Failed to update path")
		ctx.sendResponse(500, "Internal server error\n")
		return types.ActionPause
	}

	return types.ActionContinue
}

func (ctx *httpContext) sendResponse(statusCode int, body string) {
	proxywasm.SendHttpResponse(uint32(statusCode), [][2]string{{"content-type", "text/plain"}}, []byte(body), -1)
}

// [END serviceextensions_plugin_jwt_auth]
