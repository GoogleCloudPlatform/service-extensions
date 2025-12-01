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
"""Tools for ext_authz callout servers.

Provides commonly used methods for building authorization responses
in ext_authz callout servers. Includes utilities for creating allowed
and denied responses with configurable headers and status codes.
"""

from envoy.service.auth.v3 import external_auth_pb2 as auth_pb2
from envoy.config.core.v3 import base_pb2
from envoy.type.v3 import http_status_pb2
from google.rpc import status_pb2


def allow_request(headers_to_add: list[tuple[str, str]] = None) -> auth_pb2.CheckResponse:
    """Create an allowed response with optional headers.
    
    This function generates a CheckResponse that allows the request to proceed.
    Optionally adds headers to the response that will be forwarded upstream.
    
    Args:
        headers_to_add: Optional list of tuples representing headers to add
            to the allowed response. Each tuple should be (key, value).
            
    Returns:
        CheckResponse: An authorization response that allows the request
        with any specified headers added.
    """
    ok_response = auth_pb2.OkHttpResponse()
    if headers_to_add:
        for key, value in headers_to_add:
            header_value = base_pb2.HeaderValue(key=key, value=value)
            header_option = base_pb2.HeaderValueOption(header=header_value)
            ok_response.headers.append(header_option)
    
    return auth_pb2.CheckResponse(
        status=status_pb2.Status(code=0),
        ok_response=ok_response
    )


def deny_request(status_code: http_status_pb2.StatusCode = http_status_pb2.StatusCode.Forbidden, 
                 body: str = None, headers: list[tuple[str, str]] = None) -> auth_pb2.CheckResponse:
    """Create a denied response with status, body and headers.
    
    This function generates a CheckResponse that denies the request with
    configurable HTTP status code, response body, and headers.
    
    Args:
        status_code: The HTTP status code to return in the denied response.
            Defaults to 403 Forbidden.
        body: Optional response body to include with the denied response.
        headers: Optional list of tuples representing headers to add to
            the denied response. Each tuple should be (key, value).
            
    Returns:
        CheckResponse: An authorization response that denies the request
        with the specified status code, body, and headers.
    """
    status = http_status_pb2.HttpStatus(code=status_code)
    denied_response = auth_pb2.DeniedHttpResponse(status=status)
    
    if body:
        denied_response.body = body
        
    if headers:
        for key, value in headers:
            header_value = base_pb2.HeaderValue(key=key, value=value)
            header_option = base_pb2.HeaderValueOption(header=header_value)
            denied_response.headers.append(header_option)
    
    return auth_pb2.CheckResponse(
        denied_response=denied_response
    )
