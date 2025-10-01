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
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from service.callout_server import CalloutServerAuth
from service.callout_tools import allow_request, deny_request
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.type.v3 import http_status_pb2

class CalloutServerExample(CalloutServerAuth):
    """External authorization server implementing IP-based access control."""

    BLOCKED_IP_RANGE = ipaddress.ip_network('10.0.0.0/24')

    def on_check(self, request: auth_pb2.CheckRequest, context) -> auth_pb2.CheckResponse:
        try:
            client_ip = self.extract_client_ip(request)
            
            # Reject if no client IP could be extracted
            if client_ip is None:
                logging.info("Request denied: could not extract client IP")
                return deny_request(
                    status_code=http_status_pb2.StatusCode.Forbidden,
                    headers=[('x-client-ip-allowed', 'false')]
                )
            
            # Reject if IP is invalid
            if not self.is_valid_ip(client_ip):
                logging.info(f"Request denied: invalid IP address: {client_ip}")
                return deny_request(
                    status_code=http_status_pb2.StatusCode.Forbidden,
                    headers=[('x-client-ip-allowed', 'false')]
                )
            
            # Reject if IP is in blocked range
            if self.is_ip_blocked(client_ip):
                logging.info(f"Request denied for blocked IP: {client_ip}")
                return deny_request(
                    status_code=http_status_pb2.StatusCode.Forbidden,
                    headers=[('x-client-ip-allowed', 'false')]
                )
        except Exception as e:
            logging.error(f"Error in Check method: {str(e)}")
            logging.error(traceback.format_exc())
            return deny_request()

    def extract_client_ip(self, request: auth_pb2.CheckRequest) -> str:
        """Extracts the client IP address from the 'x-forwarded-for' header."""
        # Try to access headers through the header_map structure
        if hasattr(request.attributes.request.http, 'header_map'):
            for header in request.attributes.request.http.header_map.headers:
                if header.key.lower() == 'x-forwarded-for':
                    # Get the first IP from the X-Forwarded-For list
                    ips = header.raw_value.decode('utf-8').split(',')
                    if ips:
                        return ips[0].strip()
        
        # Fallback: try to access headers through the dictionary
        if hasattr(request.attributes.request.http, 'headers'):
            headers = request.attributes.request.http.headers
            xff_header = headers.get('x-forwarded-for', '')
            if xff_header:
                return xff_header.split(',')[0].strip()
        
        return None

    def is_valid_ip(self, ip_str: str) -> bool:
        """Check if the IP address is valid."""
        try:
            ipaddress.ip_address(ip_str)
            return True
        except ValueError:
            return False

    def is_ip_blocked(self, ip_str: str) -> bool:
        """Check if the IP address is in the blocked range."""
        try:
            ip_addr = ipaddress.ip_address(ip_str)
            return ip_addr in self.BLOCKED_IP_RANGE
        except ValueError:
            logging.warning(f"Invalid IP address in is_ip_blocked: {ip_str}")
            return True

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    CalloutServerExample().run()
