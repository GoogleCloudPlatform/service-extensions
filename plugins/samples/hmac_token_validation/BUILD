load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/time",
        "@boringssl//:ssl",
        "@boost//:url",
        "//:boost_exception",
    ],
    linkopts = [
        "-sUSE_PTHREADS=0",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)