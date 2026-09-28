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

#ifndef NET_TURING_WASM_LUA_COROUTINE_H_
#define NET_TURING_WASM_LUA_COROUTINE_H_

#include <cstddef>
#include <cstdint>

#include "envoy_lua_api.h"
#include "lua_state.h"
#include "stream_state_interface.h"
#include "absl/status/status.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace sample::lua {

enum class LuaStreamCoroutineMode { kRequest, kResponse };

// Manages the execution lifecycle of a Lua coroutine bound to an HTTP stream
// (request or response flow). Handles starting, resuming, yielding, and state
// transitions during stream filtering.
class LuaStreamCoroutine final : public StreamStateInterface {
 public:
  explicit LuaStreamCoroutine(LuaState::Thread& thread,
                              LuaStreamCoroutineMode mode)
      : mode_(mode),
        state_(ExecutionState::kYielded),
        yield_reason_(YieldReason::kWaitToStart),
        lua_thread_(thread),
        handle_(*this,
                Handle::Options{
                    .is_request = (mode == LuaStreamCoroutineMode::kRequest)}) {
  }

  LuaStreamCoroutine(const LuaStreamCoroutine&) = delete;
  LuaStreamCoroutine& operator=(const LuaStreamCoroutine&) = delete;
  LuaStreamCoroutine(LuaStreamCoroutine&&) noexcept = delete;
  LuaStreamCoroutine& operator=(LuaStreamCoroutine&&) noexcept = delete;
  ~LuaStreamCoroutine() override = default;

  // Starts the coroutine by executing the corresponding Lua entry point
  // (`envoy_on_request` or `envoy_on_response`).
  absl::StatusOr<ExecutionState> Start();

  // Resumes execution of a yielded coroutine, passing `narg` arguments on
  // stack.
  absl::StatusOr<ExecutionState> Resume(int narg = 0);

  // Yields coroutine execution with the specified `reason` and `nresults`
  // return.
  int Yield(YieldReason reason, int nresults) override;

  void MarkHeadersPassedOn() override { headers_passed_on_ = true; }
  [[nodiscard]] bool IsHeadersPassedOn() const override {
    return headers_passed_on_;
  }
  [[nodiscard]] bool IsHeadersReceived() const override {
    return received_headers_;
  }
  [[nodiscard]] bool IsBodyReceived() const override { return received_body_; }
  [[nodiscard]] bool IsTrailersReceived() const override {
    return received_trailers_;
  }
  [[nodiscard]] bool IsStreamEnded() const override { return stream_ended_; }

  // Processes request or response headers.
  absl::StatusOr<ExecutionState> HandleHeaders(uint32_t num_headers,
                                               bool end_of_stream);

  // Processes request or response body data.
  absl::StatusOr<ExecutionState> HandleBody(size_t body_buffer_length,
                                            bool end_of_stream);

  // Processes request or response trailers.
  absl::StatusOr<ExecutionState> HandleTrailers(uint32_t num_trailers);

  absl::StatusOr<ExecutionState> HandleHttpResponse(uint32_t headers,
                                                    size_t body_size,
                                                    uint32_t trailers);

  [[nodiscard]] LuaStreamCoroutineMode GetLuaStreamCoroutineMode() const {
    return mode_;
  }
  [[nodiscard]] ExecutionState GetState() const { return state_; }
  [[nodiscard]] YieldReason GetYieldReason() const { return yield_reason_; }

 private:
  absl::Status RunToCompletion();

  LuaStreamCoroutineMode mode_ = LuaStreamCoroutineMode::kRequest;

  ExecutionState state_ = ExecutionState::kYielded;
  YieldReason yield_reason_ = YieldReason::kWaitToStart;

  LuaState::Thread& lua_thread_;
  Handle handle_;

  bool headers_passed_on_ = false;
  bool received_headers_ = false;
  bool received_body_ = false;
  bool has_body_data_ = false;
  bool body_chunk_consumed_ = false;
  bool received_trailers_ = false;

  // Used to keep track of the stream ending on a headers-only or no-trailers
  // request/response so that we don't yield expecting body/trailers.
  bool stream_ended_ = false;
};

}  // namespace sample::lua
#endif  // NET_TURING_WASM_LUA_COROUTINE_H_
