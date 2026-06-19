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
	"google.golang.org/protobuf/encoding/prototext"
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
	cookieConfigs []*CookieConfig
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

// OnPluginStart parses the text protobuf configuration.
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

	// Parse text-format protobuf configuration.
	var managerConfig CookieManagerConfig
	if err := prototext.Unmarshal(config, &managerConfig); err != nil {
		proxywasm.LogErrorf("Failed to parse cookie manager configuration: %v", err)
		return types.OnPluginStartStatusFailed
	}

	if len(managerConfig.GetCookies()) == 0 {
		proxywasm.LogWarnf("No cookie configurations found, no cookies will be managed")
		return types.OnPluginStartStatusOK
	}

	for _, cookie := range managerConfig.GetCookies() {
		if cookie.GetName() == "" {
			proxywasm.LogErrorf("Cookie configuration missing required 'name' field")
			continue
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
		if config.GetOperation() != CookieOperation_DELETE {
			continue
		}
		for i, cookie := range requestCookies {
			if cookie[0] == config.GetName() {
				requestCookies = append(requestCookies[:i], requestCookies[i+1:]...)
				modified = true
				proxywasm.LogInfof("Marking cookie for deletion before CDN cache: %s", config.GetName())
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
		switch config.GetOperation() {
		case CookieOperation_SET, CookieOperation_COOKIE_OPERATION_UNSPECIFIED:
			addSetCookieHeader(config)
		case CookieOperation_OVERWRITE:
			overwriteCookie(config)
		}
	}

	return types.ActionContinue
}

// parseRequestCookies parses the Cookie header into ordered name-value pairs.
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

func effectivePath(config *CookieConfig) string {
	if p := config.GetPath(); p != "" {
		return p
	}
	return "/"
}

// buildSetCookieValue constructs a Set-Cookie header value from config attributes.
func buildSetCookieValue(config *CookieConfig) string {
	var b strings.Builder
	b.WriteString(config.GetName())
	b.WriteString("=")
	b.WriteString(config.GetValue())
	b.WriteString("; Path=")
	b.WriteString(effectivePath(config))
	if config.GetDomain() != "" {
		b.WriteString("; Domain=")
		b.WriteString(config.GetDomain())
	}
	if config.GetMaxAge() > 0 {
		b.WriteString("; Max-Age=")
		b.WriteString(strconv.Itoa(int(config.GetMaxAge())))
	}
	if config.GetHttpOnly() {
		b.WriteString("; HttpOnly")
	}
	if config.GetSecure() {
		b.WriteString("; Secure")
	}
	if config.GetSameSiteStrict() {
		b.WriteString("; SameSite=Strict")
	}
	return b.String()
}

// addSetCookieHeader adds a new Set-Cookie response header.
func addSetCookieHeader(config *CookieConfig) {
	if err := proxywasm.AddHttpResponseHeader("Set-Cookie", buildSetCookieValue(config)); err != nil {
		proxywasm.LogErrorf("failed to add Set-Cookie header: %v", err)
		return
	}
	logType := "session"
	if config.GetMaxAge() > 0 {
		logType = "persistent"
	}
	proxywasm.LogInfof("Setting %s cookie: %s", logType, config.GetName())
}

// overwriteCookie replaces an existing Set-Cookie header for the target cookie
// name while preserving other Set-Cookie headers.
func overwriteCookie(config *CookieConfig) {
	existing, getErr := proxywasm.GetHttpResponseHeader("Set-Cookie")
	if err := proxywasm.RemoveHttpResponseHeader("Set-Cookie"); err != nil {
		proxywasm.LogErrorf("failed to remove Set-Cookie header: %v", err)
	}

	// Preserve non-matching Set-Cookie values from the combined header.
	if getErr == nil && existing != "" {
		prefix := config.GetName() + "="
		for _, cookie := range strings.Split(existing, ", ") {
			if !strings.HasPrefix(cookie, prefix) {
				if err := proxywasm.AddHttpResponseHeader("Set-Cookie", cookie); err != nil {
					proxywasm.LogErrorf("failed to re-add Set-Cookie header: %v", err)
				}
			}
		}
	}

	// Set the new value or expire the cookie.
	if config.GetValue() != "" {
		addSetCookieHeader(config)
	} else {
		expire := config.GetName() + "=; Path=" + effectivePath(config) + "; Max-Age=0"
		if config.GetDomain() != "" {
			expire += "; Domain=" + config.GetDomain()
		}
		if err := proxywasm.AddHttpResponseHeader("Set-Cookie", expire); err != nil {
			proxywasm.LogErrorf("failed to add expiry Set-Cookie header: %v", err)
		}
		proxywasm.LogInfof("Removing Set-Cookie directive for: %s", config.GetName())
	}
}

// [END serviceextensions_plugin_set_reset_cookie]
