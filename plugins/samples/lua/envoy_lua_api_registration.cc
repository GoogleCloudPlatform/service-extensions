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

#include "envoy_lua_api_registration.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "envoy_lua_api.h"
#include "envoy_lua_api_shims.h"
#include "lua_state.h"
#include "stream_state_interface.h"
#include "absl/container/flat_hash_map.h"
#include "absl/status/status.h"
#include "status_macros.h"
#include "absl/status/statusor.h"
#include "absl/strings/str_format.h"
#include "absl/strings/string_view.h"
#include "LuaBridge/LuaBridge.h"
#include "LuaBridge/detail/LuaRef.h"
#include "LuaBridge/detail/Namespace.h"
#include "LuaBridge/detail/Result.h"
#include "LuaBridge/detail/Stack.h"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace sample::lua {

namespace {

template <typename T, typename PushType>
bool PushOrStringifyError(lua_State* state, absl::StatusOr<T> status_or,
                          PushType pusher) {
  if (status_or.ok()) {
    return pusher(state, *status_or);
  }
  lua_pushstring(state, status_or.status().ToString().c_str());
  return false;
}

}  // namespace

template <typename T>
void RegisterStatusOr(LuaState& state, absl::string_view name) {
  luabridge::getGlobalNamespace(state.state())
      .beginClass<absl::StatusOr<T>>(std::string(name).c_str())
      .addProperty("is_status_node",
                   [](const absl::StatusOr<T>*) { return true; })
      .addProperty("has_value", &absl::StatusOr<T>::ok)
      .addFunction("ok", &absl::StatusOr<T>::ok)
      .addFunction("message",
                   [](const absl::StatusOr<T>& s) {
                     return std::string(s.status().message());
                   })
      .addFunction(
          "value",
          [](const absl::StatusOr<T>* s, lua_State* state) -> T {
            if (!s->ok()) {
              luaL_error(
                  state, "Attempt to get value() from an error absl::StatusOr: %s",
                  std::string(s->status().message()).c_str());
            }
            return **s;
          })
      .endClass();
}
template void RegisterStatusOr<std::string>(LuaState& state,
                                            absl::string_view name);
template void RegisterStatusOr<int>(LuaState& state, absl::string_view name);
template void RegisterStatusOr<int*>(LuaState& state, absl::string_view name);

