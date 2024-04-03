# Testing Details

Most of the tests in this directory are associated with example images defined under [extproc/examples](/callouts/python/extproc/example/). The main exception to this is [basic_grpc_test.py](basic_grpc_test.py) which tests the basic functionality of the [Callout Server](/callouts/python/extproc/service/callout_server.py).

## Adding tests for new examples

Create a new example under the [extproc/examples](/callouts/python/extproc/example/) directory that implements the new feature or use case. 

Create a new test file importing the new server.

```python
from extproc.example.<path_to_callout_server> import (
  CalloutServerExample as CalloutServerTest,
)
```

Each test case needs a server to test off of.
Importing `setup_server` from [basic_grpc_test.py](basic_grpc_test.py) gives access to the `server` fixture:
```python
from extproc.tests.basic_grpc_test import setup_server
@pytest.mark.parametrize('server', [{}], indirect=True)
...
```

This fixture will set up a server on a per class basis, and will not recreate fixtures with identical parameters within the same class.
By default this fixture will generate a basic `CalloutServer` to test with.
To provide the `CalloutServerTest` imported above, generate a custom config:
```python
from extproc.tests.basic_grpc_test import insecure_kwargs
_local_test_args: dict = {
    "kwargs": insecure_kwargs,
    "test_class": CalloutServerTest
}

@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
...
```
In the example above `insecure_kwargs` is a set of `CalloutServer` initalization `kwargs` that will generate a server with the insecure port open. 
Setting `test_class` to the imported local version of `CalloutServerTest` causes `'server'` to generate the callout server from the local `CalloutServerTest` rather than `CalloutServer`.

Putting that all together as a basic health checking test:
```python
import urllib.request
from extproc.example.<path_to_callout_server> import (
  CalloutServerExample as CalloutServerTest,
)
from extproc.service.callout_server import addr_to_str
from extproc.tests.basic_grpc_test import setup_server, insecure_kwargs,

_local_test_args: dict = {
    "kwargs": insecure_kwargs,
    "test_class": CalloutServerTest
}

@pytest.mark.parametrize('server', [_local_test_args], indirect=True)
def test_basic_server_health_check(self, server: CalloutServerTest) -> None:
  """Test that the health check sub server returns the expected 200 code."""
  assert server.health_check_address is not None
  response = urllib.request.urlopen(
      f'http://{addr_to_str(server.health_check_address)}')
  assert not response.read()
  assert response.getcode() == 200
```

## Adding tests for baseline server functionality

If adding tests for new functionality for the [callout_server.py](/callouts/python/extproc/service/callout_server.py) add them as test cases to [basic_grpc_test.py](basic_grpc_test.py).
