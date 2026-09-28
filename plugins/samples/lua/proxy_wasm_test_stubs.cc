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

#include "proxy_wasm_test_stubs.h"

#include <cstddef>
#include <cstdint>

#include "absl/base/nullability.h"
#include "proxy_wasm_intrinsics.h"

namespace {
sample::lua::MockProxyWasmAbi* absl_nullable current_mock_proxy_wasm_abi =
    nullptr;
}

namespace sample::lua {
MockProxyWasmAbi::MockProxyWasmAbi() { current_mock_proxy_wasm_abi = this; }
MockProxyWasmAbi::~MockProxyWasmAbi() { current_mock_proxy_wasm_abi = nullptr; }
}  // namespace sample::lua

extern "C" {
WasmResult proxy_log(LogLevel level, const char* logMessage,
                     size_t messageSize) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_log(level, logMessage,
                                                  messageSize);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_property(const char* path_ptr, size_t path_size,
                              const char** value_ptr_ptr,
                              size_t* value_size_ptr) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_property(
        path_ptr, path_size, value_ptr_ptr, value_size_ptr);
  }
  return WasmResult::NotFound;
}

WasmResult proxy_send_local_response(
    uint32_t response_code, const char* response_code_details_ptr,
    size_t response_code_details_size, const char* body_ptr, size_t body_size,
    const char* additional_response_header_pairs_ptr,
    size_t additional_response_header_pairs_size, uint32_t grpc_status) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_send_local_response(
        response_code, response_code_details_ptr, response_code_details_size,
        body_ptr, body_size, additional_response_header_pairs_ptr,
        additional_response_header_pairs_size, grpc_status);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_configuration(const char** configuration_ptr,
                                   size_t* configuration_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_configuration(
        configuration_ptr, configuration_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_status(uint32_t* status_code_ptr, const char** message_ptr,
                            size_t* message_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_status(
        status_code_ptr, message_ptr, message_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_log_level(LogLevel* level) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_log_level(level);
  }
  return WasmResult::Ok;
}

WasmResult proxy_set_tick_period_milliseconds(uint32_t millisecond) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_set_tick_period_milliseconds(
        millisecond);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_current_time_nanoseconds(uint64_t* nanoseconds) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_current_time_nanoseconds(
        nanoseconds);
  }
  return WasmResult::Ok;
}

WasmResult proxy_set_property(const char* path_ptr, size_t path_size,
                              const char* value_ptr, size_t value_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_set_property(
        path_ptr, path_size, value_ptr, value_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_continue_stream(WasmStreamType stream_type) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_continue_stream(stream_type);
  }
  return WasmResult::Ok;
}

WasmResult proxy_close_stream(WasmStreamType stream_type) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_close_stream(stream_type);
  }
  return WasmResult::Ok;
}

WasmResult proxy_clear_route_cache() {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_clear_route_cache();
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_shared_data(const char* key_ptr, size_t key_size,
                                 const char** value_ptr, size_t* value_size,
                                 uint32_t* cas) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_shared_data(
        key_ptr, key_size, value_ptr, value_size, cas);
  }
  return WasmResult::Ok;
}

WasmResult proxy_set_shared_data(const char* key_ptr, size_t key_size,
                                 const char* value_ptr, size_t value_size,
                                 uint32_t cas) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_set_shared_data(
        key_ptr, key_size, value_ptr, value_size, cas);
  }
  return WasmResult::Ok;
}

WasmResult proxy_register_shared_queue(const char* queue_name_ptr,
                                       size_t queue_name_size,
                                       uint32_t* token) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_register_shared_queue(
        queue_name_ptr, queue_name_size, token);
  }
  return WasmResult::Ok;
}

WasmResult proxy_resolve_shared_queue(const char* vm_id, size_t vm_id_size,
                                      const char* queue_name_ptr,
                                      size_t queue_name_size, uint32_t* token) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_resolve_shared_queue(
        vm_id, vm_id_size, queue_name_ptr, queue_name_size, token);
  }
  return WasmResult::Ok;
}

