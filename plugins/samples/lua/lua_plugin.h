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

#ifndef NET_TURING_WASM_LUA_LUA_PLUGIN_H_
#define NET_TURING_WASM_LUA_LUA_PLUGIN_H_

#include <cstddef>
#include <cstdint>
#include <memory>

#include "coroutine.h"
#include "lua_state.h"
#include "absl/base/nullability.h"
#include "absl/strings/string_view.h"
#include "proxy_wasm_intrinsics.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace sample::lua {

class LuaHttpContext final : public Context {
 public:
  explicit LuaHttpContext(uint32_t id, RootContext* root);

  LuaHttpContext(const LuaHttpContext&) = delete;
  LuaHttpContext(LuaHttpContext&&) noexcept = delete;
  LuaHttpContext& operator=(const LuaHttpContext&) = delete;
  LuaHttpContext& operator=(LuaHttpContext&&) noexcept = delete;

  void onCreate() override;

  FilterHeadersStatus onRequestHeaders(uint32_t num_headers,
                                       bool end_of_stream) override;
  FilterDataStatus onRequestBody(size_t body_buffer_length,
                                 bool end_of_stream) override;
  FilterTrailersStatus onRequestTrailers(uint32_t num_trailers) override;

  FilterHeadersStatus onResponseHeaders(uint32_t num_headers,
                                        bool end_of_stream) override;
  FilterDataStatus onResponseBody(size_t body_buffer_length,
                                  bool end_of_stream) override;
  FilterTrailersStatus onResponseTrailers(uint32_t num_trailers) override;

 private:
  std::unique_ptr<LuaState::Thread> lua_request_thread_;
  std::unique_ptr<LuaStreamCoroutine> request_coroutine_;

  std::unique_ptr<LuaState::Thread> lua_response_thread_;
  std::unique_ptr<LuaStreamCoroutine> response_coroutine_;

  LuaState* GetRootLuaState();
};

class LuaRootContext final : public RootContext {
 public:
  explicit LuaRootContext(uint32_t id, absl::string_view root_id)
      : RootContext(id, root_id) {}

  LuaRootContext(const LuaRootContext&) = delete;
  LuaRootContext(LuaRootContext&&) noexcept = delete;
  LuaRootContext& operator=(const LuaRootContext&) = delete;
  LuaRootContext& operator=(LuaRootContext&&) noexcept = delete;

  bool onConfigure(size_t cfg_size) override;

 private:
  // The Lua interpreter state holds the VM execution stack, globals, and
  // registry. Initialized once per Wasm VM lifetime and shared across all
  // request streams and callbacks to avoid setup overhead.
  absl_nullable std::unique_ptr<LuaState> lua_state_;

  friend class LuaHttpContext;
};

}  // namespace sample::lua
#endif  // NET_TURING_WASM_LUA_LUA_PLUGIN_H_
