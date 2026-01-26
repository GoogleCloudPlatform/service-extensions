package(default_visibility = ["//visibility:public"])

licenses(["notice"])  # Apache 2

exports_files(["service/main.cc"])

cc_library(
    name = "callout_service_cpp_lib",
    srcs = ['service/callout_server.h'],
    deps = [
        "@boost//:beast",
        "@com_google_absl//absl/flags:flag",
        "@com_google_absl//absl/flags:parse",
        "@com_google_absl//absl/log:log",
        "@com_github_grpc_grpc//:grpc++",
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

cc_library(
    name = "jwt-cpp",
    deps = ["@com_github_thalhammer_jwt_cpp//:jwt-cpp"],
    visibility = ["//visibility:public"],
)
