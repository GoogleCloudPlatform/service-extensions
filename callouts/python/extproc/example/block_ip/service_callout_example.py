# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import ipaddress
import traceback
from concurrent import futures
import grpc
from grpc import ServicerContext
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.service.auth.v3 import external_auth_pb2_grpc as auth_pb2_grpc
from envoy.config.core.v3 import base_pb2
from google.rpc import status_pb2
from envoy.type.v3 import http_status_pb2


class CalloutServerExample(auth_pb2_grpc.AuthorizationServicer):
    """External authorization server implementing IP-based access control."""

    # Blocked IP range (CIDR notation)
    BLOCKED_IP_RANGE = ipaddress.ip_network('10.0.0.0/24')

    def Check(self, request: auth_pb2.CheckRequest, context: ServicerContext) -> auth_pb2.CheckResponse:
        """Main authorization method implementing the IP-based access control logic."""
        try:
            client_ip = self.extract_client_ip(request)
            
            if client_ip and self.is_ip_blocked(client_ip):
                logging.info(f"Request denied for blocked IP: {client_ip}")
                return self.deny_request(client_ip, False)
            else:
                logging.info(f"Request allowed for IP: {client_ip}")
                return self.allow_request(client_ip, True)
        except Exception as e:
            logging.error(f"Error in Check method: {str(e)}")
            logging.error(traceback.format_exc())
            raise

    def extract_client_ip(self, request: auth_pb2.CheckRequest) -> str:
        """Extracts the client IP address from the 'x-forwarded-for' header."""
        headers = request.attributes.request.http.headers
        xff_header = headers.get('x-forwarded-for', '')
        
        if xff_header:
            return xff_header.split(',')[0].strip()
        return None

    def is_ip_blocked(self, ip_str: str) -> bool:
        """Checks if the given IP address is within the blocked range."""
        try:
            ip_addr = ipaddress.ip_address(ip_str)
            return ip_addr in self.BLOCKED_IP_RANGE
        except ValueError:
            logging.warning(f"Invalid IP address: {ip_str}")
            return False

    def allow_request(self, client_ip: str, allowed: bool) -> auth_pb2.CheckResponse:
        """Creates an OK response with the 'x-client-ip-allowed' header."""
        headers = self.create_headers(client_ip, allowed)
        
        ok_response = auth_pb2.OkHttpResponse(
            headers=headers
        )
        
        return auth_pb2.CheckResponse(
            ok_response=ok_response
        )

    def deny_request(self, client_ip: str, allowed: bool) -> auth_pb2.CheckResponse:
        """Creates a denied response with the 'x-client-ip-allowed' header."""
        try:
            status = http_status_pb2.HttpStatus(code=http_status_pb2.StatusCode.Forbidden)
            headers = self.create_headers(client_ip, allowed)
            
            denied_response = auth_pb2.DeniedHttpResponse(
                status=status,
                headers=headers
            )
            
            return auth_pb2.CheckResponse(
                denied_response=denied_response
            )
            
        except Exception as e:
            logging.error(f"Error in deny_request: {str(e)}")
            logging.error(traceback.format_exc())
            raise

    def create_headers(self, client_ip: str, allowed: bool) -> list:
        """Creates the 'x-client-ip-allowed' header with the authorization decision."""
        header_value = base_pb2.HeaderValue(
            key='x-client-ip-allowed',
            value=str(allowed).lower()
        )
        
        header_option = base_pb2.HeaderValueOption(header=header_value)
        
        return [header_option]

    def __init__(self, *args, **kwargs):
        super().__init__()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthorizationServicer_to_server(CalloutServerExample(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    serve()
