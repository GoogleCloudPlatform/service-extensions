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
 * @brief Implementation of a custom callout server that performs HTTP redirects
 * @ingroup redirect_example
 */

#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "service/callout_server.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

/**
 * @class CustomCalloutServer
 * @brief Custom implementation of callout server that performs HTTP redirects
 *
 * This server demonstrates how to implement a simple HTTP redirect by:
 * - Intercepting incoming requests
 * - Generating an immediate response with a 301 status code
 * - Setting the appropriate Location header for the redirect target
 */
class CustomCalloutServer : public CalloutServer {
 public:
  /**
   * @brief Processes incoming request headers to perform a redirect
   *
   * This method intercepts all incoming HTTP requests and responds with a
   * 301 Moved Permanently redirect to a predefined URL.
   *
   * @param request The processing request containing headers
   * @param response The response to populate with redirect information
   */
  void OnRequestHeader(ProcessingRequest* request,
                       ProcessingResponse* response) override {
    // Create an immediate response for redirection
    auto* immediate_response = response->mutable_immediate_response();
    
    // Set HTTP 301 Moved Permanently status code
    immediate_response->mutable_status()->set_code(
        static_cast<enum envoy::type::v3::StatusCode>(301));
    
    // Add Location header for redirect target
    auto* header = immediate_response->mutable_headers()->add_set_headers();
    header->mutable_header()->set_key("Location");
    header->mutable_header()->set_value("http://service-extensions.com/redirect");
  }
};