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

#ifndef CALLOUT_SERVER_H_
#define CALLOUT_SERVER_H_

#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/server_context.h>

#include <atomic>
#include <condition_variable>
#include <fstream>
#include <memory>
#include <mutex>
#include <thread>

#include "absl/log/log.h"
#include "absl/status/statusor.h"
#include "absl/strings/str_cat.h"
#include "envoy/service/ext_proc/v3/external_processor.grpc.pb.h"
#include "envoy/service/ext_proc/v3/external_processor.pb.h"

using envoy::config::core::v3::HeaderValue;
using envoy::config::core::v3::HeaderValueOption;
using envoy::service::ext_proc::v3::BodyMutation;
using envoy::service::ext_proc::v3::ExternalProcessor;
using envoy::service::ext_proc::v3::HeaderMutation;
using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

/**
 * @class CalloutServer
 * @brief Base class for implementing custom HTTP request/response processing logic
 * 
 * Provides default implementations for header/body processing operations and gRPC server setup.
 */
class CalloutServer : public ExternalProcessor::Service {
 public:
  struct ServerConfig {
    std::string secure_address;
    std::string plaintext_address;
    std::string health_check_address;
    std::string cert_path;
    std::string key_path;
    bool enable_plaintext;
    bool enable_tls;
  };

  static ServerConfig DefaultConfig() {
    return {
        .secure_address = "0.0.0.0:443",
        .plaintext_address = "0.0.0.0:8080",
        .health_check_address = "0.0.0.0:80",
        .cert_path = "ssl_creds/chain.pem",
        .key_path = "ssl_creds/privatekey.pem",
        .enable_plaintext = true,
        .enable_tls = false};
  }

  // Adds a request header field.
  static void AddRequestHeader(ProcessingResponse* response,
                               std::string_view key, std::string_view value) {
    HeaderValue* new_header = response->mutable_request_headers()
                                  ->mutable_response()
                                  ->mutable_header_mutation()
                                  ->add_set_headers()
                                  ->mutable_header();
    new_header->set_key(key);
    new_header->set_value(value);
  }

  /**
   * @brief Replaces or adds a header in the HTTP request
   * @param response The ProcessingResponse to modify
   * @param key Header name to replace
   * @param value New header value
   */
  static void ReplaceRequestHeader(ProcessingResponse* response,
                                   std::string_view key,
                                   std::string_view value) {
    HeaderValueOption* new_header_option = response->mutable_request_headers()
                                               ->mutable_response()
                                               ->mutable_header_mutation()
                                               ->add_set_headers();
    new_header_option->set_append_action(
        HeaderValueOption::OVERWRITE_IF_EXISTS_OR_ADD);
    HeaderValue* new_header = new_header_option->mutable_header();
    new_header->set_key(key);
    new_header->set_value(value);
  }

  /**
   * @brief Adds a header to the HTTP response
   * @param response The ProcessingResponse to modify
   * @param key Header name to add
   * @param value Header value to add
   */
  static void AddResponseHeader(ProcessingResponse* response,
                                std::string_view key, std::string_view value) {
    HeaderValue* new_header = response->mutable_response_headers()
                                  ->mutable_response()
                                  ->mutable_header_mutation()
                                  ->add_set_headers()
                                  ->mutable_header();
    new_header->set_key(key);
    new_header->set_value(value);
  }

  /**
   * @brief Replaces or adds a header in the HTTP response
   * @param response The ProcessingResponse to modify
   * @param key Header name to replace
   * @param value New header value
   */
  static void ReplaceResponseHeader(ProcessingResponse* response,
                                    std::string_view key,
                                    std::string_view value) {
    HeaderValueOption* new_header_option = response->mutable_response_headers()
                                               ->mutable_response()
                                               ->mutable_header_mutation()
                                               ->add_set_headers();
    new_header_option->set_append_action(
        HeaderValueOption::OVERWRITE_IF_EXISTS_OR_ADD);
    HeaderValue* new_header = new_header_option->mutable_header();
    new_header->set_key(key);
    new_header->set_value(value);
  }

