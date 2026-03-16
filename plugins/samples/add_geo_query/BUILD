load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "//:boost_exception",
        "@boost//:url",
        "@com_google_absl//absl/strings",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_go.wasm",
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)
