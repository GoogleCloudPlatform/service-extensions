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

#include <boost/asio.hpp>
#include <boost/beast.hpp>

#include "absl/flags/flag.h"
#include "absl/flags/parse.h"
#include "absl/log/log.h"
#include "callout_server.h"

ABSL_FLAG(std::string, server_address, "0.0.0.0:443",
          "The gRPC server address, like '0.0.0.0:443'");
ABSL_FLAG(uint16_t, health_check_port, 80,
          "The HTTP health check server port");
ABSL_FLAG(std::string, key_path, "ssl_creds/privatekey.pem",
          "The SSL private key file path");
ABSL_FLAG(std::string, cert_path, "ssl_creds/chain.pem",
          "The SSL certificate file path");

void StartHttpHealthCheckServer(uint16_t port) {
  namespace beast = boost::beast;
  namespace http = beast::http;
  namespace asio = boost::asio;
  using tcp = asio::ip::tcp;
  
  asio::io_context io_context;
  tcp::acceptor acceptor(io_context, {tcp::v4(), port});

  LOG(INFO) << "Health check service started on port: " << port;

  while (true) {
    tcp::socket socket(io_context);
    acceptor.accept(socket);

    beast::flat_buffer buffer;
    http::request<http::string_body> request;
    http::read(socket, buffer, request);

    http::response<http::string_body> response;
    response.version(request.version());
    response.result(http::status::ok);
    response.set(http::field::content_type, "text/plain");
    response.body() = "";
    response.prepare_payload();
    http::write(socket, response);

    socket.shutdown(tcp::socket::shutdown_send);
  }
}

int main(int argc, char** argv) {
  absl::ParseCommandLine(argc, argv);
  
  auto config = CalloutServer::DefaultConfig();
  config.secure_address = absl::GetFlag(FLAGS_server_address);
  config.key_path = absl::GetFlag(FLAGS_key_path);
  config.cert_path = absl::GetFlag(FLAGS_cert_path);

  if (!config.key_path.empty() && !config.cert_path.empty()) {
    LOG(INFO) << "Starting server with secure (TLS) mode";
  } else if (config.enable_insecure) {
    LOG(WARNING) << "Starting server in INSECURE (plaintext) mode";
  } else {
    LOG(ERROR) << "No valid configuration: secure credentials missing and insecure mode disabled";
    return 1;
  }

  std::thread health_check_thread(
      StartHttpHealthCheckServer, 
      absl::GetFlag(FLAGS_health_check_port));

  CalloutServer::RunServers(config);

  health_check_thread.join();
  return 0;
}