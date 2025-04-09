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

/**
 * @file custom_callout_server.h
 * @brief Implementation of a custom callout server that manipulates HTTP bodies
 * @ingroup add_body_example
 */

#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "service/callout_server.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

/**
 * @class CustomCalloutServer
 * @brief Custom implementation of callout server that manipulates HTTP request and response bodies
 *
 * This server demonstrates how to modify HTTP message bodies by:
 * - Appending content to request bodies
 * - Completely replacing response bodies
 */
class CustomCalloutServer : public CalloutServer {
 public:
  /**
   * @brief Processes incoming request body to modify its content
   *
   * Appends a suffix string to the original request body before it's
   * forwarded to the upstream service.
   *
   * @param request The processing request containing the body
   * @param response The response to populate with body modifications
   */
  void OnRequestBody(ProcessingRequest* request,
                     ProcessingResponse* response) override {
    const std::string modified_body = request->request_body().body() + "-added-request-body";
    CalloutServer::ReplaceRequestBody(response, modified_body);
  }

  /**
   * @brief Processes outgoing response body to replace its content
   *
   * Completely replaces the response body with a fixed string before
   * it's sent back to the client.
   *
   * @param request The processing request containing the body
   * @param response The response to populate with body modifications
   */
  void OnResponseBody(ProcessingRequest* request,
                      ProcessingResponse* response) override {
    CalloutServer::ReplaceResponseBody(response, "new-body");
  }
};