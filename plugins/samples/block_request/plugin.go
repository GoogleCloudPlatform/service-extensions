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

// [START serviceextensions_plugin_block_request]
package main

import (
	"fmt"
	"strings"

	"github.com/google/uuid"
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
	pluginContext *pluginContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	uuid.EnableRandPool()
	return types.OnPluginStartStatusOK
}

func (*pluginContext) GenerateRequestId() string {
	uuid := uuid.NewString()
	return strings.Replace(uuid, "-", "", -1)
}

func (pluginContext *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{pluginContext: pluginContext}
}

const (
	allowedReferer = "safe-site.com"
)

// Checks whether the client's Referer header matches an expected domain. If
// not, generate a 403 Forbidden response.
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	referer, err := proxywasm.GetHttpRequestHeader("Referer")
	// Check if referer match with the expected domain.
	if err == types.ErrorStatusNotFound || !strings.Contains(referer, allowedReferer) {
		requestId := ctx.pluginContext.GenerateRequestId()
		proxywasm.LogInfof("Forbidden - Request ID: %v", requestId)
		proxywasm.SendHttpResponse(403, [][2]string{}, []byte(fmt.Sprintf("Forbidden - Request ID: %v", requestId)), 0)
		return types.ActionPause
	} else if err != nil {
		panic(err)
	}

	// Change it to a meaningful name according to your needs.
	proxywasm.AddHttpRequestHeader("my-plugin-allowed", "true")
	return types.ActionContinue
}

// [END serviceextensions_plugin_block_request]
