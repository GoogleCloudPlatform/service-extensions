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

// [START serviceextensions_plugin_overwrite_header]
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
}

// This sample replaces an HTTP header with the given key and value.
// Unlike `AddHttpRequestHeader` which appends values to existing headers,
// this plugin overwrites the entire value for the specified key if the
// header already exists or create it with the new value.
type httpContext struct {
	types.DefaultHttpContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{}
}

// It will only replace the header if it already exists.
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	// Change the key and value according to your needs.
	headerKey := "RequestHeader"
	header, err := proxywasm.GetHttpRequestHeader(headerKey)
	if err != nil && err != types.ErrorStatusNotFound {
		panic(err)
	}
	if len(header) > 0 {
		err := proxywasm.ReplaceHttpRequestHeader(headerKey, "changed")
		if err != nil {
			panic(err)
		}
	}
	return types.ActionContinue
}

// Unlike the previous example, the header will be added if it doesn't exist
// or updated if it already does.
func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	// Change the key and value according to your needs.
	err := proxywasm.ReplaceHttpResponseHeader("ResponseHeader", "changed")
	if err != nil {
		panic(err)
	}
	return types.ActionContinue
}

// [END serviceextensions_plugin_overwrite_header]
