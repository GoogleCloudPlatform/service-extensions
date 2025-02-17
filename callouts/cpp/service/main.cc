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

#include <grpcpp/grpcpp.h>

#include "absl/flags/flag.h"
#include "absl/flags/parse.h"
#include "absl/log/log.h"
#include "custom_callout_server.h"

ABSL_FLAG(std::string, server_address, "0.0.0.0:8443",
          "The gRPC server addess, like '0.0.0.0:8443'");
ABSL_FLAG(std::string, health_check_address, "0.0.0.0:8080",
          "The HTTP health check server addess, like '0.0.0.0:8080'");
ABSL_FLAG(std::string, key_path, "ssl_creds/privatekey.pem",
          "The SSL private key file path");
ABSL_FLAG(std::string, cert_path, "ssl_creds/chain.pem",
          "The SSL certificate file path");

int main(int argc, char** argv) {
  absl::ParseCommandLine(argc, argv);
  std::string server_address = absl::GetFlag(FLAGS_server_address);
  std::string health_check_address = absl::GetFlag(FLAGS_health_check_address);
  std::string key_path = absl::GetFlag(FLAGS_key_path);
  std::string cert_path = absl::GetFlag(FLAGS_cert_path);

  std::shared_ptr<grpc::ServerCredentials> secure_credentials =
      grpc::InsecureServerCredentials();

  if (key_path != "" && cert_path != "") {
    auto maybe_secure_credentials =
        CalloutServer::CreateSecureServerCredentials(key_path, cert_path);
    if (!maybe_secure_credentials) {
      return 1;
    }
    secure_credentials = maybe_secure_credentials.value();
    LOG(INFO) << "Envoy Ext Proc using secure credentials";
  } else {
    LOG(INFO) << "Envoy Ext Proc using insecure credentials";
  }

  CustomCalloutServer service;
  CalloutServer::RunServer(server_address, service, secure_credentials, true);

  return 0;
}