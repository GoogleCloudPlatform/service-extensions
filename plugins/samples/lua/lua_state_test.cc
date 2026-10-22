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

#include <memory>
#include <string>
#include <vector>

#include "envoy_lua_api.h"
#include "envoy_lua_api_registration.h"
#include "envoy_lua_api_shims.h"
#include "proxy_wasm_test_stubs.h"
#include "test_macros.h"
#include "LuaBridge/LuaBridge.h"
#include "LuaBridge/detail/LuaRef.h"
#include "LuaBridge/detail/Namespace.h"
#include "LuaBridge/detail/Result.h"
#include "LuaBridge/detail/Stack.h"
#include "absl/functional/any_invocable.h"
#include "absl/status/status.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/string_view.h"
#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "proxy_wasm_intrinsics.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace proxy_wasm_lua {
namespace {

using ::absl_testing::IsOkAndHolds;
using ::absl_testing::StatusIs;

using ::testing::HasSubstr;
using ::testing::NiceMock;

TEST(LuaStateTest, CreateSucceeds) { EXPECT_OK(LuaState::Create()); }

TEST(LuaStateTest, CreateWithCustomLibsSucceeds) {
  std::vector<luaL_Reg> libs = {{"", luaopen_base},
                                {LUA_STRLIBNAME, luaopen_string}};

  EXPECT_OK(LuaState::Create(libs));
}

static int BadLibInit(lua_State* L) {
  return luaL_error(L, "Simulated library init failure");
}

TEST(LuaStateTest, CreateFailsOnLibraryInitializationError) {
  std::vector<luaL_Reg> bad_libs = {{"bad_lib", BadLibInit}};

  EXPECT_THAT(LuaState::Create(bad_libs),
              StatusIs(absl::StatusCode::kInternal,
                       HasSubstr("Simulated library init failure")));
}

TEST(LuaStateTest, CreateFailsIfRequiredLibsMissingForSandbox) {
  std::vector<luaL_Reg> libs = {{"", luaopen_base}};

  EXPECT_THAT(LuaState::Create(libs),
              StatusIs(absl::StatusCode::kInternal,
                       HasSubstr("attempt to index global 'string'")));
}

TEST(LuaStateTest, ExecuteStringSucceedsOnValidLua) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_OK(state->ExecuteString("local x = 1 + 1"));
}

TEST(LuaStateTest, ExecuteStringFailsOnSyntaxError) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_THAT(state->ExecuteString("local x = 1 +"),
              StatusIs(absl::StatusCode::kInternal, HasSubstr("unexpected")));
}

TEST(LuaStateTest, ExecuteStringFailsOnRuntimeError) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_THAT(
      state->ExecuteString("error('Custom runtime error')"),
      StatusIs(absl::StatusCode::kInternal, HasSubstr("Custom runtime error")));
}

TEST(LuaStateTest, ExecuteStringSafelyHandlesNonStringErrors) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_THAT(
      state->ExecuteString("error({})"),
      StatusIs(absl::StatusCode::kInternal, HasSubstr("Unknown Lua error")));
  EXPECT_THAT(
      state->ExecuteString("error(nil)"),
      StatusIs(absl::StatusCode::kInternal, HasSubstr("Unknown Lua error")));
}

TEST(LuaStateTest, ExecuteStringDisallowsBytecode) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_THAT(state->ExecuteString("\033Lua"),
              StatusIs(absl::StatusCode::kInvalidArgument,
                       HasSubstr("Precompiled lua bytecode is not supported")));
  EXPECT_THAT(state->ExecuteString("\033"),
              StatusIs(absl::StatusCode::kInvalidArgument,
                       HasSubstr("Precompiled lua bytecode is not supported")));
  EXPECT_THAT(state->ExecuteString("\033somethingelse"),
              StatusIs(absl::StatusCode::kInvalidArgument,
                       HasSubstr("Precompiled lua bytecode is not supported")));
}

TEST(LuaStateTest, ExecuteStringSucceedsOnEmptyString) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_OK(state->ExecuteString(""));
}