  /**
   * @brief Removes a header from the HTTP response
   * @param response The ProcessingResponse to modify
   * @param header_name Name of the header to remove
   */
  static void RemoveResponseHeader(ProcessingResponse* response,
                                   std::string_view header_name) {
    auto* headers_mutation = response->mutable_response_headers()
                                 ->mutable_response()
                                 ->mutable_header_mutation();
    headers_mutation->add_remove_headers(header_name);
  }

  /**
   * @brief Replaces the HTTP request body
   * @param response The ProcessingResponse to modify
   * @param body New body content
   */
  static void ReplaceRequestBody(ProcessingResponse* response,
                                 std::string_view body) {
    response->mutable_request_body()
        ->mutable_response()
        ->mutable_body_mutation()
        ->set_body(body);
  }

  /**
   * @brief Replaces the HTTP response body
   * @param response The ProcessingResponse to modify
   * @param body New body content
   */
  static void ReplaceResponseBody(ProcessingResponse* response,
                                  std::string_view body) {
    response->mutable_response_body()
        ->mutable_response()
        ->mutable_body_mutation()
        ->set_body(body);
  }

  /**
   * @brief Creates SSL credentials for secure server communication
   * @param key_path Path to private key file
   * @param cert_path Path to certificate file
   * @return Optional containing server credentials or nullopt on error
   */
  static std::optional<std::shared_ptr<grpc::ServerCredentials>>
  CreateSecureServerCredentials(std::string_view key_path,
                                std::string_view cert_path) {
    auto key = ReadDataFile(key_path);
    if (!key.ok()) {
      LOG(ERROR) << "Error reading the private key file on " << key_path;
      return std::nullopt;
    }
    auto cert = ReadDataFile(cert_path);
    if (!cert.ok()) {
      LOG(ERROR) << "Error reading the certificate file on " << cert_path;
      return std::nullopt;
    }

    grpc::SslServerCredentialsOptions::PemKeyCertPair key_cert_pair;
    key_cert_pair.private_key = *key;
    key_cert_pair.cert_chain = *cert;

    grpc::SslServerCredentialsOptions ssl_options;
    ssl_options.pem_key_cert_pairs.push_back(key_cert_pair);
    return grpc::SslServerCredentials(ssl_options);
  }

  template <typename ServerType = CalloutServer>
  static bool RunServers(const ServerConfig& config = ServerConfig{}) {
    std::unique_lock<std::mutex> lock(server_mutex_);
    bool server_started = false;
  
    // Start secure server only if TLS is enabled and credentials are available
    if (config.enable_tls && !config.secure_address.empty()) {
      auto creds = CreateSecureServerCredentials(config.key_path, config.cert_path);
      if (creds) {
        secure_thread_ = std::thread([config, creds]() {
          std::unique_ptr<grpc::Server> local_server;
          auto service = std::make_unique<ServerType>();
          {
            grpc::ServerBuilder builder;
            builder.AddListeningPort(config.secure_address, *creds);
            builder.RegisterService(service.get());
            local_server = builder.BuildAndStart();
          }
  
          {
            std::lock_guard<std::mutex> lock(server_mutex_);
            secure_server_.reset(local_server.release());
            server_ready_ = true;
          }
          server_cv_.notify_one();
  
          if (secure_server_) {
            LOG(INFO) << "Secure server listening on " << config.secure_address;
            secure_server_->Wait();
          }
  
          {
            std::lock_guard<std::mutex> lock(server_mutex_);
            if (shutdown_requested_) {
              secure_server_.reset();
            }
          }
        });
        server_started = true;
      }
    }
  
    // Start plaintext server if enabled
    if (config.enable_plaintext && !plaintext_server_) {
      plaintext_thread_ = std::thread([config]() {
        std::unique_ptr<grpc::Server> local_server;
        auto service = std::make_unique<ServerType>();
        {
          grpc::ServerBuilder builder;
          builder.AddListeningPort(config.plaintext_address,
                                  grpc::InsecureServerCredentials());
          builder.RegisterService(service.get());
          local_server = builder.BuildAndStart();
        }
  
        {
          std::lock_guard<std::mutex> lock(server_mutex_);
          plaintext_server_.reset(local_server.release());
          server_ready_ = true;
        }
        server_cv_.notify_one();
  
        if (plaintext_server_) {
          LOG(INFO) << "Plaintext server listening on " << config.plaintext_address;
          plaintext_server_->Wait();
        }
  
        {
          std::lock_guard<std::mutex> lock(server_mutex_);
          if (shutdown_requested_) {
            plaintext_server_.reset();
          }
        }
      });
      server_started = true;
    }
  
    if (server_started) {
      server_cv_.wait(lock, [] { return server_ready_.load(); });
    }
    return server_started;
  }

