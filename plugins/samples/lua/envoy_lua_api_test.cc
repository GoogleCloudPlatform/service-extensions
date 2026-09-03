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

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <optional>
#include <string>

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
#include "absl/strings/match.h"
#include "absl/strings/string_view.h"
#include "include/proxy-wasm/pairs_util.h"
#include "proxy_wasm_common.h"
#include "proxy_wasm_enums.h"

namespace sample::lua {
namespace {

using ::testing::_;
using ::testing::AllOf;
using ::testing::Args;
using ::testing::DoAll;
using ::testing::ElementsAre;
using ::testing::HasSubstr;
using ::testing::IsEmpty;
using ::testing::NiceMock;
using ::testing::Not;
using ::testing::Pair;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::Test;
using ::testing::TestWithParam;
using ::testing::Values;

class LoggerTest : public Test {
 public:
  NiceMock<MockProxyWasmAbi> mock_abi_;
  Logger logger_;
};

TEST_F(LoggerTest, LogsTraceLevelMessagesSuccessfully) {
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::trace, _, _))
      .With(Args<1, 2>(WasmStrEq("trace msg")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogTrace("trace msg");
}

TEST_F(LoggerTest, LogsDebugLevelMessagesSuccessfully) {
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::debug, _, _))
      .With(Args<1, 2>(WasmStrEq("debug msg")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogDebug("debug msg");
}

TEST_F(LoggerTest, LogsInfoLevelMessagesSuccessfully) {
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::info, _, _))
      .With(Args<1, 2>(WasmStrEq("info msg")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogInfo("info msg");
}

TEST_F(LoggerTest, LogsWarnLevelMessagesSuccessfully) {
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::warn, _, _))
      .With(Args<1, 2>(WasmStrEq("warn msg")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogWarn("warn msg");
}

TEST_F(LoggerTest, LogsErrLevelMessagesSuccessfully) {
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmStrEq("err msg")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogErr("err msg");
}

TEST_F(LoggerTest, LogsCriticalLevelMessagesSuccessfully) {
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::critical, _, _))
      .With(Args<1, 2>(WasmStrEq("critical msg")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogCritical("critical msg");
}

TEST_F(LoggerTest, LogsMessagesWithEmbeddedNullCharactersCorrectly) {
  std::string_view msg("msg\0with\0nulls", 14);
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::info, _, _))
      .With(Args<1, 2>(WasmStrEq(msg)))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogInfo(msg);
}

TEST_F(LoggerTest, LogsEmptyMessagesSuccessfully) {
  std::string_view msg;
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::info, _, _))
      .With(Args<1, 2>(WasmStrEq("")))
      .WillOnce(Return(WasmResult::Ok));
  logger_.LogInfo(msg);
}

class HeaderTest : public TestWithParam<WasmHeaderMapType> {
 public:
  NiceMock<MockProxyWasmAbi> mock_abi_;
  Header header_{GetParam()};
};

TEST_P(HeaderTest, AddHeader) {
  EXPECT_CALL(mock_abi_, proxy_add_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq("foo")), Args<3, 4>(WasmStrEq("bar"))))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(header_.Add("foo", "bar"));
}

TEST_P(HeaderTest, RemoveHeader) {
  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(GetParam(), _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(header_.Remove("foo"));
}

TEST_P(HeaderTest, ReplaceHeader) {
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq("foo")), Args<3, 4>(WasmStrEq("bar"))))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(header_.Replace("foo", "bar"));
}

TEST_P(HeaderTest, GetHeaderExisting) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce(SetWasmString(std::string_view("bar")));
  { auto _s = header_.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("bar")); };
}

TEST_P(HeaderTest, GetHeaderMissing) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce([](WasmHeaderMapType, const char*, size_t,
                   const char** value_ptr, size_t* value_size) {
        *value_ptr = nullptr;
        *value_size = 0;
        return WasmResult::NotFound;
      });
  { auto _s = header_.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::nullopt); };
}

TEST_P(HeaderTest, GetHeaderCaseInsensitive) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("FOO")))
      .WillOnce(SetWasmString(std::string_view("bar")));
  { auto _s = header_.Get("FOO"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("bar")); };
}

TEST_P(HeaderTest, GetHeaderMultipleValuesJoinNatively) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("Set-Cookie")))
      .WillOnce([](WasmHeaderMapType, const char*, size_t,
                   const char** value_ptr, size_t* value_size) {
        *value_ptr = strdup("cookie_1=a, cookie_2=b");
        *value_size = 22;
        return WasmResult::Ok;
      });
  { auto _s = header_.Get("Set-Cookie"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("cookie_1=a, cookie_2=b")); };
}

