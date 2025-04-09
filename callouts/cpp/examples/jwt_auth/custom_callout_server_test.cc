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

#include "custom_callout_server.h"
#include "service/callout_server.h"
#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "envoy/type/v3/http_status.pb.h"
#include "google/protobuf/util/message_differencer.h"
#include "gtest/gtest.h"
#include <jwt-cpp/jwt.h>
#include <fstream>
#include <sys/stat.h>

using envoy::config::core::v3::HeaderMap;
using envoy::config::core::v3::HeaderValue;
using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using envoy::service::ext_proc::v3::HttpHeaders;
using envoy::type::v3::StatusCode;
using google::protobuf::util::MessageDifferencer;

class JwtServerTest : public testing::Test {
protected:
  void SetUp() override {
    // Get the path to the key files from TEST_SRCDIR
    const char* test_srcdir = std::getenv("TEST_SRCDIR");
    const char* test_workspace = std::getenv("TEST_WORKSPACE");

    if (test_srcdir && test_workspace) {
      std::string base_path = std::string(test_srcdir) + "/" + std::string(test_workspace);
      private_key_path_ = base_path + "/ssl_creds/privatekey.pem";
      public_key_path_ = base_path + "/ssl_creds/publickey.pem";
    } else {
      // Fallback to relative paths
      private_key_path_ = "ssl_creds/privatekey.pem";
      public_key_path_ = "ssl_creds/publickey.pem";
    }

    std::cout << "Using private key path: " << private_key_path_ << std::endl;
    std::cout << "Using public key path: " << public_key_path_ << std::endl;

    // Set up server configuration
    config_ = CalloutServer::DefaultConfig();
    config_.enable_plaintext = true;
    config_.plaintext_address = "0.0.0.0:8181";
    config_.health_check_address = "0.0.0.0:8081";
    config_.key_path = private_key_path_;
    config_.cert_path = "";

    server_thread_ = std::thread([this]() {
      CalloutServer::RunServers(config_);
    });
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }

  void TearDown() override {
    CalloutServer::Shutdown();
    CalloutServer::WaitForCompletion();

    if (server_thread_.joinable()) {
      server_thread_.join();
    }
  }

  // Helper method to create a request with JWT token
  void SetupRequestWithToken(ProcessingRequest* request, const std::string& token) {
    auto* headers = request->mutable_request_headers();
    auto* header_map = headers->mutable_headers();
    auto* header = header_map->add_headers();
    header->set_key("authorization");
    header->set_value("Bearer " + token);
  }

  // Generate a valid JWT token using the private key file
  std::string GenerateValidToken() {
    try {
      // Load the private key from file
      std::ifstream private_key_file(private_key_path_);

      std::stringstream buffer;
      buffer << private_key_file.rdbuf();
      std::string private_key = buffer.str();

      // Create token using the loaded private key
      auto token = jwt::create()
          .set_issuer("test_issuer")
          .set_type("JWT")
          .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
          .set_payload_claim("name", jwt::claim(std::string("Test User")))
          .set_payload_claim("role", jwt::claim(std::string("admin")))
          .sign(jwt::algorithm::rs256("", private_key));

      return token;
    } catch (const std::exception& e) {
      std::cerr << "Error generating token: " << e.what() << std::endl;
      return "";
    }
  }

  // Create an expired token using the private key file
  std::string GenerateExpiredToken() {
    try {
      // Load the private key from file
      std::ifstream private_key_file(private_key_path_);

      std::stringstream buffer;
      buffer << private_key_file.rdbuf();
      std::string private_key = buffer.str();

      // Create token with expiration in the past
      auto now = std::chrono::system_clock::now();
      auto exp = now - std::chrono::hours(1); // Expired 1 hour ago

      auto token = jwt::create()
          .set_issuer("test_issuer")
          .set_type("JWT")
          .set_expires_at(exp)
          .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
          .sign(jwt::algorithm::rs256("", private_key));

      return token;
    } catch (const std::exception& e) {
      std::cerr << "Error generating expired token: " << e.what() << std::endl;
      return "";
    }
  }

