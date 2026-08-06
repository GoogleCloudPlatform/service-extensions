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

// [START serviceextensions_plugin_error_page_with_traceid]
package main

import (
	"bytes"
	"regexp"
	"strconv"
	"strings"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const errorTemplate = `
<html>
<head>
  <title>Error {STATUS_CODE}</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; }
    .container { max-width: 800px; margin: 0 auto; }
    .trace-id { 
      background-color: #f5f5f5; 
      padding: 1rem; 
      font-family: monospace;
      word-break: break-all;
      margin-top: 2rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Error {STATUS_CODE}</h1>
    <p>We're sorry, something went wrong with your request.</p>
    
    <div class="trace-id">
      <strong>Trace ID:</strong> {TRACE_ID}
    </div>
    
    <p>Please provide this trace ID to support for assistance.</p>
  </div>
</body>
</html>
`

var w3cTraceRegex = regexp.MustCompile(`^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$`)

func getErrorTemplate(statusCode, traceID string) []byte {
	result := []byte(errorTemplate)
	result = bytes.ReplaceAll(result, []byte("{STATUS_CODE}"), []byte(statusCode))
	result = bytes.ReplaceAll(result, []byte("{TRACE_ID}"), []byte(traceID))
	return result
}

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

type vmContext struct {
	types.DefaultVMContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

type pluginContext struct {
	types.DefaultPluginContext
}

func (p *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{
		traceID: "not-available",
	}
}

type httpContext struct {
	types.DefaultHttpContext
	traceID string
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	ctx.traceID = extractTraceID()
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	status, err := proxywasm.GetHttpResponseHeader(":status")
	if err != nil || status == "" {
		return types.ActionContinue
	}

	statusCode, err := strconv.Atoi(status)
	if err != nil || statusCode < 400 {
		return types.ActionContinue
	}

	errorPage := getErrorTemplate(status, ctx.traceID)
	headers := [][2]string{
		{"Content-Type", "text/html; charset=utf-8"},
	}

	if err := proxywasm.SendHttpResponse(uint32(statusCode), headers, errorPage, -1); err != nil {
		proxywasm.LogErrorf("failed to send error page: %v", err)
	}

	return types.ActionPause
}

func extractTraceID() string {
	// Try standard Google Cloud trace header first
	// Format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
	if traceHeader, err := proxywasm.GetHttpRequestHeader("x-cloud-trace-context"); err == nil && traceHeader != "" {
		if traceID, _, found := strings.Cut(traceHeader, "/"); found {
			return traceID
		}
		return traceHeader
	}

	// Try W3C Trace Context standard
	// Format: version-trace_id-parent_id-flags
	if w3cTrace, err := proxywasm.GetHttpRequestHeader("traceparent"); err == nil && w3cTrace != "" {
		matches := w3cTraceRegex.FindStringSubmatch(w3cTrace)
		if len(matches) > 1 {
			return matches[1]
		}
		return "not-available"
	}

	return "not-available"
}

// [END serviceextensions_plugin_error_page_with_traceid]
