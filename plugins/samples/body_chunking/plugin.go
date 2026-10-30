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

// [START serviceextensions_plugin_body_chunking]
package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {}
func init() {
	proxywasm.SetHttpContext(func(contextID uint32) types.HttpContext { return &httpContext{} })
}

type httpContext struct {
	types.DefaultHttpContext
}

func sendErrorResponse(err error) {
	proxywasm.SendHttpResponse(500, [][2]string{}, []byte(err.Error()), 0)
}

// Add foo onto the end of each request body chunk
func (ctx *httpContext) OnHttpRequestBody(bodySize int, endOfStream bool) types.Action {
	chunk, err := proxywasm.GetHttpRequestBody(0, bodySize)
	if err != nil {
		sendErrorResponse(err)
		return types.ActionContinue
	}
	err = proxywasm.ReplaceHttpRequestBody(append(chunk, "foo"...))
	if err != nil {
		sendErrorResponse(err)
		return types.ActionContinue
	}
	return types.ActionContinue
}

// Add bar onto the end of each response body chunk
func (ctx *httpContext) OnHttpResponseBody(bodySize int, endOfStream bool) types.Action {
	chunk, err := proxywasm.GetHttpResponseBody(0, bodySize)
	if err != nil {
		sendErrorResponse(err)
		return types.ActionContinue
	}
	err = proxywasm.ReplaceHttpResponseBody(append(chunk, "bar"...))
	if err != nil {
		sendErrorResponse(err)
		return types.ActionContinue
	}
	return types.ActionContinue
}

// [END serviceextensions_plugin_body_chunking]
