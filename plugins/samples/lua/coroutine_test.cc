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

#include "coroutine.h"

#include <cstddef>
#include <cstring>
#include <memory>
#include <string>

#include "lua_state.h"
#include "proxy_wasm_test_stubs.h"
#include "gmock/gmock.h"
#include "gtest/gtest.h"

#ifndef LOCAL_MACROS
#define LOCAL_MACROS
#define EXPECT_OK(expr) EXPECT_TRUE(GetStatus((expr)).ok())
#define ASSERT_OK(expr) ASSERT_TRUE(GetStatus((expr)).ok())

template <typename T> absl::Status GetStatus(const absl::StatusOr<T>& v) { return v.status(); }
template <typename T> absl::Status GetStatus(const T& v) { return v; } 
inline absl::Status GetStatus(const absl::Status& v) { return v; }

#define CONCAT_INNER(a, b) a ## b
#define CONCAT(a, b) CONCAT_INNER(a, b)
#define ASSERT_OK_AND_ASSIGN(lhs, rexpr) \
    auto CONCAT(_res_, __LINE__) = (rexpr); \
    ASSERT_TRUE(GetStatus(CONCAT(_res_, __LINE__)).ok()) << GetStatus(CONCAT(_res_, __LINE__)).message(); \
    lhs = std::move(*CONCAT(_res_, __LINE__))
#endif

#include "absl/status/status.h"
#include "absl/strings/string_view.h"
#include "LuaBridge/detail/CFunctions.h"
#include "LuaBridge/detail/LuaRef.h"
#include "LuaBridge/detail/Result.h"
#include "proxy_wasm_intrinsics.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace sample::lua {
namespace {

using ::testing::_;
using ::testing::DoAll;
using ::testing::Not;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StrEq;

TEST(CoroutineTest, StartCoroutineReturnsOk) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
    end
  )lua"));
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, StartCoroutineWithRuntimeErrorReturnsNotOk) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      nil_function()
      return "should not be reached"
    end
  )lua"));
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(GetStatus(coroutine.Start()).ok());
  EXPECT_EQ(coroutine.GetState(), ExecutionState::kExited);
}

TEST(CoroutineTest, StartCoroutineYieldsWhenBodyNotReceived) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);
  lua_state->RegisterFunction(
      "mock_get_body", [&coroutine](lua_State* L) -> int {
        if (!coroutine.IsBodyReceived() && !coroutine.IsStreamEnded()) {
          return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBody,
                                 0);
        }
        return luaL_error(L, "Sync get_body not mocked");
      });
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      local body = mock_get_body()
      return body
    end
  )lua"));
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBody);
}

TEST(CoroutineTest, ResumeCoroutineReturnsOkAndExits) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);
  lua_state->RegisterFunction(
      "mock_get_body", [&coroutine](lua_State* L) -> int {
        if (!coroutine.IsBodyReceived() && !coroutine.IsStreamEnded()) {
          return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBody,
                                 0);
        }
        return luaL_error(L, "Sync get_body not mocked");
      });
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      local body = mock_get_body()
      return body
    end
  )lua"));

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, ResumeExitedCoroutineReturnsFailedPrecondition) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      return "ok"
    end
  )lua"));
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };

  { auto _s = coroutine.Resume(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kFailedPrecondition); };
}

TEST(CoroutineTest, ResumeErroredCoroutineReturnsFailedPrecondition) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      error("test error")
    end
  )lua"));
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(GetStatus(coroutine.Start()).ok());

  { auto _s = coroutine.Resume(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kFailedPrecondition); };
  EXPECT_EQ(coroutine.GetState(), ExecutionState::kExited);
}

TEST(CoroutineTest, MultipleYieldResumeCyclesCompleteSuccessfully) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);
  lua_state->RegisterFunction("mock_yield", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      mock_yield()
      mock_yield()
      mock_yield()
    end
  )lua"));
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleHeadersWithEndOfStreamExitsCoroutine) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("get_body", [&coroutine](lua_State* L) -> int {
    if (!coroutine.IsBodyReceived() && !coroutine.IsStreamEnded()) {
      return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBody, 0);
    }
    return luaL_error(L, "Sync get_body not mocked");
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      local body = get_body()
      if type(body) ~= "userdata" then
        error("failure")
      end
    end
  )lua"));
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };

  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
  EXPECT_TRUE(coroutine.IsStreamEnded());
}

