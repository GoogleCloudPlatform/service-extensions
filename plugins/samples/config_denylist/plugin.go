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

// [START serviceextensions_plugin_config_denylist]
package main

import (
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
	tokens map[string]struct{}
}

type httpContext struct {
	types.DefaultHttpContext
	tokens map[string]struct{}
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{tokens: make(map[string]struct{})}
}

func (ctx *pluginContext) OnPluginStart(int) types.OnPluginStartStatus {
	config, err := proxywasm.GetPluginConfiguration()
	if err != types.ErrorStatusNotFound {
		if err != nil {
			proxywasm.LogErrorf("Error reading the configuration: %v", err)
			return types.OnPluginStartStatusFailed
		}
		for _, token := range strings.Fields(string(config)) {
			ctx.tokens[token] = struct{}{}
		}
	}
	proxywasm.LogInfof("Config keys size %v", len(ctx.tokens))
	return types.OnPluginStartStatusOK
}

func (ctx *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{tokens: ctx.tokens}
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	userToken, err := proxywasm.GetHttpRequestHeader("User-Token")
	if err != nil {
		proxywasm.SendHttpResponse(403, [][2]string{}, []byte("Access forbidden - token missing.\n"), 0)
		return types.ActionContinue
	}
	if _, found := ctx.tokens[userToken]; found {
		proxywasm.SendHttpResponse(403, [][2]string{}, []byte("Access forbidden.\n"), 0)
		return types.ActionContinue
	}
	return types.ActionContinue
}

// [END serviceextensions_plugin_config_denylist]
