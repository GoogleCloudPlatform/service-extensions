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
  // Processes the incoming HTTP request headers.
  void OnRequestHeader(ProcessingRequest* request,
                       ProcessingResponse* response) override {
    CalloutServer::AddRequestHeader(response, "add-header-request",
                                    "Value-request");
    CalloutServer::ReplaceRequestHeader(response, "replace-header-request",
                                        "Value-request");
  }

  // Processes the outgoing HTTP response headers.
  void OnResponseHeader(ProcessingRequest* request,
                        ProcessingResponse* response) override {
    CalloutServer::AddResponseHeader(response, "add-header-response",
                                     "Value-response");
    CalloutServer::ReplaceResponseHeader(response, "replace-header-response",
                                         "Value-response");
  }

  // Processes the incoming HTTP request body.
  void OnRequestBody(ProcessingRequest* request,
                     ProcessingResponse* response) override {
    CalloutServer::ReplaceRequestBody(response, "new-body-request");
  }

  // Processes the outgoing HTTP response body.
  void OnResponseBody(ProcessingRequest* request,
                      ProcessingResponse* response) override {
    CalloutServer::ReplaceResponseBody(response, "new-body-response");
  }
};
