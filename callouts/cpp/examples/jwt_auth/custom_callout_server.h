// Copyright 2025 Google LLC.
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

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <unordered_map>
#include <jwt-cpp/jwt.h>
#include <grpcpp/grpcpp.h>
#include "envoy/service/ext_proc/v3/external_processor.pb.h"
#include "service/callout_server.h"
#include "envoy/type/v3/http_status.pb.h"

using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;
using envoy::service::ext_proc::v3::HttpHeaders;
using envoy::type::v3::StatusCode;

std::string extract_jwt_token(const HttpHeaders& request_headers) {
    for (const auto& header : request_headers.headers().headers()) {
        if (header.key() == "authorization") {
            std::string auth_value = header.value();
            size_t pos = auth_value.find("Bearer ");
            if (pos != std::string::npos) {
                return auth_value.substr(pos + 7); // 7 is length of "Bearer "
            }
        }
    }
    return {};
}

class CustomCalloutServer : public CalloutServer {
public:
    CustomCalloutServer() {
        load_public_key("ssl_creds/publickey.pem");
    }

    void load_public_key(const std::string& path) {
        std::ifstream key_file(path);
        if (key_file) {
            std::stringstream buffer;
            buffer << key_file.rdbuf();
            public_key_ = buffer.str();
            std::cout << "Successfully loaded public key from " << path << ", length: " << public_key_.length() << std::endl;
        } else {
            std::cerr << "Unable to open public key file: " << path << std::endl;
        }
    }

    // Processes the incoming HTTP request headers.
    void OnRequestHeader(ProcessingRequest* request, ProcessingResponse* response) override {
        const HttpHeaders& headers = request->request_headers();
        std::string jwt_token = extract_jwt_token(headers);

        if (jwt_token.empty()) {
            std::cerr << "WARNING: No Authorization token found." << std::endl;
            // Deny the request
            response->mutable_immediate_response()->mutable_status()->set_code(StatusCode::Unauthorized);
            response->mutable_immediate_response()->set_body("No Authorization token found");
            return;
        }

        try {
            auto decoded = jwt::decode(jwt_token);

            auto verifier = jwt::verify()
                .allow_algorithm(jwt::algorithm::rs256(public_key_));

            verifier.verify(decoded); // May throw if verification fails

            // Extract claims and add them as headers
            auto payload = decoded.get_payload_claims();
            for (auto& claim : payload) {
                std::string claim_value;
                if (claim.second.get_type() == jwt::json::type::string) {
                    claim_value = claim.second.as_string();
                } else {
                    // Convert other types to string as needed
                    claim_value = "non-string-value";
                }

                CalloutServer::AddRequestHeader(response, "decoded-" + claim.first, claim_value);
            }
        } catch (const std::exception& e) {
            // Deny the request
            response->mutable_immediate_response()->mutable_status()->set_code(StatusCode::Unauthorized);
            response->mutable_immediate_response()->set_body("Invalid Authorization token");
        }
    }

private:
    std::string public_key_;
};