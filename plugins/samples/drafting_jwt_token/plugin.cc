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

// [START serviceextensions_plugin_drafting_jwt_token]
#include <string>
#include <vector>
#include <map>
#include <sstream>
#include <chrono>
#include <openssl/hmac.h>
#include <openssl/evp.h>
#include <openssl/buffer.h>
#include "proxy_wasm_intrinsics.h"
#include "json.hpp"

using json = nlohmann::json;

// Base64 URL-safe encoding
std::string base64_url_encode(const unsigned char* buffer, size_t length) {
    BIO *bio, *b64;
    BUF_MEM *bufferPtr;

    b64 = BIO_new(BIO_f_base64());
    bio = BIO_new(BIO_s_mem());
    bio = BIO_push(b64, bio);

    BIO_set_flags(bio, BIO_FLAGS_BASE64_NO_NL);
    BIO_write(bio, buffer, length);
    BIO_flush(bio);
    BIO_get_mem_ptr(bio, &bufferPtr);

    std::string result(bufferPtr->data, bufferPtr->length);
    BIO_free_all(bio);

    // Convert to URL-safe base64
    for (char& c : result) {
        if (c == '+') c = '-';
        if (c == '/') c = '_';
    }
    
    // Remove padding
    result.erase(std::remove(result.begin(), result.end(), '='), result.end());
    
    return result;
}

// Base64 URL-safe decoding
std::string base64_url_decode(const std::string& input) {
    std::string base64 = input;
    
    // Convert from URL-safe to standard base64
    for (char& c : base64) {
        if (c == '-') c = '+';
        if (c == '_') c = '/';
    }
    
    // Add padding if needed
    while (base64.length() % 4) {
        base64 += '=';
    }
    
    BIO *bio, *b64;
    int decodeLen = base64.length();
    unsigned char* buffer = new unsigned char[decodeLen];
    
    bio = BIO_new_mem_buf(base64.c_str(), -1);
    b64 = BIO_new(BIO_f_base64());
    bio = BIO_push(b64, bio);
    
    BIO_set_flags(bio, BIO_FLAGS_BASE64_NO_NL);
    int length = BIO_read(bio, buffer, decodeLen);
    BIO_free_all(bio);
    
    std::string result(reinterpret_cast<char*>(buffer), length);
    delete[] buffer;
    
    return result;
}

// HMAC SHA256 signing
std::string hmac_sha256(const std::string& key, const std::string& data) {
    unsigned char* digest;
    unsigned int digest_len;
    
    digest = HMAC(EVP_sha256(), 
                  key.c_str(), key.length(),
                  reinterpret_cast<const unsigned char*>(data.c_str()), data.length(),
                  nullptr, &digest_len);
    
    return std::string(reinterpret_cast<char*>(digest), digest_len);
}

class JWTPluginContext : public Context {
public:
    explicit JWTPluginContext(uint32_t id, RootContext* root) : Context(id, root) {}

    FilterHeadersStatus onRequestHeaders(uint32_t headers, bool end_of_stream) override;
    
private:
    std::string generateJWT(const std::string& user_id, int expiration_minutes);
    std::string verifyJWT(const std::string& token);
    json getUserEntitlements(const std::string& user_id);
};

class JWTPluginRootContext : public RootContext {
public:
    explicit JWTPluginRootContext(uint32_t id, std::string_view root_id) 
        : RootContext(id, root_id) {}

    bool onConfigure(size_t config_size) override;
    bool onStart(size_t vm_configuration_size) override;

    std::string secret_key_;
    std::map<std::string, json> kv_store_;
    int default_expiration_ = 60; // minutes
};

bool JWTPluginRootContext::onConfigure(size_t config_size) {
    auto configuration_data = getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_size);
    
    try {
        auto config = json::parse(configuration_data->view());
        
        // Load secret key
        if (config.contains("secret_key")) {
            secret_key_ = config["secret_key"].get<std::string>();
        } else {
            LOG_WARN("No secret_key configured, using default (INSECURE)");
            secret_key_ = "default_secret_key_change_me";
        }
        
        // Load default expiration
        if (config.contains("default_expiration_minutes")) {
            default_expiration_ = config["default_expiration_minutes"].get<int>();
        }
        
        // Load KV Store data
        if (config.contains("data")) {
            kv_store_ = config["data"].get<std::map<std::string, json>>();
            LOG_INFO("Loaded " + std::to_string(kv_store_.size()) + " entries into KV store");
        }
        
        LOG_INFO("JWT Plugin configured successfully");
        return true;
        
    } catch (const std::exception& e) {
        LOG_ERROR("Configuration error: " + std::string(e.what()));
        return false;
    }
}