  CalloutServer::ServerConfig config_;
  std::thread server_thread_;
  std::string private_key_path_;
  std::string public_key_path_;

};

TEST_F(JwtServerTest, NoAuthorizationToken) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service(public_key_path_);

  // Set up a request headers message
  request.mutable_request_headers();

  // Call the OnRequestHeader method without setting a token
  service.OnRequestHeader(&request, &response);

  // Verify the response indicates unauthorized
  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(), "No Authorization token found");
}

TEST_F(JwtServerTest, ValidJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;

  // Create a service instance with the public key path from Bazel environment
  CustomCalloutServer service(public_key_path_);

  // Generate a valid token using the private key from file
  std::string token;
  try {
    // Load the private key from file
    std::ifstream private_key_file(private_key_path_);

    std::stringstream buffer;
    buffer << private_key_file.rdbuf();
    std::string private_key = buffer.str();

    // Create token using the loaded private key
    auto token = jwt::create()
        .set_issuer("test_issuer")
        .set_type("JWT")
        .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
        .set_payload_claim("name", jwt::claim(std::string("Test User")))
        .set_payload_claim("role", jwt::claim(std::string("admin")))
        .sign(jwt::algorithm::rs256("", private_key));

    SetupRequestWithToken(&request, token);

    // Call the OnRequestHeader method
    service.OnRequestHeader(&request, &response);

    // Verify the response has request headers with decoded claims
    EXPECT_FALSE(response.has_immediate_response());
    EXPECT_TRUE(response.has_request_headers());

    // Check for specific headers that should be added based on JWT claims
    bool found_sub = false;
    bool found_name = false;
    bool found_role = false;

    const auto& headers = response.request_headers().response().header_mutation().set_headers();
    for (const auto& header : headers) {
      if (header.header().key() == "decoded-sub" && header.header().value() == "1234567890") {
        found_sub = true;
      }
      if (header.header().key() == "decoded-name" && header.header().value() == "Test User") {
        found_name = true;
      }
      if (header.header().key() == "decoded-role" && header.header().value() == "admin") {
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

  // Set an invalid token
  SetupRequestWithToken(&request, "invalid.jwt.token");

  // Call the OnRequestHeader method
  service.OnRequestHeader(&request, &response);

  // Verify the response indicates unauthorized
  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(), "Invalid Authorization token");
}

TEST_F(JwtServerTest, ExpiredJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service(public_key_path_);

  // Generate an expired token using the private key from file
  try {
    // Load the private key from file
    std::ifstream private_key_file(private_key_path_);

    std::stringstream buffer;
    buffer << private_key_file.rdbuf();
    std::string private_key = buffer.str();

    // Create token with expiration in the past
    auto now = std::chrono::system_clock::now();
    auto exp = now - std::chrono::hours(1); // Expired 1 hour ago

    auto token = jwt::create()
        .set_issuer("test_issuer")
        .set_type("JWT")
        .set_expires_at(exp)
        .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
        .sign(jwt::algorithm::rs256("", private_key));

    SetupRequestWithToken(&request, token);

    // Call the OnRequestHeader method
    service.OnRequestHeader(&request, &response);

    // Verify the response indicates unauthorized
    EXPECT_TRUE(response.has_immediate_response());
    EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
    EXPECT_EQ(response.immediate_response().body(), "Invalid Authorization token");
  } catch (const std::exception& e) {
    FAIL() << "Exception during test: " << e.what();
  }
}

TEST_F(JwtServerTest, MalformedAuthorizationHeader) {
  ProcessingRequest request;
  ProcessingResponse response;
  CustomCalloutServer service;  // Create a local instance of the service

  // Set a malformed authorization header (missing "Bearer " prefix)
  auto* headers = request.mutable_request_headers();
  auto* header_map = headers->mutable_headers();
  auto* header = header_map->add_headers();
  header->set_key("authorization");
  header->set_value("some-token-without-bearer-prefix");

  // Call the OnRequestHeader method
  service.OnRequestHeader(&request, &response);

  // Verify the response indicates unauthorized
  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(), "No Authorization token found");
}