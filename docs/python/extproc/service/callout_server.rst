Callout Server
=====================

This module provides an SDK for creating service callout servers. It handles incoming service callout requests and performs necessary header and body transformations.

Functions
---------

.. function:: addr_to_str(address)

   Converts a tuple address into a formatted IP string.

   :param tuple[str, int] address: The address to format.
   :return: A string representation of the IP address.

Classes
-------

.. class:: HealthCheckService

   A server class for responding to health check pings.

   .. method:: do_GET()

      Handles GET requests and responds with a 200 OK status, sending no content.

.. class:: CalloutServer

   A server wrapper for managing service callout servers and processing callouts.

   :param tuple[str, int]|None address: The main server address. Default is None.
   :param int|None port: The main server port. Default is None.
   :param tuple[str, int]|None health_check_address: The health check server address. Default is None.
   :param int|None health_check_port: The health check server port. Default is None.
   :param bool combined_health_check: Indicates whether to combine health check with the main server. Default is False.
   :param bool secure_health_check: Indicates if the health check should use SSL. Default is False.
   :param tuple[str, int]|None insecure_address: The insecure server address. Default is None.
   :param int|None insecure_port: The insecure server port. Default is None.
   :param str|None default_ip: The default IP address used if others are not specified. Default is '0.0.0.0'.
   :param str cert_path: The path to the SSL certificate. Default is './extproc/ssl_creds/localhost.crt'.
   :param str cert_key_path: The path to the SSL certificate key. Default is './extproc/ssl_creds/localhost.key'.
   :param str public_key_path: The path to the public key. Default is './extproc/ssl_creds/publickey.pem'.
   :param int server_thread_count: The number of threads for the server. Default is 2.

   .. method:: run()

      Starts all configured servers and enters the main loop until a shutdown is initiated.

   .. method:: shutdown()

      Shuts down all servers and stops serving.

   .. method:: process(request_iterator, context)

      Processes incoming callout requests.

      :param Iterator[ProcessingRequest] request_iterator: An iterator over incoming requests.
      :param ServicerContext context: The gRPC service context.
      :return: An iterator over processing responses.

   .. method:: on_request_headers(headers, context)

      Processes incoming request headers.

      :param HttpHeaders headers: The headers to process.
      :param ServicerContext context: The gRPC service context.
      :return: Optional header modification object.

   .. method:: on_response_headers(headers, context)

      Processes incoming response headers.

      :param HttpHeaders headers: The headers to process.
      :param ServicerContext context: The gRPC service context.
      :return: Optional header modification object.

   .. method:: on_request_body(body, context)

      Processes an incoming request body.

      :param HttpBody body: The body to process.
      :param ServicerContext context: The gRPC service context.
      :return: Optional body modification object.

   .. method:: on_response_body(body, context)

      Processes an incoming response body.

      :param HttpBody body: The body to process.
      :param ServicerContext context: The gRPC service context.
      :return: Optional body modification object.