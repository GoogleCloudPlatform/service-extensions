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

// [START serviceextensions_plugin_redirect_bulk]
package main

import (
	"bytes"
	"strings"

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
	domainMappings map[string]string
}

type httpContext struct {
	types.DefaultHttpContext
	domainMappings map[string]string
}

func (*vmContext) NewPluginContext(uint32) types.PluginContext {
	return &pluginContext{
		domainMappings: make(map[string]string),
	}
}

func (p *pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{
		domainMappings: p.domainMappings,
	}
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	// Get plugin configuration
	config, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogErrorf("Failed to get plugin configuration: %v", err)
		return types.OnPluginStartStatusFailed
	}

	// Parse configuration
	mappings := make(map[string]string)

	// Parse each line as "source_domain target_domain"
	for _, line := range bytes.Split(config, []byte("\n")) {
		line = bytes.TrimSpace(line)
		if len(line) == 0 || bytes.HasPrefix(line, []byte("#")) {
			continue // Skip empty lines and comments
		}

		parts := bytes.Fields(line)
		if len(parts) == 2 {
			// Convert source domain to lowercase for case-insensitive matching
			mappings[strings.ToLower(string(parts[0]))] = string(parts[1])
		} else {
			proxywasm.LogWarnf("Invalid mapping format: %s", string(line))
		}
	}

	p.domainMappings = mappings
	proxywasm.LogInfof("Loaded %d domain mappings", len(p.domainMappings))

	return types.OnPluginStartStatusOK
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Get the ":authority" header which contains the hostname
	authority, err := proxywasm.GetHttpRequestHeader(":authority")
	if err != nil || authority == "" {
		return types.ActionContinue
	}

	// Extract the domain part (remove port if present)
	domain := authority
	if idx := strings.Index(authority, ":"); idx != -1 {
		domain = authority[:idx]
	}

	// Convert domain to lowercase for case-insensitive matching
	domainLowercase := strings.ToLower(domain)

	// Check if this domain should be redirected
	if targetDomain, exists := ctx.domainMappings[domainLowercase]; exists {
		// Get the path
		path, err := proxywasm.GetHttpRequestHeader(":path")
		if err != nil {
			path = ""
		}

		// Get the scheme (http or https)
		scheme, err := proxywasm.GetHttpRequestHeader(":scheme")
		if err != nil || scheme == "" {
			scheme = "https"
		}

		// Construct the new URL
		newURL := scheme + "://" + targetDomain + path

		// Send a 301 response with the new location
		headers := [][2]string{
			{"Location", newURL},
		}
		body := []byte("Redirecting to " + newURL)
		if err := proxywasm.SendHttpResponse(301, headers, body, -1); err != nil {
			proxywasm.LogErrorf("Failed to send redirect response: %v", err)
		}
	}

	return types.ActionContinue
}

// [END serviceextensions_plugin_redirect_bulk]