bool JWTPluginRootContext::onStart(size_t vm_configuration_size) {
    LOG_INFO("JWT Plugin started");
    return true;
}

json JWTPluginContext::getUserEntitlements(const std::string& user_id) {
    auto* root = dynamic_cast<JWTPluginRootContext*>(this->root());
    
    if (root->kv_store_.find(user_id) != root->kv_store_.end()) {
        return root->kv_store_[user_id];
    }
    
    // Return default/free tier if user not found
    json default_entitlements = {
        {"plan", "free"},
        {"permissions", json::array()}
    };
    
    return default_entitlements;
}

std::string JWTPluginContext::generateJWT(const std::string& user_id, int expiration_minutes) {
    auto* root = dynamic_cast<JWTPluginRootContext*>(this->root());
    
    // Get current time
    auto now = std::chrono::system_clock::now();
    auto now_seconds = std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count();
    
    // Calculate expiration and not-before times
    long exp = now_seconds + (expiration_minutes * 60);
    long nbf = now_seconds;
    
    // Create JWT header
    json header = {
        {"alg", "HS256"},
        {"typ", "JWT"}
    };
    
    // Get user entitlements from KV store
    json entitlements = getUserEntitlements(user_id);
    
    // Create JWT payload with registered and public claims
    json payload = {
        {"sub", user_id},
        {"exp", exp},
        {"nbf", nbf},
        {"iat", now_seconds}
    };
    
    // Merge user entitlements (public claims)
    if (entitlements.contains("plan")) {
        payload["plan"] = entitlements["plan"];
    }
    if (entitlements.contains("permissions")) {
        payload["permissions"] = entitlements["permissions"];
    }
    if (entitlements.contains("roles")) {
        payload["roles"] = entitlements["roles"];
    }
    
    // Encode header and payload
    std::string header_str = header.dump();
    std::string payload_str = payload.dump();
    
    std::string header_encoded = base64_url_encode(
        reinterpret_cast<const unsigned char*>(header_str.c_str()), 
        header_str.length()
    );
    
    std::string payload_encoded = base64_url_encode(
        reinterpret_cast<const unsigned char*>(payload_str.c_str()), 
        payload_str.length()
    );
    
    // Create signature
    std::string signing_input = header_encoded + "." + payload_encoded;
    std::string signature = hmac_sha256(root->secret_key_, signing_input);
    std::string signature_encoded = base64_url_encode(
        reinterpret_cast<const unsigned char*>(signature.c_str()), 
        signature.length()
    );
    
    // Assemble final JWT
    return signing_input + "." + signature_encoded;
}

std::string JWTPluginContext::verifyJWT(const std::string& token) {
    auto* root = dynamic_cast<JWTPluginRootContext*>(this->root());
    
    // Split token into parts
    std::vector<std::string> parts;
    std::stringstream ss(token);
    std::string part;
    
    while (std::getline(ss, part, '.')) {
        parts.push_back(part);
    }
    
    if (parts.size() != 3) {
        return "Invalid token format";
    }
    
    // Verify signature
    std::string signing_input = parts[0] + "." + parts[1];
    std::string expected_signature = hmac_sha256(root->secret_key_, signing_input);
    std::string expected_signature_encoded = base64_url_encode(
        reinterpret_cast<const unsigned char*>(expected_signature.c_str()), 
        expected_signature.length()
    );
    
    if (parts[2] != expected_signature_encoded) {
        return "Invalid signature";
    }
    
    // Decode and verify payload
    try {
        std::string payload_str = base64_url_decode(parts[1]);
        json payload = json::parse(payload_str);
        
        // Verify expiration
        auto now = std::chrono::system_clock::now();
        auto now_seconds = std::chrono::duration_cast<std::chrono::seconds>(
            now.time_since_epoch()
        ).count();
        
        if (payload.contains("exp") && payload["exp"].get<long>() < now_seconds) {
            return "Token expired";
        }
        
        // Verify not-before
        if (payload.contains("nbf") && payload["nbf"].get<long>() > now_seconds) {
            return "Token not yet valid";
        }
        
        return "valid";
        
    } catch (const std::exception& e) {
        return "Token verification failed: " + std::string(e.what());
    }
}

