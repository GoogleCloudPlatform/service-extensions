import pytest
import urllib.request
import json

from extproc.example.observability.service_callout_example import ObservabilityServerExample
from extproc.tests.basic_grpc_test import make_request, setup_server, get_insecure_channel
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpBody
from envoy.service.ext_proc.v3.external_processor_pb2_grpc import ExternalProcessorStub

# Replace the default ports of the server so that they do not clash with running programs.
default_kwargs: dict = {
    'address': ('0.0.0.0', 8443),
    'health_check_address': ('0.0.0.0', 8080)
}
# Arguments for running an insecure server alongside the secure grpc.
insecure_kwargs: dict = default_kwargs | {'insecure_address': ('0.0.0.0', 8000)}
_ = setup_server
_local_test_args: dict = {
    "kwargs": insecure_kwargs,
    "test_class": ObservabilityServerExample
}

class TestObservabilityServer(object):
    """observability server functionality test."""

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_observability_request(self, server: ObservabilityServerExample) -> None:
        with get_insecure_channel(server) as channel:
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
            base_url = 'http://0:10000/counters'
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
