load("//:plugins.bzl", "proxy_wasm_plugin_go", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_go(
    name = "plugin_go.wasm",
    srcs = ["plugin.go"],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@boringssl//:crypto",
        "@com_google_absl//absl/strings",
    ],
    linkopts = [
        "-sUSE_PTHREADS=0",
        "-sSHARED_MEMORY=0",
        "-sRELOCATABLE=0",
        "-sASYNCIFY_LAZY_LOAD_CODE=0",
        "-sIMPORTED_MEMORY=0",
        "-sALLOW_MEMORY_GROWTH=1",
    ],
)

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//bazel/cargo/remote:proxy-wasm",
    ],
)

proxy_wasm_tests(
    name = "tests",
    config = ":config.json",
    plugins = [
        ":plugin_go.wasm",
        ":plugin_cpp.wasm", 
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)
