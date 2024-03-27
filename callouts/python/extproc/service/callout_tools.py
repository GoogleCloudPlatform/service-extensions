"""Library of commonly used methods within a callout server."""

import typing
import logging
import grpc
from envoy.config.core.v3.base_pb2 import HeaderValue
from envoy.config.core.v3.base_pb2 import HeaderValueOption
from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2


def add_header_mutation(
    add: list[tuple[str, str]] | None = None,
    remove: list[str] | None = None,
    clear_route_cache: bool = False,
    append_action: typing.Union[HeaderValueOption.HeaderAppendAction,
                                None] = None,
) -> service_pb2.HeadersResponse:
  """Generate a header response for incoming requests.

  Args:
    add: A list of tuples representing headers to add.
    remove: List of header strings to remove from the request.
    clear_route_cache: If true, will enable clear_route_cache on the response.
    append_action: Supported actions types for header append action.
  Returns:
    The constructed header response object.
  """
  header_mutation = service_pb2.HeadersResponse()
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
    headers: service_pb2.HttpHeaders,
    clear_route_cache: bool = False,
) -> service_pb2.HeadersResponse:
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

  header_mutation = service_pb2.HeadersResponse()

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
) -> service_pb2.BodyResponse:
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
  body_mutation = service_pb2.BodyResponse()
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
