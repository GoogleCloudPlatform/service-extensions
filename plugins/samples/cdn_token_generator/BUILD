load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@boringssl//:crypto",
        "@com_google_absl//absl/strings",
        "@com_google_re2//:re2",
    ],
    linkopts = [
        # To avoid the error:
        # emcc: error: INITIAL_HEAP is currently not compatible with IMPORTED_MEMORY
        # (which is enabled indirectly via SHARED_MEMORY).
        # Disabling pthreads avoids shared memory issues with WASM.
        "-sUSE_PTHREADS=0",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":config.data",
    plugins = [
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)
