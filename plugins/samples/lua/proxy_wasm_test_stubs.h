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

#ifndef NET_TURING_WASM_LUA_PROXY_WASM_TEST_STUBS_H_
#define NET_TURING_WASM_LUA_PROXY_WASM_TEST_STUBS_H_

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>

#include "stream_state_interface.h"
#include "gmock/gmock.h"
#include "absl/strings/match.h"
#include "proxy_wasm_intrinsics.h"

namespace sample::lua {

class MockStreamState : public StreamStateInterface {
 public:
  MOCK_METHOD(int, Yield, (YieldReason, int), (override));
  MOCK_METHOD(void, MarkHeadersPassedOn, (), (override));
  MOCK_METHOD(bool, IsHeadersPassedOn, (), (const, override));
  MOCK_METHOD(bool, IsHeadersReceived, (), (const, override));
  MOCK_METHOD(bool, IsBodyReceived, (), (const, override));
  MOCK_METHOD(bool, IsTrailersReceived, (), (const, override));
  MOCK_METHOD(bool, IsStreamEnded, (), (const, override));
};

// Mock implementation of the Proxy-Wasm ABI.
// Used to set expectations on how the Proxy-Wasm SDK calls ABI functions during
// testing.
class MockProxyWasmAbi {
 public:
  MockProxyWasmAbi();
  ~MockProxyWasmAbi();

  // Mock is dynamically injected singleton; do not copy/move.
  MockProxyWasmAbi(const MockProxyWasmAbi&) = delete;
  MockProxyWasmAbi& operator=(const MockProxyWasmAbi&) = delete;
  MockProxyWasmAbi(MockProxyWasmAbi&&) = delete;
  MockProxyWasmAbi& operator=(MockProxyWasmAbi&&) = delete;

