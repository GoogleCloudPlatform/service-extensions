load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_go", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

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

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
    deps = ["@com_github_proxy_wasm_proxy_wasm_go_sdk//proxywasm:go_default_library"]
)

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "@proxy_wasm//:proxy_wasm",
        "@base64//:base64",
        "@hmac//:hmac",
        "@regex//:regex",
        "@sha2//:sha2",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_go.wasm",
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)