TEST(CoroutineTest, HandleHeadersWithHttpCallYieldsWaitForHttp) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("http_call", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      http_call()
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_FALSE(coroutine.IsHeadersReceived());
  EXPECT_OK(coroutine.HandleHeaders(5, false));
  EXPECT_TRUE(coroutine.IsHeadersReceived());
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, SequentialYieldsCompleteSuccessfully) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("http_call", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      http_call()
      http_call()
    end
  )lua"));

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);
  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, LuaScriptErrorTransitionsCoroutineToExited) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      error("this script is broken")
    end
  )lua"));

  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(coroutine.Start().ok());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleHeadersWithoutYieldCompletesExecution) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
    end
  )lua"));

  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, TryResumeSelfInsideLuaReturnsFailedPrecondition) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("http_call", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });

  state->RegisterFunction("try_resume_self", [&coroutine](lua_State* L) -> int {
    if (coroutine.Resume().status().code() ==
        absl::StatusCode::kFailedPrecondition) {
      lua_pushstring(L, "resume_failed_precondition");
      return 1;
    }
    return 0;
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      return try_resume_self()
    end
  )lua"));
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleHeadersOnAlreadyEndedStreamDoesNotChangeState) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
    end
  )lua"));

  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_TRUE(coroutine.IsStreamEnded());
  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
}

TEST(CoroutineTest, HandleHeadersInResponseModeExitsCoroutine) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_response()
      return "response_success"
    end
  )lua"));

  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kResponse);

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, LuaScriptErrorAfterYieldTransitionsCoroutineToExited) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("http_call", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      http_call()
      error("error after yield")
    end
  )lua"));

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);

  EXPECT_FALSE(coroutine.Resume().ok());
  EXPECT_EQ(coroutine.GetState(), ExecutionState::kExited);
}

TEST(CoroutineTest, HandleHeadersWithTrailersEndOfStreamExitsCoroutine) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("get_trailers", [&coroutine](lua_State* L) -> int {
    if (coroutine.IsTrailersReceived()) {
      return luaL_error(L, "Sync get_trailers not mocked");
    }
    if (coroutine.IsStreamEnded()) {
      lua_pushnil(L);
      return 1;
    }
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForTrailers,
                           0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      local trailers = get_trailers()
      if trailers ~= nil then
        error("failure")
      end
    end
  )lua"));

  EXPECT_OK(coroutine.HandleHeaders(5, true));
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleHeadersYieldsWaitForBody) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("get_body", [&coroutine](lua_State* L) -> int {
    if (!coroutine.IsBodyReceived() && !coroutine.IsStreamEnded()) {
      return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBody, 0);
    }
    return luaL_error(L, "Sync get_body not mocked");
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      local body = get_body()
      if type(body) ~= "userdata" then
        error("failure")
      end
    end
  )lua"));

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBody);
}

TEST(CoroutineTest, HandleHeadersYieldsWaitForTrailers) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("get_trailers", [&coroutine](lua_State* L) -> int {
    if (coroutine.IsTrailersReceived()) {
      return luaL_error(L, "Sync get_trailers not mocked");
    }
    if (coroutine.IsStreamEnded()) {
      lua_pushnil(L);
      return 1;
    }
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForTrailers,
                           0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      local trailers = get_trailers()
      if type(trailers) ~= "userdata" then
        error("failure")
      end
    end
  )lua"));

  EXPECT_OK(coroutine.Start());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForTrailers);
}

