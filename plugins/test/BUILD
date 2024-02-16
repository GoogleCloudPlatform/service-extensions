licenses(["notice"])  # Apache 2

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "framework",
    testonly = 1,
    srcs = ["framework.cc"],
    hdrs = ["framework.h"],
    deps = [
        "@boost//:algorithm",
        "@boost//:dll",
        "@boost//:filesystem",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_googletest//:gtest",
        "@proxy_wasm_cpp_host//:base_lib",
        "@proxy_wasm_cpp_host//test:utility_lib",
    ],
)

cc_library(
    name = "dynamic_test",
    testonly = 1,
    srcs = ["dynamic_test.cc"],
    hdrs = ["dynamic_test.h"],
    deps = [
        ":framework",
        ":runner_cc_proto",
        "@com_google_benchmark//:benchmark",
        "@com_google_googletest//:gtest",
        "@com_google_protobuf//:protobuf",
        "@com_google_re2//:re2",
    ],
)

cc_library(
    name = "runner_lib",
    testonly = 1,
    srcs = ["runner_main.cc"],
    deps = [
        ":dynamic_test",
        ":framework",
        ":runner_cc_proto",
        "@com_google_absl//absl/flags:flag",
        "@com_google_absl//absl/flags:parse",
        "@com_google_benchmark//:benchmark",
        "@com_google_googletest//:gtest",
        "@com_google_protobuf//:protobuf",
    ],
)

cc_binary(
    name = "runner",
    testonly = 1,
    deps = [":runner_lib"],
)

proto_library(
    name = "runner_proto",
    srcs = ["runner.proto"],
)

cc_proto_library(
    name = "runner_cc_proto",
    deps = [":runner_proto"],
)
