import threading
import grpc
import pytest

from extproc.example.async_server.service_callout_example import AsyncServerExample
from extproc.service.callout_server import CalloutServer, addr_to_str
from extproc.tests.basic_grpc_test import make_request, setup_server, get_insecure_channel
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import ProcessingRequest
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
    "test_class": AsyncServerExample
}

class TestAsyncServer(object):
    """Async server functionality test."""

    @pytest.mark.parametrize('server', [_local_test_args], indirect=True)
    def test_async_request(self, server: AsyncServerExample) -> None:
        with get_insecure_channel(server) as channel:
            stub = ExternalProcessorStub(channel)
            body = HttpBody(end_of_stream=False)
            headers = HttpHeaders(end_of_stream=False)
            end_headers = HttpHeaders(end_of_stream=True)
            make_request(stub, request_headers=headers, observability_mode=True)            
            make_request(stub, request_body=body, observability_mode=True)
            make_request(stub, response_headers=headers, observability_mode=True)
            make_request(stub, response_body=body, observability_mode=True)
            make_request(stub, request_headers=end_headers, observability_mode=True)
            channel.close()
