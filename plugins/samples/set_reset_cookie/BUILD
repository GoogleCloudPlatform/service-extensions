load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_tests")
load("@com_google_protobuf//:protobuf.bzl", "cc_proto_library")
load("@rules_proto//proto:defs.bzl", "proto_library")

licenses(["notice"])

proto_library(
    name = "cookie_config_proto",
    srcs = ["cookie_config.proto"],
)

cc_proto_library(
    name = "cookie_config_cc_proto",
    deps = [":cookie_config_proto"],
)

proxy_wasm_plugin_cpp(
    name = "cookie_manager.wasm",
    srcs = ["plugin.cc"],
    deps = [
        ":cookie_config_cc_proto",
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/strings:str_format",
        "@com_google_protobuf//:protobuf",
    ],
)

proxy_wasm_tests(
    name = "cookie_manager_tests",
    plugins = [
        ":cookie_manager.wasm",
    ],
    tests = ":tests.textpb",
)
