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

#include "examples/add_header/custom_callout_server.h"

#include <memory>

#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "google/protobuf/util/message_differencer.h"
#include "gtest/gtest.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using envoy::service::ext_proc::v3::HeaderMutation;
using google::protobuf::util::MessageDifferencer;

class AddHeaderServerTest : public testing::Test {
 protected:
  void SetUp() override {
    // Initialize minimal request structure
    request_.mutable_request_headers();
    request_.mutable_response_headers();
  }

  CustomCalloutServer service_;
  ProcessingRequest request_;
};

TEST_F(AddHeaderServerTest, OnRequestHeaderAddsHeader) {
  ProcessingResponse response;
  
  service_.OnRequestHeader(&request_, &response);

  // Verify request header mutation
  const auto& mutation = response.request_headers().response().header_mutation();
  ASSERT_GT(mutation.set_headers_size(), 0);
  
  const auto& first_header = mutation.set_headers(0).header();
  EXPECT_EQ(first_header.key(), "header-request");
  EXPECT_EQ(first_header.value(), "request");
}

TEST_F(AddHeaderServerTest, OnResponseHeaderOperations) {
  ProcessingResponse response;
  
  service_.OnResponseHeader(&request_, &response);

  // Verify response header additions
  const auto& mutation = response.response_headers().response().header_mutation();
  ASSERT_GT(mutation.set_headers_size(), 0);
  
  const auto& added_header = mutation.set_headers(0).header();
  EXPECT_EQ(added_header.key(), "header-response");
  EXPECT_EQ(added_header.value(), "response");

  // Verify header removal
  ASSERT_GT(mutation.remove_headers_size(), 0);
  EXPECT_EQ(mutation.remove_headers(0), "foo");
}

TEST_F(AddHeaderServerTest, MultipleOperations) {
  ProcessingResponse response1;
  ProcessingResponse response2;
  
  service_.OnRequestHeader(&request_, &response1);
  service_.OnResponseHeader(&request_, &response2);

  // Verify request headers mutation
  EXPECT_TRUE(response1.has_request_headers());
  EXPECT_FALSE(response1.has_response_headers());

  // Verify response headers mutation
  EXPECT_TRUE(response2.has_response_headers());
  EXPECT_FALSE(response2.has_request_headers());
}