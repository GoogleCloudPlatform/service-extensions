Callout Server
====================

Callout Server

.. automodule:: callouts.python.extproc.service.callout_server
   :members:
   :undoc-members:
   :show-inheritance:
   :exclude-members: on_request_headers, on_response_headers, on_request_body, on_response_body

.. py:function:: on_request_headers(headers, context)

   Process incoming request headers.

   :param HttpHeaders headers: The headers to process.
   :param ServicerContext context: The gRPC service context.
   :return: Optional header modification object. Can be either `None`, `HeadersResponse`, or `ImmediateResponse`.

.. py:function:: on_response_headers(headers, context)

   Process incoming response headers.

   :param HttpHeaders headers: The headers to process.
   :param ServicerContext context: The gRPC service context.
   :return: Optional header modification object. Can be either `None` or `HeadersResponse`.

.. py:function:: on_request_body(body, context)

   Process an incoming request body.

   :param HttpBody body: The body to process.
   :param ServicerContext context: The gRPC service context.
   :return: Optional body modification object. Can be either `None`, `BodyResponse`, or `ImmediateResponse`.

.. py:function:: on_response_body(body, context)

   Process an incoming response body.

   :param HttpBody body: The body to process.
   :param ServicerContext context: The gRPC service context.
   :return: Optional body modification object. Can be either `None` or `BodyResponse`.