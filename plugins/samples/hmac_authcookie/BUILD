load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/time",
        "@com_google_re2//:re2",
        "@boringssl//:ssl",
    ],
    linkopts = [
        # To avoid the error:
        # library_pthread.js:26: #error "STANDALONE_WASM does not support shared memories yet".
        # Disabling the pthreads avoids the inclusion of the library_pthread.js.
        "-sUSE_PTHREADS=0",
    ],
)

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:base64",
        "//bazel/cargo/remote:hmac",
        "//bazel/cargo/remote:regex",
        "//bazel/cargo/remote:proxy-wasm",
        "//bazel/cargo/remote:sha2",
        "//bazel/cargo/remote:hex",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)