TEST(
    CoroutineTest,
    HandleTrailersResumesCoroutineYieldedForNativeBodyChunksCompletesExecution) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        chunk_num = chunk_num + 1
      end
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };

  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest,
     HandleBodyConsecutivelyPushesMultipleChunksToLuaIteratorLoop) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        -- we verify that chunk is effectively parsed natively as a robust
        -- Buffer C++ userdata type
        local len = chunk:length()
        chunk_num = chunk_num + 1
      end
      -- if we accurately process precisely 3 chunks.
      if chunk_num ~= 3 then
         error("failure_" .. tostring(chunk_num))
      end
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(50, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(100, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(25, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleBodyExitsCoroutineIfBodyChunksLoopTerminatesEarly) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        chunk_num = chunk_num + 1
        if chunk_num == 2 then
          break
        end
      end
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(50, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(100, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleBodyGracefullyProcessesZeroLengthChunks) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      local chunk_len = -1
      for chunk in h:bodyChunks() do
        chunk_len = chunk:length()
        chunk_num = chunk_num + 1
      end
      -- if we accurately process the single 0-sized chunk,
      -- gracefully return success.
      if chunk_num ~= 1 or chunk_len ~= 0 then
        error("failure_" .. tostring(chunk_num) .. "_" .. tostring(chunk_len))
      end
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);
  { auto _s = coroutine.HandleBody(0, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(
    CoroutineTest,
    HandleTrailersGracefullyTerminatesBodyChunksIteratorAfterIntermediateChunks) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        local len = chunk:length()
        chunk_num = chunk_num + 1
      end
      -- We expect exactly 2 intermediate chunks processed before trailers
      -- terminate the stream.
      if chunk_num ~= 2 then
         error("failure_" .. tostring(chunk_num))
      end
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(50, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(40, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, StartAlreadyStartedCoroutineReturnsFailedPrecondition) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("get_body", [&coroutine](lua_State* L) -> int {
    if (!coroutine.IsBodyReceived() && !coroutine.IsStreamEnded()) {
      return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBody, 0);
    }
    return luaL_error(L, "Sync get_body not mocked");
  });
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      get_body()
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };

  { auto _s = coroutine.Start(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kFailedPrecondition); };
}

TEST(CoroutineTest, HandleStreamMethodsOnErroredCoroutineReturnsOk) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      error("explicit error")
    end
  )lua"));
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(coroutine.Start().ok());

  EXPECT_EQ(coroutine.GetState(), ExecutionState::kExited);
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
  { auto _s = coroutine.HandleBody(100, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleStreamMethodsOnExitedCoroutineReturnsOk) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
    end
  )lua"));
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
  { auto _s = coroutine.HandleBody(100, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleHeadersSetsStreamEndedToTrue) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(coroutine.IsStreamEnded());
  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_TRUE(coroutine.IsStreamEnded());
}

TEST(CoroutineTest, HandleBodySetsStreamEndedToTrue) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(coroutine.IsStreamEnded());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(100, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_TRUE(coroutine.IsStreamEnded());
}

TEST(CoroutineTest, HandleTrailersSetsStreamEndedToTrue) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       state->NewThread());

  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  EXPECT_FALSE(coroutine.IsStreamEnded());
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_TRUE(coroutine.IsStreamEnded());
}

