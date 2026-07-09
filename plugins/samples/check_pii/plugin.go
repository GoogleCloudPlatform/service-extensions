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

// [START serviceextensions_plugin_check_pii]
package main

import (
	"bytes"
	"regexp"

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
	cardMatcher   *regexp.Regexp
	code10Matcher *regexp.Regexp
}
type httpContext struct {
	types.DefaultHttpContext
	cardMatcher   *regexp.Regexp
	code10Matcher *regexp.Regexp
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	// Compile the regex expressions at plugin setup time for optimal performance.
	// Credit card numbers in a 16-digit hyphenated format.
	// 10-digit numeric codes.
	return &pluginContext{
		cardMatcher:   regexp.MustCompile(`\d{4}-\d{4}-\d{4}-(\d{4})`),
		code10Matcher: regexp.MustCompile(`\d{7}(\d{3})`),
	}
}

func (p *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{
		cardMatcher:   p.cardMatcher,
		code10Matcher: p.code10Matcher,
	}
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Disallow server compression so we can read the plaintext body.
	err := proxywasm.ReplaceHttpRequestHeader("accept-encoding", "identity")
	if err != nil {
		proxywasm.LogErrorf("failed to replace accept-encoding header: %v", err)
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	headers, err := proxywasm.GetHttpResponseHeaders()
	if err != nil {
		proxywasm.LogErrorf("failed to get response headers: %v", err)
		return types.ActionContinue // Fail open
	}

	for i := range headers {
		key := headers[i][0]
		value := headers[i][1]

		maskedValue := ctx.maskPIIString(value)
		if maskedValue != value {
			err = proxywasm.ReplaceHttpResponseHeader(key, maskedValue)
			if err != nil {
				proxywasm.LogErrorf("failed to replace header %s: %v", key, err)
			}
		}
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseBody(numBytes int, endOfStream bool) types.Action {
	if numBytes == 0 {
		return types.ActionContinue
	}

	body, err := proxywasm.GetHttpResponseBody(0, numBytes)
	if err != nil {
		proxywasm.LogErrorf("failed to get response body: %v", err)
		return types.ActionContinue // Fail open
	}

	// Note: this example does not handle PII split across chunk boundaries.
	maskedBody := ctx.maskPIIBytes(body)

	// Only interact with the WASM host if modifications were actually made
	if !bytes.Equal(body, maskedBody) {
		err = proxywasm.ReplaceHttpResponseBody(maskedBody)
		if err != nil {
			proxywasm.LogErrorf("failed to replace response body: %v", err)
		}
	}

	return types.ActionContinue
}

// maskPIIString is used for Headers (which are naturally strings)
func (ctx *httpContext) maskPIIString(value string) string {
	value = ctx.cardMatcher.ReplaceAllString(value, "XXXX-XXXX-XXXX-${1}")
	value = ctx.code10Matcher.ReplaceAllString(value, "XXXXXXX${1}")
	return value
}

// maskPIIBytes is used for the Body (avoids memory allocation overhead)
func (ctx *httpContext) maskPIIBytes(value []byte) []byte {
	value = ctx.cardMatcher.ReplaceAll(value, []byte("XXXX-XXXX-XXXX-${1}"))
	value = ctx.code10Matcher.ReplaceAll(value, []byte("XXXXXXX${1}"))
	return value
}

// [END serviceextensions_plugin_check_pii]
