# Add Body Plugin (Python)

This plugin demonstrates HTTP body manipulation at the proxy layer by intercepting both the incoming request body and the outgoing response body. It appends a fixed suffix to the request body and fully replaces the response body with a static string. Use this plugin when you need to modify body content at the proxy layer without changing application logic — for example, enriching request payloads with metadata or normalising upstream responses. It operates during the **request body** and **response body** processing phases.

## How It Works

1. The proxy receives an HTTP request and invokes the plugin's `on_request_body` callback.
2. The handler decodes the existing request body as UTF-8 and appends `"-added-request-body"` to it, producing a modified body.
3. The modified request is forwarded to the upstream service.
4. When the upstream responds, the proxy invokes the plugin's `on_response_body` callback.
5. The handler discards the original response body and replaces it entirely with the static string `"new-body"`.
6. The modified response is returned to the client.

## Ext_Proc Callbacks Used

| Callback | Purpose |
|---|---|
| `on_request_body` | Reads the existing request body and appends `"-added-request-body"` to it |
| `on_response_body` | Replaces the outgoing response body entirely with `"new-body"` |

## Key Code Walkthrough

- **Class structure** — `CalloutServerExample` extends `callout_server.CalloutServer` and overrides only the two body phase callbacks. No constructor override is needed; the base class handles all server lifecycle concerns. The server is started by calling `.run()` directly on an instance.

- **Request body mutation** — `on_request_body` decodes the raw body bytes with `body.body.decode('utf-8')`, appends the static suffix `"-added-request-body"`, and passes the concatenated string to `callout_tools.add_body_mutation`. This overwrites the request body with the appended content before forwarding to the upstream.

- **Response body mutation** — `on_response_body` passes the static string `"new-body"` directly to `callout_tools.add_body_mutation`, discarding the original response body entirely and substituting the fixed replacement.

- **`add_body_mutation` utility** — Both callbacks delegate to `callout_tools.add_body_mutation`, a shared helper from the `extproc.service` package that constructs the appropriate `BodyResponse` protobuf message, abstracting away the boilerplate of building the mutation directly.

- **Server startup** — The `__main__` block sets the log level to `DEBUG` and calls `CalloutServerExample().run()` to start the gRPC server with default configuration.

## Configuration

No configuration is required for the default setup. The body strings are hardcoded directly in each callback:

- Request body suffix: `"-added-request-body"` (appended to existing UTF-8 content)
- Response body replacement: `"new-body"` (replaces existing content entirely)

## Build

Install the required dependencies from the repository root:
```bash
pip install -r requirements.txt
```

## Run

Start the callout server with default configuration:
```bash
python -m extproc.example.add_body
```

Or run directly:
```bash
python add_body.py
```

## Test

Run the unit tests for this sample:
```bash
# Run all tests for the add_body sample
python -m pytest tests/add_body_test.py

# With verbose output
python -m pytest -v tests/add_body_test.py
```

## Expected Behavior

| Scenario | Input | Output |
|---|---|---|
| **Request body is appended** | Request body `"hello"` | Modified body `"hello-added-request-body"` forwarded to upstream |
| **Empty request body is appended** | Request body `""` | Modified body `"-added-request-body"` forwarded to upstream |
| **Response body is replaced** | Any response body from upstream | Response body replaced with `"new-body"` |
| **Non-UTF-8 request body** | Request body with non-UTF-8 bytes | `decode('utf-8')` raises `UnicodeDecodeError`; no mutation applied |

## Available Languages

- [x] [Go](add_body.go)
- [x] [Java](AddBody.java)
- [x] [Python](service_callout_example.py)