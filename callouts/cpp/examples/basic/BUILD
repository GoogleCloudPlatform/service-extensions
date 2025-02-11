package(default_visibility = ["//visibility:public"])

licenses(["notice"])  # Apache 2

cc_binary(
    name = "basic_cpp",
    srcs = ["basic.cc", "basic.h"],
    deps = [
        "//:callout_service_cpp_lib",
    ],
)

cc_test(
    name = "basic_cpp_tests",
    srcs = ["basic_test.cc"],
    deps = [
        ":basic_cpp",
        "//:callout_service_cpp_lib",
        "@com_google_googletest//:gtest",
        "@com_google_googletest//:gtest_main",
    ],
)
