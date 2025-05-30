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
// [START serviceextensions_plugin_hello_world]
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
func (vc *vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}
func (pc *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Send HTTP response immediately to avoid unnecessary path
	proxywasm.SendHttpResponse(200, [][2]string{
		{"Content-Type", "text/plain"},
		{":status", "200"},
	}, []byte("Hello World"), -1)
	return types.ActionPause
}
func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	return types.ActionContinue
}
func (ctx *httpContext) OnHttpResponseBody(bodySize int, endOfStream bool) types.Action {
	return types.ActionContinue
}
// [END serviceextensions_plugin_hello_world]