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

	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
	"google.golang.org/protobuf/encoding/prototext"
	
	pb "plugins/samples/set_reset_cookie/cookie_config.proto" 
)

func main() {
	proxywasm.SetVMContext(&vmContext{})
}

type vmContext struct {
	types.DefaultVMContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &cookieManagerRootContext{}
}

// CookieManagerRootContext handles plugin configuration
type cookieManagerRootContext struct {
	types.DefaultPluginContext
	cookieConfigs []*pb.CookieConfig
}

func (ctx *cookieManagerRootContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	// Handle empty configuration
	if pluginConfigurationSize == 0 {
		proxywasm.LogWarn("Empty configuration provided, no cookies will be managed")
		ctx.cookieConfigs = nil
		return types.OnPluginStartStatusOK // Empty config is valid, just does nothing
	}

	configurationData, err := proxywasm.GetPluginConfiguration()
	if err != nil {
		proxywasm.LogErrorf("Failed to retrieve configuration data buffer: %v", err)
		return types.OnPluginStartStatusFailed
	}

	var config pb.CookieManagerConfig
	configString := string(configurationData)

	// Attempt to parse the protobuf configuration
	if err := prototext.Unmarshal(configurationData, &config); err != nil {
		proxywasm.LogError("Failed to parse cookie manager configuration as text protobuf. " +
			"Please ensure configuration follows the text protobuf format. " +
			"Example: cookies { name: \"session\" value: \"abc\" }")
		return types.OnPluginStartStatusFailed
	}

	// Validate parsed configuration
	if len(config.Cookies) == 0 {
		proxywasm.LogWarn("Configuration parsed successfully but contains no cookie definitions")
		ctx.cookieConfigs = nil
		return types.OnPluginStartStatusOK
	}

	// Store the parsed cookie configurations with validation
	ctx.cookieConfigs = nil
	validCookies := 0

	for _, cookieConfig := range config.Cookies {
		// Validate required fields based on operation type
		if cookieConfig.Name == "" {
			proxywasm.LogError("Cookie configuration missing required 'name' field, skipping")
			continue
		}

		if cookieConfig.Operation == pb.CookieOperation_SET ||
			cookieConfig.Operation == pb.CookieOperation_OVERWRITE {
			if cookieConfig.Value == "" {
				proxywasm.LogWarnf("Cookie '%s' has SET/OVERWRITE operation but empty value", cookieConfig.Name)
			}
		}

		ctx.cookieConfigs = append(ctx.cookieConfigs, cookieConfig)
		validCookies++

		// Log configuration for debugging
		proxywasm.LogDebugf("Configured cookie: name=%s, operation=%d",
			cookieConfig.Name, int(cookieConfig.Operation))
	}

	if validCookies == 0 {
		proxywasm.LogError("No valid cookie configurations found after validation")
		return types.OnPluginStartStatusFailed
	}

	proxywasm.LogInfof("Successfully loaded %d cookie configuration(s)", validCookies)
	return types.OnPluginStartStatusOK
}

func (ctx *cookieManagerRootContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &cookieManagerHttpContext{
		root:            ctx,
		requestCookies:  make(map[string]string),
		cookiesToDelete: []string{},
	}
}

// CookieManagerHttpContext handles HTTP request/response processing
type cookieManagerHttpContext struct {
	types.DefaultHttpContext
	root            *cookieManagerRootContext
	requestCookies  map[string]string
	cookiesToDelete []string
}

func (ctx *cookieManagerHttpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Parse existing cookies from request
	ctx.parseRequestCookies()

	// Process DELETE operations before CDN cache
	ctx.processCookieDeletions()

	return types.ActionContinue
}

func (ctx *cookieManagerHttpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	// Process SET and OVERWRITE operations
	ctx.processCookieOperations()

	return types.ActionContinue
}

// Parse cookies from the Cookie header
func (ctx *cookieManagerHttpContext) parseRequestCookies() {
	cookieHeader, err := proxywasm.GetHttpRequestHeader("Cookie")
	if err != nil {
		return
	}

	cookies := cookieHeader
	for _, cookiePair := range strings.Split(cookies, "; ") {
		parts := strings.SplitN(cookiePair, "=", 2)
		if len(parts) == 2 {
			ctx.requestCookies[parts[0]] = parts[1]
		}
	}
}

