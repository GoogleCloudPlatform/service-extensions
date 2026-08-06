load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
    deps = [
        "@com_github_golang_jwt_jwt_v5//:jwt",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":publickey.pem",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)
