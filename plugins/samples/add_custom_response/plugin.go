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

// [START serviceextensions_plugin_add_custom_response]
package main

import (
	"strconv"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const redirectPage = "https://storage.googleapis.com/www.example.com/server-error.html"

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

type (
	vmContext     struct{ types.DefaultVMContext }
	pluginContext struct{ types.DefaultPluginContext }
	httpContext   struct{ types.DefaultHttpContext }
)

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	statusVal, err := proxywasm.GetHttpResponseHeader(":status")
	if err != nil || statusVal == "" {
		return types.ActionContinue
	}

	// Attempt to parse the status as an integer.
	responseCode, parseErr := strconv.Atoi(statusVal)
	if parseErr != nil {
		return types.ActionContinue
	}

	// If this is a 5xx response, send a 302 redirect to the custom page.
	if responseCode/100 == 5 {
		proxywasm.SendHttpResponse(302, [][2]string{{"Origin-Status", statusVal}, {"Location", redirectPage}}, nil, 0)
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_add_custom_response]
