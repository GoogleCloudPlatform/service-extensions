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

// [START serviceextensions_plugin_redirect]
package main

import (
	"fmt"
	"strings"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const (
	oldPathPrefix = "/foo/"
	newPathPrefix = "/bar/"
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

func (p *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	// Get the path from request headers
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		proxywasm.LogErrorf("failed to get path header: %v", err)
		return types.ActionContinue
	}

	// Check if path starts with old prefix
	if strings.HasPrefix(path, oldPathPrefix) {
		// Create new path by replacing prefix
		newPath := newPathPrefix + strings.TrimPrefix(path, oldPathPrefix)

		// Send redirect response
		headers := [][2]string{{"Location", newPath}}
		body := []byte("Content moved to " + newPath)

		if err := proxywasm.SendHttpResponse(301, headers, body, -1); err != nil {
			proxywasm.LogErrorf("failed to send redirect response: %v", err)
			return types.ActionContinue
		}

		return types.ActionPause
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_redirect]
