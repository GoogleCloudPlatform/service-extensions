
load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:proxy-wasm",
        "//bazel/cargo/remote:lol_html",
        "//bazel/cargo/remote:serde",
        "//bazel/cargo/remote:serde_json",
    ],
)

proxy_wasm_tests(
    name = "recaptcha_session_tests",
    config = ":session_key.config",
    data = [
        ":session_key_expected_response_body.data",
        ":response_body.data",
    ],
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":session_tests.textpb",
)

proxy_wasm_tests(
    name = "recaptcha_action_tests",
    config = ":action_key.config",
    data = [
        ":action_key_expected_response_body.data",
        ":response_body.data",
    ],
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":action_tests.textpb",
)

