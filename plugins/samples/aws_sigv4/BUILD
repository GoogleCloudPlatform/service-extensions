load("@rules_rust//rust:defs.bzl", "rust_test")
load("//:plugins.bzl", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:proxy-wasm",
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:serde",
        "//bazel/cargo/remote:serde_json",
        "//bazel/cargo/remote:sha2",
        "//bazel/cargo/remote:hmac",
        "//bazel/cargo/remote:hex",
        "//bazel/cargo/remote:p256",
    ],
)

rust_test(
    name = "plugin_unit_tests",
    srcs = [
        "plugin.rs",
        "tests/tests.rs",
    ],
    crate_root = "plugin.rs",
    deps = [
        "//bazel/cargo/remote:proxy-wasm",
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:serde",
        "//bazel/cargo/remote:serde_json",
        "//bazel/cargo/remote:sha2",
        "//bazel/cargo/remote:hmac",
        "//bazel/cargo/remote:hex",
        "//bazel/cargo/remote:p256",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = "tests/config_sigv4.json",
    plugins = [":plugin_rust.wasm"],
    tests = "tests/tests.textpb",
)

proxy_wasm_tests(
    name = "tests_ec2_post",
    config = "tests/config_sigv4_ec2.json",
    plugins = [":plugin_rust.wasm"],
    tests = "tests/tests_ec2_post.textpb",
)

proxy_wasm_tests(
    name = "tests_sigv4a_global",
    config = "tests/config_sigv4a_global.json",
    plugins = [":plugin_rust.wasm"],
    tests = "tests/tests_sigv4a_global.textpb",
)

proxy_wasm_tests(
    name = "tests_sigv4a_multiregion",
    config = "tests/config_sigv4a_multiregion.json",
    plugins = [":plugin_rust.wasm"],
    tests = "tests/tests_sigv4a_multiregion.textpb",
)

proxy_wasm_tests(
    name = "tests_noconfig",
    plugins = [":plugin_rust.wasm"],
    tests = "tests/tests_noconfig.textpb",
)
