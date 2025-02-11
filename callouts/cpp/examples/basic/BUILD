package(default_visibility = ["//visibility:public"])

licenses(["notice"])  # Apache 2

cc_binary(
    name = "basic_cpp",
    srcs = ["main.cc"],
    deps = [
        ":basic_cpp_lib",
    ],
)

cc_library(
    name = "basic_cpp_lib",
    srcs = ["basic.h"],
    deps = [
        "//:callout_service_cpp_lib",
    ],
)

cc_test(
    name = "basic_cpp_tests",
    srcs = ["basic_test.cc"],
    deps = [
        ":basic_cpp_lib",
        "@com_google_googletest//:gtest",
        "@com_google_googletest//:gtest_main",
    ],
)