TEST_P(HeaderTest, GetHeaderEmptyValue) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("empty-header")))
      .WillOnce([](WasmHeaderMapType, const char*, size_t,
                   const char** value_ptr, size_t* value_size) {
        *value_ptr = strdup("");
        *value_size = 0;
        return WasmResult::Ok;
      });
  { auto _s = header_.Get("empty-header"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("")); };
}

TEST_P(HeaderTest, GetHeaderInternalFailure) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("broken-header")))
      .WillOnce([](WasmHeaderMapType, const char*, size_t,
                   const char** value_ptr,
                   size_t* value_size) { return WasmResult::InternalFailure; });
  { auto _s = header_.Get("broken-header"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::nullopt); };
}

TEST_P(HeaderTest, RemoveHeaderCaseInsensitive) {
  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(GetParam(), _, _))
      .With(Args<1, 2>(WasmStrEq("Foo")))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(header_.Remove("Foo"));
}

TEST_P(HeaderTest, ReplaceHeaderCaseInsensitive) {
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq("fOo")),
                  Args<3, 4>(WasmStrEq("replaced-bar"))))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(header_.Replace("fOo", "replaced-bar"));
}

TEST_P(HeaderTest, AddHeaderReturnsErrorOnInternalFailure) {
  EXPECT_CALL(mock_abi_, proxy_add_header_map_value(GetParam(), _, _, _, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  { auto _s = header_.Add("foo", "bar"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, RemoveHeaderIgnoresBadArgument) {
  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(GetParam(), _, _))
      .WillOnce(Return(WasmResult::BadArgument));
  { auto _s = header_.Remove("foo"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, ReplaceHeaderReturnsErrorOnInternalFailure) {
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(GetParam(), _, _, _, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  { auto _s = header_.Replace("foo", "bar"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, GetPairsDecodesEmbeddedNullBytes) {
  std::string_view key_with_null("foo\0bar", 7);
  std::string_view value_with_null("value\0null", 10);
  proxy_wasm::Pairs expected_pairs = {{key_with_null, value_with_null}};

  std::string buffer(proxy_wasm::PairsUtil::pairsSize(expected_pairs), '\0');
  ASSERT_TRUE(proxy_wasm::PairsUtil::marshalPairs(expected_pairs, buffer.data(),
                                                  buffer.size()));

  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(SetWasmPairs(buffer));

  { auto _s = header_.GetPairs(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre(Pair(key_with_null, value_with_null))); };
}

TEST_P(HeaderTest, GetPairsPreservesMultipleEntriesForSameKey) {
  proxy_wasm::Pairs expected_pairs = {
      {"Set-Cookie", "cookie_1=a"},
      {"Set-Cookie", "cookie_2=b"},
      {"Custom-Header", "value1"},
  };
  std::string buffer(proxy_wasm::PairsUtil::pairsSize(expected_pairs), '\0');
  ASSERT_TRUE(proxy_wasm::PairsUtil::marshalPairs(expected_pairs, buffer.data(),
                                                  buffer.size()));

  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(SetWasmPairs(buffer));

  { auto _s = header_.GetPairs(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre(Pair("Set-Cookie", "cookie_1=a"),
                                       Pair("Set-Cookie", "cookie_2=b"),
                                       Pair("Custom-Header", "value1"))); };
}

TEST_P(HeaderTest, GetPairsInternalFailureReturnsError) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  { auto _s = header_.GetPairs(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, GetPairsNotFoundReturnsEmpty) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(Return(WasmResult::NotFound));
  { auto _s = header_.GetPairs(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, IsEmpty()); };
}

TEST_P(HeaderTest, GetPairsHandlesEmptyStrings) {
  proxy_wasm::Pairs expected_pairs = {
      {"Empty-Value", ""},
      {"", "Empty-Key"},
      {"", ""},
  };
  std::string buffer(proxy_wasm::PairsUtil::pairsSize(expected_pairs), '\0');
  ASSERT_TRUE(proxy_wasm::PairsUtil::marshalPairs(expected_pairs, buffer.data(),
                                                  buffer.size()));

  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(SetWasmPairs(buffer));

  { auto _s = header_.GetPairs(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre(Pair("Empty-Value", ""),
                                       Pair("", "Empty-Key"), Pair("", ""))); };
}

TEST_P(HeaderTest, GetPairsPreservesDuplicateKeysWithDifferentCasing) {
  proxy_wasm::Pairs expected_pairs = {
      {"X-Header", "Value1"},
      {"x-header", "Value2"},
  };
  std::string buffer(proxy_wasm::PairsUtil::pairsSize(expected_pairs), '\0');
  ASSERT_TRUE(proxy_wasm::PairsUtil::marshalPairs(expected_pairs, buffer.data(),
                                                  buffer.size()));

  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(SetWasmPairs(buffer));

  { auto _s = header_.GetPairs(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre(Pair("X-Header", "Value1"),
                                       Pair("x-header", "Value2"))); };
}

TEST_P(HeaderTest, AddHeaderEmbeddedNulls) {
  std::string_view key_with_null("foo\0bar", 7);
  std::string_view value_with_null("baz\0qux", 7);

  EXPECT_CALL(mock_abi_, proxy_add_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq(key_with_null)),
                  Args<3, 4>(WasmStrEq(value_with_null))))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(header_.Add(key_with_null, value_with_null));
}

TEST_P(HeaderTest, ReplaceHeaderEmbeddedNulls) {
  std::string_view key_with_null("foo\0bar", 7);
  std::string_view value_with_null("baz\0qux", 7);

  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq(key_with_null)),
                  Args<3, 4>(WasmStrEq(value_with_null))))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(header_.Replace(key_with_null, value_with_null));
}

TEST_P(HeaderTest, RemoveHeaderEmbeddedNulls) {
  std::string_view key_with_null("foo\0bar", 7);

  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(GetParam(), _, _))
      .With(Args<1, 2>(WasmStrEq(key_with_null)))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(header_.Remove(key_with_null));
}

TEST_P(HeaderTest, GetHeaderEmbeddedNulls) {
  std::string_view key_with_null("foo\0bar", 7);

  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .With(Args<1, 2>(WasmStrEq(key_with_null)))
      .WillOnce(SetWasmString(std::string_view("baz")));

  { auto _s = header_.Get(key_with_null); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("baz")); };
}

TEST_P(HeaderTest, RemoveHeaderIgnoresNotFound) {
  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(GetParam(), _, _))
      .WillOnce(Return(WasmResult::NotFound));
  { auto _s = header_.Remove("foo"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, ReplaceHeaderIgnoresNotFound) {
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(GetParam(), _, _, _, _))
      .WillOnce(Return(WasmResult::NotFound));
  { auto _s = header_.Replace("foo", "bar"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, GetPairsHandlesEmptyMapCorrectly) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce([](WasmHeaderMapType, const char** ptr, size_t* size) {
        *ptr = nullptr;
        *size = 0;
        return WasmResult::Ok;
      });

  { auto _s = header_.GetPairs(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, IsEmpty()); };
}

TEST_P(HeaderTest, GetHeaderOkWithNullptr) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(GetParam(), _, _, _, _))
      .WillOnce([](WasmHeaderMapType, const char*, size_t, const char** ptr,
                   size_t* size) {
        *ptr = nullptr;
        *size = 0;
        return WasmResult::Ok;
      });

  { auto _s = header_.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::nullopt); };
}

TEST_P(HeaderTest, GetAtIndexAndGetNumValues) {
  proxy_wasm::Pairs expected_pairs = {
      {"foo", "val1"},
      {"bar", "val2"},
      {"FOO", "val3"},
      {"", "empty_key_val"},
  };
  std::string buffer(proxy_wasm::PairsUtil::pairsSize(expected_pairs), '\0');
  ASSERT_TRUE(proxy_wasm::PairsUtil::marshalPairs(expected_pairs, buffer.data(),
                                                  buffer.size()));

  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillRepeatedly(SetWasmPairs(buffer));

  { auto _s = header_.GetNumValues("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 2); };
  { auto _s = header_.GetNumValues("FOO"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 2); };
  { auto _s = header_.GetNumValues("bar"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 1); };
  { auto _s = header_.GetNumValues("baz"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 0); };
  { auto _s = header_.GetNumValues(""); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 1); };

  { auto _s = header_.GetAtIndex("foo", 0); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("val1")); };

  { auto _s = header_.GetAtIndex("FOO", 0); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("val1")); };

  { auto _s = header_.GetAtIndex("foo", 1); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("val3")); };

  { auto _s = header_.GetAtIndex("FOO", 1); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("val3")); };

  { auto _s = header_.GetAtIndex("foo", 2); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::nullopt); };

  { auto _s = header_.GetAtIndex("foo", -1); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInvalidArgument); };  // or what status?

  { auto _s = header_.GetAtIndex("baz", 0); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::nullopt); };

  { auto _s = header_.GetAtIndex("", 0); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("empty_key_val")); };
}

