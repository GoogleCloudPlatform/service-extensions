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
import traceback
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from service.callout_server import CalloutServerAuth
from service.callout_tools import allow_request, deny_request
from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.type.v3 import http_status_pb2

import jwt
from jwt.exceptions import InvalidTokenError
from typing import Union, Any

class JwtAuthServer(CalloutServerAuth):
    """External authorization server implementing JWT token validation.
    
    This server extracts JWT tokens from Authorization headers, validates them,
    and makes authorization decisions based on the validity of the token.
    If valid, it adds decoded token fields as request headers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._load_public_key('ssl_creds/publickey.pem')

    def _load_public_key(self, path: str) -> None:
        """Load the public key used for JWT validation."""
        try:
            with open(path, 'rb') as key_file:
                self.public_key = key_file.read()
            logging.info("Public key loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load public key: {str(e)}")
            self.public_key = None

    def on_check(self, request: auth_pb2.CheckRequest, context) -> auth_pb2.CheckResponse:
        """Process the authorization check request.
        
        Extracts JWT token from headers, validates it, and makes authorization decision.
        If valid, adds decoded token claims as headers to the upstream request.
        """
        try:
            logging.debug("Received Check request")
            
            # Extract JWT token from request
            jwt_token = self.extract_jwt_token(request)
            if jwt_token is None:
                logging.info("Request denied: No JWT token found")
                return deny_request(
                    status_code=http_status_pb2.StatusCode.Unauthorized,
                    body="No Authorization token found."
                )
            
            # Validate JWT token
            decoded = self.validate_jwt_token(jwt_token)
            if decoded is None:
                logging.info("Request denied: Invalid JWT token")
                return deny_request(
                    status_code=http_status_pb2.StatusCode.Unauthorized,
                    body="Authorization token is invalid."
                )
            
            # Token is valid, add decoded fields as headers
            logging.info(f"JWT token valid for subject: {decoded.get('sub', 'unknown')}")
            headers_to_add = [
                (f'decoded-{key}', str(value)) for key, value in decoded.items()
            ]
            
            return allow_request(headers_to_add=headers_to_add)
            
        except Exception as e:
            logging.error(f"Error in Check method: {str(e)}")
            logging.error(traceback.format_exc())
            return deny_request(
                status_code=http_status_pb2.StatusCode.InternalServerError,
                body="Internal server error"
            )

    def extract_jwt_token(self, request: auth_pb2.CheckRequest) -> Union[str, None]:
        """Extract JWT token from Authorization header.
        
        Args:
            request: The authorization check request
            
        Returns:
            The JWT token string if found, None otherwise
        """
        # Try to access headers through HTTP attributes
        if hasattr(request.attributes.request.http, 'headers'):
            auth_header = request.attributes.request.http.headers.get('authorization')
            if auth_header:
                # Extract token part after "Bearer"
                parts = auth_header.strip().split(' ')
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    return parts[1]
        
        # Try to access headers through header_map structure
        if hasattr(request.attributes.request.http, 'header_map'):
            for header in request.attributes.request.http.header_map.headers:
                if header.key.lower() == 'authorization':
                    auth_value = header.raw_value.decode('utf-8') if header.raw_value else header.value
                    if auth_value:
                        parts = auth_value.strip().split(' ')
                        if len(parts) == 2 and parts[0].lower() == 'bearer':
                            return parts[1]
        
        return None

    def validate_jwt_token(self, token: str) -> Union[Any, None]:
        """Validate JWT token using the public key.
        
        Args:
            token: JWT token string to validate
            
        Returns:
            Decoded JWT payload if valid, None otherwise
        """
        if not self.public_key:
            logging.error("Public key not loaded, cannot validate token")
            return None
            
        try:
            decoded = jwt.decode(token, self.public_key, algorithms=['RS256'])
            logging.info(f"JWT token successfully decoded: {decoded}")
            return decoded
        except InvalidTokenError as e:
            logging.error(f"JWT validation failed: {str(e)}")
            return None

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    JwtAuthServer().run()
