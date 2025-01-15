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

// [START serviceextensions_plugin_log_query]
package main

import (
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

type puginContext struct {
	types.DefaultPluginContext
}

type httpContext struct {
	types.DefaultHttpContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &puginContext{}
}

func (*puginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{}
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != types.ErrorStatusNotFound {
		if err != nil {
			panic(err)
		}
		u, err := url.Parse(path)
		if err != nil {
			panic(err)
		}
		token := u.Query().Get("token")
		if token == "" {
			token = "<missing>"
		}
		proxywasm.LogInfof("token: %s", token)
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_log_query]
