load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:proxy-wasm",
    ],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
)

proxy_wasm_tests(
    name = "tests",
    data = [
        ":request_headers.data",
        ":response_headers.data",
    ],
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)

proxy_wasm_tests(
    name = "testsyaml",
    data = [
        ":request_headers.data",
        ":response_headers.data",
    ],
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_rust.wasm",
    ],
    tests = ":tests.yaml",
)
