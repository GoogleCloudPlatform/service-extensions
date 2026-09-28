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
#include <cstdint>

#include "envoy_lua_api.h"
#include "lua_state.h"
#include "absl/status/status.h"
#include "status_macros.h"
#include "absl/status/statusor.h"
#include "absl/strings/str_cat.h"
#include "LuaBridge/LuaBridge.h"
#include "LuaBridge/detail/LuaRef.h"
#include "LuaBridge/detail/Result.h"
#include "LuaBridge/detail/Stack.h"
#include "proxy_wasm_intrinsics.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace sample::lua {

absl::StatusOr<ExecutionState> LuaStreamCoroutine::Start() {
  if (state_ != ExecutionState::kYielded ||
      yield_reason_ != YieldReason::kWaitToStart) {
    return absl::FailedPreconditionError(
        "Cannot start already started coroutine");
  }

  absl::StatusOr<ExecutionState> status = lua_thread_.ExecuteFunction(
      (mode_ == LuaStreamCoroutineMode::kRequest) ? "envoy_on_request"
                                                  : "envoy_on_response",
      handle_);

  if (!status.ok()) {
    state_ = ExecutionState::kExited;
    return status.status();
  }

  state_ = status.value();

  if (stream_ended_) {
    RETURN_IF_ERROR(RunToCompletion());
  }

  return state_;
}

absl::StatusOr<ExecutionState> LuaStreamCoroutine::Resume(int narg) {
  if (state_ == ExecutionState::kExited) {
    return absl::FailedPreconditionError("Cannot resume exited coroutine");
  }
  yield_reason_ = YieldReason::kNone;
  absl::StatusOr<ExecutionState> result = lua_thread_.Resume(narg);

  if (!result.ok()) {
    state_ = ExecutionState::kExited;
    return result.status();
  }

  state_ = result.value();
  return state_;
}

int LuaStreamCoroutine::Yield(YieldReason reason, int nresults) {
  state_ = ExecutionState::kYielded;
  yield_reason_ = reason;
  return lua_thread_.Yield(nresults);
}

absl::Status LuaStreamCoroutine::RunToCompletion() {
  while (state_ != ExecutionState::kExited) {
    switch (yield_reason_) {
      case YieldReason::kWaitForBodyChunks:
        if (!body_chunk_consumed_ && has_body_data_) {
          if (luabridge::Result result = luabridge::push(
                  lua_thread_.state(),
                  Buffer(mode_ == LuaStreamCoroutineMode::kRequest
                             ? WasmBufferType::HttpRequestBody
                             : WasmBufferType::HttpResponseBody));
              !result) {
            return absl::InternalError(
                absl::StrCat("Failed to push final body chunk to coroutine: ",
                             result.message()));
          }
          body_chunk_consumed_ = true;
        } else {
          if (luabridge::Result result =
                  luabridge::push(lua_thread_.state(), nullptr);
              !result) {
            return absl::InternalError(absl::StrCat(
                "Failed to push nil to coroutine: ", result.message()));
          }
        }
        RETURN_IF_ERROR(Resume(1).status());
        break;

      case YieldReason::kWaitForBody:
        if (luabridge::Result result =
                luabridge::push(lua_thread_.state(),
                                Buffer(mode_ == LuaStreamCoroutineMode::kRequest
                                           ? WasmBufferType::HttpRequestBody
                                           : WasmBufferType::HttpResponseBody));
            !result) {
          return absl::InternalError(absl::StrCat(
              "Failed to push emptybody to coroutine: ", result.message()));
        }
        RETURN_IF_ERROR(Resume(1).status());
        break;

      case YieldReason::kWaitForTrailers: {
        WasmHeaderMapType trailer_type =
            mode_ == LuaStreamCoroutineMode::kRequest
                ? WasmHeaderMapType::RequestTrailers
                : WasmHeaderMapType::ResponseTrailers;
        if (luabridge::Result result =
                luabridge::push(lua_thread_.state(), Header(trailer_type));
            !result) {
          return absl::InternalError(
              absl::StrCat("Failed to push empty trailers to coroutine: ",
                           result.message()));
        }
        RETURN_IF_ERROR(Resume(1).status());
        break;
      }

      case YieldReason::kWaitForHeaders:
      case YieldReason::kWaitForHttp:
      case YieldReason::kWaitToStart:
      case YieldReason::kResponded:
      case YieldReason::kNone:
        return absl::OkStatus();
    }
  }
  return absl::OkStatus();
}

