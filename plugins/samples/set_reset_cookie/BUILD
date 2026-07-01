load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proto_library(
    name = "cookie_config_proto",
    srcs = ["cookie_config.proto"],
)

cc_proto_library(
    name = "cookie_config_cc_proto",
    deps = [":cookie_config_proto"],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        ":cookie_config_cc_proto",
        "@com_google_absl//absl/strings",
        "@com_google_protobuf//:protobuf",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":tests_config.textpb",
    plugins = [
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)
