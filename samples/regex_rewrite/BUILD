load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust")

licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "//cargo:regex",
        "//cargo:proxy_wasm",
        "//cargo:log",
    ],
)

# Blocked on emscripten update to fix Abseil/RE2 compatibility:
# https://github.com/proxy-wasm/proxy-wasm-cpp-sdk/pull/157
# NOTE: Plugins can be built using that PR -- it's blocked on Envoy.
#proxy_wasm_plugin_cpp(
#    name = "plugin_cpp.wasm",
#    srcs = ["plugin.cc"],
#    deps = [
#        "@com_google_re2//:re2",
#        "@proxy_wasm_cpp_sdk//contrib:contrib_lib",
#    ],
#)

cc_test(
    name = "plugin_test",
    srcs = ["test.cc"],
    data = [
        #":plugin_cpp.wasm",
        ":plugin_rust.wasm",
    ],
    deps = [
        "//test:framework",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_googletest//:gtest_main",
        "@proxy_wasm_cpp_host//:base_lib",
        "@proxy_wasm_cpp_host//:v8_lib",
        "@proxy_wasm_cpp_host//test:utility_lib",
    ],
)
