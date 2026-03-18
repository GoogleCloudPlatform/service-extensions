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

// [START serviceextensions_plugin_set_reset_cookie]
package main

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {}

func init() {
	proxywasm.SetVMContext(&vmContext{})
}

// Cookie operation types.
const (
	opSET       = "SET"
	opDELETE    = "DELETE"
	opOVERWRITE = "OVERWRITE"
)

// cookieConfig holds the parsed configuration for a single cookie operation.
type cookieConfig struct {
	operation      string
	name           string
	value          string
	path           string
	domain         string
	maxAge         int
	httpOnly       bool
	secure         bool
	sameSiteStrict bool
}

type vmContext struct {
	types.DefaultVMContext
}

type pluginContext struct {
	types.DefaultPluginContext
	cookieConfigs []cookieConfig
}

type httpContext struct {
	types.DefaultHttpContext
	pluginCtx *pluginContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (ctx *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{pluginCtx: ctx}
}

// OnPluginStart parses the pipe-delimited configuration.
// Format: OPERATION|name|value|path|domain|max_age|http_only|secure|same_site_strict
func (ctx *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	config, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogWarnf("Empty configuration provided, no cookies will be managed")
		return types.OnPluginStartStatusOK
	}

	configStr := string(config)
	if len(strings.TrimSpace(configStr)) == 0 {
		proxywasm.LogWarnf("Empty configuration provided, no cookies will be managed")
		return types.OnPluginStartStatusOK
	}

	for _, line := range strings.Split(configStr, "\n") {
		line = strings.TrimSpace(line)
		// Skip empty lines and comments.
		if line == "" || line[0] == '#' {
			continue
		}

		fields := strings.Split(line, "|")
		if len(fields) < 2 {
			proxywasm.LogErrorf("Invalid config line: %s", line)
			continue
		}

		cookie := cookieConfig{
			path:   "/",
			maxAge: -1, // -1 for session cookie
		}

		// Parse operation.
		switch fields[0] {
		case opSET:
			cookie.operation = opSET
		case opDELETE:
			cookie.operation = opDELETE
		case opOVERWRITE:
			cookie.operation = opOVERWRITE
		default:
			proxywasm.LogErrorf("Unknown operation: %s", fields[0])
			continue
		}

		cookie.name = fields[1]
		if cookie.name == "" {
			proxywasm.LogErrorf("Cookie name cannot be empty")
			continue
		}

		// Parse optional fields.
		if len(fields) > 2 {
			cookie.value = fields[2]
		}
		if len(fields) > 3 && fields[3] != "" {
			cookie.path = fields[3]
		}
		if len(fields) > 4 {
			cookie.domain = fields[4]
		}
		if len(fields) > 5 && fields[5] != "" {
			maxAge, err := strconv.Atoi(fields[5])
			if err != nil {
				proxywasm.LogErrorf("Invalid max_age value: %s", fields[5])
				continue
			}
			cookie.maxAge = maxAge
		}
		if len(fields) > 6 {
			cookie.httpOnly = fields[6] == "true"
		}
		if len(fields) > 7 {
			cookie.secure = fields[7] == "true"
		}
		if len(fields) > 8 {
			cookie.sameSiteStrict = fields[8] == "true"
		}

		ctx.cookieConfigs = append(ctx.cookieConfigs, cookie)
	}

	if len(ctx.cookieConfigs) == 0 {
		proxywasm.LogWarnf("No valid cookie configurations found, no cookies will be managed")
		return types.OnPluginStartStatusOK
	}

	proxywasm.LogInfof("Successfully loaded %d cookie configuration(s)", len(ctx.cookieConfigs))
	return types.OnPluginStartStatusOK
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	// Parse existing cookies from the request Cookie header.
	requestCookies := parseRequestCookies()

	// Process DELETE operations: remove matching cookies from the request.
	modified := false
	for _, config := range ctx.pluginCtx.cookieConfigs {
		if config.operation != opDELETE {
			continue
		}
		for i, cookie := range requestCookies {
			if cookie[0] == config.name {
				requestCookies = append(requestCookies[:i], requestCookies[i+1:]...)
				modified = true
				proxywasm.LogInfof("Marking cookie for deletion before CDN cache: %s", config.name)
				break
			}
		}
	}

	// Rebuild the Cookie header if any cookies were deleted.
	if modified {
		if len(requestCookies) == 0 {
			if err := proxywasm.RemoveHttpRequestHeader("Cookie"); err != nil {
				proxywasm.LogErrorf("failed to remove Cookie header: %v", err)
			}
		} else {
			parts := make([]string, 0, len(requestCookies))
			for _, cookie := range requestCookies {
				parts = append(parts, cookie[0]+"="+cookie[1])
			}
			if err := proxywasm.ReplaceHttpRequestHeader("Cookie", strings.Join(parts, "; ")); err != nil {
				proxywasm.LogErrorf("failed to replace Cookie header: %v", err)
			}
		}
	}

	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		if err := recover(); err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()

	for _, config := range ctx.pluginCtx.cookieConfigs {
		switch config.operation {
		case opSET:
			addSetCookieHeader(config)
		case opOVERWRITE:
			overwriteCookie(config)
		}
	}

	return types.ActionContinue
}

