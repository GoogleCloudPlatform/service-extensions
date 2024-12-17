load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
)

proxy_wasm_tests(
    name = "tests",
    data = [
        ":expected_request_body.data",
        ":request_body.data",
        ":response_body.data",
    ],
    plugins = [
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)
