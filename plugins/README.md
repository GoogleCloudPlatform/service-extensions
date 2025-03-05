<a name="docs"></a>

# Google Cloud Service Extension Plugins Samples

Code samples and tools for developing
[Google Cloud Service Extensions](https://cloud.google.com/service-extensions/)
WebAssembly (wasm) plugins.

Each sample/recipe has an example plugin written in Rust and C++, and an
accompanying unit test that verifies both.

# Getting started

We recommend the following process:

1.  Write a wasm plugin using the [samples](#samples) and SDKs as a starting
    point: [C++](https://github.com/proxy-wasm/proxy-wasm-cpp-sdk),
    [Go](https://github.com/proxy-wasm/proxy-wasm-go-sdk),
    [Rust](https://github.com/proxy-wasm/proxy-wasm-rust-sdk). See also the
    [best practices](https://cloud.google.com/service-extensions/docs/plugin-best-practices).
1.  [Build](#build) the plugin.
1.  [Test and benchmark](#test) the plugin.

<a name="build"></a>

# Building

All sample plugins can be built using [Bazel](https://bazel.build/). If you
prefer to use language-native toolchains, see the SDK-specific instructions:

-   C++ supports
    [Make](https://github.com/proxy-wasm/proxy-wasm-cpp-sdk/blob/main/docs/building.md)
-   Rust supports
    [Cargo](https://github.com/proxy-wasm/proxy-wasm-rust-sdk/tree/main/examples/hello_world)
-   Go supports the
    [Go tool](https://github.com/proxy-wasm/proxy-wasm-go-sdk/blob/main/README.md#minimal-example-plugin)

All languages also support Bazel; we recommend the
[Bazelisk](https://github.com/bazelbuild/bazelisk#installation) wrapper which
provides support for multiple Bazel versions:

```bash
# A target is defined using BUILD files. Dependencies are in WORKSPACE.
$ bazelisk build <target>

# For example, to build a sample in C++ and Rust, from the plugins/ directory:
$ bazelisk build //samples/add_header:plugin_cpp.wasm
$ bazelisk build //samples/add_header:plugin_rust.wasm
```

C++ builds may require a specific toolchain: `--config=clang` or `--config=gcc`.

<a name="test"></a>

# Testing and benchmarking

1.  Write a plugin test file (text proto) to specify the plugin's functional
    expectations ([example](samples/testing/tests.textpb)). Consult the plugin
    tester [proto API](test/runner.proto) as needed.
1.  Add `benchmark: true` to tests that exemplify common wasm operations
    ([example](samples/add_header/tests.textpb)).
1.  Run + Test + Benchmark your wasm plugin as follows!

```bash
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
-   To disable benchmarking for faster iteration, add `--nobench`.
-   To disable unit testing for cleaner output, add `--notest`.
-   To optionally specify plugin config data, add `--config=<path>`.

You can also run tests using Bazel. This is **much slower** the first time,
because this builds both the tester and the V8 runtime from scratch. Use the
Docker command above for a better experience.

```bash
bazelisk test --config=bench --test_output=all //samples/...
```

<a name="samples"></a>

# Samples & Recipes

The [samples](samples/) folder contains Samples & Recipes to use as a reference
for your own plugin. Extend them to fit your particular use case.

*   [Testing examples](samples/testing): A demonstration of our test framework
    capabilities (sending inputs and checking results).
*   [Log each Wasm call](samples/log_calls): Don't change anything about the
    traffic (noop plugin). Log each wasm invocation, including lifecycle
    callbacks.
*   [Add HTTP request & response headers](samples/add_header): Add a header on
    both the client request and server response paths. Also check for existing
    headers.
*   [Plugin config with a list of tokens to deny](samples/config_denylist): Deny
    a request whenever it contains a known bad token. Bad tokens are loaded at
    plugin initialization time from plugin configuration.
*   [Log the value of a query parameter](samples/log_query): Emit a custom
    variable to Cloud Logging. Demonstrate a standard way to parse query string
    values from the request.
*   [Set or update query parameter](samples/set_query): Change the path, and
    specifically query string values.
*   [Rewrite the path using regex](samples/regex_rewrite): Remove a piece of the
    URI using regex replacement. Demonstrate a standard way to use regular
    expressions, compiling them at plugin initialization.
*   [Overwrite HTTP request & response headers](samples/overwrite_header):
    Overwrite a header on both the client request and server response paths.
*   [Normalize a HTTP header on request](samples/normalize_header): Creates a
    new HTTP header (client-device-type) to shard requests based on device
    according to the existence of HTTP Client Hints or User-Agent header values.
*   [Block request with particular header](samples/block_request): Check whether
    the client's Referer header matches an expected domain. If not, generate a
    403 Forbidden response.
*   [Overwrite origin response error code](samples/overwrite_errcode):
    Overwrites error code served from origin from 5xx error to 4xx error class.
*   [Perform a HTTP redirect](samples/redirect): Redirect a given URL to another
    URL.
*   [Set a cookie for a given client request](samples/set_cookie): Set cookie on
    HTTP response for a particular client request.
*   [A/B decisioning based on query param](samples/ab_testing): Showcase A/B
    testing in action, 50% chance a user is served file A and 50% chance they
    are served file B.
*   [Custom error page](samples/add_custom_response): For a certain class of
    origin errors, redirect to a custom error page hosted on GCS.
*   [Validate client JWT for authorization](samples/jwt_auth): Ensures user
    authentication by verifying an RS256-signed JWT token in the query string
    and subsequently removing it.
*   [Check for PII on response](samples/check_pii): Checks the response HTTP
    headers and body for the presence of credit card numbers. If found, the
    initial numbers will be masked.
*   [Validate client token on query string using HMAC](samples/hmac_authtoken):
    Check the client request URL for a valid token signed using HMAC.
*   [Validate client token using HMAC with cookie](samples/hmac_authcookie): Check
    the client request for a valid token signed using HMAC provided via a cookie.
*   [Rewrite domains in html response body](samples/html_domain_rewrite/): Parse
    html in response body chunks and replace insances of "foo.com" with
    "bar.com" in `<a href=***>`.

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
environment. The contexts implement the ABI / feature set described above
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

## Go and Gazelle

This project leverages [gazelle](https://github.com/bazel-contrib/bazel-gazelle)
to integrate Go mod with Bazel. In order to add new Go dependencies:

*   Instruct Gazelle to generate a repo rule for your dependency using the Go
    import URL, for example: `$ bazel run //:gazelle -- update-repos
    github.com/proxy-wasm/proxy-wasm-go-sdk`
*   Add a import statement to the Go source file `import
    "github.com/proxy-wasm/proxy-wasm-go-sdk/types"`.
*   Run `$ bazel run //:gazelle` to add the autogenerated repo rule dependency
    to the Go file's build file
