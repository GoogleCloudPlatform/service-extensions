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

/**
 * @file custom_callout_server.h
 * @brief Implementation of a custom callout server that performs JWT authentication
 * @ingroup jwt_auth_example
 */

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

/**
 * @brief Extracts JWT token from HTTP Authorization header
 *
 * Searches for the Authorization header in the request headers and extracts
 * the JWT token if it's present in the format "Bearer <token>".
 *
 * @param request_headers The HTTP headers from the request
 * @return The JWT token string, or empty string if not found
 */
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

/**
 * @class CustomCalloutServer
 * @brief Custom implementation of callout server that performs JWT authentication
 *
 * This server validates JWT tokens in incoming requests by:
 * - Extracting the token from the Authorization header
 * - Verifying the token signature using a public key
 * - Extracting claims from valid tokens and adding them as request headers
 * - Rejecting requests with missing or invalid tokens
 */
class CustomCalloutServer : public CalloutServer {
public:
    /**
     * @brief Default constructor
     *
     * Initializes the server with the default public key path
     */
    CustomCalloutServer() {
        // In a real application, use the default path
        load_public_key_from_file("ssl_creds/publickey.pem");
    }

    /**
     * @brief Constructor with custom key path
     *
     * Initializes the server with a specified public key file path
     *
     * @param key_path Path to the public key file
     */
    explicit CustomCalloutServer(const std::string& key_path) {
        load_public_key_from_file(key_path);
    }

    /**
     * @brief Constructor with public key string
     *
     * Initializes the server with a public key provided directly as a string
     *
     * @param public_key_str The public key as a string
     * @param is_key_string Flag to indicate the parameter is a key string (not a path)
     */
    explicit CustomCalloutServer(const std::string& public_key_str, bool is_key_string)
        : public_key_(public_key_str) {
        if (!public_key_.empty()) {
            std::cout << "Using provided public key, length: " << public_key_.length() << std::endl;
        } else {
            std::cerr << "WARNING: Empty public key provided" << std::endl;
        }
    }

    /**
     * @brief Loads a public key from a file
     *
     * Reads the public key from the specified file path and stores it
     * for JWT verification
     *
     * @param path Path to the public key file
     */
    void load_public_key_from_file(const std::string& path) {
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

    /**
     * @brief Processes incoming request headers for JWT authentication
     *
     * Extracts and validates JWT tokens from incoming requests:
     * - If no token is found, returns a 401 Unauthorized response
     * - If the token is invalid, returns a 401 Unauthorized response
     * - If the token is valid, extracts claims and adds them as request headers
     *
     * @param request The processing request containing headers
     * @param response The response to populate with authentication results
     */
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
    /**
     * @brief The public key used for JWT verification
     *
     * This key is used to verify the signature of incoming JWT tokens
     */
    std::string public_key_;
};