load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    crate_features = ["jwt-compact/rsa"],
    deps = [
        "@crate_index//:proxy-wasm",
        "@crate_index//:url",
        "@crate_index//:rsa",
        "@crate_index//:jwt-compact",
    ],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@jwt_verify_lib//:jwt_verify_lib",
        "//:boost_exception",
        "@boost//:url",
    ],
    linkopts = [
        # BoringSSL crypto assumes -pthread is OK to use:
        # https://github.com/google/boringssl/blob/9ac494a171014fa0f06dbf2b0e08abf1d7ec85aa/BUILD.bazel#L87
        #
        # Using -pthread results in linker errors like:
        # "error: --shared-memory is disallowed by lto.tmp because it was not
        # compiled with 'atomics' or 'bulk-memory' features."
        #
        # Override the -pthread option to avoid the error.
        # Consider moving this to ProxyWasmCppSdk.
        "-sUSE_PTHREADS=0",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":publickey.pem",
    plugins = [
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)

proxy_wasm_tests(
    name = "tests_rust",
    config = ":publickey.pem",
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":tests_rust.textpb",
)