// parseRequestCookies parses the Cookie header into ordered name-value pairs.
// Uses a slice to preserve original cookie order.
func parseRequestCookies() [][2]string {
	cookieHeader, err := proxywasm.GetHttpRequestHeader("Cookie")
	if err != nil || cookieHeader == "" {
		return nil
	}

	var cookies [][2]string
	for _, pair := range strings.Split(cookieHeader, "; ") {
		idx := strings.Index(pair, "=")
		if idx > 0 {
			cookies = append(cookies, [2]string{pair[:idx], pair[idx+1:]})
		}
	}
	return cookies
}

// buildSetCookieValue constructs a Set-Cookie header value from config attributes.
func buildSetCookieValue(config cookieConfig) string {
	var b strings.Builder
	b.WriteString(config.name)
	b.WriteString("=")
	b.WriteString(config.value)
	b.WriteString("; Path=")
	b.WriteString(config.path)
	if config.domain != "" {
		b.WriteString("; Domain=")
		b.WriteString(config.domain)
	}
	if config.maxAge > 0 {
		b.WriteString("; Max-Age=")
		b.WriteString(strconv.Itoa(config.maxAge))
	}
	if config.httpOnly {
		b.WriteString("; HttpOnly")
	}
	if config.secure {
		b.WriteString("; Secure")
	}
	if config.sameSiteStrict {
		b.WriteString("; SameSite=Strict")
	}
	return b.String()
}

// addSetCookieHeader adds a new Set-Cookie response header.
func addSetCookieHeader(config cookieConfig) {
	if err := proxywasm.AddHttpResponseHeader("Set-Cookie", buildSetCookieValue(config)); err != nil {
		proxywasm.LogErrorf("failed to add Set-Cookie header: %v", err)
		return
	}
	logType := "session"
	if config.maxAge != -1 {
		logType = "persistent"
	}
	proxywasm.LogInfof("Setting %s cookie: %s", logType, config.name)
}

// overwriteCookie replaces an existing Set-Cookie header for the target cookie
// name while preserving other Set-Cookie headers.
// Note: The proxy-wasm host combines multiple Set-Cookie headers into a single
// comma-separated value, so we split by ", " and reconstruct. This means
// origin cookies using the Expires attribute (which contains a comma in its
// date format) will be corrupted. Use Max-Age instead of Expires.
func overwriteCookie(config cookieConfig) {
	existing, err := proxywasm.GetHttpResponseHeader("Set-Cookie")
	if err := proxywasm.RemoveHttpResponseHeader("Set-Cookie"); err != nil {
		proxywasm.LogErrorf("failed to remove Set-Cookie header: %v", err)
	}

	// Preserve non-matching Set-Cookie values from the combined header.
	if err == nil && existing != "" {
		prefix := config.name + "="
		for _, cookie := range strings.Split(existing, ", ") {
			if !strings.HasPrefix(cookie, prefix) {
				if err := proxywasm.AddHttpResponseHeader("Set-Cookie", cookie); err != nil {
					proxywasm.LogErrorf("failed to re-add Set-Cookie header: %v", err)
				}
			}
		}
	}

	// Set the new value or expire the cookie.
	if config.value != "" {
		addSetCookieHeader(config)
	} else {
		expire := config.name + "=; Path=" + config.path + "; Max-Age=0"
		if config.domain != "" {
			expire += "; Domain=" + config.domain
		}
		if err := proxywasm.AddHttpResponseHeader("Set-Cookie", expire); err != nil {
			proxywasm.LogErrorf("failed to add expiry Set-Cookie header: %v", err)
		}
		proxywasm.LogInfof("Removing Set-Cookie directive for: %s", config.name)
	}
}

// [END serviceextensions_plugin_set_reset_cookie]
