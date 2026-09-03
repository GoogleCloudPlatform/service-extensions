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

#ifndef NET_TURING_WASM_LUA_LUA_STATE_H_
#define NET_TURING_WASM_LUA_LUA_STATE_H_

#include <memory>
#include <string>
#include <vector>

#include "absl/base/attributes.h"
#include "absl/base/nullability.h"
#include "absl/functional/any_invocable.h"
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/strings/string_view.h"
#include "absl/types/span.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
}

namespace sample::lua {

namespace internal {
using LuaStatePtr =
    std::unique_ptr<lua_State, absl::AnyInvocable<void(lua_State*)>>;
}  // namespace internal

class Handle;

// Represents the execution state of a thread-like object
enum class ExecutionState {
  kExited,
  kYielded,
};

// A C++ wrapper around the core lua_State.
// Manages the lifecycle of a Lua VM and provides functionality for executing
// strings.
class LuaState {
 public:
  // Represents an executing Lua coroutine/thread.
  class Thread {
   public:
    Thread(const Thread&) = delete;
    Thread& operator=(const Thread&) = delete;
    Thread(Thread&&) noexcept = delete;
    Thread& operator=(Thread&&) noexcept = delete;

    lua_State* absl_nonnull state() { return thread_state_.get(); }

    // Yields the current Lua thread with `n_results` results.
    // NOTE: Meant to be called from the Lua side in a lua_CFunction.
    int Yield(int n_results);

    // Resumes the execution of this thread passing `n_arg` arguments.
    absl::StatusOr<ExecutionState> Resume(int n_arg);

    // Executes a Lua function with no arguments
    absl::StatusOr<ExecutionState> ExecuteFunction(absl::string_view func_name);

    // Executes a Lua function passing an Envoy Handle
    absl::StatusOr<ExecutionState> ExecuteFunction(absl::string_view func_name,
                                                   Handle& handle);

    // Executes a Lua function passing an integer
    absl::StatusOr<ExecutionState> ExecuteFunction(absl::string_view func_name,
                                                   int arg);

   private:
    explicit Thread(lua_State* thread_state, LuaState& root_state, int ref)
        : thread_state_(thread_state, [&root_state, ref](lua_State* state) {
            if (state != nullptr && ref != LUA_NOREF) {
              luaL_unref(root_state.state(), LUA_REGISTRYINDEX, ref);
            }
          }) {}

    absl::Status CanExecuteFunction();
    internal::LuaStatePtr thread_state_;
    bool is_finished_ = false;
    bool is_running_ = false;
    friend class LuaState;
  };

  // Creates and initializes a new Lua state, optionally loading the specified
  // `libs_to_load`.
  static absl::StatusOr<absl_nonnull std::unique_ptr<LuaState>> Create(
      absl::Span<const luaL_Reg> libs_to_load = {});

  LuaState(const LuaState&) = delete;
  LuaState& operator=(const LuaState&) = delete;

  LuaState(LuaState&& other) noexcept = delete;
  LuaState& operator=(LuaState&& other) noexcept = delete;
  virtual ~LuaState() = default;

  lua_State* absl_nonnull state() const { return state_.get(); }

  // Executes the provided Lua code string `s` in the current context.
  absl::Status ExecuteString(absl::string_view s);

  // Registers a C/C++ callback into the global Lua environment.
  // NOTE: The function is bound to the lifespan of this LuaState. Any
  // references captured by the given function must outlive the LuaState.
  // Do not call this in a hot loop, as registered functions are permanently
  // appended and kept alive for the lifetime of the LuaState.
  void RegisterFunction(absl::string_view name, lua_CFunction func);
  void RegisterFunction(absl::string_view name,
                        absl::AnyInvocable<std::string()> func);
  void RegisterFunction(absl::string_view name, absl::AnyInvocable<int()> func);
  void RegisterFunction(absl::string_view name,
                        absl::AnyInvocable<int(lua_State*)> func);

  // Spawns and returns a new Lua thread (coroutine) attached to this state.
  absl::StatusOr<absl_nonnull std::unique_ptr<LuaState::Thread>> NewThread()
      ABSL_ATTRIBUTE_LIFETIME_BOUND;

 private:
  explicit LuaState(lua_State* given_state)
      : state_(given_state, [](lua_State* state) { lua_close(state); }) {}
  // Stable-pointer vector tracking all registered C++ closures bound to the VM
  // to ensure they outlive any Lua-side invocations without relying on full
  // userdata memory management.
  std::vector<std::unique_ptr<absl::AnyInvocable<int(lua_State*)>>> closures_;
  // The managed underlying Lua VM instance wrapper.
  internal::LuaStatePtr state_;
};

// RAII helper to inject a globally accessible C/C++ function into the Lua VM
// for the duration of a scope, and properly unregister it (set to nil) upon
// destruction. Use this to safely manage sandbox-escalation functions or temp
// shims.
class ScopedGlobalFunction {
 public:
  template <typename Func>
  ScopedGlobalFunction(LuaState& state, absl::string_view name, Func&& func)
      : state_(state), name_(name) {
    state_.RegisterFunction(name, std::forward<Func>(func));
  }

  ~ScopedGlobalFunction() {
    lua_pushnil(state_.state());
    lua_setglobal(state_.state(), name_.c_str());
  }

 private:
  LuaState& state_;
  std::string name_;
};

}  // namespace sample::lua

#endif  // NET_TURING_WASM_LUA_LUA_STATE_H_