TEST(LuaStateTest, RegisterFunctionCFunctionSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  state->RegisterFunction("c_func",
                          static_cast<lua_CFunction>([](lua_State* L) -> int {
                            lua_pushinteger(L, 42);
                            return 1;
                          }));
  EXPECT_OK(state->ExecuteString("assert(c_func() == 42)"));
}

TEST(LuaStateTest, RegisterFunctionStdFunctionStringSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  std::string captured = "hello";
  state->RegisterFunction("std_func_str", [captured]() -> std::string {
    return captured + " world";
  });
  EXPECT_OK(state->ExecuteString("assert(std_func_str() == 'hello world')"));
}

TEST(LuaStateTest, RegisterFunctionStdFunctionIntSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  int counter = 0;
  state->RegisterFunction("std_func_int", [&counter]() -> int {
    counter++;
    return counter;
  });
  EXPECT_OK(state->ExecuteString("assert(std_func_int() == 1)"));
  EXPECT_OK(state->ExecuteString("assert(std_func_int() == 2)"));
  EXPECT_EQ(counter, 2);
}

TEST(LuaStateTest, RegisterFunctionStdFunctionStateArgSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  state->RegisterFunction("std_func_state", absl::AnyInvocable<int(lua_State*)>(
                                                [](lua_State* L) -> int {
                                                  lua_pushinteger(L, 100);
                                                  return 1;
                                                }));
  EXPECT_OK(state->ExecuteString("assert(std_func_state() == 100)"));
}

TEST(LuaStateTest, RegisterFunctionOverwritesPreviousFunction) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  state->RegisterFunction(
      "my_func", absl::AnyInvocable<int(lua_State*)>([](lua_State* L) -> int {
        lua_pushinteger(L, 1);
        return 1;
      }));
  EXPECT_OK(state->ExecuteString("assert(my_func() == 1)"));

  state->RegisterFunction(
      "my_func", absl::AnyInvocable<int(lua_State*)>([](lua_State* L) -> int {
        lua_pushinteger(L, 2);
        return 1;
      }));
  EXPECT_OK(state->ExecuteString("assert(my_func() == 2)"));
}

TEST(LuaStateTest, RegisterFunctionWithYieldingStdFunctionSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  state->RegisterFunction("yielding_func", absl::AnyInvocable<int(lua_State*)>(
                                               [](lua_State* L) -> int {
                                                 lua_pushinteger(L, 55);
                                                 return lua_yield(L, 1);
                                               }));
  EXPECT_THAT(thread->ExecuteFunction("yielding_func"),
              IsOkAndHolds(ExecutionState::kYielded));
  EXPECT_EQ(lua_gettop(thread->state()), 1);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 55);
}

TEST(LuaStateTest, RegisterFunctionWithYieldingMultipleValuesSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  state->RegisterFunction(
      "yielding_multi_func",
      absl::AnyInvocable<int(lua_State*)>([](lua_State* L) -> int {
        lua_pushinteger(L, 55);
        lua_pushinteger(L, 100);
        return lua_yield(L, 2);
      }));
  EXPECT_THAT(thread->ExecuteFunction("yielding_multi_func"),
              IsOkAndHolds(ExecutionState::kYielded));
  EXPECT_EQ(lua_gettop(thread->state()), 2);
  EXPECT_EQ(lua_tonumber(thread->state(), -2), 55);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 100);
}

TEST(LuaStateTest, RegisterFunctionWithYieldingZeroValuesSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  state->RegisterFunction(
      "yielding_zero_func",
      absl::AnyInvocable<int(lua_State*)>(
          [](lua_State* L) -> int { return lua_yield(L, 0); }));
  EXPECT_THAT(thread->ExecuteFunction("yielding_zero_func"),
              IsOkAndHolds(ExecutionState::kYielded));
  EXPECT_EQ(lua_gettop(thread->state()), 0);
}

TEST(LuaStateTest, RegisterFunctionClosuresListStability) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  for (int i = 0; i < 1000; i++) {
    std::string name = absl::StrCat("func_", i);
    state->RegisterFunction(name, [i](lua_State* L) -> int {
      lua_pushinteger(L, i);
      return 1;
    });
  }

  EXPECT_OK(state->ExecuteString("assert(func_0() == 0)"));
  EXPECT_OK(state->ExecuteString("assert(func_999() == 999)"));
}

