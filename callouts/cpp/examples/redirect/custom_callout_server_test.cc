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

#include <google/protobuf/arena.h>

#include "envoy/config/core/v3/base.pb.h"
#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "envoy/type/v3/http_status.pb.h"
#include "google/protobuf/util/message_differencer.h"
#include "gtest/gtest.h"

using envoy::config::core::v3::HeaderValue;
using envoy::service::ext_proc::v3::HeaderMutation;
using envoy::service::ext_proc::v3::ImmediateResponse;
using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using envoy::type::v3::StatusCode;
using google::protobuf::util::MessageDifferencer;

class RedirectServerTest : public testing::Test {
 protected:
  void SetUp() override {
    // Setup code if needed
  }

  CustomCalloutServer service_;
};

TEST_F(RedirectServerTest, OnRequestHeaderReturnsRedirect) {
  // Initialize request/response
  google::protobuf::Arena arena;
  ProcessingRequest* request =
      google::protobuf::Arena::Create<ProcessingRequest>(&arena);
  ProcessingResponse* response =
      google::protobuf::Arena::Create<ProcessingResponse>(&arena);

  // Call the method under test
  service_.OnRequestHeader(request, response);

  // Build expected response
  ProcessingResponse expected_response;
  ImmediateResponse* expected_immediate =
      expected_response.mutable_immediate_response();
  
  // Verify status code
  expected_immediate->mutable_status()->set_code(StatusCode::MovedPermanently);
  
  // Verify Location header
  HeaderMutation* expected_headers = expected_immediate->mutable_headers();
  HeaderValue* location_header = expected_headers->add_set_headers()->mutable_header();
  location_header->set_key("Location");
  location_header->set_value("http://service-extensions.com/redirect");

  // Compare messages
  MessageDifferencer differencer;
  std::string diff_string;
  differencer.ReportDifferencesToString(&diff_string);
  
  EXPECT_TRUE(differencer.Compare(*response, expected_response))
      << "Redirect response mismatch:\n" << diff_string;
}