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

class CustomCalloutServerTest : public testing::Test {
 private:
  std::unique_ptr<grpc::Server> server;

 protected:
  void SetUp() override {

    // Initialize the server
    std::string server_address("0.0.0.0:8080");

    server = CalloutServer::RunServer(server_address, service_, false);
  }

  void TearDown() override {
    server->Shutdown();
  }

  // Helper method to create a request with JWT token
  void SetupRequestWithToken(ProcessingRequest* request, const std::string& token) {
    auto* headers = request->mutable_request_headers();
    auto* header_map = headers->mutable_headers();
    auto* header = header_map->add_headers();
    header->set_key("authorization");
    header->set_value("Bearer " + token);
  }

  // Generate a valid JWT token for testing using the actual key files
  std::string GenerateValidToken() {
    try {
        // Load the private key from file
        std::string private_key_path = "ssl_creds/privatekey.pem";
        std::ifstream private_key_file(private_key_path);
        if (!private_key_file) {
            std::cerr << "Failed to open private key file: " << private_key_path << std::endl;
            throw std::runtime_error("Failed to open private key file");
        }

        std::stringstream buffer;
        buffer << private_key_file.rdbuf();
        std::string private_key = buffer.str();

        std::cout << "Loaded private key, length: " << private_key.length() << std::endl;

        // Create token using the loaded private key
        auto token = jwt::create()
            .set_issuer("test_issuer")
            .set_type("JWT")
            .set_payload_claim("sub", jwt::claim(std::string("1234567890")))
            .set_payload_claim("name", jwt::claim(std::string("Test User")))
            .set_payload_claim("role", jwt::claim(std::string("admin")))
            .sign(jwt::algorithm::rs256("", private_key));

        std::cout << "Successfully generated token" << std::endl;
        return token;
    } catch (const std::exception& e) {
        std::cerr << "Error generating token: " << e.what() << std::endl;
        throw;
    }
  }

    // Create an expired token
    std::string GenerateExpiredToken() {
      try {
          // Load the private key from file
          std::string private_key_path = "ssl_creds/privatekey.pem";
          std::ifstream private_key_file(private_key_path);
          if (!private_key_file) {
              std::cerr << "Failed to open private key file: " << private_key_path << std::endl;
              throw std::runtime_error("Failed to open private key file");
          }

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
          throw;
      }
    }

    CustomCalloutServer service_;
};

TEST_F(CustomCalloutServerTest, NoAuthorizationToken) {
  ProcessingRequest request;
  ProcessingResponse response;

  // Call the OnRequestHeader method without setting a token
  service_.OnRequestHeader(&request, &response);

  // Verify the response indicates unauthorized
  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(), "No Authorization token found");
}

TEST_F(CustomCalloutServerTest, ValidJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;

  // Generate and set a valid token
  std::string token = GenerateValidToken();
  SetupRequestWithToken(&request, token);

  // Call the OnRequestHeader method
  service_.OnRequestHeader(&request, &response);

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
}

TEST_F(CustomCalloutServerTest, InvalidJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;

  // Set an invalid token
  SetupRequestWithToken(&request, "invalid.jwt.token");

  // Call the OnRequestHeader method
  service_.OnRequestHeader(&request, &response);

  // Verify the response indicates unauthorized
  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(), "Invalid Authorization token");
}

TEST_F(CustomCalloutServerTest, ExpiredJwtToken) {
  ProcessingRequest request;
  ProcessingResponse response;

  // Generate and set an expired token
  try {
    std::string token = GenerateExpiredToken();
    SetupRequestWithToken(&request, token);

    // Call the OnRequestHeader method
    service_.OnRequestHeader(&request, &response);

    // Verify the response indicates unauthorized
    EXPECT_TRUE(response.has_immediate_response());
    EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
    EXPECT_EQ(response.immediate_response().body(), "Invalid Authorization token");
  } catch (const std::exception& e) {
    FAIL() << "Exception during test: " << e.what();
  }
}

TEST_F(CustomCalloutServerTest, MalformedAuthorizationHeader) {
  ProcessingRequest request;
  ProcessingResponse response;

  // Set a malformed authorization header (missing "Bearer " prefix)
  auto* headers = request.mutable_request_headers();
  auto* header_map = headers->mutable_headers();
  auto* header = header_map->add_headers();
  header->set_key("authorization");
  header->set_value("some-token-without-bearer-prefix");

  // Call the OnRequestHeader method
  service_.OnRequestHeader(&request, &response);

  // Verify the response indicates unauthorized
  EXPECT_TRUE(response.has_immediate_response());
  EXPECT_EQ(response.immediate_response().status().code(), StatusCode::Unauthorized);
  EXPECT_EQ(response.immediate_response().body(), "No Authorization token found");
}