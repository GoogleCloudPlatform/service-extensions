load("@io_bazel_rules_go//go:def.bzl", "go_binary")
load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_re2//:re2",
    ],
)

go_binary(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
    goarch = "wasm",
    goos = "wasip1",
    linkmode = "c-shared",
    deps = [
        "@com_github_proxy_wasm_proxy_wasm_go_sdk//proxywasm:go_default_library",
        "@com_github_proxy_wasm_proxy_wasm_go_sdk//proxywasm/types:go_default_library",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)
