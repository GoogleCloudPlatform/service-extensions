# Network Basic

A baseline `ext_proc` **L4 (TCP)** callout server. Unlike every other example in [`../../example/`](../../example/), this one processes raw connection data below the HTTP layer, rather than HTTP headers and bodies — it's the network-layer counterpart to the L7 [`basic`](../../example/basic/) reference.

## How It Works

1. Cloud Load Balancing streams raw bytes from the client to the callout server as they arrive on the connection (the read path).
2. `on_read_data` receives each chunk, logs it, and passes it through unmodified.
3. Bytes flowing back from the origin to the client (the write path) are streamed through `on_write_data` the same way.
4. Because `modified=False` is returned on both paths, this example only observes traffic — it doesn't mutate it. Change `processed_data` and set `modified=True` to actually rewrite the stream.

## Callback Overridden

| Callback | Behavior |
|---|---|
| `on_read_data` | Logs bytes from client → server and passes them through unmodified |
| `on_write_data` | Logs bytes from server → client and passes them through unmodified |

## Run

```bash
cd callouts/python
python -m extproc.l4_example.network_basic.network_service_callout_example
```

Command-line options (address, port, TLS, etc.) are available via `--help`; see [`../../service/command_line_tools.py`](../../service/command_line_tools.py).

## Additional Details

This example extends [`NetworkCalloutServer`](../../service/network_callout_server.py), the L4 counterpart to the HTTP-focused `CalloutServer` used by every example under [`../../example/`](../../example/). See [`../../README.md`](../../README.md) for the L4 quick-start, including how the network `ext_proc` proto is generated with `buf`.
