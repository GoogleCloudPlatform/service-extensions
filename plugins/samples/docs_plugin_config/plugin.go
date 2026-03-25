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

// [START serviceextensions_plugin_docs_plugin_config]
package main

import (
	"fmt"

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
	secret string
}

type httpContext struct {
	types.DefaultHttpContext
	pluginContext *pluginContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (ctx *pluginContext) OnPluginStart(int) types.OnPluginStartStatus {
	config, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogErrorf("Error reading the configuration: %v", err)
		return types.OnPluginStartStatusFailed
	}
	ctx.secret = string(config)
	return types.OnPluginStartStatusOK
}

func (ctx *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{pluginContext: ctx}
}

func (ctx *pluginContext) Secret() string {
	return ctx.secret
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	// Use secret here...
	proxywasm.LogInfof("secret: %v", ctx.pluginContext.Secret())
	return types.ActionContinue
}

// [END serviceextensions_plugin_docs_plugin_config]
