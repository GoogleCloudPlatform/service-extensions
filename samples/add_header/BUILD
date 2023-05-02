# TODO(mstevenson): describe this package.

load("//samples:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "@proxy_wasm_rust_sdk//:proxy_wasm",
        "@proxy_wasm_rust_sdk//bazel/cargo:log",
    ],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@proxy_wasm_cpp_sdk//contrib:contrib_lib",
    ],
)

cc_test(
    name = "plugin_test",
    srcs = ["test.cc"],
    data = [
        ":plugin_cpp.wasm",
        ":plugin_rust.wasm",
    ],
    deps = [
        "//samples:test_fixture",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_googletest//:gtest_main",
        "@proxy_wasm_cpp_host//:base_lib",
        "@proxy_wasm_cpp_host//:v8_lib",
        "@proxy_wasm_cpp_host//test:utility_lib",
    ],
)
