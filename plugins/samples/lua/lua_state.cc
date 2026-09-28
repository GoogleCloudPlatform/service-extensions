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

#include "lua_state.h"

#include <array>
#include <cstddef>
#include <memory>
#include <string>
#include <utility>

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

#include "envoy_lua_api.h"
#include "envoy_lua_api_registration.h"
#include "absl/base/nullability.h"
#include "absl/functional/any_invocable.h"
#include "absl/memory/memory.h"
#include "absl/status/status.h"
#include "status_macros.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_format.h"
#include "absl/strings/string_view.h"
#include "absl/types/span.h"
#include "LuaBridge/LuaBridge.h"

namespace sample::lua {

namespace {

// This list defines the safe subset of Lua standard libraries to load.
// We must load libraries manually instead of using `luaL_openlibs` because the
// Proxy-Wasm sandbox restricts filesystem/OS access. Libraries like 'io' and
// 'os' would fail to link or load due to missing WASI host exports.
//
// Evaluating new items for this list:
// - Ensure the library does not require unsupported host syscalls (e.g., file
//   I/O, process control).
// - Verify it does not compromise the sandbox security model.
//
// TODO (geraldyywang): Add debug library in set up so we can save the traceback
// function for friendlier debug log message, then delete debug library from Lua
// table so user cannot use it to hang the VM
constexpr std::array<luaL_Reg, 5> kLuaLibs = {{
    {.name = "", .func = luaopen_base},
    {.name = LUA_COLIBNAME, .func = luaopen_coroutine},
    {.name = LUA_TABLIBNAME, .func = luaopen_table},
    {.name = LUA_STRLIBNAME, .func = luaopen_string},
    {.name = LUA_MATHLIBNAME, .func = luaopen_math},
}};

absl::Status LuaErrorToStatus(lua_State* state) {
  if (lua_gettop(state) == 0) {
    return absl::InternalError("Unknown Lua error (empty stack)");
  }
  size_t len = 0;
  const char* raw_err = lua_tolstring(state, -1, &len);
  absl::string_view msg = raw_err != nullptr
                              ? absl::string_view(raw_err, len)
                              : absl::string_view("Unknown Lua error");
  absl::Status err = absl::InternalError(msg);
  return err;
}

absl::Status ReadAndPopLuaError(lua_State* state) {
  if (lua_gettop(state) == 0) {
    return absl::InternalError("Unknown Lua error (empty stack)");
  }
  absl::Status err = LuaErrorToStatus(state);
  lua_pop(state, 1);
  return err;
}

template <typename... Args>
absl::StatusOr<ExecutionState> ExecuteFunctionImpl(LuaState::Thread* thread,
                                                   absl::string_view func_name,
                                                   Args&&... args) {
  luabridge::StackRestore restore(thread->state());

  lua_getglobal(thread->state(), std::string(func_name).c_str());
  if (!lua_isfunction(thread->state(), -1)) {
    return absl::NotFoundError(
        absl::StrCat("could not find ", func_name, " as a global function"));
  }

  absl::Status captured_error = absl::OkStatus();
  auto push_arg = [&captured_error](lua_State* lua_state, auto&& arg) -> bool {
    luabridge::Result res =
        luabridge::push(lua_state, std::forward<decltype(arg)>(arg));
    if (!res) {
      captured_error = absl::InternalError(
          absl::StrCat("Failed to push argument: ", res.message()));
      return false;
    }
    return true;
  };

  if constexpr (sizeof...(args) > 0) {
    if (!(push_arg(thread->state(), std::forward<Args>(args)) && ...)) {
      return captured_error;
    }
  }

  restore.reset();
  return thread->Resume(sizeof...(args));
}

}  // namespace

namespace {
template <typename Func>
void RegisterFunctionImpl(lua_State* lua_state, absl::string_view name, Func func) {
  luabridge::getGlobalNamespace(lua_state).addFunction(std::string(name).c_str(),
                                               std::move(func));
}
}  // namespace

void LuaState::RegisterFunction(absl::string_view name, lua_CFunction func) {
  lua_pushcfunction(state(), func);
  lua_setglobal(state(), std::string(name).c_str());
}

void LuaState::RegisterFunction(absl::string_view name,
                                absl::AnyInvocable<std::string()> func) {
  RegisterFunctionImpl(state(), name, std::move(func));
}

void LuaState::RegisterFunction(absl::string_view name,
                                absl::AnyInvocable<int()> func) {
  RegisterFunctionImpl(state(), name, std::move(func));
}

// LuaBridge swallows LUA_YIELD integers, so this custom trampoline bypasses it
// to preserve the raw VM yielding signals.
void LuaState::RegisterFunction(absl::string_view name,
                                absl::AnyInvocable<int(lua_State*)> func) {
  closures_.push_back(
      std::make_unique<absl::AnyInvocable<int(lua_State*)>>(std::move(func)));
  lua_pushlightuserdata(state(), closures_.back().get());
  lua_pushcclosure(
      state(),
      [](lua_State* lua_state) -> int {
        auto* f = static_cast<absl::AnyInvocable<int(lua_State*)>*>(
            lua_touserdata(lua_state, lua_upvalueindex(1)));
        return (*f)(lua_state);
      },
      1);
  lua_setglobal(state(), std::string(name).c_str());
}

absl::Status LuaState::ExecuteString(absl::string_view s) {
  if (!s.empty() && s[0] == LUA_SIGNATURE[0]) {
    return absl::InvalidArgumentError(
        "Precompiled lua bytecode is not supported");
  }
  if (luaL_loadbuffer(state(), s.data(), s.size(), "ExecuteString") != 0 ||
      lua_pcall(state(), /*nargs=*/0, /*nresults=*/0, /*errfunc=*/0) != 0) {
    return ReadAndPopLuaError(state());
  }
  return absl::OkStatus();
}

absl::StatusOr<absl_nonnull std::unique_ptr<LuaState>> LuaState::Create(
    absl::Span<const luaL_Reg> libs_to_load) {
  lua_State* new_raw_state = luaL_newstate();
  if (new_raw_state == nullptr) {
    return absl::InternalError("Could not create new lua state");
  }
  // Using WrapUnique and new because the LuaState constructor is private.
  // It is deliberately private to enforce that it's constructed via the Create
  // factory.
  absl_nonnull std::unique_ptr<LuaState> new_lua_state =
      absl::WrapUnique(new LuaState(new_raw_state));

  absl::Span<const luaL_Reg> libs_to_open =
      libs_to_load.empty() ? absl::MakeConstSpan(kLuaLibs) : libs_to_load;

  for (const auto& lib : libs_to_open) {
    lua_pushcfunction(new_lua_state->state(), [](lua_State* lua_state) -> int {
      const char* name = lua_tostring(lua_state, 1);
      lua_CFunction func =
          reinterpret_cast<lua_CFunction>(lua_touserdata(lua_state, 2));
      luaL_requiref(lua_state, name, func, 1);
      return 0;
    });
    lua_pushstring(new_lua_state->state(), lib.name);
    lua_pushlightuserdata(new_lua_state->state(),
                          reinterpret_cast<void*>(lib.func));
    if (lua_pcall(new_lua_state->state(), /*nargs=*/2, /*nresults=*/0,
                  /*errfunc=*/0) != 0) {
      absl::Status err = ReadAndPopLuaError(new_lua_state->state());
      return absl::InternalError(absl::StrFormat(
          "Could not open library %s: %s", lib.name, err.message()));
    }
  }

  // Stub out dangerous functionality in included lua libraries
  RETURN_IF_ERROR(new_lua_state->ExecuteString(R"lua(
        local orig_rep = string.rep
        string.rep = function(s, n)
          if #s * n > 65536 then
            error('string.rep: size limit exceeded (max 64KB)')
          end
          return orig_rep(s, n)
        end
        load = nil
        loadstring = nil
        loadfile = nil
        dofile = nil
      )lua"));
      

  RETURN_IF_ERROR(RegisterEnvoyApi(*new_lua_state));

  return new_lua_state;
}

absl::StatusOr<absl_nonnull std::unique_ptr<LuaState::Thread>>
LuaState::NewThread() {
  lua_State* new_thread = lua_newthread(state());
  if (new_thread == nullptr) {
    return absl::InternalError("Could not create new thread");
  }
  int ref = luaL_ref(state(), LUA_REGISTRYINDEX);

  // Using WrapUnique and new because the Thread constructor is private;
  // thread lifecycle initialization requires context from the enclosing
  // LuaState.
  return absl::WrapUnique(new Thread(new_thread, *this, ref));
}

int LuaState::Thread::Yield(int n_results) {
  return lua_yield(state(), n_results);
}

absl::StatusOr<ExecutionState> LuaState::Thread::Resume(int n_arg) {
  if (is_finished_) {
    return absl::FailedPreconditionError("cannot resume dead thread");
  }

  if (n_arg < 0 || n_arg > lua_gettop(state())) {
    return absl::InvalidArgumentError(
        "not enough arguments on stack to resume");
  }

  if (lua_status(state()) != LUA_YIELD && n_arg == lua_gettop(state())) {
    return absl::InvalidArgumentError(
        "not enough arguments on stack to resume");
  }

  if (is_running_) {
    return absl::FailedPreconditionError("cannot resume a running thread");
  }

  is_running_ = true;
  int rc = lua_resume(state(), nullptr, n_arg);
  is_running_ = false;

  if (rc == 0) {
    is_finished_ = true;
    return ExecutionState::kExited;
  } else if (rc == LUA_YIELD) {
    return ExecutionState::kYielded;
  }

  is_finished_ = true;
  return ReadAndPopLuaError(state());
}

absl::Status LuaState::Thread::CanExecuteFunction() {
  if (is_finished_) {
    return absl::FailedPreconditionError("cannot execute on dead thread");
  }
  if (lua_status(state()) == LUA_YIELD) {
    return absl::FailedPreconditionError("cannot execute on yielded thread");
  }
  return absl::OkStatus();
}

absl::StatusOr<ExecutionState> LuaState::Thread::ExecuteFunction(
    absl::string_view func_name) {
  RETURN_IF_ERROR(CanExecuteFunction());
  return ExecuteFunctionImpl(this, func_name);
}

absl::StatusOr<ExecutionState> LuaState::Thread::ExecuteFunction(
    absl::string_view func_name, Handle& handle) {
  RETURN_IF_ERROR(CanExecuteFunction());
  return ExecuteFunctionImpl(this, func_name, &handle);
}

absl::StatusOr<ExecutionState> LuaState::Thread::ExecuteFunction(
    absl::string_view func_name, int arg) {
  RETURN_IF_ERROR(CanExecuteFunction());
  return ExecuteFunctionImpl(this, func_name, arg);
}

}  // namespace sample::lua
