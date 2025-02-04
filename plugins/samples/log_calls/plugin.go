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

// [START serviceextensions_plugin_log_calls]
package main

import (
	"fmt"
	"strings"

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

func (*pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Recover from any potential panics to avoid crashing the plugin
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(
				500,
				[][2]string{},
				[]byte(fmt.Sprintf("Internal Server Error: %v", err)),
				-1,
			)
		}
	}()

	proxywasm.LogInfo("http OnHttpRequestHeaders called")

	config, err := proxywasm.GetPluginConfiguration()

	if err != nil {

		for _, numHeaders := range strings.Fields(string(config)) {
			headerKey, err := proxywasm.GetHttpRequestHeader(numHeaders)
			if err == nil && strings.EqualFold(headerKey, "x-custom-header") {
				headerValue, err := proxywasm.GetHttpRequestHeader(headerKey)
				// Normalize the header value
				if err == nil {
					normalizedValue := strings.ToLower(headerValue)
					proxywasm.ReplaceHttpRequestHeader(headerKey, normalizedValue)
				}

			}
		}
	}

	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	proxywasm.LogInfo("http OnHttpResponseHeaders called")

	return types.ActionContinue
}

// [END serviceextensions_plugin_log_calls]
