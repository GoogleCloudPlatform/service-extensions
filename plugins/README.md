# Google Cloud Service Extension Plugins Samples

Code samples and tools for developing
[Google Cloud Service Extensions](https://cloud.google.com/service-extensions/)
WebAssembly (wasm) plugins.

Each sample/recipe has an example plugin written in Rust and C++, and an
accompanying unit test that verifies both.

# Getting started

We recommend the following process:

1.  Using the [samples](samples/) and
    [Proxy-Wasm](https://github.com/proxy-wasm) SDKs as a starting point, write
    a wasm plugin in a language of your choice. Get it building.
1.  Write a plugin test file (textproto) to specify the plugin's functional
    expectations ([example](samples/testing/tests.textpb)). Consult the plugin
    tester [proto API](test/runner.proto) as needed.
1.  Add `benchmark: true` to tests that exemplify common wasm operations
    ([example](samples/add_header/tests.textpb)).
1.  Run + Test + Benchmark your wasm plugin as follows!

```
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/local/path/to/tests.textpb \
    --plugin /mnt/local/path/to/plugin.wasm
```

Tips:

-   When benchmarking and publishing, compile a release (optimized) wasm build.
-   Try sending empty or invalid input. Verify your plugin doesn't crash.
-   To see plugin-emitted logs on the console, add `--logfile=/dev/stdout`.
-   To see a trace of logs and wasm ABI calls, add `--loglevel=TRACE`.
-   Optionally specify plugin config data using the `--config=<path>` flag.

# Samples & Recipes

The [samples](samples/) folder contains Samples & Recipes to use as a reference
for your own plugin. Extend them to fit your particular use case.

*   [Testing examples](samples/testing): A demonstration of our test framework
    capabilities (sending inputs and checking results).
*   [Log each Wasm call](samples/noop_logs): Don't change anything about the
    traffic (noop plugin). Log each wasm invocation, including lifecycle
    callbacks.
*   [Add HTTP request & response headers](samples/add_header): Add a header on
    both the client request and server response paths. Also check for existing
    headers.
*   [Plugin config with a list of tokens to deny](samples/config_denylist): Deny
    a request whenever it contains a known bad token. Bad tokens are loaded at
    plugin initialization time from plugin configuration.
*   [Log the value of a query parameter](samples/query_log): Emit a custom
    variable to Cloud Logging. Demonstrate a standard way to parse query string
    values from the request.
*   [Rewrite the path using regex](samples/regex_rewrite): Remove a piece of the
    URI using regex replacement. Demonstrate a standard way to use regular
    expressions, compiling them at plugin initialization.
*   [Overwrite HTTP request & response headers](samples/overwrite_header):
    Overwrite a header on both the client request and server response paths.
*   [Normalize a HTTP header on request](samples/normalize_header): Creates a new
    HTTP header (client-device-type) to shard requests based on device according
    to the existence of HTTP Client Hints or User-Agent header values.
*   [Validate client JWT for authorization](samples/jwt_auth): Ensures user
    authentication by verifying an RS256-signed JWT token in the query string
    and subsequently removing it.

# Samples tests

Run these commands from the `plugins/` subdirectory of this repository.

Build all plugins and run all plugin tests:

`$ bazelisk test --test_output=all //samples/...`

When running benchmarks, be sure to add `--config=bench`:

`$ bazelisk test --test_output=all --config=bench //samples/add_header/...`

# Feature set / ABI

Service Extension plugins are compiled against the ProxyWasm ABI, described
here: https://github.com/proxy-wasm/spec/tree/master

Service Extension plugins currently support a subset of the ProxyWasm spec.
Support will grow over time. The current feature set includes:

*   Root context lifecycle callbacks (host -> wasm)
    *   on_context_create
    *   on_vm_start
    *   on_configure
    *   on_done
    *   on_delete
*   Stream context lifecycle callbacks (host -> wasm)
    *   on_context_create
    *   on_done
    *   on_delete
*   Stream context HTTP callbacks (host -> wasm)
    *   on_request_headers
    *   on_response_headers
*   Stream context HTTP hostcalls (wasm -> host)
    *   send_local_response
    *   get_header_map_value, add_header_map_value, replace_header_map_value,
        remove_header_map_value
    *   get_header_map_pairs, set_header_map_pairs
    *   get_header_map_size
*   Other hostcalls (wasm -> host)
    *   log
    *   get_current_time_nanoseconds (frozen per stream)
    *   get_property ("plugin_root_id" only)
    *   get_buffer_status, get_buffer_bytes, set_buffer_bytes
        (PluginConfiguration, HttpRequestBody, HttpResponseBody)

# Implementation details

## Fixture

In support of unit testing, this repo contains an `HttpTest` fixture with a
`TestWasm` host implementation and `TestHttpContext` stream handler. These
minimal implementations loosely match GCP Service Extension execution
environment. The contexts implement the ABI / feature set described below
(mainly HTTP headers and logging), but often in a simple way (behaviors may not
match GCP exactly).

## Rust and Cargo

This project leverages
[crate_universe](http://bazelbuild.github.io/rules_rust/crate_universe.html) to
integrate Cargo with Bazel. In order to add new Rust library dependencies:

*   Edit dependencies in Cargo.toml
*   Regenerate Bazel targets: `$ CARGO_BAZEL_REPIN=1 bazelisk sync
    --only=crate_index`
*   Reference libraries as `@crate_index//:<target>`

# TODO

*   Write more plugin samples