WasmResult proxy_dequeue_shared_queue(uint32_t token, const char** data_ptr,
                                      size_t* data_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_dequeue_shared_queue(
        token, data_ptr, data_size);
  }
  return WasmResult::Ok;
}
WasmResult proxy_enqueue_shared_queue(uint32_t token, const char* data_ptr,
                                      size_t data_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_enqueue_shared_queue(
        token, data_ptr, data_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_add_header_map_value(WasmHeaderMapType type,
                                      const char* key_ptr, size_t key_size,
                                      const char* value_ptr,
                                      size_t value_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_add_header_map_value(
        type, key_ptr, key_size, value_ptr, value_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_header_map_value(WasmHeaderMapType type,
                                      const char* key_ptr, size_t key_size,
                                      const char** value_ptr,
                                      size_t* value_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_header_map_value(
        type, key_ptr, key_size, value_ptr, value_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_header_map_pairs(WasmHeaderMapType type, const char** ptr,
                                      size_t* size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_header_map_pairs(type, ptr,
                                                                   size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_set_header_map_pairs(WasmHeaderMapType type, const char* ptr,
                                      size_t size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_set_header_map_pairs(type, ptr,
                                                                   size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_replace_header_map_value(WasmHeaderMapType type,
                                          const char* key_ptr, size_t key_size,
                                          const char* value_ptr,
                                          size_t value_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_replace_header_map_value(
        type, key_ptr, key_size, value_ptr, value_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_remove_header_map_value(WasmHeaderMapType type,
                                         const char* key_ptr, size_t key_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_remove_header_map_value(
        type, key_ptr, key_size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_header_map_size(WasmHeaderMapType type, size_t* size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_header_map_size(type, size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_buffer_bytes(WasmBufferType type, uint32_t start,
                                  uint32_t length, const char** ptr,
                                  size_t* size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_buffer_bytes(
        type, start, length, ptr, size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_buffer_status(WasmBufferType type, size_t* length_ptr,
                                   uint32_t* flags_ptr) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_buffer_status(
        type, length_ptr, flags_ptr);
  }
  return WasmResult::Ok;
}

WasmResult proxy_set_buffer_bytes(WasmBufferType type, uint32_t start,
                                  uint32_t length, const char* ptr,
                                  size_t size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_set_buffer_bytes(
        type, start, length, ptr, size);
  }
  return WasmResult::Ok;
}

WasmResult proxy_http_call(const char* uri_ptr, size_t uri_size,
                           void* header_pairs_ptr, size_t header_pairs_size,
                           const char* body_ptr, size_t body_size,
                           void* trailer_pairs_ptr, size_t trailer_pairs_size,
                           uint32_t timeout_milliseconds, uint32_t* token_ptr) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_http_call(
        uri_ptr, uri_size, header_pairs_ptr, header_pairs_size, body_ptr,
        body_size, trailer_pairs_ptr, trailer_pairs_size, timeout_milliseconds,
        token_ptr);
  }
  return WasmResult::Ok;
}

WasmResult proxy_grpc_call(const char* service_ptr, size_t service_size,
                           const char* service_name_ptr,
                           size_t service_name_size,
                           const char* method_name_ptr, size_t method_name_size,
                           void* initial_metadata_ptr,
                           size_t initial_metadata_size,
                           const char* request_ptr, size_t request_size,
                           uint32_t timeout_milliseconds, uint32_t* token_ptr) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_grpc_call(
        service_ptr, service_size, service_name_ptr, service_name_size,
        method_name_ptr, method_name_size, initial_metadata_ptr,
        initial_metadata_size, request_ptr, request_size, timeout_milliseconds,
        token_ptr);
  }
  return WasmResult::Ok;
}

WasmResult proxy_grpc_stream(const char* service_ptr, size_t service_size,
                             const char* service_name_ptr,
                             size_t service_name_size,
                             const char* method_name_ptr,
                             size_t method_name_size, void* initial_metadata,
                             size_t initial_metadata_size,
                             uint32_t* token_ptr) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_grpc_stream(
        service_ptr, service_size, service_name_ptr, service_name_size,
        method_name_ptr, method_name_size, initial_metadata,
        initial_metadata_size, token_ptr);
  }
  return WasmResult::Ok;
}

WasmResult proxy_grpc_cancel(uint32_t token) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_grpc_cancel(token);
  }
  return WasmResult::Ok;
}

WasmResult proxy_grpc_close(uint32_t token) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_grpc_close(token);
  }
  return WasmResult::Ok;
}

WasmResult proxy_grpc_send(uint32_t token, const char* message_ptr,
                           size_t message_size, uint32_t end_stream) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_grpc_send(
        token, message_ptr, message_size, end_stream);
  }
  return WasmResult::Ok;
}

WasmResult proxy_define_metric(MetricType type, const char* name_ptr,
                               size_t name_size, uint32_t* metric_id) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_define_metric(
        type, name_ptr, name_size, metric_id);
  }
  return WasmResult::Ok;
}

WasmResult proxy_increment_metric(uint32_t metric_id, int64_t offset) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_increment_metric(metric_id,
                                                               offset);
  }
  return WasmResult::Ok;
}

WasmResult proxy_record_metric(uint32_t metric_id, uint64_t value) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_record_metric(metric_id, value);
  }
  return WasmResult::Ok;
}

WasmResult proxy_get_metric(uint32_t metric_id, uint64_t* result) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_get_metric(metric_id, result);
  }
  return WasmResult::Ok;
}

WasmResult proxy_set_effective_context(uint32_t effective_context_id) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_set_effective_context(
        effective_context_id);
  }
  return WasmResult::Ok;
}

WasmResult proxy_done() {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_done();
  }
  return WasmResult::Ok;
}

WasmResult proxy_call_foreign_function(const char* function_name,
                                       size_t function_name_size,
                                       const char* arguments,
                                       size_t arguments_size, char** results,
                                       size_t* results_size) {
  if (current_mock_proxy_wasm_abi) {
    return current_mock_proxy_wasm_abi->proxy_call_foreign_function(
        function_name, function_name_size, arguments, arguments_size, results,
        results_size);
  }
  return WasmResult::Ok;
}
}

extern "C" int __wasi_random_get(unsigned char* buf, unsigned long buf_len) {
  return 0;
}
