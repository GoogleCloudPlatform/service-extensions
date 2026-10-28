# Python ext_authz Callouts

This directory contains the Python SDK for **`ext_authz`** callouts — Envoy's external authorization gRPC API. It's a separate protocol from the `ext_proc` examples in [`../extproc/`](../extproc/), and answers a narrower question: *should this request be allowed at all?*

## ext_authz vs. ext_proc

| | `ext_proc` (`../extproc/`) | `ext_authz` (here) |
|---|---|---|
| Question it answers | How should this request/response be transformed? | Should this request be allowed through? |
| Call shape | Up to four calls per request (headers/body × request/response) | One `Check` call per request |
| Typical use | Header/body rewriting, routing, redirects | Allow/deny decisions — IP blocklists, custom auth policies |
| Examples | `add_header`, `jwt_auth`, `redirect`, … | [`block_ip`](example/block_ip/) |

If you need to mutate traffic, use `ext_proc`. If you only need an allow/deny decision — and want it evaluated once, before the request reaches your backend — `ext_authz` is usually the simpler fit; `jwt_auth` under `ext_proc` is a valid alternative when you also need to forward decoded claims as headers.

## Requirements

- Python 3.11+
- [buf](https://buf.build/docs/introduction)
- [requirements.txt](../requirements.txt) (shared with `extproc`)

> All commands are expected to be run from within the `callouts/python` directory.

## Quick Start

Install dependencies the same way as for `extproc`:

```bash
cd callouts/python
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Generate the `ext_authz` proto library with `buf`:

```bash
buf -v generate \
  https://github.com/envoyproxy/envoy.git#subdir=api \
  --path envoy/service/auth/v3/external_auth.proto \
  --include-imports
```

## Examples

| Example | Description |
|---|---|
| [block_ip](example/block_ip/) | Denies requests from a blocklisted source IP range |

## Developing ext_authz Callouts

[`service/callout_server.py`](service/callout_server.py) provides `CalloutServerAuth`, the `ext_authz` counterpart to `extproc`'s `CalloutServer`. Override `on_check` to implement your own authorization logic:

```python
from service.callout_server import CalloutServerAuth

class MyAuthServer(CalloutServerAuth):
  def on_check(self, request, context):
    ...  # return allow_request(...) or deny_request(...)
```

See [`service/callout_tools.py`](service/callout_tools.py) for the `allow_request` / `deny_request` helpers.

## Test

```bash
python -m pytest extauthz/tests/
```