TEST(LuaStateTest, RegisterFunctionWithHugeName) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  std::string huge_name(10000, 'a');
  state->RegisterFunction(
      huge_name, absl::AnyInvocable<int(lua_State*)>([](lua_State* L) -> int {
        lua_pushboolean(L, 1);
        return 1;
      }));
  std::string execute_script =
      absl::StrCat("assert(", huge_name, "() == true)");
  EXPECT_OK(state->ExecuteString(execute_script));
}

TEST(LuaStateTest, RegisterFunctionWithEmptyStringName) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  state->RegisterFunction(
      "", absl::AnyInvocable<int(lua_State*)>([](lua_State* L) -> int {
        lua_pushboolean(L, 1);
        return 1;
      }));
  EXPECT_OK(state->ExecuteString("assert(_G['']() == true)"));
}

TEST(LuaStateTest, RegisterFunctionWithUnprintableCharacters) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  std::string bad_name = "func\x01\x02!";
  state->RegisterFunction(
      bad_name, absl::AnyInvocable<int(lua_State*)>([](lua_State* L) -> int {
        lua_pushinteger(L, 123);
        return 1;
      }));
  std::string lua_script = "assert(_G['func\\001\\002!']() == 123)";
  EXPECT_OK(state->ExecuteString(lua_script));
}

TEST(SandboxingTest, DangerousGlobalsAreNil) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_OK(state->ExecuteString("assert(load == nil)"));
  EXPECT_OK(state->ExecuteString("assert(loadstring == nil)"));
  EXPECT_OK(state->ExecuteString("assert(loadfile == nil)"));
  EXPECT_OK(state->ExecuteString("assert(dofile == nil)"));
  EXPECT_OK(state->ExecuteString("assert(os == nil)"));
  EXPECT_OK(state->ExecuteString("assert(io == nil)"));
}

TEST(SandboxingTest, StringRepUnderLimitOk) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_OK(state->ExecuteString("local s = string.rep('a', 65536)"));
}

TEST(SandboxingTest, StringRepOverLimitFails) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_THAT(
      state->ExecuteString("local s = string.rep('a', 65537)"),
      StatusIs(absl::StatusCode::kInternal, HasSubstr("size limit exceeded")));
}

TEST(SandboxingTest, StringRepWithLongerStringUnderLimitOk) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_OK(state->ExecuteString("local s = string.rep('aaaa', 16384)"));
}

TEST(SandboxingTest, StringRepWithLongerStringOverLimitFails) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_THAT(
      state->ExecuteString("local s = string.rep('aaaa', 16385)"),
      StatusIs(absl::StatusCode::kInternal, HasSubstr("size limit exceeded")));
}

TEST(SandboxingTest, StringRepHandlesNegativeAndZero) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  EXPECT_OK(state->ExecuteString("local s = string.rep('a', 0)"));
  EXPECT_OK(state->ExecuteString("local s = string.rep('a', -78)"));
}

TEST(LuaThreadTest, NewThreadSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());

  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  EXPECT_NE(thread->state(), nullptr);
}

TEST(LuaThreadTest, ThreadYieldMethodSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  LuaState::Thread* thread_ptr = thread.get();
  state->RegisterFunction(
      "ccall_yield",
      absl::AnyInvocable<int(lua_State*)>([thread_ptr](lua_State* L) -> int {
        lua_pushnumber(L, 99);
        return thread_ptr->Yield(/*n_results=*/1);
      }));
  EXPECT_THAT(thread->ExecuteFunction("ccall_yield"),
              IsOkAndHolds(ExecutionState::kYielded));
  EXPECT_EQ(lua_gettop(thread->state()), 1);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 99);
}

TEST(LuaThreadTest, ThreadResumeAndYieldSucceed) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  ASSERT_OK(
      state->ExecuteString("function test_yield() coroutine.yield(42) end"));

  EXPECT_THAT(thread->ExecuteFunction("test_yield"),
              IsOkAndHolds(ExecutionState::kYielded));
  EXPECT_EQ(lua_gettop(thread->state()), 1);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 42);

  EXPECT_THAT(thread->Resume(/*n_arg=*/0),
              IsOkAndHolds(ExecutionState::kExited));
}

