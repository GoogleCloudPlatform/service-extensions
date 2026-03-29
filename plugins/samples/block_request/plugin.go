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

// [START serviceextensions_plugin_block_request]
package main

import (
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {}
func init() {
	uuid.EnableRandPool()
	proxywasm.SetHttpContext(newHttpContext)
}

type httpContext struct {
	types.DefaultHttpContext
}

func newHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}

func generateRequestId() string {
	id := uuid.NewString()
	return strings.Replace(id, "-", "", -1)
}

const (
	allowedReferer = "safe-site.com"
)

// Checks whether the client's Referer header matches an expected domain. If
// not, generate a 403 Forbidden response.
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	referer, err := proxywasm.GetHttpRequestHeader("Referer")
	// Check if referer match with the expected domain.
	if err == types.ErrorStatusNotFound || !strings.Contains(referer, allowedReferer) {
		requestId := generateRequestId()
		proxywasm.LogInfof("Forbidden - Request ID: %v", requestId)
		proxywasm.SendHttpResponse(403, [][2]string{}, []byte(fmt.Sprintf("Forbidden - Request ID: %v", requestId)), 0)
		return types.ActionContinue
	} else if err != nil {
		proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		return types.ActionContinue
	}

	// Change it to a meaningful name according to your needs.
	proxywasm.AddHttpRequestHeader("my-plugin-allowed", "true")
	return types.ActionContinue
}

// [END serviceextensions_plugin_block_request]
