# Google Cloud Service Extension Plugins Samples

Recipes and code samples for
[Google Cloud Service Extensions](https://cloud.google.com/service-extensions/).

Each recipe has an example plugin written in Rust and C++, and an accompanying
unit test that verifies both.

# Quick start

All commands in this README are intended to be run from the `plugins` subdirectory of this repository.

Build all plugins and run all plugin tests:

`$ bazelisk test --test_output=all //samples/...`

Build and run benchmarks for a plugin:

`$ bazelisk run --config=bench //samples/add_header:plugin_test`

# Samples & Recipes

The samples folder contains Samples & Recipes to use as a reference for your own
plugin. Extend them to fit your particular use case.

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

# Feature set / ABI

Service Extension plugins are compiled against the ProxyWasm ABI, described here:
https://github.com/proxy-wasm/spec/tree/master

Service Extension plugins currently support a subset of the ProxyWasm spec. Support
will grow over time. The current feature set includes:

*   Root context lifecycle callbacks
    *   on_context_create
    *   on_vm_start
    *   on_configure
    *   on_done
    *   on_delete
*   Stream context lifecycle callbacks
    *   on_context_create
    *   on_done
    *   on_delete
*   Stream context HTTP callbacks
    *   on_request_headers
    *   on_response_headers
*   Stream context HTTP methods
    *   send_local_response
    *   get__header_map_value, add_header_map_value, replace_header_map_value,
        remove_header_map_value
    *   get_header_map_pairs, set_header_map_pairs
    *   get_header_map_size
*   Other methods
    *   log
    *   get_current_time_nanoseconds (frozen per stream)
    *   get_property ("plugin_root_id" only)
    *   get_buffer_status, get_buffer_bytes (PluginConfiguration only)

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
*   Regenerate Bazel targets: `$ CARGO_BAZEL_REPIN=1 bazelisk build ...`
*   Reference libraries as `@crate_index//:<target>`

# TODO

*   Write more plugin samples
*   Add Golang recipes: https://github.com/tetratelabs/proxy-wasm-go-sdk