TEST(LuaThreadTest, ResumePropagatesErrors) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  ASSERT_OK(
      state->ExecuteString("function test_err() error('thread err') end"));
  EXPECT_THAT(thread->ExecuteFunction("test_err"),
              StatusIs(absl::StatusCode::kInternal, HasSubstr("thread err")));
}

TEST(LuaThreadTest, ResumeWithArgumentsSucceeds) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  ASSERT_OK(state->ExecuteString("function test_args(x) return x * 2 end"));
  EXPECT_THAT(thread->ExecuteFunction("test_args", 21),
              IsOkAndHolds(ExecutionState::kExited));
  EXPECT_EQ(lua_gettop(thread->state()), 1);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 42);
}

TEST(LuaThreadTest, ResumeFinishedThreadReturnsError) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  ASSERT_OK(state->ExecuteString("function test_empty() return end"));
  EXPECT_THAT(thread->ExecuteFunction("test_empty"),
              IsOkAndHolds(ExecutionState::kExited));
  EXPECT_THAT(thread->ExecuteFunction("test_empty"),
              StatusIs(absl::StatusCode::kFailedPrecondition,
                       HasSubstr("cannot execute on dead thread")));
}

TEST(LuaThreadTest, ResumeErroredThreadReturnsError) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  ASSERT_OK(state->ExecuteString(
      "function test_err_first() error('first error') end"));
  EXPECT_THAT(thread->ExecuteFunction("test_err_first"),
              StatusIs(absl::StatusCode::kInternal, HasSubstr("first error")));

  EXPECT_THAT(thread->Resume(/*n_arg=*/0),
              StatusIs(absl::StatusCode::kFailedPrecondition,
                       HasSubstr("cannot resume dead thread")));
}

TEST(LuaThreadTest, ExecuteFunctionSucceedsWithNoArgs) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString(
      "function no_args_func() _G.function_called = true end"));

  EXPECT_THAT(thread->ExecuteFunction("no_args_func"),
              IsOkAndHolds(ExecutionState::kExited));
  EXPECT_OK(state->ExecuteString("assert(_G.function_called == true)"));
}

TEST(LuaThreadTest, ExecuteFunctionReturnsYieldedStatus) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(
      state->ExecuteString("function yield_func() coroutine.yield() end"));

  EXPECT_THAT(thread->ExecuteFunction("yield_func"),
              IsOkAndHolds(ExecutionState::kYielded));
  EXPECT_THAT(thread->Resume(/*n_arg=*/0),
              IsOkAndHolds(ExecutionState::kExited));
}

TEST(LuaThreadTest, ExecuteFunctionWithArgsYields) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString(
      "function yield_func_with_args(x) coroutine.yield(x) end"));

  EXPECT_THAT(thread->ExecuteFunction("yield_func_with_args", 42),
              IsOkAndHolds(ExecutionState::kYielded));

  EXPECT_EQ(lua_gettop(thread->state()), 1);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 42);
}

TEST(LuaThreadTest, ExecuteFunctionFailsIfFunctionNotFound) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  EXPECT_THAT(
      thread->ExecuteFunction("does_not_exist"),
      StatusIs(absl::StatusCode::kNotFound, HasSubstr("could not find")));
}

TEST(LuaThreadTest, ExecuteFunctionFailsOnRuntimeError) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString(
      "function broken_func() error('execution failed') end"));

  EXPECT_THAT(
      thread->ExecuteFunction("broken_func"),
      StatusIs(absl::StatusCode::kInternal, HasSubstr("execution failed")));
}

TEST(LuaThreadTest, ExecuteFunctionWithHandle) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(
      state->ExecuteString("function test_handle(h) coroutine.yield(h) end"));

  NiceMock<MockStreamState> mock_coroutine;
  Handle test_handle(mock_coroutine);
  EXPECT_THAT(thread->ExecuteFunction("test_handle", test_handle),
              IsOkAndHolds(ExecutionState::kYielded));

  EXPECT_EQ(lua_gettop(thread->state()), 1);
  luabridge::LuaRef ref = luabridge::LuaRef::fromStack(thread->state(), -1);
  EXPECT_TRUE(ref.isUserdata());
  EXPECT_EQ(ref.getClassName().value_or("MISSING"), "Handle");
  luabridge::TypeResult<Handle*> cast_result = ref.cast<Handle*>();
  ASSERT_TRUE(cast_result || cast_result.error().value() == 0)
      << "Cast failed: " << cast_result.error_cstr();
  EXPECT_EQ(cast_result.value(), &test_handle);
  EXPECT_THAT(thread->Resume(/*n_arg=*/0),
              IsOkAndHolds(ExecutionState::kExited));
}

