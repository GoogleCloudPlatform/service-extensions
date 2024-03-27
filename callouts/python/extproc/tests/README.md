# Testing Details

Most of the tests in this directory are associated with example images defined under [extproc/examples](/callouts/python/extproc/example/). The main exception to this is [basic_grpc_test.py](basic_grpc_test.py) which tests the basic functionality of the [Callout Server](/callouts/python/extproc/service/callout_server.py).

## Adding tests for new examples

Create a new example under the [extproc/examples](/callouts/python/extproc/example/) directory that implements the new feature or use case. 

Create a new test file importing the new server.

```python
from extproc.example.grpc.service_callout_example import (
  CalloutServerExample as CalloutServerTest,
)
```

The [basic_grpc_test.py](basic_grpc_test.py) file contains some code to help test with, we can import those methods with:

```python
from extproc.tests.basic_grpc_test import _wait_till_server, _make_request
```

For each test case we need to make sure a server is running to test off of.
We can do this with a fixture:
```python
@pytest.fixture(scope='class')
def setup_and_teardown():
  global server
  try:
    server = CalloutServerTest()
    # Start the server in a background thread
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    # Wait for the server to start
    _wait_till_server(lambda: server and server._setup)
    yield
    # Stop the server
    server.shutdown()
    thread.join(timeout=5)
  finally:
    del server
```

This exposes a global variable `server` that can be used within test functions.
Together with a test function:

```python
@pytest.mark.usefixtures('setup_and_teardown')
def test_basic_server_health_check(self) -> None:
  """Test that the health check sub server returns the expected 200 code."""
  response = urllib.request.urlopen(
    f'http://{server.health_check_ip}:{server.health_check_port}')
  assert not response.read()
  assert response.getcode() == 200
```

## Adding tests for baseline server functionality:

If adding tests for new functionality for the [callout_server.py](/callouts/python/extproc/service/callout_server.py) add them as test cases to [basic_grpc_test.py](basic_grpc_test.py).