TEST_P(HeaderTest, GetNumValuesInternalFailureReturnsError) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  { auto _s = header_.GetNumValues("foo"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, GetAtIndexInternalFailureReturnsError) {
  EXPECT_CALL(mock_abi_, proxy_get_header_map_pairs(GetParam(), _, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  { auto _s = header_.GetAtIndex("foo", 0); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_P(HeaderTest, AddHeaderEmptyValue) {
  EXPECT_CALL(mock_abi_, proxy_add_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq("foo")), Args<3, 4>(WasmStrEq(""))))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(header_.Add("foo", ""));
}

TEST_P(HeaderTest, ReplaceHeaderEmptyValue) {
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(GetParam(), _, _, _, _))
      .With(AllOf(Args<1, 2>(WasmStrEq("foo")), Args<3, 4>(WasmStrEq(""))))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(header_.Replace("foo", ""));
}
INSTANTIATE_TEST_SUITE_P(AllMapTypes, HeaderTest,
                         Values(WasmHeaderMapType::RequestHeaders,
                                WasmHeaderMapType::RequestTrailers,
                                WasmHeaderMapType::ResponseHeaders,
                                WasmHeaderMapType::ResponseTrailers));

class SslConnectionTest : public Test {
 public:
  NiceMock<MockProxyWasmAbi> mock_abi_;
  SslConnection ssl_connection_;
};

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsTrue) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly(SetWasmProperty(
          std::string(reinterpret_cast<const char*>(&"\x01"), 1)));
  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, true); };
}

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsTrue8Byte) {
  uint64_t val = 1;
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly(
          SetWasmProperty(std::string(reinterpret_cast<const char*>(&val), 8)));
  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, true); };
}

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsFalseWhenNotFound) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly(Return(WasmResult::NotFound));
  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, false); };
}

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsFalse1Byte) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly(SetWasmProperty(
          std::string(reinterpret_cast<const char*>(&"\x00"), 1)));
  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, false); };
}

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsFalse8Byte) {
  uint64_t val = 0;
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly(
          SetWasmProperty(std::string(reinterpret_cast<const char*>(&val), 8)));
  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, false); };
}

TEST_F(SslConnectionTest,
       GetUrlEncodedPemPeerCertChainReturnsCorrectlyConstructedChain) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_leaf")) {
          value = "leafA";
        } else if (absl::StrContains(path, "client_cert_chain")) {
          value = "chainB,chainC";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetUrlEncodedPemEncodedPeerCertificateChain(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, AllOf(Not(IsEmpty()), HasSubstr("leafA"),
                                 HasSubstr("chainB"), HasSubstr("chainC"))); };
}

TEST_F(SslConnectionTest,
       GetUrlEncodedPemPeerCertChainReturnsLeafOnlyWhenChainIsEmpty) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_leaf")) {
          value = "leafA";
        } else if (absl::StrContains(path, "client_cert_chain")) {
          value = "";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetUrlEncodedPemEncodedPeerCertificateChain(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, AllOf(Not(IsEmpty()), HasSubstr("leafA"),
                                 Not(HasSubstr(",")))); };
}

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsTrueFallback) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "mtls")) {
          value = std::string(reinterpret_cast<const char*>(&"\x00"), 1);
        } else if (absl::StrContains(path, "client_cert_present")) {
          value = std::string(reinterpret_cast<const char*>(&"\x01"), 1);
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, true); };
}

TEST_F(SslConnectionTest, PeerCertificatePresentedReturnsFalseFallback) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "mtls") ||
            absl::StrContains(path, "client_cert_present")) {
          value = std::string(reinterpret_cast<const char*>(&"\x00"), 1);
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.PeerCertificatePresented(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, false); };
}

TEST_F(SslConnectionTest, PeerCertificateValidatedReturnsTrueFallback) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "peer_certificate_valid")) {
          value = std::string(reinterpret_cast<const char*>(&"\x00"), 1);
        } else if (absl::StrContains(path, "client_cert_chain_verified")) {
          value = std::string(reinterpret_cast<const char*>(&"\x01"), 1);
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.PeerCertificateValidated(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, true); };
}

TEST_F(SslConnectionTest, PeerCertificateValidatedReturnsFalseFallback) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "peer_certificate_valid") ||
            absl::StrContains(path, "client_cert_chain_verified")) {
          value = std::string(reinterpret_cast<const char*>(&"\x00"), 1);
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.PeerCertificateValidated(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, false); };
}

TEST_F(SslConnectionTest, GetUriSanPeerCertificateFallback) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_uri_sans")) {
          // base64 encoded "example.com" -> ZXhhbXBsZS5jb20=
          // base64 encoded "test.org" -> dGVzdC5vcmc=
          value = "ZXhhbXBsZS5jb20=,dGVzdC5vcmc=";
        } else if (absl::StrContains(path, "client_cert_spiffe_id")) {
          value = "spiffe://example.com/foo";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetUriSanPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre("example.com", "test.org",
                                       "spiffe://example.com/foo")); };
}

TEST_F(SslConnectionTest, GetDnsSansPeerCertificateFallback) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_dnsname_sans")) {
          // base64 encoded "example.com" -> ZXhhbXBsZS5jb20=
          // base64 encoded "test.org" -> dGVzdC5vcmc=
          value = "ZXhhbXBsZS5jb20=,dGVzdC5vcmc=";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetDnsSansPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre("example.com", "test.org")); };
}

TEST_F(SslConnectionTest,
       GetUriSanPeerCertificateUsesStandardPropertyIfPresent) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "uri_san_peer_certificate")) {
          value = "spiffe://standard.com";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetUriSanPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre("spiffe://standard.com")); };
}