FilterHeadersStatus JWTPluginContext::onRequestHeaders(uint32_t headers, bool end_of_stream) {
    auto* root = dynamic_cast<JWTPluginRootContext*>(this->root());
    auto path = getRequestHeader(":path");
    auto method = getRequestHeader(":method");
    
    // Token generation endpoint
    if (path->view() == "/generate-token" && method->view() == "POST") {
        // Get user_id from header or body
        auto user_id_header = getRequestHeader("x-user-id");
        
        if (!user_id_header || user_id_header->view().empty()) {
            sendLocalResponse(400, "", "Missing x-user-id header", {});
            return FilterHeadersStatus::StopIteration;
        }
        
        std::string user_id(user_id_header->view());
        
        // Get optional expiration override
        int expiration = root->default_expiration_;
        auto exp_header = getRequestHeader("x-expiration-minutes");
        if (exp_header) {
            try {
                expiration = std::stoi(std::string(exp_header->view()));
            } catch (...) {
                // Use default if invalid
            }
        }
        
        // Generate JWT
        std::string jwt = generateJWT(user_id, expiration);
        
        // Return JWT in response
        json response = {
            {"token", jwt},
            {"expires_in", expiration * 60},
            {"token_type", "Bearer"}
        };
        
        sendLocalResponse(200, "", response.dump(), {
            {"content-type", "application/json"}
        });
        
        return FilterHeadersStatus::StopIteration;
    }
    
    // Token verification endpoint
    if (path->view() == "/verify-token" && method->view() == "GET") {
        auto auth_header = getRequestHeader("authorization");
        
        if (!auth_header || auth_header->view().empty()) {
            sendLocalResponse(401, "", "Missing Authorization header", {});
            return FilterHeadersStatus::StopIteration;
        }
        
        std::string auth(auth_header->view());
        
        // Extract Bearer token
        if (auth.substr(0, 7) != "Bearer ") {
            sendLocalResponse(401, "", "Invalid Authorization format", {});
            return FilterHeadersStatus::StopIteration;
        }
        
        std::string token = auth.substr(7);
        std::string verification_result = verifyJWT(token);
        
        if (verification_result == "valid") {
            json response = {
                {"valid", true},
                {"message", "Token is valid"}
            };
            sendLocalResponse(200, "", response.dump(), {
                {"content-type", "application/json"}
            });
        } else {
            json response = {
                {"valid", false},
                {"message", verification_result}
            };
            sendLocalResponse(401, "", response.dump(), {
                {"content-type", "application/json"}
            });
        }
        
        return FilterHeadersStatus::StopIteration;
    }
    
    // For other requests, validate token if present
    auto auth_header = getRequestHeader("authorization");
    if (auth_header && !auth_header->view().empty()) {
        std::string auth(auth_header->view());
        
        if (auth.substr(0, 7) == "Bearer ") {
            std::string token = auth.substr(7);
            std::string verification_result = verifyJWT(token);
            
            if (verification_result != "valid") {
                sendLocalResponse(401, "", "Unauthorized: " + verification_result, {});
                return FilterHeadersStatus::StopIteration;
            }
            
            // Token is valid, add user info to headers for downstream services
            try {
                std::vector<std::string> parts;
                std::stringstream ss(token);
                std::string part;
                
                while (std::getline(ss, part, '.')) {
                    parts.push_back(part);
                }
                
                if (parts.size() == 3) {
                    std::string payload_str = base64_url_decode(parts[1]);
                    json payload = json::parse(payload_str);
                    
                    if (payload.contains("sub")) {
                        addRequestHeader("x-jwt-user", payload["sub"].get<std::string>());
                    }
                    if (payload.contains("plan")) {
                        addRequestHeader("x-jwt-plan", payload["plan"].get<std::string>());
                    }
                }
            } catch (...) {
                // Continue even if header extraction fails
            }
        }
    }
    
    return FilterHeadersStatus::Continue;
}

static RegisterContextFactory register_JWTPlugin(
    CONTEXT_FACTORY(JWTPluginContext),
    ROOT_FACTORY(JWTPluginRootContext)
);
// [END serviceextensions_plugin_drafting_jwt_token]