  static void Shutdown() {
    std::unique_lock<std::mutex> lock(server_mutex_);
    shutdown_requested_ = true;
    if (plaintext_server_) {
      plaintext_server_->Shutdown();
    }
    if (secure_server_) {
      secure_server_->Shutdown();
    }
  }
  
  static void WaitForCompletion() {
    if (plaintext_thread_.joinable()) {
      plaintext_thread_.join();
    }
    if (secure_thread_.joinable()) {
      secure_thread_.join();
    }
    std::lock_guard<std::mutex> lock(server_mutex_);
    plaintext_server_.reset();
    secure_server_.reset();
  }

  /**
   * @brief Main processing loop for handling gRPC streams
   * @param context Server context
   * @param stream Bidirectional gRPC stream
   * @return gRPC status
   */
  grpc::Status Process(
      grpc::ServerContext* context,
      grpc::ServerReaderWriter<ProcessingResponse, ProcessingRequest>* stream)
      override {
    ProcessingRequest request;
    while (stream->Read(&request)) {
      ProcessingResponse response;
      ProcessRequest(&request, &response);
      stream->Write(response);
    }
    return grpc::Status::OK;
  }

  /**
   * @brief Handle HTTP request headers (to be overridden)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnRequestHeader(ProcessingRequest* request,
                               ProcessingResponse* response) {
    LOG(INFO) << "OnRequestHeader called.";
  }

  /**
   * @brief Handle HTTP response headers (to be overridden)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnResponseHeader(ProcessingRequest* request,
                                ProcessingResponse* response) {
    LOG(INFO) << "OnResponseHeader called.";
  }

  /**
   * @brief Handle HTTP request body (to be overridden)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnRequestBody(ProcessingRequest* request,
                             ProcessingResponse* response) {
    LOG(INFO) << "OnRequestBody called.";
  }

  /**
   * @brief Handle HTTP response body (to be overridden)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnResponseBody(ProcessingRequest* request,
                              ProcessingResponse* response) {
    LOG(INFO) << "OnResponseBody called.";
  }

 private:
  static inline std::shared_ptr<grpc::Server> plaintext_server_ = nullptr;
  static inline std::shared_ptr<grpc::Server> secure_server_ = nullptr;
  static inline std::thread secure_thread_;
  static inline std::thread plaintext_thread_;
  static inline std::mutex server_mutex_;
  static inline std::condition_variable server_cv_;
  static inline std::atomic<bool> server_ready_{false};
  static inline std::atomic<bool> shutdown_requested_{false};

  static absl::StatusOr<std::string> ReadDataFile(std::string_view path) {
    std::ifstream file(std::string{path}, std::ios::binary);
    if (file.fail()) {
      return absl::NotFoundError(
          absl::StrCat("failed to open: ", path, ", error: ", strerror(errno)));
    }
    std::stringstream file_string_stream;
    file_string_stream << file.rdbuf();
    return file_string_stream.str();
  }

  void ProcessRequest(ProcessingRequest* request, ProcessingResponse* response) {
    switch (request->request_case()) {
      case ProcessingRequest::kRequestHeaders:
        OnRequestHeader(request, response);
        break;
      case ProcessingRequest::kResponseHeaders:
        OnResponseHeader(request, response);
        break;
      case ProcessingRequest::kRequestBody:
        OnRequestBody(request, response);
        break;
      case ProcessingRequest::kResponseBody:
        OnResponseBody(request, response);
        break;
      default:
        LOG(WARNING) << "Received a ProcessingRequest with no request data.";
        break;
    }
  }
};

#endif  // CALLOUT_SERVER_H_