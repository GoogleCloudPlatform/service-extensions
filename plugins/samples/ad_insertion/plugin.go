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

// [START serviceextensions_plugin_ad_insertion]
package main

import (
	"fmt"
	"sort"
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
	adConfigs        map[string]adConfig
	gptLibraryURL    string
	injectGptLibrary bool
}

type httpContext struct {
	types.DefaultHttpContext
	pluginContext   *pluginContext
	shouldInsertAds bool
	isAdRequest     bool
}

type adConfig struct {
	Slot         string // GAM ad slot path (e.g., "/1234/header_ad")
	Size         string // Ad dimensions (e.g., "728x90")
	Marker       string // HTML tag to insert ads relative to
	InsertBefore bool   // Insert before (true) or after (false) the marker
}

type insertion struct {
	pos     int
	content string
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (ctx *pluginContext) OnPluginStart(int) types.OnPluginStartStatus {
	// Ad configuration - set this to be loaded from plugin config
	// Format: {position_name, {gam_slot, ad_size, html_marker, insert_before}}
	ctx.adConfigs = map[string]adConfig{
		"header": {
			Slot:         "/1234/header_ad",
			Size:         "728x90",
			Marker:       "<body>",
			InsertBefore: false,
		},
		"content": {
			Slot:         "/1234/content_ad",
			Size:         "300x250",
			Marker:       "<article>",
			InsertBefore: false,
		},
		"sidebar": {
			Slot:         "/1234/sidebar_ad",
			Size:         "160x600",
			Marker:       "</article>",
			InsertBefore: true,
		},
	}

	// GPT library configuration
	ctx.gptLibraryURL = "https://securepubads.g.doubleclick.net/tag/js/gpt.js"
	ctx.injectGptLibrary = true

	return types.OnPluginStartStatusOK
}

func (ctx *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{pluginContext: ctx}
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	// Skip ad insertion for ad requests to avoid infinite loops
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err == nil && strings.Contains(path, "/ads/") {
		ctx.isAdRequest = true
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	// Check if response is HTML and should process for ad insertion
	contentType, err := proxywasm.GetHttpResponseHeader("Content-Type")
	if err == nil && strings.Contains(contentType, "text/html") {
		ctx.shouldInsertAds = true
		// Remove Content-Length header since we'll modify the body
		proxywasm.RemoveHttpResponseHeader("Content-Length")
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseBody(bodySize int, endOfStream bool) types.Action {
	if !ctx.shouldInsertAds || ctx.isAdRequest {
		return types.ActionContinue
	}

	// Process HTML body and inject GAM ads
	body, err := proxywasm.GetHttpResponseBody(0, bodySize)
	if err != nil {
		return types.ActionContinue
	}

	bodyStr := string(body)
	modifiedBody := ctx.processBodyWithGAM(bodyStr)

	proxywasm.ReplaceHttpResponseBody([]byte(modifiedBody))
	return types.ActionContinue
}

func (ctx *httpContext) isGptAlreadyLoaded(body string) bool {
	return strings.Contains(body, "googletag") ||
		strings.Contains(body, "gpt.js") ||
		strings.Contains(body, "doubleclick.net/tag/js/gpt")
}

func (ctx *httpContext) processBodyWithGAM(body string) string {
	// Slice to store all insertions: (position, content)
	insertions := []insertion{}

	// 1. Prepare GPT library injection if needed and not already present
	if ctx.pluginContext.injectGptLibrary && !ctx.isGptAlreadyLoaded(body) {
		ctx.prepareGptLibraryInjection(body, &insertions)
	}

	// 2. Prepare all ad insertions in single pass
	for position, config := range ctx.pluginContext.adConfigs {
		ctx.prepareAdInsertion(body, position, config, &insertions)
	}

	// 3. Apply all insertions in reverse order (to maintain correct indices)
	if len(insertions) > 0 {
		return ctx.applyAllInsertions(body, insertions)
	}

	return body
}

func (ctx *httpContext) prepareGptLibraryInjection(body string, insertions *[]insertion) {
	if headPos := strings.Index(body, "<head>"); headPos != -1 {
		gptScript := fmt.Sprintf("\n  <script async src=\"%s\"></script>", ctx.pluginContext.gptLibraryURL)
		*insertions = append(*insertions, insertion{pos: headPos + 6, content: gptScript})
		return
	}

	if bodyPos := strings.Index(body, "<body>"); bodyPos != -1 {
		gptScript := fmt.Sprintf("<script async src=\"%s\"></script>\n", ctx.pluginContext.gptLibraryURL)
		*insertions = append(*insertions, insertion{pos: bodyPos, content: gptScript})
	}
}

func (ctx *httpContext) prepareAdInsertion(body string, position string, config adConfig, insertions *[]insertion) {
	markerPos := strings.Index(body, config.Marker)
	if markerPos == -1 {
		return
	}

	insertPos := markerPos
	if !config.InsertBefore {
		insertPos += len(config.Marker)
	}

	adHTML := ctx.generateGAMAdHTML(position, config)
	*insertions = append(*insertions, insertion{pos: insertPos, content: adHTML})
}

func (ctx *httpContext) applyAllInsertions(body string, insertions []insertion) string {
	// Sort insertions by position in DESCENDING order
	// This ensures that later insertions don't affect positions of earlier ones
	sort.Slice(insertions, func(i, j int) bool {
		return insertions[i].pos > insertions[j].pos
	})

	// Apply all insertions
	result := body
	for _, ins := range insertions {
		result = result[:ins.pos] + ins.content + result[ins.pos:]
	}

	return result
}

func (ctx *httpContext) generateGAMAdHTML(position string, config adConfig) string {
	// GAM Ad HTML Template
	return fmt.Sprintf(`<div id="ad-container-%s" class="ad-unit">
  <!-- GAM Ad Slot: %s -->
  <script>
    (function() {
      // Same-domain GAM integration
      var googletag = window.googletag || {};
      googletag.cmd = googletag.cmd || [];
      googletag.cmd.push(function() {
        googletag.defineSlot('%s', 
                            [%s], 
                            'ad-container-%s').addService(googletag.pubads());
        googletag.pubads().enableSingleRequest();
        googletag.enableServices();
      });
    })();
  </script>
  <div id="div-gpt-ad-%s">
    <script>
      googletag.cmd.push(function() { 
        googletag.display('div-gpt-ad-%s'); 
      });
    </script>
  </div>
</div>`, position, config.Slot, config.Slot, config.Size, position, position, position)
}

// [END serviceextensions_plugin_ad_insertion]
