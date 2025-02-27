load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:proxy-wasm",
        "//bazel/cargo/remote:lol_html",
    ],
)

proxy_wasm_tests(
    name = "tests",
    data = [
        ":expected_response_body100.data",
        ":response_body100.data",
        ":expected_response_body50.data",
        ":response_body50.data",
    ],
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)