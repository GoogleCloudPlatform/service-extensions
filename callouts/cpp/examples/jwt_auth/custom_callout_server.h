// Copyright 2024 Google LLC.
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

#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include <stdexcept>
#include <sstream>
#include <memory>
#include <jwt-cpp/jwt.h>
#include "server.h" // Include the relevant server header
#include "utils.h"  // Include the relevant utils header
#include "extproc.pb.h" // Include the generated protobuf header

class ExampleCalloutService : public GRPCCalloutService {
public:
    ExampleCalloutService(const std::string& keyPath) {
        LoadPublicKey(keyPath);
    }

    ExampleCalloutService() : ExampleCalloutService("./extproc/ssl_creds/publickey.pem") {}

private:
    std::vector<uint8_t> PublicKey;

    void LoadPublicKey(const std::string& path) {
        std::ifstream keyFile(path, std::ios::binary);
        if (!keyFile) {
            throw std::runtime_error("Failed to load public key: " + path);
        }
        PublicKey.assign((std::istreambuf_iterator<char>(keyFile)), std::istreambuf_iterator<char>());
        keyFile.close();
    }

    std::string ExtractJWTToken(const extproc::HttpHeaders& headers) {
        for (const auto& header : headers.headers()) {
            if (header.key() == "Authorization") {
                return header.raw_value();
            }
        }
        throw std::runtime_error("No Authorization header found");
    }

    std::unordered_map<std::string, std::string> ValidateJWTToken(const extproc::HttpHeaders& headers) {
        std::string tokenString = ExtractJWTToken(headers);

        if (tokenString.rfind("Bearer ", 0) == 0) {
            tokenString.erase(0, std::string("Bearer ").length());
        }

        auto decodedToken = jwt::decode(tokenString);

        // Verify the token with the public key
        auto verifier = jwt::verify()
                            .allow_algorithm(jwt::algorithm::rs256(PublicKey.data(), PublicKey.size()))
                            .with_issuer("your-issuer"); // Set your issuer here

        verifier.verify(decodedToken); // This will throw if verification fails

        std::unordered_map<std::string, std::string> claims;
        for (const auto& e : decodedToken.get_payload_claims()) {
            claims[e.first] = e.second.as_string(); // Convert claim to string
        }

        return claims;
    }

public:
    extproc::ProcessingResponse HandleRequestHeaders(const extproc::HttpHeaders& headers) {
        std::unordered_map<std::string, std::string> claims;
        try {
            claims = ValidateJWTToken(headers);
        } catch (const std::exception& e) {
            throw std::runtime_error("Authorization token is invalid: " + std::string(e.what()));
        }

        std::vector<HeaderMutationItem> decodedItems;
        for (const auto& [key, value] : claims) {
            if (key == "iat" || key == "exp") {
                long long intVal = std::stoll(value);
                decodedItems.emplace_back(HeaderMutationItem{"decoded-" + key, std::to_string(intVal)});
            } else {
                decodedItems.emplace_back(HeaderMutationItem{"decoded-" + key, value});
            }
        }

        // Assuming AddHeaderMutation is defined in utils.h
        return extproc::ProcessingResponse{
            .request_headers = AddHeaderMutation(decodedItems, nullptr, true, nullptr)
        };
    }
};