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

// [START serviceextensions_plugin_set_query]
package main

import (
	"fmt"
	"net/url"
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

func (*pluginContext) NewHttpContext(uint32) types.HttpContext {
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

	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		proxywasm.LogError("Failed to retrieve the :path header")
		return types.ActionContinue
	}

	parsedURL, err := url.Parse(path)
	if err != nil {
		proxywasm.LogWarnf("Failed to parse URL: %v", err)
		return types.ActionContinue
	}

	val := "new val"
	// Manually replace spaces with '+'
	encodedVal := strings.ReplaceAll(val, " ", "+")
	queryParams := parsedURL.Query()

	// Update the query parameters
	queryParams.Del("key") // Remove existing key if it exists
	queryParams.Add("key", encodedVal)

	// Rebuild the URL with the updated query parameters
	parsedURL.RawQuery = queryParams.Encode()

	// url.Values.Encode converts spaces to %2B, fix this manually
	parsedURL.RawQuery = strings.ReplaceAll(parsedURL.RawQuery, "%2B", "+")

	// Replace the request header ":path" with the updated URL
	proxywasm.ReplaceHttpRequestHeader(":path", parsedURL.String())
	if err != nil {
		proxywasm.LogErrorf("Failed to replace :path header: %v", err)
		return types.ActionContinue
	}

	proxywasm.LogInfof("Updated :path header to: %s", parsedURL.String())

	return types.ActionContinue
}

// [END serviceextensions_plugin_set_query]