TEST(LuaThreadTest, ResumeFailsIfNotEnoughArgsOnStack) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  EXPECT_THAT(thread->Resume(/*n_arg=*/1),
              StatusIs(absl::StatusCode::kInvalidArgument,
                       HasSubstr("not enough arguments on stack to resume")));

  EXPECT_THAT(thread->Resume(/*n_arg=*/-1),
              StatusIs(absl::StatusCode::kInvalidArgument,
                       HasSubstr("not enough arguments on stack to resume")));
}

TEST(LuaThreadTest, ResumeSucceedsWithExactArgsOnStack) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString(
      "function test3() local x = coroutine.yield(); return x end"));
  EXPECT_THAT(thread->ExecuteFunction("test3"),
              IsOkAndHolds(ExecutionState::kYielded));

  lua_settop(thread->state(), 0);
  lua_pushnumber(thread->state(), 42);

  EXPECT_THAT(thread->Resume(/*n_arg=*/1),
              IsOkAndHolds(ExecutionState::kExited));
  EXPECT_EQ(lua_gettop(thread->state()), 1);
  EXPECT_EQ(lua_tonumber(thread->state(), -1), 42);
}

TEST(LuaThreadTest, ResumeSucceedsWithMoreArgsOnStack) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString(
      "function test3() local x = coroutine.yield(); return x end"));
  EXPECT_THAT(thread->ExecuteFunction("test3"),
              IsOkAndHolds(ExecutionState::kYielded));

  lua_settop(thread->state(), 0);
  lua_pushnumber(thread->state(), 100);
  lua_pushnumber(thread->state(), 42);

  EXPECT_THAT(thread->Resume(/*n_arg=*/1),
              IsOkAndHolds(ExecutionState::kExited));
}

TEST(LuaThreadTest, ExecuteFunctionFailsWhenThreadIsYielded) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString("function test5() coroutine.yield() end"));
  EXPECT_THAT(thread->ExecuteFunction("test5"),
              IsOkAndHolds(ExecutionState::kYielded));

  EXPECT_THAT(thread->ExecuteFunction("some_func"),
              StatusIs(absl::StatusCode::kFailedPrecondition,
                       HasSubstr("cannot execute on yielded thread")));
}

TEST(LuaThreadTest, ExecuteFunctionFailsWhenThreadIsFinished) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString("function test6() return end"));
  EXPECT_THAT(thread->ExecuteFunction("test6"),
              IsOkAndHolds(ExecutionState::kExited));

  EXPECT_THAT(thread->ExecuteFunction("some_func"),
              StatusIs(absl::StatusCode::kFailedPrecondition,
                       HasSubstr("cannot execute on dead thread")));
}

TEST(LuaThreadTest, ExecuteFunctionFailsIfNotAFunction) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  ASSERT_OK(state->ExecuteString("not_a_func = 42"));

  EXPECT_THAT(
      thread->ExecuteFunction("not_a_func"),
      StatusIs(absl::StatusCode::kNotFound, HasSubstr("could not find")));
}

struct FakeStatusTest {
  absl::Status ReturnOk() const { return absl::OkStatus(); }
  absl::Status ReturnError() const {
    return absl::InvalidArgumentError("This is a mock error");
  }
  absl::Status ReturnErrorWithoutMessage() const {
    return absl::InternalError("");
  }
  absl::StatusOr<std::string> ReturnStatusOrOk() const {
    return std::string("statusor data");
  }
  absl::StatusOr<std::string> ReturnStatusOrError() const {
    return absl::InvalidArgumentError("statusor mock error");
  }
  absl::StatusOr<int*> ReturnStatusOrNullptr() const { return nullptr; }
  absl::StatusOr<int> ReturnStatusOrIntOk() const { return 42; }
};

