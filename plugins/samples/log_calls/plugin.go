// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// [START serviceextensions_plugin_log_calls]
package main

import (
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

func (*vmContext) OnVMStart(vmConfigurationSize int) types.OnVMStartStatus {
	proxywasm.LogInfof("root onStart called")
	return types.OnVMStartStatusOK
}
func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	proxywasm.LogInfof("root onCreate called")
	return &pluginContext{}
}
func (*pluginContext) OnPluginStart(int) types.OnPluginStartStatus {
	proxywasm.LogInfof("root onConfigure called")
	return types.OnPluginStartStatusOK
}
func (*pluginContext) NewHttpContext(uint32) types.HttpContext {
	proxywasm.LogInfof("http onCreate called")
	return &httpContext{}
}
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	proxywasm.LogInfof("http onRequestHeaders called")
	return types.ActionContinue
}
func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	proxywasm.LogInfof("http onResponseHeaders called")
	return types.ActionContinue
}
func (*httpContext) OnHttpStreamDone() {
	proxywasm.LogInfof("http onDone called")
	proxywasm.LogInfof("http onDelete called")
}

// [END serviceextensions_plugin_log_calls]
