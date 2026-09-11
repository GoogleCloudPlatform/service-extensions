load("//:plugins.bzl", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proto_library(
    name = "cookie_config_proto",
    srcs = ["cookie_config.proto"],
)

genrule(
    name = "cookie_config_descriptor",
    srcs = ["cookie_config.proto"],
    outs = ["cookie_config_descriptor.bin"],
    cmd = "$(location @com_google_protobuf//:protoc) --descriptor_set_out=$@ --proto_path=$$(dirname $(location cookie_config.proto)) $(location cookie_config.proto)",
    tools = ["@com_google_protobuf//:protoc"],
)

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    compile_data = [":cookie_config_descriptor"],
    rustc_env = {"PROTO_DESCRIPTOR": "$(execpath :cookie_config_descriptor)"},
    deps = [
        "//bazel/cargo/remote:log",
        "//bazel/cargo/remote:prost-reflect",
        "//bazel/cargo/remote:proxy-wasm",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":tests_config.txtpb",
    plugins = [
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)
