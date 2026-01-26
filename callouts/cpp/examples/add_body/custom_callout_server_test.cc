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

#include "examples/add_body/custom_callout_server.h"

#include <memory>

#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "google/protobuf/util/message_differencer.h"
#include "gtest/gtest.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using google::protobuf::util::MessageDifferencer;

class AddBodyServerTest : public testing::Test {
 protected:
  void SetUp() override {
    // Test setup for direct method testing (no gRPC server needed)
  }

  CustomCalloutServer service_;  // Instance of the custom callout server to test
};

TEST_F(AddBodyServerTest, OnRequestBodyAppend) {
  google::protobuf::Arena arena;
  ProcessingRequest* request = google::protobuf::Arena::Create<ProcessingRequest>(&arena);
  ProcessingResponse* response = google::protobuf::Arena::Create<ProcessingResponse>(&arena);

  // Set initial request body to simulate an incoming request
  request->mutable_request_body()->set_body("test-body");
  
  // Call the OnRequestBody method to process the request body
  service_.OnRequestBody(request, response);

  // Verify that the body mutation appends the expected string
  EXPECT_EQ(response->request_body().response().body_mutation().body(),
            "test-body-added-request-body");
}

TEST_F(AddBodyServerTest, OnResponseBodyReplace) {
  google::protobuf::Arena arena;
  ProcessingRequest* request = google::protobuf::Arena::Create<ProcessingRequest>(&arena);
  ProcessingResponse* response = google::protobuf::Arena::Create<ProcessingResponse>(&arena);
  
  // Call the OnResponseBody method to process the response body
  service_.OnResponseBody(request, response);

  // Verify that the response body is replaced with the expected value
  EXPECT_EQ(response->response_body().response().body_mutation().body(),
            "new-body");
}

TEST_F(AddBodyServerTest, ClearBodyHandling) {
  google::protobuf::Arena arena;
  ProcessingRequest* request = google::protobuf::Arena::Create<ProcessingRequest>(&arena);
  ProcessingResponse* response = google::protobuf::Arena::Create<ProcessingResponse>(&arena);

  // Set an initial request body to test mutation functionality
  request->mutable_request_body()->set_body("to-clear");
  
  // Call the OnRequestBody method to process the request body
  service_.OnRequestBody(request, response);
  
  // Verify that the body mutation appends the expected string without clearing
  EXPECT_EQ(response->request_body().response().body_mutation().body(),
            "to-clear-added-request-body");
}