load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "@crate_index//:cookie",
        "@crate_index//:hex",
        "@crate_index//:hmac",
        "@crate_index//:log",
        "@crate_index//:proxy-wasm",
        "@crate_index//:sha2",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)