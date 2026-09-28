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

#include "lua_plugin.h"

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <utility>

#include "coroutine.h"
#include "lua_state.h"
#include "absl/base/casts.h"
#include "absl/base/nullability.h"
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/string_view.h"
#include "proxy_wasm_intrinsics.h"



extern "C" {
// __syscall_dup3 is required by the core Lua runtime. We stub it here to
// satisfy the linker and return -ENOSYS since file descriptor duplication is
// not supported or needed in the Proxy-Wasm sandbox.
int __syscall_dup3(int oldfd, int newfd, int flags) { return -ENOSYS; }
}
namespace sample::lua {

namespace {

uint32_t AbslStatusToHttpStatusCode(const absl::Status& status) {
  if (status.ok()) return 200;
  switch (status.code()) {
    case absl::StatusCode::kInvalidArgument:
    case absl::StatusCode::kFailedPrecondition:
    case absl::StatusCode::kOutOfRange:
      return 400;
    case absl::StatusCode::kUnauthenticated:
      return 401;
    case absl::StatusCode::kPermissionDenied:
      return 403;
    case absl::StatusCode::kNotFound:
      return 404;
    case absl::StatusCode::kAlreadyExists:
      return 409;
    case absl::StatusCode::kResourceExhausted:
      return 429;
    case absl::StatusCode::kUnimplemented:
      return 501;
    case absl::StatusCode::kUnavailable:
      return 503;
    case absl::StatusCode::kDeadlineExceeded:
      return 504;
    case absl::StatusCode::kInternal:
    case absl::StatusCode::kUnknown:
    case absl::StatusCode::kDataLoss:
    case absl::StatusCode::kAborted:
    default:
      return 500;
  }
}

void HandleEventError(const absl::Status& status) {
  uint32_t http_code = AbslStatusToHttpStatusCode(status);
  sendLocalResponse(static_cast<uint32_t>(http_code),
                    /*response_code_details=*/"plugin_error",
                    /*body=*/status.message(),
                    /*additional_response_headers=*/{});
}

FilterHeadersStatus HandleHeadersEvent(
    LuaStreamCoroutine* absl_nullable coroutine, uint32_t num_headers,
    bool end_of_stream) {
  if (!coroutine) {
    HandleEventError(
        absl::InternalError("No coroutine exists to process event"));
    return FilterHeadersStatus::StopIteration;
  }

  absl::StatusOr<ExecutionState> status =
      coroutine->HandleHeaders(num_headers, end_of_stream);
  if (!status.ok()) {
    HandleEventError(status.status());
    return FilterHeadersStatus::StopIteration;
  }

  switch (coroutine->GetYieldReason()) {
    case LuaStreamCoroutine::YieldReason::kWaitForHttp:
    case LuaStreamCoroutine::YieldReason::kWaitForBody:
    case LuaStreamCoroutine::YieldReason::kResponded:
      return FilterHeadersStatus::StopIteration;
    default:
      coroutine->MarkHeadersPassedOn();
      return FilterHeadersStatus::Continue;
  }
}

FilterDataStatus HandleBodyEvent(LuaStreamCoroutine* absl_nullable coroutine,
                                 size_t body_buffer_length,
                                 bool end_of_stream) {
  if (!coroutine) {
    HandleEventError(
        absl::InternalError("No coroutine exists to process event"));
    return FilterDataStatus::StopIterationNoBuffer;
  }

  if (absl::StatusOr<ExecutionState> status =
          coroutine->HandleBody(body_buffer_length, end_of_stream);
      !status.ok()) {
    HandleEventError(status.status());
    return FilterDataStatus::StopIterationNoBuffer;
  }

  switch (coroutine->GetYieldReason()) {
    case LuaStreamCoroutine::YieldReason::kWaitForHttp:
      return FilterDataStatus::StopIterationAndWatermark;
    case LuaStreamCoroutine::YieldReason::kWaitForBody:
      return FilterDataStatus::StopIterationAndBuffer;
    case LuaStreamCoroutine::YieldReason::kResponded:
      return FilterDataStatus::StopIterationNoBuffer;
    default:
      coroutine->MarkHeadersPassedOn();
      return FilterDataStatus::Continue;
  }
}

FilterTrailersStatus HandleTrailersEvent(
    LuaStreamCoroutine* absl_nullable coroutine, uint32_t num_trailers) {
  if (!coroutine) {
    HandleEventError(
        absl::InternalError("No coroutine exists to process event"));
    return FilterTrailersStatus::StopIteration;
  }

  absl::StatusOr<ExecutionState> status =
      coroutine->HandleTrailers(num_trailers);
  if (!status.ok()) {
    HandleEventError(status.status());
    return FilterTrailersStatus::StopIteration;
  }

  switch (coroutine->GetYieldReason()) {
    case LuaStreamCoroutine::YieldReason::kWaitForHttp:
    case LuaStreamCoroutine::YieldReason::kResponded:
      return FilterTrailersStatus::StopIteration;
    default:
      coroutine->MarkHeadersPassedOn();
      return FilterTrailersStatus::Continue;
  }
}

}  // namespace

bool LuaRootContext::onConfigure(size_t cfg_size) {
  absl::StatusOr<std::unique_ptr<LuaState>> new_lua_state = LuaState::Create();
  if (!new_lua_state.ok()) {
    LOG_ERROR(absl::StrCat("[LuaRootContext] onConfigure: ",
                           new_lua_state.status().ToString()));
    return false;
  }

  if (cfg_size > 0) {
    WasmDataPtr config_data =
        getBufferBytes(WasmBufferType::PluginConfiguration, 0, cfg_size);

    if (!config_data || config_data->size() == 0) {
      LOG_ERROR("[LuaRootContext] onConfigure: could not get config data");
      return false;
    }

    if (absl::Status status =
            (*new_lua_state)->ExecuteString(config_data->view());
        !status.ok()) {
      LOG_ERROR(absl::StrCat("[LuaRootContext] onConfigure: lua error -- ",
                             status.ToString()));
      return false;
    }
  }

  lua_state_ = std::move(*new_lua_state);
  return true;
}

LuaHttpContext::LuaHttpContext(uint32_t id, RootContext* root)
    : Context(id, root) {}

void LuaHttpContext::onCreate() {
  LuaState* lua_state = GetRootLuaState();
  if (!lua_state) {
    LOG_ERROR(
        absl::StrCat("[LuaHttpContext] onCreate: root Lua state is null"));
    return;
  }

  absl::StatusOr<std::unique_ptr<LuaState::Thread>> request_thread =
      lua_state->NewThread();
  if (!request_thread.ok()) {
    LOG_ERROR(
        absl::StrCat("[LuaHttpContext] onCreate: thread creation failed -- ",
                     request_thread.status().ToString()));
  } else {
    lua_request_thread_ = std::move(*request_thread);
    request_coroutine_ = std::make_unique<LuaStreamCoroutine>(
        *lua_request_thread_, LuaStreamCoroutineMode::kRequest);
  }

  absl::StatusOr<std::unique_ptr<LuaState::Thread>> response_thread =
      lua_state->NewThread();
  if (!response_thread.ok()) {
    LOG_ERROR(
        absl::StrCat("[LuaHttpContext] onCreate: thread creation failed -- ",
                     response_thread.status().ToString()));
  } else {
    lua_response_thread_ = std::move(*response_thread);
    response_coroutine_ = std::make_unique<LuaStreamCoroutine>(
        *lua_response_thread_, LuaStreamCoroutineMode::kResponse);
  }
}

FilterHeadersStatus LuaHttpContext::onRequestHeaders(uint32_t num_headers,
                                                     bool end_of_stream) {
  if (!request_coroutine_) {
    HandleEventError(
        absl::InternalError("No coroutine exists to process event"));
    return FilterHeadersStatus::StopIteration;
  }

  if (absl::StatusOr<ExecutionState> status = request_coroutine_->Start();
      !status.ok()) {
    LOG_ERROR(
        absl::StrCat("[LuaHttpContext] Failed to start request coroutine: ",
                     status.status().ToString()));
    return FilterHeadersStatus::StopIteration;
  }
  return HandleHeadersEvent(request_coroutine_.get(), num_headers,
                            end_of_stream);
}

FilterDataStatus LuaHttpContext::onRequestBody(size_t body_buffer_length,
                                               bool end_of_stream) {
  return HandleBodyEvent(request_coroutine_.get(), body_buffer_length,
                         end_of_stream);
}

FilterTrailersStatus LuaHttpContext::onRequestTrailers(uint32_t num_trailers) {
  return HandleTrailersEvent(request_coroutine_.get(), num_trailers);
}

FilterHeadersStatus LuaHttpContext::onResponseHeaders(uint32_t num_headers,
                                                      bool end_of_stream) {
  if (!response_coroutine_) {
    HandleEventError(
        absl::InternalError("No coroutine exists to process event"));
    return FilterHeadersStatus::StopIteration;
  }

  if (absl::StatusOr<ExecutionState> status = response_coroutine_->Start();
      !status.ok()) {
    LOG_ERROR(
        absl::StrCat("[LuaHttpContext] Failed to start response coroutine: ",
                     status.status().ToString()));
    return FilterHeadersStatus::StopIteration;
  }
  return HandleHeadersEvent(response_coroutine_.get(), num_headers,
                            end_of_stream);
}

FilterDataStatus LuaHttpContext::onResponseBody(size_t body_buffer_length,
                                                bool end_of_stream) {
  return HandleBodyEvent(response_coroutine_.get(), body_buffer_length,
                         end_of_stream);
}

FilterTrailersStatus LuaHttpContext::onResponseTrailers(uint32_t num_trailers) {
  return HandleTrailersEvent(response_coroutine_.get(), num_trailers);
}

LuaState* LuaHttpContext::GetRootLuaState() {
  LuaRootContext* lua_root = static_cast<LuaRootContext*>(this->root());
  if (!lua_root) {
    return nullptr;
  }
  return lua_root->lua_state_.get();
}

}  // namespace sample::lua