  MOCK_METHOD(WasmResult, proxy_log, (LogLevel, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_get_property,
              (const char*, size_t, const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_send_local_response,
              (uint32_t, const char*, size_t, const char*, size_t, const char*,
               size_t, uint32_t));
  MOCK_METHOD(WasmResult, proxy_get_configuration, (const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_get_status, (uint32_t*, const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_get_log_level, (LogLevel*));
  MOCK_METHOD(WasmResult, proxy_set_tick_period_milliseconds, (uint32_t));
  MOCK_METHOD(WasmResult, proxy_get_current_time_nanoseconds, (uint64_t*));
  MOCK_METHOD(WasmResult, proxy_set_property,
              (const char*, size_t, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_continue_stream, (WasmStreamType));
  MOCK_METHOD(WasmResult, proxy_close_stream, (WasmStreamType));
  MOCK_METHOD(WasmResult, proxy_clear_route_cache, ());
  MOCK_METHOD(WasmResult, proxy_get_shared_data,
              (const char*, size_t, const char**, size_t*, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_set_shared_data,
              (const char*, size_t, const char*, size_t, uint32_t));
  MOCK_METHOD(WasmResult, proxy_register_shared_queue,
              (const char*, size_t, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_resolve_shared_queue,
              (const char*, size_t, const char*, size_t, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_dequeue_shared_queue,
              (uint32_t, const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_enqueue_shared_queue,
              (uint32_t, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_add_header_map_value,
              (WasmHeaderMapType, const char*, size_t, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_get_header_map_value,
              (WasmHeaderMapType, const char*, size_t, const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_get_header_map_pairs,
              (WasmHeaderMapType, const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_set_header_map_pairs,
              (WasmHeaderMapType, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_replace_header_map_value,
              (WasmHeaderMapType, const char*, size_t, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_remove_header_map_value,
              (WasmHeaderMapType, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_get_header_map_size,
              (WasmHeaderMapType, size_t*));
  MOCK_METHOD(WasmResult, proxy_get_buffer_bytes,
              (WasmBufferType, uint32_t, uint32_t, const char**, size_t*));
  MOCK_METHOD(WasmResult, proxy_get_buffer_status,
              (WasmBufferType, size_t*, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_set_buffer_bytes,
              (WasmBufferType, uint32_t, uint32_t, const char*, size_t));
  MOCK_METHOD(WasmResult, proxy_http_call,
              (const char*, size_t, void*, size_t, const char*, size_t, void*,
               size_t, uint32_t, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_grpc_call,
              (const char*, size_t, const char*, size_t, const char*, size_t,
               void*, size_t, const char*, size_t, uint32_t, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_grpc_stream,
              (const char*, size_t, const char*, size_t, const char*, size_t,
               void*, size_t, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_grpc_cancel, (uint32_t));
  MOCK_METHOD(WasmResult, proxy_grpc_close, (uint32_t));
  MOCK_METHOD(WasmResult, proxy_grpc_send,
              (uint32_t, const char*, size_t, uint32_t));
  MOCK_METHOD(WasmResult, proxy_define_metric,
              (MetricType, const char*, size_t, uint32_t*));
  MOCK_METHOD(WasmResult, proxy_increment_metric, (uint32_t, int64_t));
  MOCK_METHOD(WasmResult, proxy_record_metric, (uint32_t, uint64_t));
  MOCK_METHOD(WasmResult, proxy_get_metric, (uint32_t, uint64_t*));
  MOCK_METHOD(WasmResult, proxy_set_effective_context, (uint32_t));
  MOCK_METHOD(WasmResult, proxy_done, ());
  MOCK_METHOD(WasmResult, proxy_call_foreign_function,
              (const char*, size_t, const char*, size_t, char**, size_t*));
};

// Populates value_ptr and value_size out-parameters of the
// proxy_get_header_map_value mock hostcall
ACTION_P(SetWasmString, value) {
  const char** out_data = arg3;
  size_t* out_size = arg4;
  char* p = static_cast<char*>(std::malloc(value.size()));
  std::memcpy(p, value.data(), value.size());
  *out_data = p;
  *out_size = value.size();
  return WasmResult::Ok;
}

// Populates pairs_ptr and pairs_size out-parameters of the
// proxy_get_header_map_pairs mock hostcall
ACTION_P(SetWasmPairs, bytes_str) {
  const char** out_data = arg1;
  size_t* out_size = arg2;
  char* p = static_cast<char*>(std::malloc(bytes_str.size()));
  std::memcpy(p, bytes_str.data(), bytes_str.size());
  *out_data = p;
  *out_size = bytes_str.size();
  return WasmResult::Ok;
}

// Populates value_ptr and value_size out-parameters of the
// proxy_get_property mock hostcall
ACTION_P(SetWasmProperty, value) {
  const char** out_data = arg2;
  size_t* out_size = arg3;
  if (value.empty()) {
    *out_data = nullptr;
    *out_size = 0;
  } else {
    char* p = static_cast<char*>(malloc(value.size()));
    memcpy(p, value.data(), value.size());
    *out_data = p;
    *out_size = value.size();
  }
  return WasmResult::Ok;
}

// Populates ptr and size out-parameters of the
// proxy_get_buffer_bytes mock hostcall
ACTION_P(SetWasmBufferBytes, string_data) {
  std::string s(string_data);
  if (s.empty()) {
    *arg3 = nullptr;
    *arg4 = 0;
  } else {
    *arg3 = ::strdup(s.c_str());
    *arg4 = s.length();
  }
  return WasmResult::Ok;
}

// Expects a tuple of (char*, size_t) as its argument.
MATCHER_P(WasmStrEq, expected_str, "") {
  return std::string_view(std::get<0>(arg), std::get<1>(arg)) == expected_str;
}

MATCHER_P(WasmHasSubstr, expected_substr, "") {
  return absl::StrContains(std::string_view(std::get<0>(arg), std::get<1>(arg)),
                           expected_substr);
}

}  // namespace sample::lua

#endif  // NET_TURING_WASM_LUA_PROXY_WASM_TEST_STUBS_H_
