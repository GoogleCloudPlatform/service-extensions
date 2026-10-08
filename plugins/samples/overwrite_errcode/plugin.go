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

// [START serviceextensions_plugin_overwrite_errcode]
package main

import (
	"fmt"
	"strconv"

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

func (*httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	statusVal, err := proxywasm.GetHttpResponseHeader(":status")
	if err != nil {
		proxywasm.LogErrorf("failed to get status header: %v", err)
		return types.ActionContinue
	}

	responseCode, err := strconv.Atoi(statusVal)
	if err != nil {
		proxywasm.LogErrorf("failed to parse status code: %v", err)
		return types.ActionContinue
	}

	if responseCode/100 == 5 {
		newStatus := mapResponseCode(responseCode)
		err = proxywasm.ReplaceHttpResponseHeader(":status", strconv.Itoa(newStatus))
		if err != nil {
			proxywasm.LogErrorf("failed to set status header: %v", err)
		}
	}

	return types.ActionContinue
}

// mapResponseCode remaps all 5xx responses to 404
func mapResponseCode(responseCode int) int {
	if responseCode/100 == 5 {
		return 404
	}
	return responseCode
}

// [END serviceextensions_plugin_overwrite_errcode]
