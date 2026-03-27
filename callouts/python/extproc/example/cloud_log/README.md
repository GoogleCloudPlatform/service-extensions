# Cloud Log Callout

This callout server inspects HTTP request headers and bodies and enforces
presence checks before allowing traffic to proceed, logging every authorization
decision to Google Cloud Logging. It demonstrates how to integrate a callout
server with the Cloud Logging API using Compute Engine credentials — combining
traffic enforcement with structured cloud-native observability. It overrides
`on_request_headers` and `on_request_body` to validate the presence of required
fields and deny any request that fails the check. Use this callout when you
need to gate traffic on specific header or body content and retain a cloud-based
audit trail of every allow or deny decision.

## How It Works

1. The load balancer intercepts an HTTP request and sends a `ProcessingRequest`
   with `request_headers` to the callout server.
2. The server's `on_request_headers` callback checks whether the header
   `header-check` is present. If it is not, the request is denied and the
   decision is logged to Cloud Logging. If it is present, the server adds
   `header-request: request`, clears the route cache, and logs the allow
   decision.
3. The load balancer then sends a `ProcessingRequest` with `request_body`.
4. The server's `on_request_body` callback checks whether the body contains
   the substring `body-check`. If it does not, the request is denied and the
   decision is logged to Cloud Logging. If it is present, the server replaces
   the body with `replaced-body` and logs the allow decision.
5. All decisions — both allow and deny — are written to Google Cloud Logging
   via a client authenticated with Compute Engine credentials.
6. The modified request is forwarded to the origin server.

## Callbacks Overridden

| Callback | Behavior |
|---|---|
| `on_request_headers` | Denies and logs if `header-check` is absent; otherwise adds `header-request: request` and clears route cache |
| `on_request_body` | Denies and logs if `body-check` is absent; otherwise replaces the body with `replaced-body` |

## Cloud Logging Setup

This example uses `google.cloud.logging` with Compute Engine credentials. The
setup is intended as a demonstration and is not production-hardened. For
production use, refer to the
[google-auth documentation](https://google-auth.readthedocs.io/en/latest/).

```python
client = google.cloud.logging.Client(
    project='test-project', credentials=compute_engine.Credentials()
)
client.setup_logging()
```

Replace `test-project` with your actual GCP project ID before deploying.

## Run

```bash
cd callouts/python
python -m extproc.example.cloud_log.service_callout_example
```

## Test

```bash
cd callouts/python
pytest extproc/tests/basic_grpc_test.py
```

The `cloud_log` example is tested as part of the basic gRPC integration tests
rather than having a dedicated test file.

## Expected Behavior

| Scenario | Description |
|---|---|
| **`header-check` present** | The request is allowed to proceed. The server adds `header-request: request`, clears the route cache, and logs the allow decision to Cloud Logging. |
| **`header-check` absent** | The request is denied immediately. The server closes the connection and logs the deny decision with the message `"header-check" not found within the request headers`. |
| **`body-check` present** | The request body is allowed to proceed. The server replaces the body with `replaced-body` and logs the allow decision to Cloud Logging. |
| **`body-check` absent** | The request is denied immediately. The server closes the connection and logs the deny decision with the message `"body-check" not found within the request body`. |
| **Cloud Logging unavailable** | If the Cloud Logging client cannot authenticate or reach the API, the server will fail to initialize. Ensure valid Compute Engine credentials and network access to the Cloud Logging API are available. |

## Available Languages

- [x] [Python](.) (this directory)
- [ ] Go
- [ ] Java
