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

// [START serviceextensions_plugin_country_query]
package main

import (
	"fmt"
	"net/url"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const defaultCountry = "unknown"

var clientRegionPath = []string{"request", "client_region"}

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

func (*vmContext) NewPluginContext(uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{}
}

func (ctx *httpContext) OnHttpRequestHeaders(int, bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	countryValue := ctx.getCountryValue()

	proxywasm.LogInfof("country: %s", countryValue)

	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != types.ErrorStatusNotFound {
		if err != nil {
			panic(err)
		}
		u, err := url.Parse(path)
		if err != nil {
			panic(err)
		}
		query := u.Query()
		query.Set("country", countryValue)
		u.RawQuery = query.Encode()

		proxywasm.ReplaceHttpRequestHeader(":path", u.String())
	}

	return types.ActionContinue
}

func (ctx *httpContext) getCountryValue() string {
	value, err := proxywasm.GetProperty(clientRegionPath)
	if err != nil || len(value) == 0 {
		return defaultCountry
	}

	return string(value)
}

// [END serviceextensions_plugin_country_query]
