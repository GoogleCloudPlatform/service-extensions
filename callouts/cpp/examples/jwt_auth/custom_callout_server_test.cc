// Copyright 2025 Google LLC
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

#include <fstream>
#include <sstream>

#include <jwt-cpp/jwt.h>
#include <sys/stat.h>

#include "custom_callout_server.h"
#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "envoy/type/v3/http_status.pb.h"
#include "google/protobuf/util/message_differencer.h"
#include "gtest/gtest.h"
#include "service/callout_server.h"

using envoy::config::core::v3::HeaderMap;
using envoy::config::core::v3::HeaderValue;
using envoy::service::ext_proc::v3::HttpHeaders;
using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using envoy::type::v3::StatusCode;
using google::protobuf::util::MessageDifferencer;

class JwtServerTest : public testing::Test {
 protected:
  void SetUp() override {
    const char* test_srcdir = std::getenv("TEST_SRCDIR");
    const char* test_workspace = std::getenv("TEST_WORKSPACE");

    if (test_srcdir && test_workspace) {
      std::string base_path =
          std::string(test_srcdir) + "/" + std::string(test_workspace);
      private_key_path_ = base_path + "/ssl_creds/privatekey.pem";
      public_key_path_ = base_path + "/ssl_creds/publickey.pem";
    } else {
      private_key_path_ = "ssl_creds/privatekey.pem";
      public_key_path_ = "ssl_creds/publickey.pem";
    }

    config_ = CalloutServerRunner::DefaultConfig();
    config_.enable_plaintext = true;
    config_.plaintext_address = "0.0.0.0:8181";
    config_.health_check_address = "0.0.0.0:8081";
    config_.key_path = private_key_path_;
    config_.cert_path = "";
    config_.num_threads = 1;

    server_thread_ = std::thread([this]() {
      CalloutServerRunner::RunServers<CustomCalloutServer>(config_);
    });
    while (!CalloutServerRunner::IsReady()) {
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
  }

  void TearDown() override {
    CalloutServerRunner::Shutdown();
    if (server_thread_.joinable()) {
      server_thread_.join();
    }
  }

  void SetupRequestWithToken(ProcessingRequest* request,
                             const std::string& token) {
    auto* headers = request->mutable_request_headers();
    auto* header_map = headers->mutable_headers();
    auto* header = header_map->add_headers();
    header->set_key("authorization");
    header->set_value("Bearer " + token);
  }

  std::string GenerateValidToken() {
    std::ifstream private_key_file(private_key_path_);
    std::stringstream buffer;
    buffer << private_key_file.rdbuf();
    std::string private_key = buffer.str();

    return jwt::create()
        .set_issuer("test_issuer")
        .set_type("JWT")
        .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
        .set_payload_claim("name", jwt::claim(std::string("Test User")))
        .set_payload_claim("role", jwt::claim(std::string("admin")))
        .sign(jwt::algorithm::rs256("", private_key));
  }

  std::string GenerateExpiredToken() {
    std::ifstream private_key_file(private_key_path_);
    std::stringstream buffer;
    buffer << private_key_file.rdbuf();
    std::string private_key = buffer.str();

    auto exp = std::chrono::system_clock::now() - std::chrono::hours(1);
    return jwt::create()
        .set_issuer("test_issuer")
        .set_type("JWT")
        .set_expires_at(exp)
        .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
        .sign(jwt::algorithm::rs256("", private_key));
  }

  CalloutServerRunner::ServerConfig config_;
  std::thread server_thread_;
  std::string private_key_path_;
  std::string public_key_path_;
};

TEST_F(JwtServerTest, NoAuthorizationToken) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service(public_key_path_);

  request.mutable_request_headers();
  service.OnRequestHeader(&request, &response);

  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(),
            StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(),
            "No Authorization token found");
}

TEST_F(JwtServerTest, ValidJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service(public_key_path_);

  try {
    std::string token = GenerateValidToken();
    SetupRequestWithToken(&request, token);
    service.OnRequestHeader(&request, &response);

    EXPECT_FALSE(response.has_immediate_response());
    EXPECT_TRUE(response.has_request_headers());

    bool found_sub = false;
    bool found_name = false;
    bool found_role = false;

    const auto& headers =
        response.request_headers().response().header_mutation().set_headers();
    for (const auto& header : headers) {
      if (header.header().key() == "decoded-sub" &&
          header.header().value() == "1234567890") {
        found_sub = true;
      }
      if (header.header().key() == "decoded-name" &&
          header.header().value() == "Test User") {
        found_name = true;
      }
      if (header.header().key() == "decoded-role" &&
          header.header().value() == "admin") {
        found_role = true;
      }
    }

    EXPECT_TRUE(found_sub) << "Missing decoded-sub header";
    EXPECT_TRUE(found_name) << "Missing decoded-name header";
    EXPECT_TRUE(found_role) << "Missing decoded-role header";
  } catch (const std::exception& e) {
    FAIL() << "Exception during test: " << e.what();
  }
}

TEST_F(JwtServerTest, InvalidJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service(public_key_path_);

  SetupRequestWithToken(&request, "invalid.jwt.token");
  service.OnRequestHeader(&request, &response);

  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(),
            StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(),
            "Invalid Authorization token");
}

TEST_F(JwtServerTest, ExpiredJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service(public_key_path_);

  try {
    std::string token = GenerateExpiredToken();
    SetupRequestWithToken(&request, token);
    service.OnRequestHeader(&request, &response);

    EXPECT_TRUE(response.has_immediate_response());
    EXPECT_EQ(response.immediate_response().status().code(),
              StatusCode::Unauthorized);
    EXPECT_EQ(response.immediate_response().body(),
              "Invalid Authorization token");
  } catch (const std::exception& e) {
    FAIL() << "Exception during test: " << e.what();
  }
}

TEST_F(JwtServerTest, MalformedAuthorizationHeader) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service;

  auto* headers = request.mutable_request_headers();
  auto* header_map = headers->mutable_headers();
  auto* header = header_map->add_headers();
  header->set_key("authorization");
  header->set_value("some-token-without-bearer-prefix");

  service.OnRequestHeader(&request, &response);

  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(),
            StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(),
            "No Authorization token found");
}
