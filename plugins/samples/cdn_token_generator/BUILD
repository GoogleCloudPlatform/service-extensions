load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proto_library(
    name = "cdn_token_config_proto",
    srcs = ["cdn_token_config.proto"],
)

cc_proto_library(
    name = "cdn_token_config_cc_proto",
    deps = [":cdn_token_config_proto"],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        ":cdn_token_config_cc_proto",
        "@boringssl//:crypto",
        "@com_google_absl//absl/strings",
        "@com_google_protobuf//:protobuf",
        "@com_google_re2//:re2",
    ],
    linkopts = [
        "-sUSE_PTHREADS=0",
    ],
)

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
)

proxy_wasm_tests(
    name = "tests",
    config = ":tests_config.textpb",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)
