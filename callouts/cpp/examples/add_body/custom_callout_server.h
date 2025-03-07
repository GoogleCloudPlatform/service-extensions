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

#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "service/callout_server.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

class CustomCalloutServer : public CalloutServer {
 public:
  // Processes the incoming HTTP request body
  void OnRequestBody(ProcessingRequest* request,
                     ProcessingResponse* response) override {
    const std::string modified_body = request->request_body().body() + "-added-request-body";
    CalloutServer::ReplaceRequestBody(response, modified_body);
  }

  // Processes the outgoing HTTP response body
  void OnResponseBody(ProcessingRequest* request,
                      ProcessingResponse* response) override {
    CalloutServer::ReplaceResponseBody(response, "new-body");
  }
};