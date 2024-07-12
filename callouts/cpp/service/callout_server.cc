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

#include <envoy/service/ext_proc/v3/external_processor.grpc.pb.h>
#include <envoy/service/ext_proc/v3/external_processor.pb.h>
#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/server_context.h>

#include <memory>
#include <string>

class EnvoyExtProcServer final
    : public envoy::service::ext_proc::v3::ExternalProcessor::Service {
 public:
  grpc::Status Process(
      grpc::ServerContext* context,
      grpc::ServerReaderWriter<envoy::service::ext_proc::v3::ProcessingResponse,
                               envoy::service::ext_proc::v3::ProcessingRequest>*
          stream) override {
    (void)context;

    envoy::service::ext_proc::v3::ProcessingRequest request;
    while (stream->Read(&request)) {
      envoy::service::ext_proc::v3::ProcessingResponse response;
      ProcessRequest(&request, &response);
      stream->Write(response);
    }

    return grpc::Status::OK;
  }

 private:
  void ProcessRequest(
      envoy::service::ext_proc::v3::ProcessingRequest* request,
      envoy::service::ext_proc::v3::ProcessingResponse* response) {
      switch (request->request_case())
      {
      case envoy::service::ext_proc::v3::ProcessingRequest::RequestCase::kRequestHeaders:
        /* code */
        break;
      default:
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
  std::cout << "Envoy Ext Proc server listening on " << server_address
            << std::endl;

  server->Wait();
}

int main(int argc, char** argv) {
  std::string server_address("localhost:50052");

  RunServer(server_address);

  return 0;
}