namespace {

// Helper to easily bind C-closures into the metatable.
void InjectClosure(lua_State* state, absl::string_view name,
                   lua_CFunction closure) {
  lua_pushlstring(state, name.data(), name.size());
  lua_pushcfunction(state, closure);
  lua_rawset(state, -3);
}

// Injects pure C-closures for native yielding accessors (body, headers,
// trailers) into the Handle class metatable. This bypasses LuaBridge's static
// method wrappers which prevent returning the lua_yield() status code natively.
absl::Status InjectNativeYieldAccessors(lua_State* state) {
  class FakeState : public StreamStateInterface {
   public:
    int Yield(YieldReason, int) override { return 0; }
    bool IsHeadersReceived() const override { return true; }
    bool IsBodyReceived() const override { return true; }
    bool IsTrailersReceived() const override { return true; }
    void MarkHeadersPassedOn() override {}
    bool IsHeadersPassedOn() const override { return true; }
    bool IsStreamEnded() const override { return true; }
  };

  // Push a fake instance so LuaBridge attaches the Handle metatable.
  FakeState fake_state;
  Handle fake_handle(fake_state);
  (void)luabridge::push(state, &fake_handle);

  if (!lua_getmetatable(state, -1)) {
    lua_pop(state, 1);  // pop fake_handle
    return absl::InternalError(
        "Failed to get metatable for Handle in LuaBridge");
  }

  InjectClosure(state, "body", [](lua_State* state) -> int {
    luabridge::TypeResult<Handle*> handle_res =
        luabridge::Stack<Handle*>::get(state, 1);
    if (!handle_res) return luaL_error(state, "expected Handle");
    Handle* handle = *handle_res;
    if (!handle->GetStreamState().IsBodyReceived()) {
      return handle->GetStreamState().Yield(
          StreamStateInterface::YieldReason::kWaitForBody, 0);
    }
    if (PushOrStringifyError(state, handle->GetBody(),
                             [](lua_State* s, Buffer& b) {
                               (void)luabridge::push(s, b);
                               return true;
                             })) {
      return 1;
    }
    return lua_error(state);
  });

  InjectClosure(state, "headers", [](lua_State* state) -> int {
    luabridge::TypeResult<Handle*> handle_res =
        luabridge::Stack<Handle*>::get(state, 1);
    if (!handle_res) return luaL_error(state, "expected Handle");
    Handle* handle = *handle_res;
    if (!handle->GetStreamState().IsHeadersReceived()) {
      return handle->GetStreamState().Yield(
          StreamStateInterface::YieldReason::kWaitForHeaders, 0);
    }
    if (PushOrStringifyError(state, handle->GetHeaders(),
                             [](lua_State* s, Header& h) {
                               (void)luabridge::push(s, h);
                               return true;
                             })) {
      return 1;
    }
    return lua_error(state);
  });

  InjectClosure(state, "trailers", [](lua_State* state) -> int {
    luabridge::TypeResult<Handle*> handle_res =
        luabridge::Stack<Handle*>::get(state, 1);
    if (!handle_res) return luaL_error(state, "expected Handle");
    Handle* handle = *handle_res;
    if (!handle->GetStreamState().IsTrailersReceived()) {
      return handle->GetStreamState().Yield(
          StreamStateInterface::YieldReason::kWaitForTrailers, 0);
    }
    if (PushOrStringifyError(state, handle->GetTrailers(),
                             [](lua_State* s, Header& h) {
                               (void)luabridge::push(s, h);
                               return true;
                             })) {
      return 1;
    }
    return lua_error(state);
  });

  InjectClosure(state, "bodyChunks", [](lua_State* state) -> int {
    luabridge::TypeResult<Handle*> handle_res =
        luabridge::Stack<Handle*>::get(state, 1);
    if (!handle_res) return luaL_error(state, "expected Handle");

    lua_pushcfunction(state, [](lua_State* iter_state) -> int {
      luabridge::TypeResult<Handle*> iter_handle_res =
          luabridge::Stack<Handle*>::get(iter_state, 1);
      if (!iter_handle_res) return luaL_error(iter_state, "expected Handle");
      Handle* internal_handle = *iter_handle_res;

      return internal_handle->GetStreamState().Yield(
          StreamStateInterface::YieldReason::kWaitForBodyChunks, 0);
    });

    lua_pushvalue(state, 1);

    // We wrap this because the generic `for` loop expects a Lua closure to
    // yield, not a C function.
    if (luaL_loadstring(state,
                        "local cfunc, handle = ...; return function() return "
                        "cfunc(handle) end, nil, nil") != 0) {
      return lua_error(state);
    }
    lua_insert(state, -3);
    lua_call(state, 2, 3);
    return 3;
  });

  lua_pop(state, 1);  // pop metatable
  lua_pop(state, 1);  // pop fake_handle

  return absl::OkStatus();
}

}  // namespace

