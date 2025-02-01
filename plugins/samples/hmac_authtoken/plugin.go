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

// [START serviceextensions_plugin_hmac_authtoken]
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/url"

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
}

type httpContext struct {
	types.DefaultHttpContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{}
}

const (
	// Replace with your desired secret key.
	secretKey = "your_secret_key"
)

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		panic(err)
	}
	u, err := url.ParseRequestURI(path)
	if err != nil {
		proxywasm.LogErrorf("Error parsing the :path HTTP header: %v", err)
		proxywasm.SendHttpResponse(400, [][2]string{}, []byte("Error parsing the :path HTTP header.\n"), 0)
		return types.ActionPause
	}

	token := u.Query().Get("token")
	// Check if the HMAC token exists.
	if token == "" {
		proxywasm.LogErrorf("Access forbidden - missing token.")
		proxywasm.SendHttpResponse(403, [][2]string{}, []byte("Access forbidden - missing token.\n"), 0)
		return types.ActionPause
	}

	// Strip the token from the URL.
	query := u.Query()
	query.Del("token")
	newPath := (&url.URL{
		Path:     u.Path,
		RawQuery: query.Encode(),
	}).String()
	// Compare if the generated signature matches the token sent.
	// In this sample the signature is generated using the request :path.
	if !ctx.CheckHmacSignature(newPath, token) {
		proxywasm.LogErrorf("Access forbidden - invalid token.")
		proxywasm.SendHttpResponse(403, [][2]string{}, []byte("Access forbidden - invalid token.\n"), 0)
		return types.ActionPause
	}

	err = proxywasm.ReplaceHttpRequestHeader(":path", newPath)
	if err != nil {
		panic(err)
	}
	return types.ActionContinue

}

func (*httpContext) CheckHmacSignature(data string, token string) bool {
	mac := hmac.New(sha256.New, []byte(secretKey))
	mac.Write([]byte(data))
	expectedMAC := mac.Sum(nil)
	proxywasm.LogInfof("expectedMAC: %v, path: %v", hex.EncodeToString(expectedMAC), data)
	return hex.EncodeToString(expectedMAC) == token
}

// [END serviceextensions_plugin_hmac_authtoken]