// Process cookie deletions before CDN cache
func (ctx *cookieManagerHttpContext) processCookieDeletions() {
	configs := ctx.root.cookieConfigs

	for _, config := range configs {
		if config.Operation == pb.CookieOperation_DELETE {
			if _, exists := ctx.requestCookies[config.Name]; exists {
				ctx.cookiesToDelete = append(ctx.cookiesToDelete, config.Name)
				proxywasm.LogInfof("Marking cookie for deletion before CDN cache: %s", config.Name)
			}
		}
	}

	// Remove deleted cookies from request
	if len(ctx.cookiesToDelete) > 0 {
		ctx.rebuildCookieHeader()
	}
}

// Rebuild Cookie header without deleted cookies
func (ctx *cookieManagerHttpContext) rebuildCookieHeader() {
	var remainingCookies []string

	for name, value := range ctx.requestCookies {
		shouldDelete := false
		for _, deleteName := range ctx.cookiesToDelete {
			if name == deleteName {
				shouldDelete = true
				break
			}
		}

		if !shouldDelete {
			remainingCookies = append(remainingCookies, fmt.Sprintf("%s=%s", name, value))
		}
	}

	if len(remainingCookies) == 0 {
		proxywasm.RemoveHttpRequestHeader("Cookie")
	} else {
		proxywasm.ReplaceHttpRequestHeader("Cookie", strings.Join(remainingCookies, "; "))
	}
}

// Process SET and OVERWRITE operations
func (ctx *cookieManagerHttpContext) processCookieOperations() {
	configs := ctx.root.cookieConfigs

	for _, config := range configs {
		if config.Operation == pb.CookieOperation_SET {
			ctx.setCookie(config)
		} else if config.Operation == pb.CookieOperation_OVERWRITE {
			ctx.overwriteCookie(config)
		}
	}
}

// Set or reset a cookie
func (ctx *cookieManagerHttpContext) setCookie(config *pb.CookieConfig) {
	cookieValue := fmt.Sprintf("%s=%s", config.Name, config.Value)

	// Add Path attribute
	cookieValue += fmt.Sprintf("; Path=%s", config.Path)

	// Add Domain attribute if specified
	if config.Domain != "" {
		cookieValue += fmt.Sprintf("; Domain=%s", config.Domain)
	}

	// Add Max-Age for persistent cookies (session if -1)
	if config.MaxAge > 0 {
		cookieValue += fmt.Sprintf("; Max-Age=%d", config.MaxAge)
	}

	// Add security attributes
	if config.HttpOnly {
		cookieValue += "; HttpOnly"
	}

	if config.Secure {
		cookieValue += "; Secure"
	}

	if config.SameSiteStrict {
		cookieValue += "; SameSite=Strict"
	}

	proxywasm.AddHttpResponseHeader("Set-Cookie", cookieValue)

	logType := "session"
	if config.MaxAge != -1 {
		logType = "persistent"
	}
	proxywasm.LogInfof("Setting %s cookie: %s=%s", logType, config.Name, config.Value)
}

// Overwrite or remove existing Set-Cookie headers
func (ctx *cookieManagerHttpContext) overwriteCookie(config *pb.CookieConfig) {
	// Remove all existing Set-Cookie headers for this cookie
	proxywasm.RemoveHttpResponseHeader("Set-Cookie")

	// If value is not empty, set the new cookie
	if config.Value != "" {
		ctx.setCookie(config)
		proxywasm.LogInfof("Overwriting existing cookie: %s", config.Name)
	} else {
		// Complete removal - set expired cookie
		expireCookie := fmt.Sprintf("%s=; Path=%s; Max-Age=0", config.Name, config.Path)

		if config.Domain != "" {
			expireCookie += fmt.Sprintf("; Domain=%s", config.Domain)
		}

		proxywasm.AddHttpResponseHeader("Set-Cookie", expireCookie)
		proxywasm.LogInfof("Removing Set-Cookie directive for: %s", config.Name)
	}
}
// [END serviceextensions_plugin_set_reset_cookie]
