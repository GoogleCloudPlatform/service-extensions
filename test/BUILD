licenses(["notice"])  # Apache 2

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "framework",
    testonly = 1,
    hdrs = ["framework.h"],
    srcs = ["framework.cc"],
    deps = [
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_googletest//:gtest",
        "@proxy_wasm_cpp_host//:base_lib",
        "@proxy_wasm_cpp_host//test:utility_lib",
    ],
)
