"""Library of commonly used methods within a callout server."""
import argparse
import logging
import typing
from typing import Union, Literal

from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.config.core.v3.base_pb2 import HeaderValueOption
from envoy.service.ext_proc.v3.external_processor_pb2 import HeaderMutation
from envoy.service.ext_proc.v3.external_processor_pb2 import HttpHeaders
from envoy.service.ext_proc.v3.external_processor_pb2 import BodyResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import HeadersResponse
from envoy.service.ext_proc.v3.external_processor_pb2 import ImmediateResponse
from envoy.type.v3.http_status_pb2 import StatusCode
import grpc


def _false_or_addr(value: str) -> Literal[False] | tuple[str, int] | None:
  if value == "False":
    return False
  return _addr(value)


def _addr(value: str) -> tuple[str, int] | None:
  if not value:
    return None
  if ':' not in value:
    return None
  address_values = value.split(':')
  return (address_values[0], int(address_values[1]))


def add_command_line_args() -> argparse.ArgumentParser:
  """Adds command line args that can be passed to the CalloutServer constructor."""
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--secure_health_check',
      action="store_true",
      help="Run a HTTPS health check rather than an HTTP one.",
  )
  parser.add_argument(
      '--combined_health_check',
      action="store_true",
      help="Do not create a seperate health check server.",
  )
  parser.add_argument(
      '--address',
      type=_addr,
      help='Address for the server with format: "0.0.0.0:443"',
  )
  parser.add_argument(
      '--health_check_address',
      type=_addr,
      help=('Health check address for the server with format: "0.0.0.0:80",' +
            'if False, no health check will be run.'),
  )
  parser.add_argument(
      '--insecure_address',
      type=_addr,
      help='Address for the insecure debug port with format: "0.0.0.0:443"',
  )

  parser.add_argument(
      '--port',
      type=int,
      help='Port of the server, uses default_ip as the ip unless --address is specified.',
  )
  parser.add_argument(
      '--health_check_port',
      type=int,
      help='Health check port of the server, uses default_ip as the ip unless --health_check_address is specified.',
  )
  parser.add_argument(
      '--insecure_port',
      type=int,
      help='Insecure debug port of the server, uses default_ip as the ip unless --insecure_address is specified.',
  )
  return parser


def add_header_mutation(
    add: list[tuple[str, str]] | None = None,
    remove: list[str] | None = None,
    clear_route_cache: bool = False,
    append_action: typing.Optional[HeaderValueOption.HeaderAppendAction] = None,
) -> HeadersResponse:
  """Generate a header response for incoming requests.

  Args:
    add: A list of tuples representing headers to add.
    remove: List of header strings to remove from the request.
    clear_route_cache: If true, will enable clear_route_cache on the response.
    append_action: Supported actions types for header append action.
  Returns:
    The constructed header response object.
  """
  header_mutation = HeadersResponse()
  if add:
    for k, v in add:
      header_value_option = HeaderValueOption(
          header=HeaderValue(key=k, raw_value=bytes(v, 'utf-8')))
      if append_action:
        header_value_option.append_action = append_action
      header_mutation.response.header_mutation.set_headers.append(
          header_value_option)
  if remove is not None:
    header_mutation.response.header_mutation.remove_headers.extend(remove)
  if clear_route_cache:
    header_mutation.response.clear_route_cache = True
  return header_mutation


def normalize_header_mutation(
    headers: HttpHeaders,
    clear_route_cache: bool = False,
) -> HeadersResponse:
  """Generate a header response for incoming requests.
  Args:
    headers: Current headers presented in the request
    clear_route_cache: If true, will enable clear_route_cache on the response.
  Returns:
    The constructed header response object.
  """

  host_value = next((header.raw_value.decode('utf-8')
                     for header in headers.headers.headers
                     if header.key == 'host'), None)

  header_mutation = HeadersResponse()

  if host_value:
    device_type = get_device_type(host_value)
    header_mutation = add_header_mutation(add=[('client-device-type',
                                                device_type)],
                                          clear_route_cache=clear_route_cache)

  if clear_route_cache:
    header_mutation.response.clear_route_cache = True
  return header_mutation


def add_body_mutation(
    body: str | None = None,
    clear_body: bool = False,
    clear_route_cache: bool = False,
) -> BodyResponse:
  """Generate a body response for incoming requests.

Args:
  body: Text of the body.
  clear_body: If set to true, the modification will clear the previous body,
    if left false, the text will be appended to the end of the previous
    body.
  clear_route_cache: If true, will enable clear_route_cache on the response.

  Returns:
    The constructed body response object.
  """
  body_mutation = BodyResponse()
  if body:
    body_mutation.response.body_mutation.body = bytes(body, 'utf-8')
  if clear_body:
    body_mutation.response.body_mutation.clear_body = True
  if clear_route_cache:
    body_mutation.response.clear_route_cache = True
  return body_mutation


def get_device_type(host_value: str) -> str:
  """Determine device type based on user agent."""
  if 'm.example.com' in host_value:
    return 'mobile'
  elif 't.example.com' in host_value:
    return 'tablet'
  return 'desktop'


def deny_request(context, msg: str | None = None):
  """Deny a grpc request and print an error message"""
  msg = msg or "Request content is invalid or not allowed"
  logging.warning(msg)
  context.abort(grpc.StatusCode.PERMISSION_DENIED, msg)


def header_immediate_response(
    code: StatusCode,
    headers: list[tuple[str, str]] | None = None,
    append_action: Union[HeaderValueOption.HeaderAppendAction, None] = None,
) -> ImmediateResponse:
  """Returns an ImmediateResponse for a header request"""
  immediate_response = ImmediateResponse()
  immediate_response.status.code = code

  if headers:
    header_mutation = HeaderMutation()
    for k, v in headers:
      header_value_option = HeaderValueOption(
          header=HeaderValue(key=k, raw_value=bytes(v, 'utf-8')))
      if append_action:
        header_value_option.append_action = append_action
      header_mutation.set_headers.append(header_value_option)

    immediate_response.headers.CopyFrom(header_mutation)
  return immediate_response
