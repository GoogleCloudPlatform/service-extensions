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

#ifndef NET_TURING_WASM_LUA_ENVOY_LUA_API_REGISTRATION_H_
#define NET_TURING_WASM_LUA_ENVOY_LUA_API_REGISTRATION_H_

#include "lua_state.h"
#include "absl/status/status.h"
#include "absl/strings/string_view.h"

namespace sample::lua {

// Helper to register absl::StatusOr<T> types with LuaBridge. The unwrapper uses
// this to identify and extract the inner value of a StatusOr object.
template <typename T>
void RegisterStatusOr(LuaState& state, absl::string_view name);

absl::Status RegisterEnvoyApi(LuaState& state);

}  // namespace sample::lua

#endif  // NET_TURING_WASM_LUA_ENVOY_LUA_API_REGISTRATION_H_
