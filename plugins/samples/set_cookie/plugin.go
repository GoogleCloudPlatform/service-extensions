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

// [START serviceextensions_plugin_set_cookie]
package main

import (
	"fmt"
	"math/rand"
	"strings"
	"time"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const cookieName = "my_cookie"

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
	// Initialize random seed
	rand.Seed(time.Now().UnixNano())
}

type vmContext struct {
	types.DefaultVMContext
}

type pluginContext struct {
	types.DefaultPluginContext
}

type httpContext struct {
	types.DefaultHttpContext
	sessionID *string
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (*pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{}
}

func generateRandom() uint64 {
	return rand.Uint64()
}

func getSessionIDFromCookie() (*string, error) {
	cookies, err := proxywasm.GetHttpRequestHeader("Cookie")
	if err != nil {
		return nil, err
	}

	// Split cookies and look for session cookie
	cookieParts := strings.Split(cookies, "; ")
	for _, cookie := range cookieParts {
		parts := strings.SplitN(cookie, "=", 2)
		if len(parts) == 2 && parts[0] == cookieName {
			return &parts[1], nil
		}
	}

	return nil, nil
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	var err error
	ctx.sessionID, err = getSessionIDFromCookie()
	if err != nil {
		proxywasm.LogErrorf("failed to get session ID from cookie: %v", err)
		return types.ActionContinue
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	if ctx.sessionID != nil {
		proxywasm.LogInfof("This current request is for the existing session ID: %s", *ctx.sessionID)
	} else {
		// Generate new session ID
		newSessionID := fmt.Sprintf("%d", generateRandom())
		proxywasm.LogInfof("New session ID created for the current request: %s", newSessionID)

		// Set the cookie
		cookieValue := fmt.Sprintf("%s=%s; Path=/; HttpOnly", cookieName, newSessionID)
		if err := proxywasm.AddHttpResponseHeader("Set-Cookie", cookieValue); err != nil {
			proxywasm.LogErrorf("failed to set cookie header: %v", err)
			return types.ActionContinue
		}
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_set_cookie]
