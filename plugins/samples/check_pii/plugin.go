// Copyright 2024 Google LLC
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

// [START serviceextensions_plugin_check_pii]
package main

import (
	"fmt"
	"regexp"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {}
func init() {
	proxywasm.SetVMContext(&context{})
}

type context struct {
	types.DefaultVMContext
	types.DefaultPluginContext
	creditCardRegex *regexp.Regexp
}
type httpContext struct {
	types.DefaultHttpContext
	creditCardRegex *regexp.Regexp
	checkBody       bool
}

func (*context) NewPluginContext(contextID uint32) types.PluginContext {
	return &context{creditCardRegex: regexp.MustCompile("\\d{4}-\\d{4}-\\d{4}-(\\d{4})")}
}
func (pluginContext *context) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{creditCardRegex: pluginContext.creditCardRegex}
}
func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	value, err := proxywasm.GetHttpResponseHeader("google-run-pii-check")
	if err != nil {
		panic(err)
	}
	if value != "true" {
		return types.ActionContinue
	}
	ctx.checkBody = true
	headers, err := proxywasm.GetHttpResponseHeaders()
	if err != nil {
		panic(err)
	}
	for i := range headers {
		result := ctx.creditCardRegex.ReplaceAllString(headers[i][1], "XXXX-XXXX-XXXX-${1}")
		if result != headers[i][1] {
			err = proxywasm.ReplaceHttpResponseHeader(headers[i][0], result)
			if err != nil {
				panic(err)
			}
		}
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseBody(numBytes int, endOfStream bool) types.Action {
	if !ctx.checkBody {
		return types.ActionContinue
	}
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	bytes, err := proxywasm.GetHttpResponseBody(0, numBytes)
	if err != nil {
		panic(err)
	}
	bytes = ctx.creditCardRegex.ReplaceAll(bytes, []byte("XXXX-XXXX-XXXX-${1}"))
	err = proxywasm.ReplaceHttpResponseBody(bytes)
	if err != nil {
		panic(err)
	}
	return types.ActionContinue
}

// [END serviceextensions_plugin_check_pii]
