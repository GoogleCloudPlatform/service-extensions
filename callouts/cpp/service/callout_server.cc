// Copyright 2023 Google LLC
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

#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/server_context.h>

#include <memory>
#include <string>

#include "absl/log/log.h"
#include "envoy/service/ext_proc/v3/external_processor.grpc.pb.h"
#include "envoy/service/ext_proc/v3/external_processor.pb.h"

using envoy::service::ext_proc::v3::ExternalProcessor;
using envoy::service::ext_proc::v3::ProcessingRequest;
using envoy::service::ext_proc::v3::ProcessingResponse;

class EnvoyExtProcServer final : public ExternalProcessor::Service {
 public:
  grpc::Status Process(
      grpc::ServerContext* context,
      grpc::ServerReaderWriter<ProcessingResponse, ProcessingRequest>* stream)
      override {
    (void)context;

    ProcessingRequest request;
    while (stream->Read(&request)) {
      ProcessingResponse response;
      ProcessRequest(&request, &response);
      stream->Write(response);
    }

    return grpc::Status::OK;
  }

  virtual void OnRequestHeader(ProcessingRequest* request,
                               ProcessingResponse* response) {}

  virtual void OnResponseHeader(ProcessingRequest* request,
                                ProcessingResponse* response) {}

  virtual void OnRequestBody(ProcessingRequest* request,
                             ProcessingResponse* response) {}

  virtual void OnResponseBody(ProcessingRequest* request,
                              ProcessingResponse* response) {}

 private:
  void ProcessRequest(ProcessingRequest* request,
                      ProcessingResponse* response) {
    switch (request->request_case()) {
      case ProcessingRequest::RequestCase::kRequestHeaders:
        this->OnRequestHeader(request, response);
        break;
      case ProcessingRequest::RequestCase::kResponseHeaders:
        this->OnResponseHeader(request, response);
        break;
      case ProcessingRequest::RequestCase::kRequestBody:
        this->OnRequestBody(request, response);
        break;
      case ProcessingRequest::RequestCase::kResponseBody:
        this->OnResponseBody(request, response);
        break;
      case ProcessingRequest::RequestCase::kRequestTrailers:
      case ProcessingRequest::RequestCase::kResponseTrailers:
        break;
      case ProcessingRequest::RequestCase::REQUEST_NOT_SET:
      default:
        LOG(WARNING) << "Received a ProcessingRequest with no request data.";
        break;
    }
  }
};

void RunServer(std::string server_address) {
  EnvoyExtProcServer service;

  grpc::ServerBuilder builder;
  builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
  builder.RegisterService(&service);

  std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
  LOG(INFO) << "Envoy Ext Proc server listening on " << server_address;

  server->Wait();
}

int main(int argc, char** argv) {
  std::string server_address("localhost:50052");

  RunServer(server_address);

  return 0;
}