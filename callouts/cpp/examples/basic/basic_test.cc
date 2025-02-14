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

#include "basic.h"

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
 private:
  std::unique_ptr<grpc::Server> server;

 protected:
  void SetUp() override {
    std::string server_address("localhost:8181");
    server = CalloutServer::RunServer(server_address, service_, false);
  }

  void TearDown() override { server->Shutdown(); }

  CustomCalloutServer service_;
};

TEST_F(BasicServerTest, OnRequestHeader) {
  // Initialize the service paremeters
  ProcessingRequest* request = ProcessingRequest::default_instance().New();
  ProcessingResponse* response = ProcessingResponse::default_instance().New();

  // Call the OnRequestHeader method
  service_.OnRequestHeader(request, response);

  // Define the expected response
  ProcessingResponse expected_response;
  HeaderMutation* header_mutation = expected_response.mutable_request_headers()
                                        ->mutable_response()
                                        ->mutable_header_mutation();

  HeaderValue* header = header_mutation->add_set_headers()->mutable_header();
  header->set_key("add-header-request");
  header->set_value("Value-request");

  HeaderValueOption* header_option = header_mutation->add_set_headers();
  header_option->set_append_action(
      HeaderValueOption::OVERWRITE_IF_EXISTS_OR_ADD);
  HeaderValue* new_header = header_option->mutable_header();
  new_header->set_key("replace-header-request");
  new_header->set_value("Value-request");

  // Compare the proto messages
  MessageDifferencer differencer;
  std::string diff_string;
  differencer.ReportDifferencesToString(&diff_string);
  EXPECT_TRUE(differencer.Compare(*response, expected_response))
      << "Responses should be equal. Difference: " << diff_string;
}

TEST_F(BasicServerTest, OnResponseHeader) {
  // Initialize the service paremeters
  ProcessingRequest* request = ProcessingRequest::default_instance().New();
  ProcessingResponse* response = ProcessingResponse::default_instance().New();

  // Call the OnResponseHeader method
  service_.OnResponseHeader(request, response);

  // Define the expected response
  ProcessingResponse expected_response;
  HeaderMutation* header_mutation =
      expected_response.mutable_response_headers()
          ->mutable_response()
          ->mutable_header_mutation();

  HeaderValue* header = header_mutation->add_set_headers()->mutable_header();
  header->set_key("add-header-response");
  header->set_value("Value-response");

  HeaderValueOption* header_option = header_mutation->add_set_headers();
  header_option->set_append_action(
      HeaderValueOption::OVERWRITE_IF_EXISTS_OR_ADD);
  HeaderValue* new_header = header_option->mutable_header();
  new_header->set_key("replace-header-response");
  new_header->set_value("Value-response");

  // Compare the proto messages
  MessageDifferencer differencer;
  std::string diff_string;
  differencer.ReportDifferencesToString(&diff_string);
  EXPECT_TRUE(differencer.Compare(*response, expected_response))
      << "Responses should be equal. Difference: " << diff_string;
}

TEST_F(BasicServerTest, OnRequestBody) {
  // Initialize the service paremeters
  ProcessingRequest* request = ProcessingRequest::default_instance().New();
  ProcessingResponse* response = ProcessingResponse::default_instance().New();

  // Call the OnRequestBody method
  service_.OnRequestBody(request, response);

  // Define the expected response
  ProcessingResponse expected_response;
  expected_response.mutable_request_body()
      ->mutable_response()
      ->mutable_body_mutation()
      ->set_body("new-body-request");

  // Compare the proto messages
  MessageDifferencer differencer;
  std::string diff_string;
  differencer.ReportDifferencesToString(&diff_string);
  EXPECT_TRUE(differencer.Compare(*response, expected_response))
      << "Responses should be equal. Difference: " << diff_string;
}

TEST_F(BasicServerTest, OnResponseBody) {
  // Initialize the service paremeters
  ProcessingRequest* request = ProcessingRequest::default_instance().New();
  ProcessingResponse* response = ProcessingResponse::default_instance().New();

  // Call the OnResponseBody method
  service_.OnResponseBody(request, response);

  // Define the expected response
  ProcessingResponse expected_response;
  expected_response.mutable_response_body()
      ->mutable_response()
      ->mutable_body_mutation()
      ->set_body("new-body-response");

  // Compare the proto messages
  MessageDifferencer differencer;
  std::string diff_string;
  differencer.ReportDifferencesToString(&diff_string);
  EXPECT_TRUE(differencer.Compare(*response, expected_response))
      << "Responses should be equal. Difference: " << diff_string;
}
