load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_plugin_cpp", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_absl//absl/strings",
        "@com_google_re2//:re2",
    ],
    linkopts = [
        "-sUSE_PTHREADS=0",
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
