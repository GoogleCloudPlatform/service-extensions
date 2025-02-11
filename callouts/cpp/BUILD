package(default_visibility = ["//visibility:public"])

licenses(["notice"])  # Apache 2

cc_library(
    name = "callout_service_cpp_lib",
    srcs = glob(['service/callout_server.h']),
    deps = [
        "@com_github_grpc_grpc//:grpc++",
        "@com_google_absl//absl/log:log",
        ":envoy_cpp",
    ],
)

load("@rules_proto_grpc//cpp:defs.bzl", "cpp_grpc_library")

cc_proto_library(
    name = "envoy_proto",
    deps = ['@envoy_api//:v3_protos']
)

cpp_grpc_library(
    name = "envoy_cpp",
    protos = ['@envoy_api//envoy/service/ext_proc/v3:pkg'],
    deps = [':envoy_proto']
)
