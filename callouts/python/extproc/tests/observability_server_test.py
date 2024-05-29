import pytest
import urllib.request
import json

from extproc.example.e2e_tests.observability_server import ObservabilityServerExample
from extproc.tests.basic_grpc_test import make_request, setup_server, get_plaintext_channel, plaintext_kwargs
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import ExternalProcessorStub

# Set up test fixture.
_ = setup_server
_local_test_args: dict = {
    "kwargs": plaintext_kwargs | {'health_check_address': ('0.0.0.0', 8008),
        'plaintext_address': ("0.0.0.0", 1248)},
    "test_class": ObservabilityServerExample
}

class TestObservabilityServer(object):
    """observability server functionality test."""

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_observability_request(self, server: ObservabilityServerExample) -> None:
        with get_plaintext_channel(server) as channel:
            stub = ExternalProcessorStub(channel)
            body = HttpBody(end_of_stream=False)
            headers = HttpHeaders(end_of_stream=False)
            end_headers = HttpHeaders(end_of_stream=True)
            # We don't care for the responses.
            make_request(stub, request_headers=headers, observability_mode=True)
            make_request(stub, request_body=body, observability_mode=True)
            make_request(stub, response_headers=headers, observability_mode=True)
            make_request(stub, response_body=body, observability_mode=True)
            make_request(stub, request_headers=end_headers, observability_mode=True)
            channel.close()
            base_url = 'http://0:8080/counters'
            with urllib.request.urlopen(base_url) as response:
                data = response.read().decode()
            counters = json.loads(data)
            assert 'request_header_count' in counters
            assert 'response_header_count' in counters
            assert 'request_body_count' in counters
            assert 'response_body_count' in counters
            assert counters['request_header_count'] == 2
            assert counters['response_header_count'] == 1
            assert counters['request_body_count'] == 1
            assert counters['response_body_count'] == 1
