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

package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"strings"
)

// MyHttpContext implements the Context interface.
type MyHttpContext struct {
	proxywasm.DefaultHttpContext
}

// NewMyHttpContext creates a new instance of MyHttpContext.
func NewMyHttpContext(id uint32, root *proxywasm.RootContext) *MyHttpContext {
	return &MyHttpContext{}
}

// OnRequestHeaders processes the incoming request headers.
func (ctx *MyHttpContext) OnRequestHeaders(headers map[string]string, endOfStream bool) proxywasm.FilterHeadersStatus {
	// Check "Sec-CH-UA-Mobile" header first (highest priority)
	if mobileHeader, exists := headers["Sec-CH-UA-Mobile"]; exists && mobileHeader == "?1" {
		proxywasm.AddRequestHeader("client-device-type", "mobile")
		return proxywasm.FilterHeadersStatusContinue
	}

	// Check "User-Agent" header for mobile substring (case insensitive)
	if userAgent, exists := headers["User-Agent"]; exists && strings.Contains(strings.ToLower(userAgent), "mobile") {
		proxywasm.AddRequestHeader("client-device-type", "mobile")
		return proxywasm.FilterHeadersStatusContinue
	}

	// No specific device type identified, set to "unknown"
	proxywasm.AddRequestHeader("client-device-type", "unknown")
	return proxywasm.FilterHeadersStatusContinue
}

// Register the MyHttpContext factory.
func Register() {
	proxywasm.RegisterHttpContextFactory(NewMyHttpContext)
}
