.. _callout_server:

Callout Server
=====================

This module provides a customizable service callout server with support for header and body transformations.

Class Definition
----------------

.. autoclass:: callouts.python.extproc.service.callout_server.CalloutServer
   :show-inheritance:

CalloutServer Methods
---------------------

.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.run
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.shutdown
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer._start_servers
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer._stop_servers
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer._loop_server
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.process
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.on_request_headers
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.on_response_headers
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.on_request_body
.. automethod:: callouts.python.extproc.service.callout_server.CalloutServer.on_response_body

HealthCheckService Class
------------------------

.. autoclass:: callouts.python.extproc.service.callout_server.HealthCheckService
   :members:
   :show-inheritance:

GRPC Callout Service
--------------------

.. autoclass:: callouts.python.extproc.service.callout_server._GRPCCalloutService
   :members:
   :show-inheritance:
