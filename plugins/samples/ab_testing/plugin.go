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

// [START serviceextensions_plugin_ab_testing]
package main

import (
	"fmt"
	"hash/fnv"
	"net/url"
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

type puginContext struct {
	types.DefaultPluginContext
}

type httpContext struct {
	types.DefaultHttpContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &puginContext{}
}

func (*puginContext) NewHttpContext(uint32) types.HttpContext {
	return &httpContext{}
}

const (
	aPath      = "/v1/"
	bPath      = "/v2/"
	percentile = 50
)

// Checks if the current request is eligible to be served by v2 file.
//
// The decision is made by hashing the userID into an integer
// value between 0 and 99, then comparing the hash to a predefined
// percentile. If the hash value is less than or equal to the percentile,
// the request is served by the v2 file. Otherwise, it is served by the
// original file.
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	defer func() {
		err := recover()
		if err != nil {
			proxywasm.SendHttpResponse(500, [][2]string{}, []byte(fmt.Sprintf("%v", err)), 0)
		}
	}()
	path, err := proxywasm.GetHttpRequestHeader(":path")
	if err != types.ErrorStatusNotFound {
		if err != nil {
			panic(err)
		}
		u, err := url.Parse(path)
		if err != nil {
			panic(err)
		}
		user := u.Query().Get("user")
		if user != "" &&
			strings.HasPrefix(strings.ToLower(path), aPath) &&
			checkPercentile(user) {
			newPath := bPath + path[len(aPath):]
			proxywasm.ReplaceHttpRequestHeader(":path", newPath)
		}
	}

	return types.ActionContinue
}

func checkPercentile(user string) bool {
	h := fnv.New64a()
	h.Write([]byte(user))
	hash := h.Sum64()
	return int(hash%100) <= percentile
}

// [END serviceextensions_plugin_ab_testing]
