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

using grpc::ServerContext;
using envoy::service::ext_proc::v3::HttpHeaders;
using extproc::service::CalloutServer;

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

std::unordered_map<std::string, std::string> validate_jwt_token(
    const std::string& key,
    const HttpHeaders& request_headers,
    const std::string& algorithm,
    ServerContext* context) {

    std::string jwt_token = extract_jwt_token(request_headers);
    if (jwt_token.empty()) {
        // Deny callout
        deny_callout(context, "No Authorization token found.");
        return {};
    }

    try {
        auto decoded = jwt::decode(jwt_token);
        auto verifier = jwt::verify().allow_algorithm(jwt::algorithm::rs256(key)).with_issuer("your-issuer");

        verifier.verify(decoded); // May throw if verification fails

        std::unordered_map<std::string, std::string> claims;
        for (const auto& e : decoded.get_payload_json().items()) {
            claims[e.key()] = e.value();
        }
        std::cout << "Approved - Decoded Values: " << jwt_token << std::endl;
        return claims;
    } catch (const std::exception& e) {
        std::cerr << "Invalid token error: " << e.what() << std::endl;
        return {};
    }
}

class CalloutServerExample : public CalloutServer {
public:
    CalloutServerExample() {
        load_public_key("./extproc/ssl_creds/publickey.pem");
    }

    void load_public_key(const std::string& path) {
        std::ifstream key_file(path);
        if (key_file) {
            std::stringstream buffer;
            buffer << key_file.rdbuf();
            public_key_ = buffer.str();
        } else {
            std::cerr << "Unable to open public key file." << std::endl;
        }
    }

    grpc::Status on_request_headers(const HttpHeaders& headers, ServerContext* context) override {
        auto decoded = validate_jwt_token(public_key_, headers, "RS256", context);

        if (!decoded.empty()) {
            std::vector<std::pair<std::string, std::string>> decoded_items;
            for (const auto& item : decoded) {
                decoded_items.emplace_back("decoded-" + item.first, item.second);
            }
            return add_header_mutation(decoded_items, true);
        } else {
            deny_callout(context, "Authorization token is invalid.");
            return grpc::Status::CANCELLED; // Or appropriate status
        }
    }

private:
    std::string public_key_;
};


void deny_callout(grpc::ServerContext* context, const std::string& msg = "") {
    // Default message if none is provided
    std::string message = msg.empty() ? "Callout DENIED." : msg;

    // Log the warning message
    std::cerr << "WARNING: " << message << std::endl;

    // Deny the callout
    context->TryCancel(); // Optionally cancel the call
    context->Abort(grpc::Status(grpc::StatusCode::PERMISSION_DENIED, message));
}

HeadersResponse add_header_mutation(
    const std::optional<std::vector<std::pair<std::string, std::string>>>& add = std::nullopt,
    const std::optional<std::vector<std::string>>& remove = std::nullopt,
    bool clear_route_cache = false,
    std::optional<int> append_action = std::nullopt) /
    HeadersResponse header_mutation;
    
    if (add) {
        for (const auto& [k, v] : *add) {
            header_mutation.response.header_mutation.set_headers.emplace_back(k, v, append_action);
        }
    }
    if (remove) {
        header_mutation.response.header_mutation.remove_headers.insert(
            header_mutation.response.header_mutation.remove_headers.end(),
            remove->begin(), remove->end());
    }
    if (clear_route_cache) {
        header_mutation.response.clear_route_cache = true;
    }
    
    return header_mutation;
}

class HeadersResponse {
public:
    struct Response {
        HeaderMutation header_mutation;
        bool clear_route_cache = false;
    } response;
};

class HeaderMutation {
public:
    std::vector<HeaderValueOption> set_headers;
    std::vector<std::string> remove_headers;
};

class HeaderValue {
public:
    std::string key;
    std::string raw_value;

    HeaderValue(const std::string& k, const std::string& v) : key(k), raw_value(v) {}
};

class HeaderValueOption {
public:
    HeaderValue header;
    std::optional<int> append_action; // Replace 'int' with actual enum type if available

    HeaderValueOption(const std::string& key, const std::string& value, std::optional<int> action = std::nullopt)
        : header(key, value), append_action(action) {}
};