TEST_F(SslConnectionTest,
       GetDnsSansPeerCertificateUsesStandardPropertyIfPresent) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "dns_san_peer_certificate")) {
          value = "standard.example.com";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetDnsSansPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, ElementsAre("standard.example.com")); };
}

TEST_F(SslConnectionTest, GetValidFromPeerCertificateParsesRfc3339) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_valid_not_before")) {
          // "2023-01-01T00:00:00Z" in unix seconds is 1672531200
          value = "2023-01-01T00:00:00Z";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetValidFromPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 1672531200); };
}

TEST_F(SslConnectionTest,
       GetValidFromPeerCertificateReturnsZeroOnInvalidFormat) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_valid_not_before")) {
          value = "invalid-timestamp";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetValidFromPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 0); };
}

TEST_F(SslConnectionTest, GetUrlEncodedPemEncodedPeerCertificateStripsColons) {
  EXPECT_CALL(mock_abi_, proxy_get_property(_, _, _, _))
      .WillRepeatedly([](const char* path_ptr, size_t path_size,
                         const char** out_data, size_t* out_size) {
        std::string path(path_ptr, path_size);
        std::string value;
        if (absl::StrContains(path, "client_cert_leaf")) {
          value = ":bGVhZjo=:";
        } else {
          return WasmResult::NotFound;
        }

        char* p = static_cast<char*>(malloc(value.size()));
        memcpy(p, value.data(), value.size());
        *out_data = p;
        *out_size = value.size();
        return WasmResult::Ok;
      });

  { auto _s = ssl_connection_.GetUrlEncodedPemEncodedPeerCertificate(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, AllOf(HasSubstr("bGVhZjo%3D"), Not(HasSubstr("%3A")))); };
}

class BufferTest : public Test {
 public:
  MockProxyWasmAbi mock_abi_;
  Buffer buffer_{WasmBufferType::HttpRequestBody};
};

TEST_F(BufferTest, GetLengthReturnsCorrectSize) {
  size_t initial_body_size = 123;
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(
          DoAll(SetArgPointee<1>(initial_body_size), Return(WasmResult::Ok)));

  { auto _s = buffer_.GetLength(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 123); };
}

TEST_F(BufferTest, GetBytesReturnsData) {
  EXPECT_CALL(mock_abi_, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                5, 10, _, _))
      .WillOnce(SetWasmBufferBytes("hello world"));

  { auto _s = buffer_.GetBytes(5, 10); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::string("hello world")); };
}

TEST_F(BufferTest, GetBytesHandlesHostReturningFewerBytes) {
  EXPECT_CALL(mock_abi_, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                2, 10, _, _))
      .WillOnce(SetWasmBufferBytes("abc"));

  { auto _s = buffer_.GetBytes(2, 10); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::string("abc")); };
}

TEST_F(BufferTest, SetBytesUpdatesBuffer) {
  size_t initial_body_size = 5;
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(
          DoAll(SetArgPointee<1>(initial_body_size), Return(WasmResult::Ok)));

  EXPECT_CALL(mock_abi_, proxy_set_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 5, _, 8))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(buffer_.SetBytes("new data"));
}

TEST_F(BufferTest, SetBytesTruncatesBuffer) {
  size_t initial_body_size = 5;
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(
          DoAll(SetArgPointee<1>(initial_body_size), Return(WasmResult::Ok)));

  EXPECT_CALL(mock_abi_, proxy_set_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 5, _, 2))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(buffer_.SetBytes("12"));
}

