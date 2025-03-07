load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_absl//absl/strings",
    ],
)

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:proxy-wasm",
    ],
    data = ["config.data"],
)

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)

proxy_wasm_tests(
    name = "domains_tests",
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":tests_domains.textpb",
)