absl::Status RegisterEnvoyApi(LuaState& state) {
  luabridge::getGlobalNamespace(state.state())
      .beginClass<Header>("Header")
      .addFunction("add", &Header::Add)
      .addFunction("remove", &Header::Remove)
      .addFunction("replace", &Header::Replace)
      .addFunction("setHttp1ReasonPhrase", &Header::SetHttp1ReasonPhrase)
      .addFunction("get", &Header::Get)
      .addFunction("getAtIndex", &Header::GetAtIndex)
      .addFunction("getNumValues", &Header::GetNumValues)
      .addFunction("get_pairs", &Header::GetPairs)
      .addFunction(
          "__pairs",
          [](Header* header, lua_State* state) -> luabridge::LuaRef {
            if (luabridge::Result result =
                    luabridge::push(state, header->GetPairs());
                !result) {
              luaL_error(state, "Failed to push headers: %s",
                         result.message().c_str());
              return luabridge::LuaRef(state);
            }
            lua_pushinteger(state, 0);

            // We construct and return a raw Lua C-closure to act as a stateful
            // iterator for Lua's `for k, v in pairs(headers) do` loops. The
            // closure encapsulates all iteration progress by relying on two
            // captured upvalues: upvalue 1: The full table of headers
            // (extracted array). upvalue 2: The current iteration index. Since
            // we return this custom self-contained generator, `pairs()`
            // flawlessly invokes it automatically ignoring the table and
            // start_key bounds it normally passes.
            lua_pushcclosure(
                state,
                [](lua_State* iter_state) -> int {
                  int idx = lua_tointeger(iter_state, lua_upvalueindex(2)) + 1;
                  lua_pushinteger(iter_state, idx);
                  lua_copy(iter_state, -1, lua_upvalueindex(2));
                  lua_pop(iter_state, 1);

                  lua_pushinteger(iter_state, idx);
                  lua_gettable(iter_state, lua_upvalueindex(1));

                  if (lua_isnil(iter_state, -1)) return 0;

                  lua_pushinteger(iter_state, 1);
                  lua_gettable(iter_state, -2);

                  lua_pushinteger(iter_state, 2);
                  lua_gettable(iter_state, -3);

                  return 2;
                },
                /*nup=*/2);

            luabridge::LuaRef iter_func =
                luabridge::LuaRef::fromStack(state, -1);
            lua_pop(state, 1);
            return iter_func;
          })
      .endClass()
      .beginClass<ParsedName>("ParsedName")
      .addFunction("commonName", &ParsedName::GetCommonName)
      .addFunction("organizationName", &ParsedName::GetOrganizationName)
      .endClass()
      .beginClass<SslConnection>("SslConnection")
      .addFunction("peerCertificatePresented",
                   &SslConnection::PeerCertificatePresented)
      .addFunction("peerCertificateValidated",
                   &SslConnection::PeerCertificateValidated)
      .addFunction("uriSanLocalCertificate",
                   &SslConnection::GetUriSanLocalCertificate)
      .addFunction("sha256PeerCertificateDigest",
                   &SslConnection::GetSha256PeerCertificateDigest)
      .addFunction("serialNumberPeerCertificate",
                   &SslConnection::GetSerialNumberPeerCertificate)
      .addFunction("issuerPeerCertificate",
                   &SslConnection::GetIssuerPeerCertificate)
      .addFunction("sha256PeerCertificateIssuerDigest",
                   &SslConnection::GetSha256PeerCertificateIssuerDigest)
      .addFunction("serialNumberPeerCertificateIssuer",
                   &SslConnection::GetSerialNumberPeerCertificateIssuer)
      .addFunction("subjectPeerCertificate",
                   &SslConnection::GetSubjectPeerCertificate)
      .addFunction("parsedSubjectPeerCertificate",
                   &SslConnection::GetParsedSubjectPeerCertificate)
      .addFunction("uriSanPeerCertificate",
                   &SslConnection::GetUriSanPeerCertificate)
      .addFunction("subjectLocalCertificate",
                   &SslConnection::GetSubjectLocalCertificate)
      .addFunction("urlEncodedPemEncodedPeerCertificate",
                   &SslConnection::GetUrlEncodedPemEncodedPeerCertificate)
      .addFunction("urlEncodedPemEncodedPeerCertificateChain",
                   &SslConnection::GetUrlEncodedPemEncodedPeerCertificateChain)
      .addFunction("dnsSansPeerCertificate",
                   &SslConnection::GetDnsSansPeerCertificate)
      .addFunction("dnsSansLocalCertificate",
                   &SslConnection::GetDnsSansLocalCertificate)
      .addFunction("oidsPeerCertificate",
                   &SslConnection::GetOidsPeerCertificate)
      .addFunction("oidsLocalCertificate",
                   &SslConnection::GetOidsLocalCertificate)
      .addFunction("validFromPeerCertificate",
                   &SslConnection::GetValidFromPeerCertificate)
      .addFunction("expirationPeerCertificate",
                   &SslConnection::GetExpirationPeerCertificate)
      .addFunction("sessionId", &SslConnection::GetSessionId)
      .addFunction("ciphersuiteId", &SslConnection::GetCiphersuiteId)
      .addFunction("ciphersuiteString", &SslConnection::GetCiphersuiteString)
      .addFunction("tlsVersion", &SslConnection::GetTlsVersion)
      .addFunction("logTrace", &SslConnection::LogTrace)
      .addFunction("logDebug", &SslConnection::LogDebug)
      .addFunction("logInfo", &SslConnection::LogInfo)
      .addFunction("logWarn", &SslConnection::LogWarn)
      .addFunction("logErr", &SslConnection::LogErr)
      .addFunction("logCritical", &SslConnection::LogCritical)
      .endClass()
      .beginClass<StreamInfo>("StreamInfo")
      .addFunction("downstreamSslConnection",
                   &StreamInfo::GetDownstreamSslConnection)
      .addFunction("logTrace", &StreamInfo::LogTrace)
      .addFunction("logDebug", &StreamInfo::LogDebug)
      .addFunction("logInfo", &StreamInfo::LogInfo)
      .addFunction("logWarn", &StreamInfo::LogWarn)
      .addFunction("logErr", &StreamInfo::LogErr)
      .addFunction("logCritical", &StreamInfo::LogCritical)
      .endClass()
      .beginClass<Connection>("Connection")
      .addFunction("ssl", &Connection::GetSsl)
      .addFunction("logTrace", &Connection::LogTrace)
      .addFunction("logDebug", &Connection::LogDebug)
      .addFunction("logInfo", &Connection::LogInfo)
      .addFunction("logWarn", &Connection::LogWarn)
      .addFunction("logErr", &Connection::LogErr)
      .addFunction("logCritical", &Connection::LogCritical)
      .endClass()
      .beginClass<Buffer>("Buffer")
      .addFunction("length", &Buffer::GetLength)
      .addFunction("getBytes", &Buffer::GetBytes)
      .addFunction("setBytes", &Buffer::SetBytes)
      .addFunction("logTrace", &Buffer::LogTrace)
      .addFunction("logDebug", &Buffer::LogDebug)
      .addFunction("logInfo", &Buffer::LogInfo)
      .addFunction("logWarn", &Buffer::LogWarn)
      .addFunction("logErr", &Buffer::LogErr)
      .addFunction("logCritical", &Buffer::LogCritical)
      .endClass()
      .beginClass<Counter>("Counter")
      .addFunction("inc", &Counter::Inc)
      .addFunction("add", &Counter::Add)
      .addFunction("value", &Counter::GetValue)
      .endClass()
      .beginClass<Gauge>("Gauge")
      .addFunction("inc", &Gauge::Inc)
      .addFunction("dec", &Gauge::Dec)
      .addFunction("add", &Gauge::Add)
      .addFunction("sub", &Gauge::Sub)
      .addFunction("set", &Gauge::Set)
      .addFunction("value", &Gauge::GetValue)
      .endClass()
      .beginClass<Histogram>("Histogram")
      .addFunction("recordValue", &Histogram::RecordValue)
      .endClass()
      .beginClass<Handle>("Handle")
      .addFunction("streamInfo", &Handle::GetStreamInfo)
      .addFunction("connection", &Handle::GetConnection)
      .addFunction("logTrace", &Handle::LogTrace)
      .addFunction("logDebug", &Handle::LogDebug)
      .addFunction("logInfo", &Handle::LogInfo)
      .addFunction("logWarn", &Handle::LogWarn)
      .addFunction("logErr", &Handle::LogErr)
      .addFunction("logCritical", &Handle::LogCritical)
      .endClass();

  luabridge::getGlobalNamespace(state.state())
      .beginClass<absl::Status>("absl_Status")
      .addProperty("is_status_node", [](const absl::Status*) { return true; })
      .addProperty("has_value", [](const absl::Status*) { return false; })
      .addFunction("ok", &absl::Status::ok)
      .addFunction(
          "message",
          [](const absl::Status& s) { return std::string(s.message()); })
      .endClass();

  RegisterStatusOr<BodyIterator>(state, "StatusOr_BodyIterator");
  RegisterStatusOr<bool>(state, "StatusOr_bool");
  RegisterStatusOr<Buffer>(state, "StatusOr_Buffer");
  RegisterStatusOr<Connection>(state, "StatusOr_Connection");
  RegisterStatusOr<ConnectionStreamInfo>(state,
                                         "StatusOr_ConnectionStreamInfo");
  RegisterStatusOr<Counter>(state, "StatusOr_Counter");
  RegisterStatusOr<DynamicMetadata>(state, "StatusOr_DynamicMetadata");
  RegisterStatusOr<ExecutionState>(state, "StatusOr_ExecutionState");
  RegisterStatusOr<FilterState>(state, "StatusOr_FilterState");
  RegisterStatusOr<Gauge>(state, "StatusOr_Gauge");
  RegisterStatusOr<Header>(state, "StatusOr_Header");
  RegisterStatusOr<Histogram>(state, "StatusOr_Histogram");
  RegisterStatusOr<HttpCallResult>(state, "StatusOr_HttpCallResult");
  RegisterStatusOr<int>(state, "StatusOr_int");
  RegisterStatusOr<int64_t>(state, "StatusOr_int64_t");
  RegisterStatusOr<Metadata>(state, "StatusOr_Metadata");
  RegisterStatusOr<PublicKey>(state, "StatusOr_PublicKey");
  RegisterStatusOr<Route>(state, "StatusOr_Route");
  RegisterStatusOr<size_t>(state, "StatusOr_size_t");
  RegisterStatusOr<StatsScope>(state, "StatusOr_StatsScope");
  RegisterStatusOr<std::string>(state, "StatusOr_string");
  RegisterStatusOr<StreamInfo>(state, "StatusOr_StreamInfo");
  RegisterStatusOr<uint64_t>(state, "StatusOr_uint64_t");
  RegisterStatusOr<VerifySignatureResult>(state,
                                          "StatusOr_VerifySignatureResult");
  RegisterStatusOr<VirtualHost>(state, "StatusOr_VirtualHost");
  RegisterStatusOr<absl::flat_hash_map<std::string, std::string>>(
      state, "StatusOr_flat_hash_map_string_string");
  RegisterStatusOr<std::optional<ParsedName>>(state,
                                              "StatusOr_optional_ParsedName");
  RegisterStatusOr<std::optional<SslConnection>>(
      state, "StatusOr_optional_SslConnection");
  RegisterStatusOr<std::optional<std::string>>(state,
                                               "StatusOr_optional_string");
  RegisterStatusOr<std::vector<std::pair<std::string, std::string>>>(
      state, "StatusOr_vector_pair_string_string");
  RegisterStatusOr<std::vector<std::string>>(state, "StatusOr_vector_string");

  RETURN_IF_ERROR(InjectNativeYieldAccessors(state.state()));
  RETURN_IF_ERROR(state.ExecuteString(kLua51CompatShims));

  {
    ScopedGlobalFunction scoped_raw_meta(
        state, "__raw_getmetatable",
        static_cast<lua_CFunction>([](lua_State* state) -> int {
          luaL_checkany(state, 1);
          if (lua_getmetatable(state, 1)) return 1;
          lua_pushnil(state);
          return 1;
        }));

    RETURN_IF_ERROR(state.ExecuteString(kStatusUnwrapperFunctionShim));

    constexpr std::array<absl::string_view, 12> unwrapper_classes = {
        "Handle", "StreamInfo",  "Connection", "ConnectionStreamInfo",
        "Buffer", "VirtualHost", "Route",      "Counter",
        "Gauge",  "Histogram",   "StatsScope", "Header"};
    for (absl::string_view cls : unwrapper_classes) {
      RETURN_IF_ERROR(state.ExecuteString(
          absl::StrFormat("attach_status_unwrapper('%s')", cls)));
    }
  }

  return absl::OkStatus();
}

}  // namespace sample::lua
