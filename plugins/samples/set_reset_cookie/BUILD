load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proto_library(
    name = "cookie_config_proto",
    srcs = ["cookie_config.proto"],
)

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = [
        "cookie_config.pb.go",
        "plugin.go",
    ],
    deps = [
        "@org_golang_google_protobuf//encoding/prototext:go_default_library",
        "@org_golang_google_protobuf//reflect/protoreflect:go_default_library",
        "@org_golang_google_protobuf//runtime/protoimpl:go_default_library",
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