TEST_F(BufferTest, SetBytesReturnsErrorOnSetFailure) {
  size_t initial_body_size = 5;
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(
          DoAll(SetArgPointee<1>(initial_body_size), Return(WasmResult::Ok)));

  EXPECT_CALL(mock_abi_, proxy_set_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 5, _, 2))
      .WillOnce(Return(WasmResult::InternalFailure));

  { auto _s = buffer_.SetBytes("12"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(BufferTest, GetLengthReturnsZeroOnFailure) {
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(Return(WasmResult::InternalFailure));

  { auto _s = buffer_.GetLength(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(BufferTest, GetBytesReturnsEmptyOnFailure) {
  EXPECT_CALL(mock_abi_, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 10, _, _))
      .WillOnce(Return(WasmResult::InternalFailure));

  { auto _s = buffer_.GetBytes(0, 10); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(BufferTest, GetBytesReturnsEmptyOnNullptr) {
  EXPECT_CALL(mock_abi_, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 10, _, _))
      .WillOnce(SetWasmBufferBytes(""));

  { auto _s = buffer_.GetBytes(0, 10); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::string("")); };
}

TEST_F(BufferTest, SetBytesDoesNotCallSetOnGetLengthFailure) {
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_set_buffer_bytes(_, _, _, _, _)).Times(0);

  { auto _s = buffer_.SetBytes("new data"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(BufferTest, GetBytesWithZeroLengthReturnsEmpty) {
  EXPECT_CALL(mock_abi_, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 0, _, _))
      .WillOnce(SetWasmBufferBytes(""));

  { auto _s = buffer_.GetBytes(0, 0); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::string("")); };
}

TEST_F(BufferTest, GetBytesAtBufferLengthReturnsEmpty) {
  size_t length = 5;
  EXPECT_CALL(mock_abi_, proxy_get_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                length, 0, _, _))
      .WillOnce(SetWasmBufferBytes(""));

  { auto _s = buffer_.GetBytes(length, 0); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::string("")); };
}

TEST_F(BufferTest, SetBytesOnEmptyBufferHandlesRangeZeroZero) {
  EXPECT_CALL(mock_abi_,
              proxy_get_buffer_status(WasmBufferType::HttpRequestBody, _, _))
      .WillOnce(DoAll(SetArgPointee<1>(0), Return(WasmResult::Ok)));

  EXPECT_CALL(mock_abi_, proxy_set_buffer_bytes(WasmBufferType::HttpRequestBody,
                                                0, 0, _, 8))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(buffer_.SetBytes("new data"));
}

class CounterTest : public ::testing::Test {
 public:
  ::testing::NiceMock<MockProxyWasmAbi> mock_abi_;
};

TEST_F(CounterTest, IncIncrementsMetricByOne) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_increment_metric(101, 1))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(counter.Inc());
}

TEST_F(CounterTest, AddIncrementsMetricByGivenAmount) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_increment_metric(101, 5))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(counter.Add(5));
}

TEST_F(CounterTest, AddHandlesZeroCorrectly) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_increment_metric(101, 0))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(counter.Add(0));
}

TEST_F(CounterTest, AddRejectsNegativeAmounts) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_increment_metric(101, _)).Times(0);
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to add to counter: amount cannot be negative")))
      .Times(0);

  { auto _s = counter.Add(-1); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInvalidArgument); };
}

TEST_F(CounterTest, GetValueReturnsCorrectValue) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_get_metric(101, _))
      .WillOnce(DoAll(SetArgPointee<1>(42), Return(WasmResult::Ok)));
  { auto _s = counter.GetValue(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 42); };
}

TEST_F(CounterTest, GetValueReturnsMaxUint64Correctly) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_get_metric(101, _))
      .WillOnce(DoAll(SetArgPointee<1>(std::numeric_limits<uint64_t>::max()),
                      Return(WasmResult::Ok)));
  { auto _s = counter.GetValue(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::numeric_limits<uint64_t>::max()); };
}

TEST_F(CounterTest, IncLogsErrorWhenIncrementFails) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_increment_metric(101, 1))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to increment counter: InternalFailure")))
      .Times(0);

  { auto _s = counter.Inc(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(CounterTest, AddLogsErrorWhenIncrementFails) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_increment_metric(101, 5))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to add to counter: InternalFailure")))
      .Times(0);

  { auto _s = counter.Add(5); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(CounterTest, GetValueLogsErrorAndReturnsZeroWhenGetFails) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_get_metric(101, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to get counter value: InternalFailure")))
      .Times(0);

  { auto _s = counter.GetValue(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(CounterTest, GetValueLogsErrorAndReturnsZeroWhenNotFound) {
  Counter counter(101);

  EXPECT_CALL(mock_abi_, proxy_get_metric(101, _))
      .WillOnce(Return(WasmResult::NotFound));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmHasSubstr("Failed to get counter value: NotFound")))
      .Times(0);

  { auto _s = counter.GetValue(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

class GaugeTest : public ::testing::Test {
 public:
  ::testing::NiceMock<MockProxyWasmAbi> mock_abi_;
};

TEST_F(GaugeTest, IncIncrementsMetricByOne) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, 1))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Inc());
}

TEST_F(GaugeTest, DecDecrementsMetricByOne) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, -1))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Dec());
}

TEST_F(GaugeTest, AddIncrementsMetricByGivenAmount) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, 5))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Add(5));
}

TEST_F(GaugeTest, SubDecrementsMetricByGivenAmount) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, -5))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Sub(5));
}

TEST_F(GaugeTest, SetRecordsMetricValue) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_record_metric(102, 42))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Set(42));
}

TEST_F(GaugeTest, GetValueReturnsCorrectValue) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_get_metric(102, _))
      .WillOnce(DoAll(SetArgPointee<1>(42), Return(WasmResult::Ok)));
  { auto _s = gauge.GetValue(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 42); };
}

TEST_F(GaugeTest, GetValueWithLargeBitPatternSurfacesCorrectly) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_get_metric(102, _))
      .WillOnce(
          DoAll(SetArgPointee<1>(0xFFFFFFFFFFFFFFFF), Return(WasmResult::Ok)));
  { auto _s = gauge.GetValue(); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, 0xFFFFFFFFFFFFFFFF); };
}

