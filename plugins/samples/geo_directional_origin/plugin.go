// Copyright 2026 Google LLC
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

// [START serviceextensions_plugin_geo_routing]
package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const (
	clientRegionProperty = "request.client_region"
	countryCodeHeader    = "x-country-code"
)

var clientRegionPropertyPath = []string{clientRegionProperty}

type vmContext struct {
	types.DefaultVMContext
}

type pluginContext struct {
	types.DefaultPluginContext
}

type httpContext struct {
	types.DefaultHttpContext
}

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}

func (ctx *httpContext) OnHttpRequestHeaders(_ int, _ bool) types.Action {
	countryCode, err := proxywasm.GetProperty(clientRegionPropertyPath)

	if err == nil && len(countryCode) > 0 {
		if err := proxywasm.ReplaceHttpRequestHeader(countryCodeHeader, string(countryCode)); err != nil {
			proxywasm.LogWarnf("failed to set country code header: %v", err)
		}
		return types.ActionContinue
	}

	if err := proxywasm.RemoveHttpRequestHeader(countryCodeHeader); err != nil {
		proxywasm.LogWarnf("failed to remove country code header: %v", err)
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_geo_routing]
