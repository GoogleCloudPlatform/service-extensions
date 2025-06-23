package(default_visibility = ["//visibility:public"])

licenses(["notice"])  # Apache 2

cc_binary(
    name = "custom_callout_server_cpp",
    srcs = ["//:service/main.cc"],
    deps = [
        ":custom_callout_server_lib",
    ],
    includes = ["."],
)

cc_library(
    name = "custom_callout_server_lib",
    srcs = ["custom_callout_server.h"],
    deps = [
        "//:callout_service_cpp_lib",
    ],
)

cc_test(
    name = "custom_callout_server_tests",
    srcs = ["custom_callout_server_test.cc"],
    deps = [
        ":custom_callout_server_lib",
        "@com_google_googletest//:gtest",
        "@com_google_googletest//:gtest_main",
    ],
)