TEST_F(GaugeTest, SetRejectsNegativeValue) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_record_metric(102, _)).Times(0);
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to set gauge: value cannot be negative")))
      .Times(0);
  { auto _s = gauge.Set(-1); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInvalidArgument); };
}

TEST_F(GaugeTest, SubRejectsNegativeAmount) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, _)).Times(0);
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmHasSubstr(
          "Failed to subtract from gauge: amount cannot be negative")))
      .Times(0);
  { auto _s = gauge.Sub(-1); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInvalidArgument); };
}

TEST_F(GaugeTest, AddRejectsNegativeAmount) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, _)).Times(0);
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to add to gauge: amount cannot be negative")))
      .Times(0);
  { auto _s = gauge.Add(-1); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInvalidArgument); };
}

TEST_F(GaugeTest, AddHandlesZeroCorrectly) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, 0))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Add(0));
}

TEST_F(GaugeTest, SetHandlesZeroCorrectly) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_record_metric(102, 0))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(gauge.Set(0));
}

TEST_F(GaugeTest, LogsErrorWhenIncrementFails) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, 1))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to increment gauge: InternalFailure")))
      .Times(0);
  { auto _s = gauge.Inc(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(GaugeTest, LogsErrorWhenDecrementFails) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, -1))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to decrement gauge: InternalFailure")))
      .Times(0);
  { auto _s = gauge.Dec(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(GaugeTest, LogsErrorWhenAddFails) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, 5))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(
          Args<1, 2>(WasmHasSubstr("Failed to add to gauge: InternalFailure")))
      .Times(0);
  { auto _s = gauge.Add(5); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(GaugeTest, LogsErrorWhenSubFails) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_increment_metric(102, -5))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to subtract from gauge: InternalFailure")))
      .Times(0);
  { auto _s = gauge.Sub(5); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(GaugeTest, LogsErrorWhenSetFails) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_record_metric(102, 42))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmHasSubstr("Failed to set gauge: InternalFailure")))
      .Times(0);
  { auto _s = gauge.Set(42); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(GaugeTest, LogsErrorAndReturnsZeroWhenGetFails) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_get_metric(102, _))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmHasSubstr("Failed to get gauge: InternalFailure")))
      .Times(0);
  { auto _s = gauge.GetValue(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(GaugeTest, LogsErrorAndReturnsZeroWhenNotFound) {
  Gauge gauge(102);
  EXPECT_CALL(mock_abi_, proxy_get_metric(102, _))
      .WillOnce(Return(WasmResult::NotFound));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmHasSubstr("Failed to get gauge: NotFound")))
      .Times(0);
  { auto _s = gauge.GetValue(); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

class HistogramTest : public ::testing::Test {
 public:
  ::testing::NiceMock<MockProxyWasmAbi> mock_abi_;
};

TEST_F(HistogramTest, RecordsMetricValue) {
  Histogram histogram(103);
  EXPECT_CALL(mock_abi_, proxy_record_metric(103, 42))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(histogram.RecordValue(42));
}

TEST_F(HistogramTest, RecordsBoundaryZeroValue) {
  Histogram histogram(103);
  EXPECT_CALL(mock_abi_, proxy_record_metric(103, 0))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(histogram.RecordValue(0));
}

TEST_F(HistogramTest, RecordsNegativeValueWrapsToUnsigned) {
  Histogram histogram(103);
  EXPECT_CALL(mock_abi_, proxy_record_metric(103, static_cast<uint64_t>(-5)))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(histogram.RecordValue(-5));
}

TEST_F(HistogramTest, RecordsInt64BoundariesWrapsToUnsigned) {
  Histogram histogram(103);

  EXPECT_CALL(
      mock_abi_,
      proxy_record_metric(
          103, static_cast<uint64_t>(std::numeric_limits<int64_t>::max())))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(histogram.RecordValue(std::numeric_limits<int64_t>::max()));

  EXPECT_CALL(
      mock_abi_,
      proxy_record_metric(
          103, static_cast<uint64_t>(std::numeric_limits<int64_t>::min())))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_OK(histogram.RecordValue(std::numeric_limits<int64_t>::min()));
}

TEST_F(HistogramTest, LogsErrorWhenRecordFails) {
  Histogram histogram(103);
  EXPECT_CALL(mock_abi_, proxy_record_metric(103, 42))
      .WillOnce(Return(WasmResult::InternalFailure));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(
          WasmHasSubstr("Failed to record histogram: InternalFailure")))
      .Times(0);
  { auto _s = histogram.RecordValue(42); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

TEST_F(HistogramTest, LogsErrorWhenRecordFailsWithBadArgument) {
  Histogram histogram(103);
  EXPECT_CALL(mock_abi_, proxy_record_metric(103, 42))
      .WillOnce(Return(WasmResult::BadArgument));
  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(
          Args<1, 2>(WasmHasSubstr("Failed to record histogram: BadArgument")))
      .Times(0);
  { auto _s = histogram.RecordValue(42); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

class HandleTest : public Test {
 public:
  NiceMock<MockStreamState> stream_state_;
  NiceMock<MockProxyWasmAbi> mock_abi_;
};

TEST_F(HandleTest, GetTrailersForRequest) {
  Handle::Options options;
  options.is_request = true;
  Handle handle(stream_state_, options);
  ASSERT_OK_AND_ASSIGN(Header trailers, handle.GetTrailers());

  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(
                             WasmHeaderMapType::RequestTrailers, _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce(SetWasmString(std::string_view("bar")));

  { auto _s = trailers.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("bar")); };
}

TEST_F(HandleTest, GetTrailersForResponse) {
  Handle::Options options;
  options.is_request = false;
  Handle handle(stream_state_, options);
  ASSERT_OK_AND_ASSIGN(Header trailers, handle.GetTrailers());

  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(
                             WasmHeaderMapType::ResponseTrailers, _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce(SetWasmString(std::string_view("bar")));

  { auto _s = trailers.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("bar")); };
}

TEST_F(HandleTest, GetHeadersForRequest) {
  Handle::Options options;
  options.is_request = true;
  Handle handle(stream_state_, options);
  ASSERT_OK_AND_ASSIGN(Header headers, handle.GetHeaders());

  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(
                             WasmHeaderMapType::RequestHeaders, _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce(SetWasmString(std::string_view("bar")));

  { auto _s = headers.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("bar")); };
}

TEST_F(HandleTest, GetHeadersForResponse) {
  Handle::Options options;
  options.is_request = false;
  Handle handle(stream_state_, options);
  ASSERT_OK_AND_ASSIGN(Header headers, handle.GetHeaders());

  EXPECT_CALL(mock_abi_, proxy_get_header_map_value(
                             WasmHeaderMapType::ResponseHeaders, _, _, _, _))
      .With(Args<1, 2>(WasmStrEq("foo")))
      .WillOnce(SetWasmString(std::string_view("bar")));

  { auto _s = headers.Get("foo"); EXPECT_TRUE(GetStatus(_s).ok()); EXPECT_THAT(*_s, std::optional<std::string>("bar")); };
}

TEST_F(HandleTest, GetTrailersMutationsAllowedWhenHeadersPassedOn) {
  EXPECT_CALL(stream_state_, IsHeadersPassedOn()).WillRepeatedly(Return(true));

  Handle::Options options;
  options.is_request = true;
  Handle handle(stream_state_, options);
  ASSERT_OK_AND_ASSIGN(Header trailers, handle.GetTrailers());

  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _)).Times(0);

  EXPECT_CALL(mock_abi_, proxy_add_header_map_value(
                             WasmHeaderMapType::RequestTrailers, _, _, _, _))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(
                             WasmHeaderMapType::RequestTrailers, _, _, _, _))
      .WillOnce(Return(WasmResult::Ok));
  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(
                             WasmHeaderMapType::RequestTrailers, _, _))
      .WillOnce(Return(WasmResult::Ok));

  EXPECT_OK(trailers.Add("foo", "bar"));
  EXPECT_OK(trailers.Replace("foo", "baz"));
  EXPECT_OK(trailers.Remove("foo"));
}

TEST_F(HandleTest, GetHeadersMutationsBlockedWhenHeadersPassedOn) {
  EXPECT_CALL(stream_state_, IsHeadersPassedOn()).WillRepeatedly(Return(true));

  Handle::Options options;
  options.is_request = true;
  Handle handle(stream_state_, options);
  ASSERT_OK_AND_ASSIGN(Header headers, handle.GetHeaders());

  EXPECT_CALL(mock_abi_, proxy_log(LogLevel::error, _, _))
      .With(Args<1, 2>(WasmHasSubstr(
          "attempt to mutate headers after they have been passed on")))
      .Times(0);

  // Assert that host SDK functions are NEVER called.
  EXPECT_CALL(mock_abi_, proxy_add_header_map_value(_, _, _, _, _)).Times(0);
  EXPECT_CALL(mock_abi_, proxy_replace_header_map_value(_, _, _, _, _))
      .Times(0);
  EXPECT_CALL(mock_abi_, proxy_remove_header_map_value(_, _, _)).Times(0);

  { auto _s = headers.Add("foo", "bar"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
  { auto _s = headers.Replace("foo", "baz"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
  { auto _s = headers.Remove("foo"); EXPECT_EQ(GetStatus(_s).code(), absl::StatusCode::kInternal); };
}

}  // namespace
}  // namespace sample::lua
