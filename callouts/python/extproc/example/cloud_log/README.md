# Cloud Logging Auth Plugin (Python)

This plugin implements content-based request authorization at the proxy layer with audit logging to Google Cloud Logging. It inspects incoming request headers and body for the presence of required sentinel values, denying any request that fails either check, and logs all authorization decisions to Cloud Logging. Approved requests have a custom header injected and their body replaced with a static string. Use this plugin when you need to enforce presence-based access control at the proxy layer with a persistent, queryable audit trail in Google Cloud. It operates during the **request headers** and **request body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_headers` callback.
2. The handler checks whether the request contains a header named `header-check`. If the header is absent, `deny_callout` is called with the message `'"header-check" not found within the request headers'` and the connection is closed.
3. If the header is present, `header-request: request` is added to the request headers and the route cache is cleared.
4. The proxy then invokes `on_request_body`.
5. The handler checks whether the request body contains the substring `"body-check"`. If it does not, `deny_callout` is called with the message `'"body-check" not found within the request body'` and the connection is closed.
6. If the body passes the check, the body is replaced with the static string `"replaced-body"`.
7. All authorization decisions — both approvals and denials — are logged to Google Cloud Logging via the configured client.
8. The modified request is forwarded to the upstream service.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_headers` | Denies requests missing `header-check`; otherwise adds `header-request: request` and clears the route cache |
| `on_request_body` | Denies requests whose body does not contain `"body-check"`; otherwise replaces the body with `"replaced-body"` |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the two request-phase callbacks. No response-phase callbacks are registered, so response headers and body pass through unmodified. The server is started by calling `.run()` directly on an instance.

- **Header authorization** — `on_request_headers` calls `callout_tools.header_contains(headers, 'header-check')` and, if it returns `False`, immediately calls `callout_tools.deny_callout(context, ...)` to close the connection with a descriptive denial message. If the check passes, `callout_tools.add_header_mutation` is called with `add=[('header-request', 'request')]` and `clear_route_cache=True`.

- **Body authorization** — `on_request_body` calls `callout_tools.body_contains(body, 'body-check')` and, if it returns `False`, calls `callout_tools.deny_callout(context, ...)` with a corresponding message. If the check passes, `callout_tools.add_body_mutation(body='replaced-body')` replaces the request body.

- **Google Cloud Logging setup** — The `__main__` block constructs a `google.cloud.logging.Client` using `compute_engine.Credentials()` targeting the project `"test-project"`, then calls `client.setup_logging()` to route the standard Python `logging` module output to Cloud Logging. This means all `logging.debug`, `logging.info`, and `logging.error` calls within the service — including denial messages — are captured in Cloud Logging automatically.

- **Credentials** — `compute_engine.Credentials()` is used for local demonstration purposes. This assumes the code runs on a Google Compute Engine instance or an environment with Application Default Credentials. The inline comment notes this setup is not intended for production.

## Configuration

No configuration is required for the default authorization logic. All sentinel values and injected content are hardcoded in the callbacks:

- Required header: `header-check` (must be present; value is not inspected)
- Required body substring: `"body-check"` (must be present anywhere in the body)
- Header added on approval: `header-request: request`
- Request phase route cache: cleared (`True`)
- Body replacement on approval: `"replaced-body"`
- Cloud Logging project: `"test-project"` (update for your environment)

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt

# Additional Cloud Logging dependencies
pip install google-cloud-logging google-auth
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.cloud_log
```

Or run directly:
```bash
python cloud_log.py
```

> **Note:** Running locally requires valid Google Cloud credentials with access to the target project. Set up Application Default Credentials before running:
> ```bash
> gcloud auth application-default login
> ```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the cloud_log sample
python -m pytest tests/cloud_log_test.py

# With verbose output
python -m pytest -v tests/cloud_log_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request approved (headers)** | Request containing `header-check` header | `header-request: request` added; route cache cleared; decision logged |
| **Request denied (headers)** | Request missing `header-check` header | Connection denied with `'"header-check" not found within the request headers'`; logged |
| **Request approved (body)** | Body containing substring `"body-check"` | Body replaced with `"replaced-body"`; decision logged |
| **Request denied (body)** | Body not containing `"body-check"` | Connection denied with `'"body-check" not found within the request body'`; logged |
| **Response phases** | Any HTTP response | Headers and body pass through unmodified; no response callbacks registered |

## Available Languages

- [x] [Python](cloud_log.py)