absl::StatusOr<ExecutionState> LuaStreamCoroutine::HandleHeaders(
    uint32_t num_headers, bool end_of_stream) {
  stream_ended_ = end_of_stream;
  received_headers_ = true;

  if (yield_reason_ == YieldReason::kWaitForHeaders) {
    WasmHeaderMapType header_type = mode_ == LuaStreamCoroutineMode::kRequest
                                        ? WasmHeaderMapType::RequestHeaders
                                        : WasmHeaderMapType::ResponseHeaders;
    if (luabridge::Result result =
            luabridge::push(lua_thread_.state(), Header(header_type));
        !result) {
      return absl::InternalError(absl::StrCat(
          "Failed to push headers to coroutine: ", result.message()));
    }
    RETURN_IF_ERROR(Resume(1).status());
  }

  if (stream_ended_) {
    RETURN_IF_ERROR(RunToCompletion());
  }

  return state_;
}

absl::StatusOr<ExecutionState> LuaStreamCoroutine::HandleBody(
    size_t body_buffer_length, bool end_of_stream) {
  if (stream_ended_) {
    return absl::FailedPreconditionError("Cannot handle body on ended stream");
  }
  stream_ended_ = end_of_stream;
  if (body_buffer_length > 0) {
    has_body_data_ = true;
    body_chunk_consumed_ = false;
  }
  if (stream_ended_) {
    received_body_ = true;
  }

  if (state_ == ExecutionState::kExited) {
    return state_;
  }

  if (yield_reason_ == YieldReason::kWaitForBodyChunks ||
      (yield_reason_ == YieldReason::kWaitForBody && stream_ended_)) {
    if (luabridge::Result result =
            luabridge::push(lua_thread_.state(),
                            Buffer(mode_ == LuaStreamCoroutineMode::kRequest
                                       ? WasmBufferType::HttpRequestBody
                                       : WasmBufferType::HttpResponseBody));
        !result) {
      return absl::InternalError(
          absl::StrCat("Failed to push body to coroutine: ", result.message()));
    }

    body_chunk_consumed_ = true;
    RETURN_IF_ERROR(Resume(1).status());
  }

  if (stream_ended_) {
    RETURN_IF_ERROR(RunToCompletion());
  }

  return state_;
}

absl::StatusOr<ExecutionState> LuaStreamCoroutine::HandleTrailers(
    uint32_t num_trailers) {
  if (stream_ended_) {
    return absl::FailedPreconditionError(
        "Cannot handle trailers on ended stream");
  }
  if (!received_headers_) {
    return absl::FailedPreconditionError(
        "Cannot process trailers before stream headers");
  }
  if (received_trailers_) {
    return absl::FailedPreconditionError("Trailers already received");
  }
  received_trailers_ = true;
  stream_ended_ = true;

  if (state_ == ExecutionState::kExited) {
    return state_;
  }

  if (yield_reason_ == YieldReason::kWaitForBody) {
    if (luabridge::Result result =
            luabridge::push(lua_thread_.state(),
                            Buffer(mode_ == LuaStreamCoroutineMode::kRequest
                                       ? WasmBufferType::HttpRequestBody
                                       : WasmBufferType::HttpResponseBody));
        !result) {
      return absl::InternalError(
          absl::StrCat("Failed to push body to coroutine: ", result.message()));
    }
    RETURN_IF_ERROR(Resume(1).status());
  }

  if (yield_reason_ == YieldReason::kWaitForBodyChunks) {
    if (luabridge::Result result =
            luabridge::push(lua_thread_.state(), nullptr);
        !result) {
      return absl::InternalError(
          absl::StrCat("Failed to push nil to coroutine: ", result.message()));
    }
    RETURN_IF_ERROR(Resume(1).status());
  }

  if (yield_reason_ == YieldReason::kWaitForTrailers) {
    WasmHeaderMapType trailer_type = mode_ == LuaStreamCoroutineMode::kRequest
                                         ? WasmHeaderMapType::RequestTrailers
                                         : WasmHeaderMapType::ResponseTrailers;
    if (luabridge::Result result =
            luabridge::push(lua_thread_.state(), Header(trailer_type));
        !result) {
      return absl::InternalError(absl::StrCat(
          "Failed to push trailers to coroutine: ", result.message()));
    }
    RETURN_IF_ERROR(Resume(1).status());
  }

  RETURN_IF_ERROR(RunToCompletion());

  return state_;
}

absl::StatusOr<ExecutionState> LuaStreamCoroutine::HandleHttpResponse(
    uint32_t headers, size_t body_size, uint32_t trailers) {
  return state_;
}

}  // namespace sample::lua
