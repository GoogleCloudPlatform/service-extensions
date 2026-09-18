load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_tests")
load("@io_bazel_rules_go//proto:def.bzl", "go_proto_library")

licenses(["notice"])  # Apache 2

proto_library(
    name = "cookie_config_proto",
    srcs = ["cookie_config.proto"],
)

go_proto_library(
    name = "cookie_config_go_proto",
    importpath = "github.com/GoogleCloudPlatform/service-extensions/plugins/samples/set_reset_cookie/cookieconfig",
    proto = ":cookie_config_proto",
)

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
    deps = [
        ":cookie_config_go_proto",
        "@org_golang_google_protobuf//encoding/prototext:go_default_library",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":tests_config.txtpb",
    plugins = [
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)
