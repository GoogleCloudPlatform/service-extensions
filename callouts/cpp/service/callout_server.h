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

#ifndef SERVICE_CALLOUT_SERVER_H_
#define SERVICE_CALLOUT_SERVER_H_

#include <atomic>
#include <condition_variable>
#include <fstream>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

#include <grpcpp/alarm.h>
#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/server_context.h>

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

// Forward declaration
template <typename ProcessorType>
class CallData;

/**
 * @class CalloutServer
 * @brief Base class for implementing custom async HTTP request/response processing logic
 *
 * Override the virtual methods to implement custom processing.
 * This class provides static helper methods for building responses
 * and virtual callback methods for processing requests.
 */
class CalloutServer {
 public:
  virtual ~CalloutServer() = default;

  /**
   * @brief Adds a header to the HTTP request
   * @param response The ProcessingResponse to modify
   * @param key Header name to add
   * @param value Header value to add
   */
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
   * @brief Handle HTTP request headers (override for custom processing)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnRequestHeader(ProcessingRequest* request,
                               ProcessingResponse* response) {}

  /**
   * @brief Handle HTTP response headers (override for custom processing)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnResponseHeader(ProcessingRequest* request,
                                ProcessingResponse* response) {}

  /**
   * @brief Handle HTTP request body (override for custom processing)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnRequestBody(ProcessingRequest* request,
                             ProcessingResponse* response) {}

  /**
   * @brief Handle HTTP response body (override for custom processing)
   * @param request Incoming processing request
   * @param response Output response to populate
   */
  virtual void OnResponseBody(ProcessingRequest* request,
                              ProcessingResponse* response) {}

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

/**
 * @class CallData
 * @brief Manages the lifecycle of a single async gRPC call
 *
 * Implements the state machine for bidirectional streaming:
 * INIT -> READING -> WRITING -> READING -> ... -> DONE
 *
 * Uses a recycling model: after completing a call, the CallData
 * re-registers for the next RPC instead of spawning new handlers.
 */
template <typename ProcessorType>
class CallData {
 public:
  enum CallStatus {
    INIT,       // Waiting for new RPC
    READING,    // Async Read in progress
    WRITING,    // Async Write in progress
    FINISHING,  // Finishing the stream
    DONE        // Ready to recycle
  };

  CallData(ExternalProcessor::AsyncService* service,
           grpc::ServerCompletionQueue* cq)
      : service_(service),
        cq_(cq),
        stream_(&ctx_),
        status_(INIT) {
    processor_ = std::make_unique<ProcessorType>();
    // Register for incoming RPC
    service_->RequestProcess(&ctx_, &stream_, cq_, cq_, this);
  }

  void Proceed(bool ok) {
    switch (status_) {
      case INIT:
        if (!ok) {
          // Server shutting down or error
          delete this;
          return;
        }
        // New RPC arrived, start reading
        status_ = READING;
        stream_.Read(&request_, this);
        break;

      case READING:
        if (!ok) {
          // Stream finished (client done sending) - finish and recycle
          status_ = FINISHING;
          stream_.Finish(grpc::Status::OK, this);
          return;
        }
        // Process the request
        response_.Clear();
        processor_->ProcessRequest(&request_, &response_);
        // Write response
        status_ = WRITING;
        stream_.Write(response_, this);
        break;

      case WRITING:
        if (!ok) {
          // Write failed, finish and recycle
          status_ = FINISHING;
          stream_.Finish(grpc::Status::OK, this);
          return;
        }
        // Write completed, read next message
        request_.Clear();
        status_ = READING;
        stream_.Read(&request_, this);
        break;

      case FINISHING:
        // Stream finished, recycle this handler
        Recycle();
        break;

      case DONE:
        // Should not reach here
        delete this;
        break;
    }
  }

 private:
  void Recycle() {
    // Reset state and re-register for next RPC
    ctx_.~ServerContext();
    new (&ctx_) grpc::ServerContext();
    stream_.~ServerAsyncReaderWriter();
    new (&stream_) grpc::ServerAsyncReaderWriter<ProcessingResponse, ProcessingRequest>(&ctx_);
    request_.Clear();
    response_.Clear();
    status_ = INIT;
    service_->RequestProcess(&ctx_, &stream_, cq_, cq_, this);
  }

  ExternalProcessor::AsyncService* service_;
  grpc::ServerCompletionQueue* cq_;
  grpc::ServerContext ctx_;
  grpc::ServerAsyncReaderWriter<ProcessingResponse, ProcessingRequest> stream_;

  ProcessingRequest request_;
  ProcessingResponse response_;
  std::unique_ptr<ProcessorType> processor_;

  CallStatus status_;
};

/**
 * @class CalloutServerRunner
 * @brief Async gRPC server using CompletionQueue
 *
 * This class manages the async gRPC server lifecycle with:
 * - Multiple CompletionQueues for better throughput
 * - Multi-threaded handler pool
 * - Handler recycling model
 */
class CalloutServerRunner {
 public:
  struct ServerConfig {
    std::string secure_address;
    std::string plaintext_address;
    std::string health_check_address;
    std::string cert_path;
    std::string key_path;
    bool enable_plaintext;
    bool enable_tls;
    int num_threads;
  };

