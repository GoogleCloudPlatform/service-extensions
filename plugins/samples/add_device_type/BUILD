load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)
