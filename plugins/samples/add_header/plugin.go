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

// [START serviceextensions_plugin_add_header]
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

func (vc *vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

type pluginContext struct {
	types.DefaultPluginContext
}

func (pc *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &myHttpContext{}
}

type myHttpContext struct {
	types.DefaultHttpContext
}

func (ctx *myHttpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	// Add and replace headers.
	if err := proxywasm.AddHttpRequestHeader("Message", "hello"); err != nil {
		panic(err)
	}
	if err := proxywasm.ReplaceHttpRequestHeader("Welcome", "warm"); err != nil {
		panic(err)
	}
	return types.ActionContinue
}

func (ctx *myHttpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	// Conditionally add to a header value.
	msgValue, err := proxywasm.GetHttpResponseHeader("Message")
	if err != nil {
		proxywasm.LogCriticalf("failed to get 'Message' header: %v", err)
	} else if msgValue == "foo" {
		if err := proxywasm.AddHttpResponseHeader("Message", "bar"); err != nil {
			panic(err)
		}
	}

	// Unconditionally remove the "Welcome" header.
	if err := proxywasm.RemoveHttpResponseHeader("Welcome"); err != nil {
		panic(err)
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_add_header]
