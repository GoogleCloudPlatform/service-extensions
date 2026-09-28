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

#ifndef NET_TURING_WASM_LUA_ENVOY_LUA_API_H_
#define NET_TURING_WASM_LUA_ENVOY_LUA_API_H_

// The C++ classes and Lua wrapper API surface defined in this file
// (e.g., Handle, Header, StreamInfo) are designed to emulate Envoy's native
// Lua HTTP filter API.
// https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter

#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "stream_state_interface.h"
#include "absl/container/flat_hash_map.h"
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/strings/string_view.h"
#include "proxy_wasm_common.h"
#include "proxy_wasm_enums.h"

namespace sample::lua {

class Logger {
 public:
  void LogTrace(std::string_view msg) const;
  void LogDebug(std::string_view msg) const;
  void LogInfo(std::string_view msg) const;
  void LogWarn(std::string_view msg) const;
  void LogErr(std::string_view msg) const;
  void LogCritical(std::string_view msg) const;
};

class Header {
 public:
  explicit Header(WasmHeaderMapType type,
                  std::function<bool()> is_passed_on = nullptr)
      : type_(type), is_passed_on_(std::move(is_passed_on)) {}
  absl::Status Add(std::string_view key, std::string_view value);
  absl::Status Remove(std::string_view key);
  absl::Status Replace(std::string_view key, std::string_view value);
  absl::Status SetHttp1ReasonPhrase(std::string_view reason_phrase);
  absl::StatusOr<std::optional<std::string>> Get(std::string_view key);
  absl::StatusOr<std::optional<std::string>> GetAtIndex(std::string_view key,
                                                        int index);
  absl::StatusOr<int> GetNumValues(std::string_view key);
  absl::StatusOr<std::vector<std::pair<std::string, std::string>>> GetPairs();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
  WasmHeaderMapType type_;
  std::function<bool()> is_passed_on_;
};

class Buffer {
 public:
  explicit Buffer(WasmBufferType type) : type_(type) {}
  absl::StatusOr<size_t> GetLength();
  absl::StatusOr<std::string> GetBytes(size_t index, size_t length);
  absl::Status SetBytes(std::string_view string);

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
  WasmBufferType type_;
};

class Metadata {
 public:
  Metadata() = default;
  absl::StatusOr<std::optional<std::string>> Get(std::string_view key);
  absl::StatusOr<std::vector<std::pair<std::string, std::string>>> GetPairs();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class DynamicMetadata {
 public:
  DynamicMetadata() = default;
  absl::StatusOr<std::optional<std::string>> Get(std::string_view filter_name);
  absl::Status Set(std::string_view filter_name, std::string_view key,
                   std::string_view value);
  absl::StatusOr<std::vector<std::pair<std::string, std::string>>> GetPairs();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class FilterState {
 public:
  FilterState() = default;
  absl::StatusOr<std::optional<std::string>> Get(std::string_view object_name);
  absl::StatusOr<std::optional<std::string>> Get(std::string_view object_name,
                                                 std::string_view field_name);
  absl::Status Set(std::string_view object_key, std::string_view factory_key,
                   std::string_view payload);

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class ParsedName {
 public:
  ParsedName() = default;
  absl::StatusOr<std::string> GetCommonName();
  absl::StatusOr<std::vector<std::string>> GetOrganizationName();
};

class SslConnection {
 public:
  SslConnection() = default;
  absl::StatusOr<bool> PeerCertificatePresented();
  absl::StatusOr<bool> PeerCertificateValidated();
  absl::StatusOr<std::vector<std::string>> GetUriSanLocalCertificate();
  absl::StatusOr<std::string> GetSha256PeerCertificateDigest();
  absl::StatusOr<std::string> GetSerialNumberPeerCertificate();
  absl::StatusOr<std::string> GetIssuerPeerCertificate();
  absl::StatusOr<std::string> GetSha256PeerCertificateIssuerDigest();
  absl::StatusOr<std::string> GetSerialNumberPeerCertificateIssuer();
  absl::StatusOr<std::string> GetSubjectPeerCertificate();
  absl::StatusOr<std::optional<ParsedName>> GetParsedSubjectPeerCertificate();
  absl::StatusOr<std::vector<std::string>> GetUriSanPeerCertificate();
  absl::StatusOr<std::string> GetSubjectLocalCertificate();
  absl::StatusOr<std::string> GetUrlEncodedPemEncodedPeerCertificate();
  absl::StatusOr<std::string> GetUrlEncodedPemEncodedPeerCertificateChain();
  absl::StatusOr<std::vector<std::string>> GetDnsSansPeerCertificate();
  absl::StatusOr<std::vector<std::string>> GetDnsSansLocalCertificate();
  absl::StatusOr<std::vector<std::string>> GetOidsPeerCertificate();
  absl::StatusOr<std::vector<std::string>> GetOidsLocalCertificate();
  absl::StatusOr<int64_t> GetValidFromPeerCertificate();
  absl::StatusOr<int64_t> GetExpirationPeerCertificate();
  absl::StatusOr<std::string> GetSessionId();
  absl::StatusOr<std::string> GetCiphersuiteId();
  absl::StatusOr<std::string> GetCiphersuiteString();
  absl::StatusOr<std::string> GetTlsVersion();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class StreamInfo {
 public:
  StreamInfo() = default;
  absl::StatusOr<std::string> GetProtocol();
  absl::StatusOr<std::string> GetRouteName();
  absl::StatusOr<std::string> GetVirtualClusterName();
  absl::StatusOr<std::string> GetDownstreamDirectLocalAddress();
  absl::StatusOr<std::string> GetDownstreamLocalAddress();
  absl::StatusOr<std::string> GetDownstreamDirectRemoteAddress();
  absl::StatusOr<std::string> GetDownstreamRemoteAddress();
  absl::StatusOr<std::string> GetRequestedServerName();
  absl::StatusOr<DynamicMetadata> GetDynamicMetadata();
  absl::StatusOr<std::optional<std::string>> GetDynamicTypedMetadata(
      std::string_view filter_name);
  absl::StatusOr<FilterState> GetFilterState();
  absl::StatusOr<std::optional<SslConnection>> GetDownstreamSslConnection();
  absl::Status DrainConnectionUponCompletion();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class ConnectionStreamInfo {
 public:
  ConnectionStreamInfo() = default;
  absl::StatusOr<DynamicMetadata> GetDynamicMetadata();
  absl::StatusOr<std::optional<std::string>> GetDynamicTypedMetadata(
      std::string_view filter_name);

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class Connection {
 public:
  Connection() = default;
  absl::StatusOr<std::optional<SslConnection>> GetSsl();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class VirtualHost {
 public:
  VirtualHost() = default;
  absl::StatusOr<Metadata> GetMetadata();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class Route {
 public:
  Route() = default;
  absl::StatusOr<Metadata> GetMetadata();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };

 private:
  Logger logger_;
};

class Counter {
 public:
  explicit Counter(uint32_t metric_id) : metric_id_(metric_id) {}
  absl::Status Inc();
  absl::Status Add(int64_t amount);
  absl::StatusOr<uint64_t> GetValue();

 private:
  uint32_t metric_id_;
};

class Gauge {
 public:
  explicit Gauge(uint32_t metric_id) : metric_id_(metric_id) {}
  absl::Status Inc();
  absl::Status Dec();
  absl::Status Add(int64_t amount);
  absl::Status Sub(int64_t amount);
  absl::Status Set(int64_t value);
  absl::StatusOr<uint64_t> GetValue();

 private:
  uint32_t metric_id_;
};

class Histogram {
 public:
  explicit Histogram(uint32_t metric_id) : metric_id_(metric_id) {}
  absl::Status RecordValue(int64_t value);

 private:
  uint32_t metric_id_;
};

class StatsScope {
 public:
  StatsScope() = default;
  absl::StatusOr<Counter> GetCounter(std::string_view name);
  absl::StatusOr<Gauge> GetGauge(std::string_view name);
  absl::StatusOr<Histogram> GetHistogram(std::string_view name,
                                         std::string_view unit);
};

class PublicKey {
 public:
  PublicKey() = default;
};

class BodyIterator {
 public:
  BodyIterator() = default;
};

enum class StrictMode { kLax, kStrict };

enum class CallMode { kSynchronous, kAsynchronous };

struct HttpCallResult {
  Header headers{WasmHeaderMapType::HttpCallResponseHeaders};
  std::optional<std::string> body;
};

struct VerifySignatureResult {
  bool is_valid;
  std::string signature;
};

class Handle {
 public:
  struct Options {
    bool is_request = true;
  };
  explicit Handle(StreamStateInterface& stream_state);
  explicit Handle(StreamStateInterface& stream_state, const Options& options);

  absl::StatusOr<Header> GetHeaders();
  absl::StatusOr<Buffer> GetBody();
  absl::StatusOr<BodyIterator> GetBodyChunks();
  absl::StatusOr<Header> GetTrailers();
  absl::StatusOr<HttpCallResult> HttpCall(
      std::string_view cluster,
      const absl::flat_hash_map<std::string, std::string>& headers,
      std::optional<std::string_view> body, uint32_t timeout_ms, CallMode mode);
  absl::StatusOr<HttpCallResult> HttpCall(
      std::string_view cluster,
      const absl::flat_hash_map<
          std::string, absl::flat_hash_map<std::string, std::string>>& headers,
      std::optional<std::string_view> body, uint32_t timeout_ms, CallMode mode);
  absl::StatusOr<HttpCallResult> HttpCall(
      std::string_view cluster,
      const absl::flat_hash_map<std::string, std::string>& headers,
      std::optional<std::string_view> body,
      const absl::flat_hash_map<std::string, std::string>& options);
  absl::StatusOr<HttpCallResult> HttpCall(
      std::string_view cluster,
      const absl::flat_hash_map<
          std::string, absl::flat_hash_map<std::string, std::string>>& headers,
      std::optional<std::string_view> body,
      const absl::flat_hash_map<std::string, std::string>& options);

  absl::Status Respond(
      const absl::flat_hash_map<std::string, std::string>& headers,
      std::optional<std::string_view> body);
  absl::Status Respond(
      const absl::flat_hash_map<
          std::string, absl::flat_hash_map<std::string, std::string>>& headers,
      std::optional<std::string_view> body);

  // deprecated soon
  // https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter
  absl::StatusOr<Metadata> GetMetadata();

  absl::StatusOr<StreamInfo> GetStreamInfo();
  absl::StatusOr<Connection> GetConnection();
  absl::StatusOr<ConnectionStreamInfo> GetConnectionStreamInfo();

  absl::Status SetUpstreamOverrideHost(std::string_view host,
                                       StrictMode strict = StrictMode::kLax);
  absl::Status ClearRouteCache();

  absl::StatusOr<absl::flat_hash_map<std::string, std::string>>
  GetFilterContext();

  absl::StatusOr<PublicKey> ImportPublicKey(std::string_view keyder,
                                            size_t keyder_length);
  absl::StatusOr<VerifySignatureResult> VerifySignature(
      std::string_view hash_function, const PublicKey& pubkey,
      std::string_view signature, size_t signature_length,
      std::string_view data, size_t data_length);
  absl::StatusOr<std::string> Base64Escape(std::string_view input);
  absl::StatusOr<uint64_t> GetTimestamp(
      std::optional<int> format = std::nullopt);
  absl::StatusOr<std::string> TimestampString(
      std::optional<int> resolution = std::nullopt);
  absl::StatusOr<VirtualHost> GetVirtualHost();
  absl::StatusOr<Route> GetRoute();
  absl::StatusOr<StatsScope> GetStats();

  void LogTrace(std::string_view msg) { logger_.LogTrace(msg); };
  void LogDebug(std::string_view msg) { logger_.LogDebug(msg); };
  void LogInfo(std::string_view msg) { logger_.LogInfo(msg); };
  void LogWarn(std::string_view msg) { logger_.LogWarn(msg); };
  void LogErr(std::string_view msg) { logger_.LogErr(msg); };
  void LogCritical(std::string_view msg) { logger_.LogCritical(msg); };
  StreamStateInterface& GetStreamState() { return stream_state_; }

 private:
  Logger logger_;
  StreamStateInterface& stream_state_;
  bool is_request_;
};

}  // namespace sample::lua
#endif  // NET_TURING_WASM_LUA_ENVOY_LUA_API_H_
