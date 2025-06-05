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

// [START serviceextensions_plugin_device_type]
package main

import (
	"strings"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const (
	userAgentHeader  = "user-agent"    // The HTTP header containing the user agent string
	deviceTypeHeader = "x-device-type" // The new HTTP header that will store the detected device type
	defaultUserAgent = "unknown"       // Default value for user agent if not provided
)

const (
	deviceTypeDesktop = "desktop"
	deviceTypeTablet  = "tablet"
	deviceTypePhone   = "phone"
	deviceTypeBot     = "bot"
	deviceTypeOther   = "other"
)

// Package-level variables for keyword lists
var (
	botKeywords = []string{
		"bot", "crawler", "spider",
		"googlebot", "bingbot", "slurp",
		"duckduckbot", "yandexbot", "baiduspider",
	}

	tabletKeywords = []string{
		"ipad", "tablet", "kindle",
		"tab", "playbook", "nexus 7",
		"sm-t", "pad", "gt-p",
	}

	mobileKeywords = []string{
		"mobile", "android", "iphone",
		"ipod", "blackberry", "windows phone",
		"webos", "iemobile", "opera mini",
	}

	desktopKeywords = []string{
		"mozilla", "chrome", "safari",
		"firefox", "msie", "opera",
		"edge", "chromium", "vivaldi",
	}
)

func main() {}

type vmContext struct{ types.DefaultVMContext }
type pluginContext struct{ types.DefaultPluginContext }
type httpContext struct{ types.DefaultHttpContext }

func init() { proxywasm.SetVMContext(&vmContext{}) }

// NewPluginContext creates a new plugin context and returns it
func (*vmContext) NewPluginContext(uint32) types.PluginContext {
	return &pluginContext{}
}

// NewHttpContext creates a new HTTP context for handling HTTP requests
func (*pluginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{}
}

// OnHttpRequestHeaders is called when the HTTP request headers are received
// It detects the device type based on the user agent and adds it as a new header
func (ctx *httpContext) OnHttpRequestHeaders(int, bool) types.Action {
	defer recoverPanic()

	userAgent, err := proxywasm.GetHttpRequestHeader(userAgentHeader)
	if err != nil {
		handleUserAgent(err)
		userAgent = defaultUserAgent
	}

	deviceType := detectDeviceType(strings.ToLower(userAgent))
	// Set the new device type header in the request
	if err := proxywasm.ReplaceHttpRequestHeader(deviceTypeHeader, deviceType); err != nil {
		proxywasm.LogErrorf("failed to set device type header: %v", err)
	}

	return types.ActionContinue
}

// detectDeviceType determines the type of device based on the user agent string
func detectDeviceType(ua string) string {
	switch {
	case isBot(ua):
		return deviceTypeBot
	case isTablet(ua):
		return deviceTypeTablet
	case isMobile(ua):
		return deviceTypePhone
	case isDesktop(ua):
		return deviceTypeDesktop
	default:
		return deviceTypeOther
	}
}

// isBot checks if the user agent indicates a bot or crawler
func isBot(ua string) bool {
	return containsAny(ua, botKeywords)
}

// isTablet checks if the user agent indicates a tablet device
func isTablet(ua string) bool {
	return containsAny(ua, tabletKeywords)
}

// isMobile checks if the user agent indicates a mobile phone
func isMobile(ua string) bool {
	return containsAny(ua, mobileKeywords)
}

// isDesktop checks if the user agent indicates a desktop device
func isDesktop(ua string) bool {
	return containsAny(ua, desktopKeywords)
}

// containsAny checks if the string contains any of the substrings provided
func containsAny(s string, subs []string) bool {
	for _, sub := range subs {
		if strings.Contains(s, sub) {
			return true
		}
	}
	return false
}

// recoverPanic recovers from any panic that occurs during processing
func recoverPanic() {
	if r := recover(); r != nil {
		proxywasm.LogErrorf("panic recovered: %v", r)

		// Attempt to set the header with the default device type in case of panic
		if err := proxywasm.ReplaceHttpRequestHeader(deviceTypeHeader, "unknown"); err != nil {
			proxywasm.LogErrorf("failed to set default device type: %v", err)
		}
	}
}

// handleUserAgent handles errors related to user agent processing
func handleUserAgent(err error) string {
	proxywasm.LogWarnf("user-agent handling error: %v", err)
	if err := proxywasm.ReplaceHttpRequestHeader(deviceTypeHeader, "unknown"); err != nil {
		proxywasm.LogErrorf("fallback header error: %v", err)
	}
	return defaultUserAgent
}

// [END serviceextensions_plugin_device_type]
