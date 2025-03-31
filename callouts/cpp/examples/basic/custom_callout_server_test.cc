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

#include "envoy/config/core/v3/base.pb.h"
#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "google/protobuf/util/message_differencer.h"
#include "gtest/gtest.h"

using envoy::config::core::v3::HeaderValue;
using envoy::config::core::v3::HeaderValueOption;
using envoy::service::ext_proc::v3::HeaderMutation;
using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using google::protobuf::util::MessageDifferencer;

class BasicServerTest : public testing::Test {
 protected:
  void SetUp() override {
    config_ = CalloutServer::DefaultConfig();
    config_.enable_plaintext = true;
    config_.plaintext_address = "0.0.0.0:8181";
    config_.health_check_address = "0.0.0.0:8081";
    config_.key_path = "";
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

  CalloutServer::ServerConfig config_;
  std::thread server_thread_;
};

TEST_F(BasicServerTest, OnRequestHeader) {
  ProcessingRequest request;
  request.mutable_request_headers();
  ProcessingResponse response;
  CustomCalloutServer service;
  
  service.OnRequestHeader(&request, &response);

  ProcessingResponse expected_response;
  auto* headers_mutation = expected_response.mutable_request_headers()
                              ->mutable_response()
                              ->mutable_header_mutation();
  
  // Add header
  auto* new_header = headers_mutation->add_set_headers()->mutable_header();
  new_header->set_key("add-header-request");
  new_header->set_value("Value-request");
  
  // Replace header
  auto* replace_header = headers_mutation->add_set_headers();
  replace_header->set_append_action(
      HeaderValueOption::OVERWRITE_IF_EXISTS_OR_ADD);
  replace_header->mutable_header()->set_key("replace-header-request");
  replace_header->mutable_header()->set_value("Value-request");

  MessageDifferencer differencer;
  std::string diff;
  differencer.ReportDifferencesToString(&diff);
  EXPECT_TRUE(differencer.Compare(response, expected_response))
      << "Differences found:\n" << diff;
}

TEST_F(BasicServerTest, OnResponseHeader) {
  ProcessingRequest request;
  request.mutable_response_headers();
  ProcessingResponse response;
  CustomCalloutServer service;
  
  service.OnResponseHeader(&request, &response);

  ProcessingResponse expected_response;
  auto* headers_mutation = expected_response.mutable_response_headers()
                               ->mutable_response()
                               ->mutable_header_mutation();
  
  // Add header
  auto* new_header = headers_mutation->add_set_headers()->mutable_header();
  new_header->set_key("add-header-response");
  new_header->set_value("Value-response");
  
  // Replace header
  auto* replace_header = headers_mutation->add_set_headers();
  replace_header->set_append_action(
      HeaderValueOption::OVERWRITE_IF_EXISTS_OR_ADD);
  replace_header->mutable_header()->set_key("replace-header-response");
  replace_header->mutable_header()->set_value("Value-response");

  MessageDifferencer differencer;
  std::string diff;
  differencer.ReportDifferencesToString(&diff);
  EXPECT_TRUE(differencer.Compare(response, expected_response))
      << "Differences found:\n" << diff;
}

TEST_F(BasicServerTest, OnRequestBody) {
  ProcessingRequest request;
  request.mutable_request_body();
  ProcessingResponse response;
  CustomCalloutServer service;
  
  service.OnRequestBody(&request, &response);

  ProcessingResponse expected_response;
  expected_response.mutable_request_body()
      ->mutable_response()
      ->mutable_body_mutation()
      ->set_body("new-body-request");

  MessageDifferencer differencer;
  std::string diff;
  differencer.ReportDifferencesToString(&diff);
  EXPECT_TRUE(differencer.Compare(response, expected_response))
      << "Differences found:\n" << diff;
}

TEST_F(BasicServerTest, OnResponseBody) {
  ProcessingRequest request;
  request.mutable_response_body();
  ProcessingResponse response;
  CustomCalloutServer service;
  
  service.OnResponseBody(&request, &response);

  ProcessingResponse expected_response;
  expected_response.mutable_response_body()
      ->mutable_response()
      ->mutable_body_mutation()
      ->set_body("new-body-response");

  MessageDifferencer differencer;
  std::string diff;
  differencer.ReportDifferencesToString(&diff);
  EXPECT_TRUE(differencer.Compare(response, expected_response))
      << "Differences found:\n" << diff;
}