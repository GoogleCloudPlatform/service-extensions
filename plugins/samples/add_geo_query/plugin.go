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

// [START serviceextensions_plugin_country_query]
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

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Get country value from Cloud CDN headers or default to "unknown"
	countryValue := ctx.getCountryValue()

	// Log the country value for GCP logs
	proxywasm.LogInfof("country: %s", countryValue)

	// Get current path and add country query parameter
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		return types.ActionContinue
	}

	newPath := ctx.addCountryParameter(path, countryValue)
	proxywasm.ReplaceHttpRequestHeader(":path", newPath)

	return types.ActionContinue
}

func (ctx *httpContext) getCountryValue() string {
	// Try common CDN country headers
	countryHeaders := []string{
		"X-Country",
		"CloudFront-Viewer-Country",
		"X-Client-Geo-Location",
		"X-AppEngine-Country",
	}

	for _, header := range countryHeaders {
		value, err := proxywasm.GetHttpRequestHeader(header)
		if err == nil && value != "" {
			return value
		}
	}

	return "unknown"
}

func (ctx *httpContext) addCountryParameter(path, countryValue string) string {
	// Check if query string already exists
	if strings.Contains(path, "?") {
		return path + "&country=" + countryValue
	}
	return path + "?country=" + countryValue
}

// [END serviceextensions_plugin_country_query]
