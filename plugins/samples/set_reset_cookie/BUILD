load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_tests")

licenses(["notice"])  

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/strings:str_format",
    ],
)

proxy_wasm_plugin_cpp(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
    deps = [
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/strings:str_format",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_go.wasm",
    ],
    tests = ":tests.textpb",
)
