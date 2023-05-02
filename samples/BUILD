licenses(["notice"])  # Apache 2

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "test_fixture",
    testonly = 1,
    hdrs = ["test_fixture.h"],
    srcs = ["test_fixture.cc"],
    deps = [
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_googletest//:gtest_main",
        "@proxy_wasm_cpp_host//:base_lib",
        "@proxy_wasm_cpp_host//test:utility_lib",
    ],
)