TEST(LuaStateTest, ValidatesStatusIsCorrectlyInterceptedAndWrapped) {
  ASSERT_OK_AND_ASSIGN(auto state, LuaState::Create());

  luabridge::getGlobalNamespace(state->state())
      .beginClass<absl::Status>("absl_Status")
      .addProperty("is_status_node", [](const absl::Status*) { return true; })
      .addProperty("has_value", [](const absl::Status*) { return false; })
      .addFunction("ok", &absl::Status::ok)
      .addFunction(
          "message",
          [](const absl::Status& s) { return std::string(s.message()); })
      .endClass();

  proxy_wasm_lua::RegisterStatusOr<std::string>(*state, "StatusOr_string");
  proxy_wasm_lua::RegisterStatusOr<int*>(*state, "StatusOr_int_ptr");
  proxy_wasm_lua::RegisterStatusOr<int>(*state, "StatusOr_int");

  luabridge::getGlobalNamespace(state->state())
      .beginClass<FakeStatusTest>("FakeStatusTest")
      .addFunction("returnOk", &FakeStatusTest::ReturnOk)
      .addFunction("returnError", &FakeStatusTest::ReturnError)
      .addFunction("returnErrorWithoutMessage",
                   &FakeStatusTest::ReturnErrorWithoutMessage)
      .addFunction("returnStatusOrOk", &FakeStatusTest::ReturnStatusOrOk)
      .addFunction("returnStatusOrError", &FakeStatusTest::ReturnStatusOrError)
      .addFunction("returnStatusOrNullptr",
                   &FakeStatusTest::ReturnStatusOrNullptr)
      .addFunction("returnStatusOrIntOk", &FakeStatusTest::ReturnStatusOrIntOk)
      .endClass();

  FakeStatusTest fake_status;
  (void)luabridge::push(state->state(), &fake_status);
  lua_setglobal(state->state(), "fake_status_object");

  EXPECT_OK(state->ExecuteString(proxy_wasm_lua::kStatusUnwrapperFunctionShim));

  {
    ScopedGlobalFunction scoped_raw(
        *state, "__raw_getmetatable",
        static_cast<lua_CFunction>([](lua_State* state) -> int {
          luaL_checkany(state, 1);
          if (lua_getmetatable(state, 1)) return 1;
          lua_pushnil(state);
          return 1;
        }));
    EXPECT_OK(
        state->ExecuteString("attach_status_unwrapper('FakeStatusTest')"));
  }

  constexpr absl::string_view lua_code = R"lua(
    local ok, res = pcall(function() return fake_status_object:returnOk() end)
    assert(ok, "ok status threw error")

    local ok2, err2 = pcall(function() return fake_status_object:returnError() end)
    assert(not ok2, "invalid argument error failed to throw")
    assert(string.find(err2, "This is a mock error"), "mock error did not contain expected message")

    local ok3, err3 = pcall(function() return fake_status_object:returnErrorWithoutMessage() end)
    assert(not ok3, "empty error message failed to throw")
    -- The error message itself might just be the file:line info, but we shouldn't crash.

    local ok4, res4 = pcall(function() return fake_status_object:returnStatusOrOk() end)
    assert(ok4, "StatusOr ok threw error")
    assert(res4 == "statusor data", "StatusOr did not unwrap to the correct value")

    local ok5, err5 = pcall(function() return fake_status_object:returnStatusOrError() end)
    assert(not ok5, "StatusOr error failed to throw")
    assert(string.find(err5, "statusor mock error"), "StatusOr error did not contain expected message")

    local ok6, res6 = pcall(function() return fake_status_object:returnStatusOrNullptr() end)
    assert(ok6, "StatusOr nullptr threw error")
    assert(res6 == nil, "StatusOr nullptr did not unwrap to nil")

    local ok7, res7 = pcall(function() return fake_status_object:returnStatusOrIntOk() end)
    assert(ok7, "StatusOr int threw error")
    assert(res7 == 42, "StatusOr int did not unwrap to the correct value")
  )lua";

  EXPECT_OK(state->ExecuteString(lua_code));
}

}  // namespace
}  // namespace proxy_wasm_lua
