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
 * @brief Implementation of a custom callout server that manipulates HTTP headers
 * @ingroup add_header_example
 */

#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "service/callout_server.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

/**
 * @class CustomCalloutServer
 * @brief Custom implementation of callout server that manipulates HTTP headers
 *
 * This server demonstrates how to modify HTTP headers by:
 * - Adding custom headers to requests
 * - Adding custom headers to responses
 * - Removing specific headers from responses
 */
class CustomCalloutServer : public CalloutServer {
 public:
  /**
   * @brief Processes incoming request headers to add custom headers
   *
   * Adds a custom header to the incoming HTTP request before it's
   * forwarded to the upstream service.
   *
   * @param request The processing request containing headers
   * @param response The response to populate with header modifications
   */
  void OnRequestHeader(ProcessingRequest* request,
                      ProcessingResponse* response) override {
    // Add custom header using helper method
    CalloutServer::AddRequestHeader(response, "header-request", "request");
  }

  /**
   * @brief Processes outgoing response headers to modify headers
   *
   * Adds a custom header to the outgoing HTTP response and removes
   * the "foo" header if present.
   *
   * @param request The processing request containing headers
   * @param response The response to populate with header modifications
   */
  void OnResponseHeader(ProcessingRequest* request,
                       ProcessingResponse* response) override {
    // Add custom response header
    CalloutServer::AddResponseHeader(response, "header-response", "response");
    
    // Remove "foo" header via mutation
    CalloutServer::RemoveResponseHeader(response, "foo");
  }
};