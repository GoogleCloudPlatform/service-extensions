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

#ifndef NET_TURING_WASM_LUA_STREAM_STATE_INTERFACE_H_
#define NET_TURING_WASM_LUA_STREAM_STATE_INTERFACE_H_

namespace sample::lua {

// Interface abstracting the coroutine functionality from the Lua stream
// filtering layer.
class StreamStateInterface {
 public:
  enum class YieldReason {
    kNone,
    kWaitForHeaders,
    kWaitForBody,
    kWaitForBodyChunks,
    kWaitForTrailers,
    kWaitForHttp,
    kWaitToStart,
    kResponded,
  };

  virtual ~StreamStateInterface() = default;

  // Yields coroutine execution with the specified `reason` and `nresults`
  // return.
  virtual int Yield(YieldReason reason, int nresults) = 0;

  virtual void MarkHeadersPassedOn() = 0;
  [[nodiscard]] virtual bool IsHeadersPassedOn() const = 0;
  [[nodiscard]] virtual bool IsHeadersReceived() const = 0;
  [[nodiscard]] virtual bool IsBodyReceived() const = 0;
  [[nodiscard]] virtual bool IsTrailersReceived() const = 0;
  [[nodiscard]] virtual bool IsStreamEnded() const = 0;
};

}  // namespace sample::lua

#endif  // NET_TURING_WASM_LUA_STREAM_STATE_INTERFACE_H_