  static ServerConfig DefaultConfig() {
    return {
        .secure_address = "0.0.0.0:443",
        .plaintext_address = "0.0.0.0:8080",
        .health_check_address = "0.0.0.0:80",
        .cert_path = "ssl_creds/chain.pem",
        .key_path = "ssl_creds/privatekey.pem",
        .enable_plaintext = true,
        .enable_tls = false,
        .num_threads = 0  // 0 means use hardware concurrency
    };
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

  template <typename ProcessorType>
  static void RunServers(const ServerConfig& config = ServerConfig{}) {
    int num_threads = config.num_threads > 0
        ? config.num_threads
        : std::thread::hardware_concurrency();

    // Use multiple completion queues - one per thread
    // This eliminates CQ contention and improves cache locality
    const int num_cqs = num_threads;

    LOG(INFO) << "Starting async gRPC server with " << num_threads
              << " threads and " << num_cqs << " completion queues";

    grpc::ServerBuilder builder;
    ExternalProcessor::AsyncService service;

    // Message sizes (4MB)
    builder.SetMaxReceiveMessageSize(4 * 1024 * 1024);
    builder.SetMaxSendMessageSize(4 * 1024 * 1024);

    // High concurrency settings
    builder.AddChannelArgument(GRPC_ARG_MAX_CONCURRENT_STREAMS, 2500);
    builder.AddChannelArgument(GRPC_ARG_ALLOW_REUSEPORT, 1);

    // HTTP/2 tuning
    builder.AddChannelArgument(GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA, 0);
    builder.AddChannelArgument(
        GRPC_ARG_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS, 10000);

    // Keepalive settings for connection health
    builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_TIME_MS, 30000);
    builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_TIMEOUT_MS, 60000);
    builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS, 1);

    // Resource quota allows headroom above thread count
    grpc::ResourceQuota quota("server_quota");
    quota.SetMaxThreads(num_threads * 2);
    builder.SetResourceQuota(quota);

    // Add listening ports
    if (config.enable_plaintext && !config.plaintext_address.empty()) {
      builder.AddListeningPort(config.plaintext_address,
                               grpc::InsecureServerCredentials());
      LOG(INFO) << "Plaintext server will listen on " << config.plaintext_address;
    }

    if (config.enable_tls && !config.secure_address.empty()) {
      auto creds = CreateSecureServerCredentials(config.key_path,
                                                  config.cert_path);
      if (creds) {
        builder.AddListeningPort(config.secure_address, *creds);
        LOG(INFO) << "Secure server will listen on " << config.secure_address;
      }
    }

    builder.RegisterService(&service);

    // Create completion queues
    std::vector<std::unique_ptr<grpc::ServerCompletionQueue>> cqs;
    for (int i = 0; i < num_cqs; ++i) {
      cqs.push_back(builder.AddCompletionQueue());
    }

    server_ = builder.BuildAndStart();
    if (!server_) {
      LOG(ERROR) << "Failed to start server";
      return;
    }

    LOG(INFO) << "Async server started";

    // Pre-allocate handlers per CQ.
    // Each handler manages one concurrent RPC stream via the recycling model.
    const int initial_handlers_per_cq = 64;
    LOG(INFO) << "Pre-allocating " << initial_handlers_per_cq << " handlers per CQ ("
              << (initial_handlers_per_cq * num_cqs) << " total)";
    for (int i = 0; i < num_cqs; ++i) {
      for (int j = 0; j < initial_handlers_per_cq; ++j) {
        new CallData<ProcessorType>(&service, cqs[i].get());
      }
    }

    // Start worker threads - multiple threads can poll the same CQ
    std::vector<std::thread> threads;
    for (int i = 0; i < num_threads; ++i) {
      // Round-robin assign threads to completion queues
      threads.emplace_back([cq = cqs[i % num_cqs].get()]() {
        HandleRpcs<ProcessorType>(cq);
      });
    }

    server_ready_ = true;

    // Wait for shutdown signal
    while (!shutdown_requested_) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    // Shutdown
    server_->Shutdown();
    for (auto& cq : cqs) {
      cq->Shutdown();
    }

    // Join all threads
    for (auto& t : threads) {
      if (t.joinable()) {
        t.join();
      }
    }

    // Drain completion queues
    for (auto& cq : cqs) {
      void* tag;
      bool ok;
      while (cq->Next(&tag, &ok)) {
        // Drain remaining events
      }
    }
  }

  static void Shutdown() {
    shutdown_requested_ = true;
  }

  static bool IsReady() {
    return server_ready_.load();
  }

 private:
  template <typename ProcessorType>
  static void HandleRpcs(grpc::ServerCompletionQueue* cq) {
    void* tag;
    bool ok;
    while (cq->Next(&tag, &ok)) {
      static_cast<CallData<ProcessorType>*>(tag)->Proceed(ok);
    }
  }

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

  static inline std::unique_ptr<grpc::Server> server_;
  static inline std::atomic<bool> server_ready_{false};
  static inline std::atomic<bool> shutdown_requested_{false};
};

#endif  // SERVICE_CALLOUT_SERVER_H_
