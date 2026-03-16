load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:proxy-wasm",
    ],
    data = ["config.data"],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_absl//absl/strings",
    ],
    data = ["config.data"],
)

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
    data = ["config.data"],
)

proxy_wasm_tests(
    name = "tests",
    config = ":config.data",
    plugins = [
        ":plugin_rust.wasm",
        ":plugin_go.wasm",
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)