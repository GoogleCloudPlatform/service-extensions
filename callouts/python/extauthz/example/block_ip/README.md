# Block IP

An `ext_authz` external authorization server implementing IP-based access control. Unlike the `ext_proc` examples elsewhere in this repo, this server is called through Envoy's authorization API (`Check`), not the processing API — it makes a single allow/deny decision per request rather than mutating headers or bodies across multiple phases.

## How It Works

1. Cloud Load Balancing sends a `CheckRequest` to the authorization server before the request is forwarded to your backend.
2. The server extracts the client IP from the `x-forwarded-for` header.
3. If the IP is missing, invalid, or falls inside the blocked range (`10.0.0.0/24` in this example), the server returns a `CheckResponse` denying the request with an HTTP 403 and an `x-client-ip-allowed: false` header.
4. Otherwise, it returns an allow decision with `x-client-ip-allowed: true` added to the request.

## Callback Overridden

| Callback | Behavior |
|---|---|
| `on_check` | Extracts the client IP, validates it, and allows or denies the request based on the configured blocked range |

## Run

```bash
cd callouts/python
python -m extauthz.example.block_ip.service_callout_example
```

## Test

```bash
cd callouts/python
python -m pytest extauthz/tests/block_ip_test.py
```

## Additional Details

The blocked range is hardcoded as `BLOCKED_IP_RANGE = ipaddress.ip_network('10.0.0.0/24')` in `service_callout_example.py` — change this to match your own policy. See [`../../service/callout_server.py`](../../service/callout_server.py) for the `CalloutServerAuth` base class this example extends, and [`../../README.md`](../../README.md) for how `ext_authz` differs from the `ext_proc` examples in [`../../../extproc/`](../../../extproc/).
