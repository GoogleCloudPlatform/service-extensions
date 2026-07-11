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
	"net/http"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const cookieName = "my_cookie"

func main() {}

func init() {
	proxywasm.SetHttpContext(func(contextID uint32) types.HttpContext {
		return &httpContext{}
	})
}

type httpContext struct {
	types.DefaultHttpContext
	sessionID *string
}

func getSessionIDFromCookie() (*string, error) {
	cookieHeader, err := proxywasm.GetHttpRequestHeader("Cookie")
	if err != nil {
		return nil, err
	}

	cookies, err := http.ParseCookie(cookieHeader)
	if err != nil {
		return nil, err
	}

	for _, cookie := range cookies {
		if cookie.Name == cookieName {
			return &cookie.Value, nil
		}
	}

	return nil, nil
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	var err error
	ctx.sessionID, err = getSessionIDFromCookie()
	if err != nil {
		proxywasm.LogErrorf("failed to get session ID from cookie: %v", err)
		return types.ActionContinue
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	if ctx.sessionID != nil {
		proxywasm.LogInfof("This current request is for the existing session ID: %s", *ctx.sessionID)
	} else {
		// Generate new session ID
		newSessionID := fmt.Sprintf("%d", rand.Uint64())
		proxywasm.LogInfof("New session ID created for the current request: %s", newSessionID)

		// Set the cookie
		cookie := &http.Cookie{
			Name:     cookieName,
			Value:    newSessionID,
			Path:     "/",
			HttpOnly: true,
		}
		if err := proxywasm.AddHttpResponseHeader("Set-Cookie", cookie.String()); err != nil {
			proxywasm.LogErrorf("failed to set cookie header: %v", err)
			return types.ActionContinue
		}
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_set_cookie]
