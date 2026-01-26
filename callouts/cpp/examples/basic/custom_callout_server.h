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
 * @brief Implementation of a custom callout server for request/response processing
 * @ingroup basic_example
 */

 #include "envoy/service/ext_proc/v3/external_processor.pb.h"
 #include "service/callout_server.h"
 
 using envoy::service::ext_proc::v3::ProcessingRequest;
 using envoy::service::ext_proc::v3::ProcessingResponse;
 
 /**
  * @class CustomCalloutServer
  * @brief Custom implementation of callout server that modifies HTTP headers and bodies
  *
  * This server demonstrates basic request/response processing capabilities by:
  * - Adding and modifying headers
  * - Replacing request/response bodies
  */
 class CustomCalloutServer : public CalloutServer {
  public:
   /**
    * @brief Processes incoming request headers
    * @param request The processing request containing headers
    * @param response The response to populate with header modifications
    */
   void OnRequestHeader(ProcessingRequest* request,
                        ProcessingResponse* response) override {
     CalloutServer::AddRequestHeader(response, "add-header-request",
                                     "Value-request");
     CalloutServer::ReplaceRequestHeader(response, "replace-header-request",
                                         "Value-request");
   }
 
   /**
    * @brief Processes outgoing response headers
    * @param request The processing request containing headers
    * @param response The response to populate with header modifications
    */
   void OnResponseHeader(ProcessingRequest* request,
                         ProcessingResponse* response) override {
     CalloutServer::AddResponseHeader(response, "add-header-response",
                                      "Value-response");
     CalloutServer::ReplaceResponseHeader(response, "replace-header-response",
                                          "Value-response");
   }
 
   /**
    * @brief Processes incoming request body
    * @param request The processing request containing the body
    * @param response The response to populate with body modifications
    */
   void OnRequestBody(ProcessingRequest* request,
                      ProcessingResponse* response) override {
     CalloutServer::ReplaceRequestBody(response, "new-body-request");
   }
 
   /**
    * @brief Processes outgoing response body
    * @param request The processing request containing the body
    * @param response The response to populate with body modifications
    */
   void OnResponseBody(ProcessingRequest* request,
                       ProcessingResponse* response) override {
     CalloutServer::ReplaceResponseBody(response, "new-body-response");
   }
 };
 