TEST(CoroutineTest, ImmediateEndOfStreamExitsWithoutYielding) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(coroutine.HandleHeaders(0, true));
  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      return "completed"
    end
  )lua"));
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest,
     HandleHeadersWithEndOfStreamWhileYieldedForHttpMaintainsYieldState) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("http_call", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      http_call()
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_FALSE(coroutine.IsHeadersReceived());
  EXPECT_FALSE(coroutine.IsStreamEnded());
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);

  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetState(), ExecutionState::kYielded);
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);

  EXPECT_TRUE(coroutine.IsHeadersReceived());
  EXPECT_TRUE(coroutine.IsStreamEnded());

  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, HandleBodyWhileYieldedForHttpMaintainsYieldState) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);
  state->RegisterFunction("http_call", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForHttp, 0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      http_call()
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_OK(coroutine.HandleHeaders(5, false));
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);

  { auto _s = coroutine.HandleBody(100, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetState(), ExecutionState::kYielded);
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForHttp);

  EXPECT_FALSE(coroutine.IsBodyReceived());

  { auto _s = coroutine.HandleBody(0, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_TRUE(coroutine.IsBodyReceived());

  { auto _s = coroutine.Resume(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, BufferSetBytesInvokesProxySetBufferBytes) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());

  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      local body = handle:body()
      body:setBytes("new_body")
    end
  )lua"));

  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  MockProxyWasmAbi mock_abi;
  size_t initial_body_size = 10;
  EXPECT_CALL(mock_abi,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillRepeatedly(
          DoAll(SetArgPointee<1>(initial_body_size), Return(WasmResult::Ok)));

  EXPECT_CALL(mock_abi,
              proxy_set_buffer_bytes(WasmBufferType::HttpRequestBody, 0,
                                     initial_body_size, StrEq("new_body"),
                                     strlen("new_body")))
      .WillOnce(Return(WasmResult::Ok));

  ASSERT_OK_AND_ASSIGN(ExecutionState state, coroutine.Start());
  EXPECT_EQ(state, ExecutionState::kYielded);
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(initial_body_size, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, BufferAndHandleLogInfoInvokesProxyLog) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());

  EXPECT_OK(lua_state->ExecuteString(R"lua(
    function envoy_on_request(handle)
      handle:logInfo("hello from handle")
      local body = handle:body()
      body:logInfo("hello from buffer")
    end
  )lua"));

  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  MockProxyWasmAbi mock_abi;
  EXPECT_CALL(mock_abi,
              proxy_log(LogLevel::info, StrEq("hello from handle"), 17))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_CALL(mock_abi,
              proxy_log(LogLevel::info, StrEq("hello from buffer"), 17))
      .WillOnce(Return(WasmResult::Ok));

  ASSERT_OK_AND_ASSIGN(ExecutionState state, coroutine.Start());
  EXPECT_EQ(state, ExecutionState::kYielded);
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, BufferGetBytesInvokesProxyGetBufferBytes) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());

  EXPECT_OK(lua_state->ExecuteString(R"lua(
    global_result = nil
    function envoy_on_request(handle)
      local body = handle:body()
      global_result = body:getBytes(0, body:length())
    end
  )lua"));

  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  MockProxyWasmAbi mock_abi;
  size_t initial_body_size = 5;
  EXPECT_CALL(mock_abi,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillRepeatedly(
          DoAll(SetArgPointee<1>(initial_body_size), Return(WasmResult::Ok)));

  EXPECT_CALL(mock_abi, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                               0, initial_body_size, _, _))
      .WillOnce(SetWasmBufferBytes("hello"));

  ASSERT_OK_AND_ASSIGN(ExecutionState state, coroutine.Start());
  EXPECT_EQ(state, ExecutionState::kYielded);
  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };

  luabridge::LuaRef global_result =
      luabridge::getGlobal(lua_state->state(), "global_result");
  luabridge::TypeResult<std::string> cast_result =
      global_result.cast<std::string>();
  ASSERT_TRUE(cast_result);
  EXPECT_EQ(*cast_result, "hello");
}

TEST(CoroutineTest, HandleTrailersCompletesOutOfOrderYieldsWithoutDeadlock) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  state->RegisterFunction("yield_for", [&coroutine](lua_State* L) -> int {
    int query = lua_tointeger(L, 1);
    if (query == 1) {
      return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForTrailers,
                             0);
    } else {
      return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBody, 0);
    }
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      local trailers = yield_for(1)
      local body = yield_for(2)
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForTrailers);

  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };

  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(CoroutineTest, RunToCompletionSafelyTerminatesBodyChunksIterator) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  state->RegisterFunction("yield_chunk", [&coroutine](lua_State* L) -> int {
    return coroutine.Yield(LuaStreamCoroutine::YieldReason::kWaitForBodyChunks,
                           0);
  });

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request()
      local count = 0
      while true do
         local chunk = yield_chunk()
         if chunk == nil then break end
         count = count + 1
      end
      global_count = count
    end
  )lua"));

  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForBodyChunks);

  { auto _s = coroutine.HandleBody(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };

  luabridge::LuaRef global_count =
      luabridge::getGlobal(state->state(), "global_count");
  ASSERT_TRUE(global_count.isNumber());
  EXPECT_EQ(global_count.cast<int>(), 3);
}

