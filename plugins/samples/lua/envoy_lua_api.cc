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

#include "envoy_lua_api.h"

#include <cstdint>
#include <cstdlib>
#include <initializer_list>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "stream_state_interface.h"
#include "absl/container/flat_hash_map.h"
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/strings/ascii.h"
#include "absl/strings/escaping.h"
#include "absl/strings/match.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/str_format.h"
#include "absl/strings/str_split.h"
#include "absl/strings/string_view.h"
#include "absl/strings/strip.h"
#include "absl/time/time.h"
#include "proxy_wasm_intrinsics.h"

namespace sample::lua {
namespace {
bool GetBoolValue(const std::initializer_list<std::string_view>& path) {
  bool out = false;
  if (::getValue<bool>(path, &out)) {
    return out;
  }
  uint64_t out_int = 0;
  if (::getValue<uint64_t>(path, &out_int)) {
    return out_int != 0;
  }
  return false;
}

int64_t FetchTimestampProperty(const std::vector<std::string>& path) {
  std::string timestamp_str;
  if (::getValue<std::string>(path, &timestamp_str) && !timestamp_str.empty()) {
    absl::Time time;
    std::string err;
    if (absl::ParseTime(absl::RFC3339_full, timestamp_str, &time, &err)) {
      return absl::ToUnixSeconds(time);
    }
  }
  return 0;
}

std::string UrlEncode(absl::string_view value) {
  std::string escaped;
  escaped.reserve(value.size() * 3);
  for (char c : value) {
    if (absl::ascii_isalnum(c) || c == '-' || c == '_' || c == '.' ||
        c == '~') {
      escaped.push_back(c);
    } else {
      absl::StrAppendFormat(&escaped, "%%%02X", static_cast<unsigned char>(c));
    }
  }
  return escaped;
}

std::string Base64DerToUrlEncodedPem(absl::string_view b64_der) {
  // NOTE: Envoy uses BoringSSL to decode the DER-encoded cert strings.
  // However, we are not looking to include BoringSSL in this plugin, so we
  // perform the conversion manually.

  // Envoy may occasionally wrap the returned DER-encoded cert strings with
  // colons (e.g., when dumping raw byte arrays), so we strip them here.
  b64_der = absl::StripPrefix(b64_der, ":");
  b64_der = absl::StripSuffix(b64_der, ":");
  std::string pem = "-----BEGIN CERTIFICATE-----\n";
  for (size_t i = 0; i < b64_der.size(); i += 64) {
    absl::StrAppend(&pem, b64_der.substr(i, 64), "\n");
  }
  absl::StrAppend(&pem, "-----END CERTIFICATE-----\n");
  return UrlEncode(pem);
}

}  // namespace

void Logger::LogTrace(std::string_view msg) const { ::logTrace(msg); }
void Logger::LogDebug(std::string_view msg) const { ::logDebug(msg); }
void Logger::LogInfo(std::string_view msg) const { ::logInfo(msg); }
void Logger::LogWarn(std::string_view msg) const { ::logWarn(msg); }
void Logger::LogErr(std::string_view msg) const { ::logError(msg); }
void Logger::LogCritical(std::string_view msg) const { ::logCritical(msg); }

absl::Status Header::Add(std::string_view key, std::string_view value) {
  if (is_passed_on_ && is_passed_on_() &&
      (type_ == WasmHeaderMapType::RequestHeaders ||
       type_ == WasmHeaderMapType::ResponseHeaders)) {
    return absl::InternalError(
        "attempt to mutate headers after they have been passed on");
  }
  WasmResult result = addHeaderMapValue(type_, key, value);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to add header: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Header::Remove(std::string_view key) {
  if (is_passed_on_ && is_passed_on_() &&
      (type_ == WasmHeaderMapType::RequestHeaders ||
       type_ == WasmHeaderMapType::ResponseHeaders)) {
    return absl::InternalError(
        "attempt to mutate headers after they have been passed on");
  }
  WasmResult result = removeHeaderMapValue(type_, key);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to remove header: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Header::Replace(std::string_view key, std::string_view value) {
  if (is_passed_on_ && is_passed_on_() &&
      (type_ == WasmHeaderMapType::RequestHeaders ||
       type_ == WasmHeaderMapType::ResponseHeaders)) {
    return absl::InternalError(
        "attempt to mutate headers after they have been passed on");
  }
  WasmResult result = replaceHeaderMapValue(type_, key, value);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to replace header: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Header::SetHttp1ReasonPhrase(std::string_view /*reason_phrase*/) {
  return absl::UnimplementedError(
      "Header::SetHttp1ReasonPhrase is not supported");
}

absl::StatusOr<std::optional<std::string>> Header::Get(std::string_view key) {
  WasmDataPtr data = getHeaderMapValue(type_, key);
  if (!data || !data->data()) {
    return std::nullopt;
  }
  return data->toString();
}

absl::StatusOr<std::optional<std::string>> Header::GetAtIndex(
    std::string_view key, int index) {
  if (index < 0) {
    return absl::InvalidArgumentError("index must be non-negative");
  }
  WasmDataPtr data = getHeaderMapPairs(type_);
  if (!data || !data->data()) {
    return absl::InternalError("Failed to get header pairs for GetAtIndex");
  }

  std::vector<std::pair<std::string_view, std::string_view>> pairs =
      data->pairs();
  int count = 0;
  for (const auto& [header_key, header_value] : pairs) {
    if (absl::EqualsIgnoreCase(header_key, key)) {
      if (count == index) {
        return std::string(header_value);
      }
      ++count;
    }
  }
  return std::nullopt;
}

// Note: Calls getHeaderMapPairs(type_) involving a host syscall and marshalling
// all headers. Consider refactoring to a shared helper for performance if
// called in a loop.
absl::StatusOr<int> Header::GetNumValues(std::string_view key) {
  WasmDataPtr ptr = getHeaderMapPairs(type_);
  int count = 0;
  if (!ptr || !ptr->data()) {
    return absl::InternalError("Failed to get header pairs for GetNumValues");
  }

  std::vector<std::pair<std::string_view, std::string_view>> pairs =
      ptr->pairs();
  for (const auto& [header_key, _] : pairs) {
    if (absl::EqualsIgnoreCase(header_key, key)) {
      ++count;
    }
  }

  return count;
}

absl::StatusOr<std::vector<std::pair<std::string, std::string>>>
Header::GetPairs() {
  std::vector<std::pair<std::string, std::string>> result;
  const char* raw_ptr = nullptr;
  size_t size = 0;
  WasmResult result_status = proxy_get_header_map_pairs(type_, &raw_ptr, &size);
  if (result_status == WasmResult::NotFound) {
    return result;
  }
  if (result_status != WasmResult::Ok) {
    return absl::InternalError(absl::StrCat("Failed to get header pairs: ",
                                            ::toString(result_status)));
  }
  WasmData data(raw_ptr, size);
  if (!data.data()) {
    return result;
  }

  std::vector<std::pair<std::string_view, std::string_view>> pairs =
      data.pairs();
  result.reserve(pairs.size());
  for (const auto& [key, value] : pairs) {
    result.emplace_back(key, value);
  }
  return result;
}

absl::StatusOr<size_t> Buffer::GetLength() {
  size_t size = 0;
  uint32_t flags = 0;
  if (WasmResult result = getBufferStatus(type_, &size, &flags);
      result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to get buffer status: ", ::toString(result)));
  }
  return size;
}

absl::StatusOr<std::string> Buffer::GetBytes(size_t index, size_t length) {
  const char* ptr = nullptr;
  size_t size = 0;
  WasmResult result = proxy_get_buffer_bytes(type_, index, length, &ptr, &size);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to get buffer bytes: ", ::toString(result)));
  }
  if (ptr == nullptr && size == 0) {
    return "";
  }
  return WasmData(ptr, size).toString();
}

absl::Status Buffer::SetBytes(std::string_view string) {
  size_t length = 0;
  uint32_t flags = 0;
  if (WasmResult result = getBufferStatus(type_, &length, &flags);
      result != WasmResult::Ok) {
    return absl::InternalError(absl::StrCat(
        "Failed to get buffer status for SetBytes: ", ::toString(result)));
  }
  if (WasmResult result = setBuffer(type_, 0, length, string);
      result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to set buffer: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::StatusOr<std::optional<std::string>> Metadata::Get(std::string_view key) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::vector<std::pair<std::string, std::string>>>
Metadata::GetPairs() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::optional<std::string>> FilterState::Get(
    std::string_view object_name) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::optional<std::string>> FilterState::Get(
    std::string_view object_name, std::string_view field_name) {
  return absl::UnimplementedError("unimplemented");
}

absl::Status FilterState::Set(std::string_view object_key,
                              std::string_view factory_key,
                              std::string_view payload) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetProtocol() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetRouteName() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetVirtualClusterName() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetDownstreamDirectLocalAddress() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetDownstreamLocalAddress() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetDownstreamDirectRemoteAddress() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetDownstreamRemoteAddress() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> StreamInfo::GetRequestedServerName() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<DynamicMetadata> StreamInfo::GetDynamicMetadata() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::optional<std::string>> StreamInfo::GetDynamicTypedMetadata(
    std::string_view filter_name) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<FilterState> StreamInfo::GetFilterState() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::optional<SslConnection>>
StreamInfo::GetDownstreamSslConnection() {
  std::string out;
  if (::getValue<std::string>({"connection", "tls_version"}, &out)) {
    return SslConnection();
  }
  return std::nullopt;
}

absl::Status StreamInfo::DrainConnectionUponCompletion() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<DynamicMetadata> ConnectionStreamInfo::GetDynamicMetadata() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::optional<std::string>>
ConnectionStreamInfo::GetDynamicTypedMetadata(std::string_view filter_name) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::optional<SslConnection>> Connection::GetSsl() {
  std::string out;
  if (::getValue<std::string>({"connection", "tls_version"}, &out)) {
    return SslConnection();
  }
  return std::nullopt;
}

absl::StatusOr<std::optional<std::string>> DynamicMetadata::Get(
    std::string_view /*filter_name*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::Status DynamicMetadata::Set(std::string_view /*filter_name*/,
                                  std::string_view /*key*/,
                                  std::string_view /*value*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::vector<std::pair<std::string, std::string>>>
DynamicMetadata::GetPairs() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> ParsedName::GetCommonName() {
  return absl::UnimplementedError("ParsedName is unsupported.");
}

absl::StatusOr<std::vector<std::string>> ParsedName::GetOrganizationName() {
  return absl::UnimplementedError("ParsedName is unsupported.");
}

absl::StatusOr<bool> SslConnection::PeerCertificatePresented() {
  return GetBoolValue({"connection", "mtls"}) ||
         GetBoolValue({"connection", "client_cert_present"});
}

absl::StatusOr<bool> SslConnection::PeerCertificateValidated() {
  return GetBoolValue({"connection", "peer_certificate_valid"}) ||
         GetBoolValue({"connection", "client_cert_chain_verified"});
}

absl::StatusOr<std::vector<std::string>>
SslConnection::GetUriSanLocalCertificate() {
  std::string out;
  if (::getValue<std::string>({"connection", "uri_san_local_certificate"},
                              &out) &&
      !out.empty()) {
    return std::vector<std::string>{out};
  }
  return std::vector<std::string>{};
}

absl::StatusOr<std::string> SslConnection::GetSha256PeerCertificateDigest() {
  std::string out;
  ::getValue<std::string>({"connection", "sha256_peer_certificate_digest"},
                          &out);
  return out;
}

absl::StatusOr<std::string> SslConnection::GetSerialNumberPeerCertificate() {
  std::string out;
  ::getValue<std::string>({"connection", "client_cert_serial_number"}, &out);
  return out;
}

absl::StatusOr<std::string> SslConnection::GetIssuerPeerCertificate() {
  return absl::UnimplementedError(
      "Property SslConnection::GetIssuerPeerCertificate is unsupported.");
}

absl::StatusOr<std::string>
SslConnection::GetSha256PeerCertificateIssuerDigest() {
  return absl::UnimplementedError(
      "Property SslConnection::GetSha256PeerCertificateIssuerDigest is "
      "unsupported.");
}

absl::StatusOr<std::string>
SslConnection::GetSerialNumberPeerCertificateIssuer() {
  return absl::UnimplementedError(
      "Property SslConnection::GetSerialNumberPeerCertificateIssuer is "
      "unsupported.");
}

absl::StatusOr<std::string> SslConnection::GetSubjectPeerCertificate() {
  std::string out;
  ::getValue<std::string>({"connection", "subject_peer_certificate"}, &out);
  return out;
}

absl::StatusOr<std::optional<ParsedName>>
SslConnection::GetParsedSubjectPeerCertificate() {
  return absl::UnimplementedError(
      "Property SslConnection::GetParsedSubjectPeerCertificate is "
      "unsupported.");
}

absl::StatusOr<std::vector<std::string>>
SslConnection::GetUriSanPeerCertificate() {
  std::string out;
  if (::getValue<std::string>({"connection", "uri_san_peer_certificate"},
                              &out) &&
      !out.empty()) {
    return std::vector<std::string>{out};
  }

  std::vector<std::string> decoded_sans;
  if (::getValue<std::string>({"connection", "client_cert_uri_sans"}, &out) &&
      !out.empty()) {
    for (absl::string_view san : absl::StrSplit(out, ',')) {
      std::string decoded;
      if (absl::Base64Unescape(san, &decoded)) {
        decoded_sans.push_back(decoded);
      }
    }
  }

  std::string spiffe;
  if (::getValue<std::string>({"connection", "client_cert_spiffe_id"},
                              &spiffe) &&
      !spiffe.empty()) {
    decoded_sans.push_back(spiffe);
  }
  return decoded_sans;
}

absl::StatusOr<std::string> SslConnection::GetSubjectLocalCertificate() {
  std::string out;
  ::getValue<std::string>({"connection", "subject_local_certificate"}, &out);
  return out;
}

absl::StatusOr<std::string>
SslConnection::GetUrlEncodedPemEncodedPeerCertificate() {
  std::string out;
  if (::getValue<std::string>({"connection", "client_cert_leaf"}, &out) &&
      !out.empty()) {
    return Base64DerToUrlEncodedPem(out);
  }
  return "";
}

absl::StatusOr<std::string>
SslConnection::GetUrlEncodedPemEncodedPeerCertificateChain() {
  std::string leaf_out;
  std::string chain_out;
  std::string full_chain = "";

  if (::getValue<std::string>({"connection", "client_cert_leaf"}, &leaf_out) &&
      !leaf_out.empty()) {
    absl::StrAppend(&full_chain, Base64DerToUrlEncodedPem(leaf_out));
  }

  if (::getValue<std::string>({"connection", "client_cert_chain"},
                              &chain_out) &&
      !chain_out.empty()) {
    for (absl::string_view cert : absl::StrSplit(chain_out, ',')) {
      absl::StrAppend(&full_chain, Base64DerToUrlEncodedPem(cert));
    }
  }
  return full_chain;
}

absl::StatusOr<std::vector<std::string>>
SslConnection::GetDnsSansPeerCertificate() {
  std::string out;
  if (::getValue<std::string>({"connection", "dns_san_peer_certificate"},
                              &out) &&
      !out.empty()) {
    return std::vector<std::string>{out};
  }

  std::vector<std::string> decoded_sans;
  if (::getValue<std::string>({"connection", "client_cert_dnsname_sans"},
                              &out) &&
      !out.empty()) {
    for (absl::string_view san : absl::StrSplit(out, ',')) {
      std::string decoded;
      if (absl::Base64Unescape(san, &decoded)) {
        decoded_sans.push_back(decoded);
      }
    }
  }
  return decoded_sans;
}

absl::StatusOr<std::vector<std::string>>
SslConnection::GetDnsSansLocalCertificate() {
  std::string out;
  if (::getValue<std::string>({"connection", "dns_san_local_certificate"},
                              &out) &&
      !out.empty()) {
    return std::vector<std::string>{out};
  }
  return std::vector<std::string>{};
}

absl::StatusOr<std::vector<std::string>>
SslConnection::GetOidsPeerCertificate() {
  return absl::UnimplementedError(
      "Property SslConnection::GetOidsPeerCertificate is unsupported.");
}

absl::StatusOr<std::vector<std::string>>
SslConnection::GetOidsLocalCertificate() {
  return absl::UnimplementedError(
      "Property SslConnection::GetOidsLocalCertificate is unsupported.");
}

absl::StatusOr<int64_t> SslConnection::GetValidFromPeerCertificate() {
  return FetchTimestampProperty({"connection", "client_cert_valid_not_before"});
}

absl::StatusOr<int64_t> SslConnection::GetExpirationPeerCertificate() {
  return FetchTimestampProperty({"connection", "client_cert_valid_not_after"});
}

absl::StatusOr<std::string> SslConnection::GetSessionId() {
  return absl::UnimplementedError(
      "Property SslConnection::GetSessionId is unsupported.");
}

absl::StatusOr<std::string> SslConnection::GetCiphersuiteId() {
  std::string out;
  if (::getValue<std::string>({"connection", "tls_cipher_suite"}, &out) &&
      !out.empty()) {
    return absl::StrCat("0x", absl::AsciiStrToLower(out));
  }
  return "";
}

absl::StatusOr<std::string> SslConnection::GetCiphersuiteString() {
  return absl::UnimplementedError(
      "Property SslConnection::GetCiphersuiteString is unsupported.");
}

absl::StatusOr<std::string> SslConnection::GetTlsVersion() {
  std::string out;
  ::getValue<std::string>({"connection", "tls_version"}, &out);
  return out;
}

absl::StatusOr<Metadata> VirtualHost::GetMetadata() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<Metadata> Route::GetMetadata() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<Counter> StatsScope::GetCounter(std::string_view /*name*/) {
  return absl::UnimplementedError("unimplemented");
}
absl::StatusOr<Gauge> StatsScope::GetGauge(std::string_view /*name*/) {
  return absl::UnimplementedError("unimplemented");
}
absl::StatusOr<Histogram> StatsScope::GetHistogram(std::string_view /*name*/,
                                                   std::string_view /*unit*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::Status Counter::Inc() {
  WasmResult result = incrementMetric(metric_id_, 1);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to increment counter: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Counter::Add(int64_t amount) {
  if (amount < 0) {
    return absl::InvalidArgumentError(
        "Failed to add to counter: amount cannot be negative");
  }
  WasmResult result = incrementMetric(metric_id_, amount);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to add to counter: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::StatusOr<uint64_t> Counter::GetValue() {
  uint64_t value = 0;
  WasmResult result = getMetric(metric_id_, &value);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to get counter value: ", ::toString(result)));
  }
  return value;
}

absl::Status Gauge::Inc() {
  WasmResult result = incrementMetric(metric_id_, 1);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to increment gauge: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Gauge::Dec() {
  WasmResult result = incrementMetric(metric_id_, -1);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to decrement gauge: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Gauge::Add(int64_t amount) {
  if (amount < 0) {
    return absl::InvalidArgumentError(
        "Failed to add to gauge: amount cannot be negative");
  }
  WasmResult result = incrementMetric(metric_id_, amount);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to add to gauge: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Gauge::Sub(int64_t amount) {
  if (amount < 0) {
    return absl::InvalidArgumentError(
        "Failed to subtract from gauge: amount cannot be negative");
  }
  WasmResult result = incrementMetric(metric_id_, -amount);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to subtract from gauge: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::Status Gauge::Set(int64_t value) {
  if (value < 0) {
    return absl::InvalidArgumentError(
        "Failed to set gauge: value cannot be negative");
  }
  WasmResult result = recordMetric(metric_id_, value);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to set gauge: ", ::toString(result)));
  }
  return absl::OkStatus();
}

absl::StatusOr<uint64_t> Gauge::GetValue() {
  uint64_t value = 0;
  WasmResult result = getMetric(metric_id_, &value);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to get gauge: ", ::toString(result)));
  }
  return value;
}

absl::Status Histogram::RecordValue(int64_t value) {
  WasmResult result = recordMetric(metric_id_, value);
  if (result != WasmResult::Ok) {
    return absl::InternalError(
        absl::StrCat("Failed to record histogram: ", ::toString(result)));
  }
  return absl::OkStatus();
}

Handle::Handle(StreamStateInterface& stream_state)
    : stream_state_(stream_state), is_request_(true) {}

Handle::Handle(StreamStateInterface& stream_state, const Options& options)
    : stream_state_(stream_state), is_request_(options.is_request) {}

absl::StatusOr<Header> Handle::GetHeaders() {
  StreamStateInterface* state = &stream_state_;
  return Header(is_request_ ? WasmHeaderMapType::RequestHeaders
                            : WasmHeaderMapType::ResponseHeaders,
                [state]() { return state->IsHeadersPassedOn(); });
}

absl::StatusOr<Buffer> Handle::GetBody() {
  return Buffer(is_request_ ? WasmBufferType::HttpRequestBody
                            : WasmBufferType::HttpResponseBody);
}

absl::StatusOr<BodyIterator> Handle::GetBodyChunks() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<Header> Handle::GetTrailers() {
  StreamStateInterface* state = &stream_state_;
  return Header(is_request_ ? WasmHeaderMapType::RequestTrailers
                            : WasmHeaderMapType::ResponseTrailers,
                [state]() { return state->IsHeadersPassedOn(); });
}

absl::StatusOr<HttpCallResult> Handle::HttpCall(
    std::string_view /*cluster*/,
    const absl::flat_hash_map<std::string, std::string>& /*headers*/,
    std::optional<std::string_view> /*body*/, uint32_t /*timeout_ms*/,
    CallMode /*mode*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<HttpCallResult> Handle::HttpCall(
    std::string_view /*cluster*/,
    const absl::flat_hash_map<
        std::string,
        absl::flat_hash_map<std::string, std::string>>& /*headers*/,
    std::optional<std::string_view> /*body*/, uint32_t /*timeout_ms*/,
    CallMode /*mode*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<HttpCallResult> Handle::HttpCall(
    std::string_view /*cluster*/,
    const absl::flat_hash_map<std::string, std::string>& /*headers*/,
    std::optional<std::string_view> /*body*/,
    const absl::flat_hash_map<std::string, std::string>& /*options*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<HttpCallResult> Handle::HttpCall(
    std::string_view /*cluster*/,
    const absl::flat_hash_map<
        std::string,
        absl::flat_hash_map<std::string, std::string>>& /*headers*/,
    std::optional<std::string_view> /*body*/,
    const absl::flat_hash_map<std::string, std::string>& /*options*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::Status Handle::Respond(
    const absl::flat_hash_map<std::string, std::string>& /*headers*/,
    std::optional<std::string_view> /*body*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::Status Handle::Respond(
    const absl::flat_hash_map<
        std::string,
        absl::flat_hash_map<std::string, std::string>>& /*headers*/,
    std::optional<std::string_view> /*body*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<Metadata> Handle::GetMetadata() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<StreamInfo> Handle::GetStreamInfo() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<Connection> Handle::GetConnection() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<ConnectionStreamInfo> Handle::GetConnectionStreamInfo() {
  return absl::UnimplementedError("unimplemented");
}

absl::Status Handle::SetUpstreamOverrideHost(std::string_view /*host*/,
                                             StrictMode /*strict*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::Status Handle::ClearRouteCache() {
  return absl::UnimplementedError("unimplemented");
}
absl::StatusOr<absl::flat_hash_map<std::string, std::string>>
Handle::GetFilterContext() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<PublicKey> Handle::ImportPublicKey(std::string_view /*keyder*/,
                                                  size_t /*keyder_length*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<VerifySignatureResult> Handle::VerifySignature(
    std::string_view /*hash_function*/, const PublicKey& /*pubkey*/,
    std::string_view /*signature*/, size_t /*signature_length*/,
    std::string_view /*data*/, size_t /*data_length*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> Handle::Base64Escape(std::string_view /*input*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<uint64_t> Handle::GetTimestamp(std::optional<int> /*format*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<std::string> Handle::TimestampString(
    std::optional<int> /*resolution*/) {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<VirtualHost> Handle::GetVirtualHost() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<Route> Handle::GetRoute() {
  return absl::UnimplementedError("unimplemented");
}

absl::StatusOr<StatsScope> Handle::GetStats() {
  return absl::UnimplementedError("unimplemented");
}

}  // namespace sample::lua
