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

import os
import json
from typing import Generator
from unittest.mock import MagicMock, patch

import grpc
import pytest
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as service_pb2_grpc
from envoy.type.v3 import http_status_pb2
from extproc.example.model_armor.service_callout_example import (
    CalloutServerExample as CalloutServerTest,
)
from extproc.tests.basic_grpc_test import (
    default_kwargs,
    get_plaintext_channel,
    make_request,
    setup_server,
)
from google.cloud import modelarmor_v1

_ = setup_server
_local_test_args = {"kwargs": default_kwargs, "test_class": CalloutServerTest}

os.environ.update({"MA_LOCATION": "us-central1"})
os.environ.update(
    {"MA_TEMPLATE": "projects/123456789/locations/us-central1/templates/123456789"}
)


@pytest.fixture
def mock_model_armor_match_found_client() -> (
    Generator[modelarmor_v1.ModelArmorClient, None, None]
):
    with patch("google.cloud.modelarmor_v1.ModelArmorClient") as mock_client:
        client_instance = mock_client.return_value
        mock_prompt_response = MagicMock()
        mock_prompt_response.sanitization_result.filter_match_state = (
            modelarmor_v1.FilterMatchState.MATCH_FOUND
        )
        client_instance.sanitize_user_prompt.return_value = mock_prompt_response
        mock_model_response = MagicMock()
        mock_model_response.sanitization_result.filter_match_state = (
            modelarmor_v1.FilterMatchState.MATCH_FOUND
        )
        client_instance.sanitize_model_response.return_value = mock_model_response
        yield client_instance


@pytest.fixture
def mock_model_armor_match_not_found_client() -> (
    Generator[modelarmor_v1.ModelArmorClient, None, None]
):
    with patch("google.cloud.modelarmor_v1.ModelArmorClient") as mock_client:
        client_instance = mock_client.return_value
        mock_prompt_response = MagicMock()
        mock_prompt_response.sanitization_result.filter_match_state = (
            modelarmor_v1.FilterMatchState.NO_MATCH_FOUND
        )
        client_instance.sanitize_user_prompt.return_value = mock_prompt_response
        mock_model_response = MagicMock()
        mock_model_response.sanitization_result.filter_match_state = (
            modelarmor_v1.FilterMatchState.NO_MATCH_FOUND
        )
        client_instance.sanitize_model_response.return_value = mock_model_response
        yield client_instance


@pytest.mark.parametrize("server", [_local_test_args], indirect=True)
def test_invalid_prompt_request(
    server: CalloutServerTest,
    mock_model_armor_match_found_client: modelarmor_v1.ModelArmorClient,
) -> None:

    with get_plaintext_channel(server) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)

        mock_body = service_pb2.HttpBody(body=b'{"prompt":"invalid mock prompt"}')
        response = make_request(stub, request_body=mock_body)

        assert (
            response.immediate_response.status.code
            == http_status_pb2.StatusCode.Forbidden
        )
        assert (
            response.immediate_response.headers.set_headers[0].header.raw_value
            == b"Provided prompt does not comply with Responsible AI filter"
        )


@pytest.mark.parametrize("server", [_local_test_args], indirect=True)
def test_valid_user_prompt(
    server: CalloutServerTest,
    mock_model_armor_match_not_found_client: modelarmor_v1.ModelArmorClient,
) -> None:

    with get_plaintext_channel(server) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)
        valid_body = '{"prompt": "valid mock prompt"}'
        mock_body = service_pb2.HttpBody(body=valid_body.encode("utf-8"))
        response = make_request(stub, request_body=mock_body)

        assert (
            response.request_body.response.body_mutation.body.decode("utf-8")
            == valid_body
        )


@pytest.mark.parametrize("server", [_local_test_args], indirect=True)
def test_invalid_model_response(
    server: CalloutServerTest,
    mock_model_armor_match_found_client: modelarmor_v1.ModelArmorClient,
) -> None:

    with get_plaintext_channel(server) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)

        mock_response_body = service_pb2.HttpBody(
            body=b"""
            {
              "choices": [
                {
                  "finish_reason": "stop",
                  "index": 0,
                  "message": {
                    "content": "Invalid LLM response",
                    "role": "assistant",
                    "name": "mock-model"
                  }
                }
              ]
            }
            """
        )
        with pytest.raises(grpc.RpcError) as e:
            make_request(stub, response_body=mock_response_body)
        assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED
        assert (
            e.value.details()
            == "Model response violates responsible AI filters. Update the prompt or contact application admin if issue persists."
        )


@pytest.mark.parametrize("server", [_local_test_args], indirect=True)
def test_valid_model_response(
    server: CalloutServerTest,
    mock_model_armor_match_not_found_client: modelarmor_v1.ModelArmorClient,
) -> None:

    with get_plaintext_channel(server) as channel:
        stub = service_pb2_grpc.ExternalProcessorStub(channel)

        valid_response_body = service_pb2.HttpBody(
            body=b"""
            {
              "choices": [
                {
                  "finish_reason": "stop",
                  "index": 0,
                  "message": {
                    "content": "Valid model response",
                    "role": "assistant",
                    "name": "mock-model"
                  }
                }
              ]
            }
            """
        )
        response = make_request(stub, response_body=valid_response_body)

        assert json.loads(
            response.response_body.response.body_mutation.body.decode("utf-8")
        ) == json.loads(valid_response_body.body.decode("utf-8"))