TEST(CoroutineTest, NativeAccessorsYieldForDataAndProvideExpectedValues) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  MockProxyWasmAbi mock_abi;
  EXPECT_CALL(mock_abi, proxy_get_header_map_value(
                            WasmHeaderMapType::RequestHeaders, testing::_,
                            testing::_, testing::_, testing::_))
      .With(testing::Args<1, 2>(WasmStrEq("h")))
      .WillRepeatedly(SetWasmString(std::string_view("val_h")));

  EXPECT_CALL(mock_abi, proxy_get_header_map_value(
                            WasmHeaderMapType::RequestTrailers, testing::_,
                            testing::_, testing::_, testing::_))
      .With(testing::Args<1, 2>(WasmStrEq("t")))
      .WillRepeatedly(SetWasmString(std::string_view("val_t")));

  EXPECT_CALL(mock_abi, proxy_get_buffer_status(WasmBufferType::HttpRequestBody,
                                                testing::_, testing::_))
      .WillRepeatedly(testing::DoAll(testing::SetArgPointee<1>(42),
                                     testing::Return(WasmResult::Ok)));

  EXPECT_OK(lua_state->ExecuteString(R"lua(
    global_status = "unstarted"
    function envoy_on_request(handle)
      global_status = "started"
      local trailers = handle:trailers()
      assert(trailers:get('t') == 'val_t', 'Failed to get trailer')
      local body = handle:body()
      assert(body:length() == 42, 'Failed to get body length')
      local headers = handle:headers()
      assert(headers:get('h') == 'val_h', 'Failed to get header')
      global_status = "completed"
    end
  )lua"));

  ASSERT_OK_AND_ASSIGN(ExecutionState state, coroutine.Start());
  EXPECT_EQ(state, ExecutionState::kYielded);
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForTrailers);

  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleTrailers(5); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };

  luabridge::LuaRef global_status =
      luabridge::getGlobal(lua_state->state(), "global_status");
  EXPECT_EQ(global_status.tostring(), "completed");
}

TEST(CoroutineTest, HandleHeadersWithEndStreamYieldsCorrectly) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> lua_state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread,
                       lua_state->NewThread());
  LuaStreamCoroutine coroutine(*thread, LuaStreamCoroutineMode::kRequest);

  MockProxyWasmAbi mock_abi;

  EXPECT_OK(lua_state->ExecuteString(R"lua(
    global_status = "unstarted"
    function envoy_on_request(handle)
      global_status = "started"
      local trailers = handle:trailers()
      local body = handle:body()
      global_status = "completed"
    end
  )lua"));

  ASSERT_OK_AND_ASSIGN(ExecutionState state, coroutine.Start());
  EXPECT_EQ(state, ExecutionState::kYielded);
  EXPECT_EQ(coroutine.GetYieldReason(),
            LuaStreamCoroutine::YieldReason::kWaitForTrailers);

  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };

  luabridge::LuaRef global_status =
      luabridge::getGlobal(lua_state->state(), "global_status");
  EXPECT_EQ(global_status.tostring(), "completed");
}

TEST(CoroutineTest,
     BodyChunksIteratorYieldsExtantChunksEvenIfStreamIsAlreadyEnded) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        local len = chunk:length()
        chunk_num = chunk_num + 1
      end
      if chunk_num ~= 1 then
         error("failure_" .. tostring(chunk_num))
      end
    end
  )lua"));

  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(100, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(LuaStreamCoroutineTest,
     BodyChunksIteratorYieldsAllExtantChunksIfMultipleBufferedBeforeStart) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        local len = chunk:length()
        chunk_num = chunk_num + 1
      end
      -- No matter how many body events natively fired before Start(),
      -- the entire payload coalesces into a single buffered block for wasm if
      -- fully unread.
      if chunk_num ~= 1 then
         error("failure_" .. tostring(chunk_num))
      end
    end
  )lua"));

  { auto _s = coroutine.HandleHeaders(5, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(100, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(50, false); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.HandleBody(20, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}

TEST(LuaStreamCoroutineTest,
     BodyChunksIteratorYieldsZeroChunksIfStreamEndedByHeaders) {
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState> state, LuaState::Create());
  ASSERT_OK_AND_ASSIGN(std::unique_ptr<LuaState::Thread> thread_ptr,
                       state->NewThread());
  LuaStreamCoroutine coroutine(*thread_ptr, LuaStreamCoroutineMode::kRequest);

  EXPECT_OK(state->ExecuteString(R"lua(
    function envoy_on_request(h)
      local chunk_num = 0
      for chunk in h:bodyChunks() do
        local len = chunk:length()
        chunk_num = chunk_num + 1
      end
      if chunk_num ~= 0 then
         error("failure_" .. tostring(chunk_num))
      end
    end
  )lua"));

  { auto _s = coroutine.HandleHeaders(5, true); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kYielded); };
  { auto _s = coroutine.Start(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ExecutionState::kExited); };
}
}  // namespace
}  // namespace sample::lua
