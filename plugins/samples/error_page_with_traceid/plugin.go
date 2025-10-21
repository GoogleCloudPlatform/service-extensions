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
	"strconv"
	"sync"

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

var (
	errorTemplateBytes []byte
	templateOnce       sync.Once
)

func getErrorTemplate(statusCode, traceID string) []byte {
	templateOnce.Do(func() {
		errorTemplateBytes = []byte(errorTemplate)
	})

	result := make([]byte, len(errorTemplateBytes))
	copy(result, errorTemplateBytes)

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
	if err != nil || len(status) < 3 {
		return types.ActionContinue
	}

	// Check for error status codes (4xx or 5xx)
	if status[0] != '4' && status[0] != '5' {
		return types.ActionContinue
	}

	errorPage := getErrorTemplate(status, ctx.traceID)
	headers := [][2]string{
		{"Content-Type", "text/html; charset=utf-8"},
	}

	statusCode, err := strconv.ParseUint(status, 10, 32)
	if err != nil {
		statusCode = 500
	}

	if err := proxywasm.SendHttpResponse(uint32(statusCode), headers, errorPage, -1); err != nil {
		proxywasm.LogErrorf("failed to send error page: %v", err)
	}

	return types.ActionPause
}

func extractTraceID() string {
	// Try Google Cloud trace header first
	if traceHeader, err := proxywasm.GetHttpRequestHeader("x-cloud-trace-context"); err == nil {
		for i := 0; i < len(traceHeader); i++ {
			if traceHeader[i] == '/' {
				return traceHeader[:i]
			}
		}
		return traceHeader
	}

	// Try W3C Trace Context
	if w3cTrace, err := proxywasm.GetHttpRequestHeader("traceparent"); err == nil {
		if len(w3cTrace) >= 55 && w3cTrace[2] == '-' {
			start := 3
			end := start + 32
			if end <= len(w3cTrace) && w3cTrace[end] == '-' {
				return w3cTrace[start:end]
			}
		}
		return "invalid-trace-format"
	}

	return "not-available"
}

// [END serviceextensions_plugin_error_page_with_traceid]
