package(default_visibility = ["//visibility:public"])

licenses(["notice"])  # Apache 2

cc_binary(
    name = "callout_service_cpp",
    srcs = glob(['service/callout_server.cc']),
    deps = [
        "@com_github_grpc_grpc//:grpc++",
        ":envoy_cpp",
    ],
)

load("@rules_proto_grpc//cpp:defs.bzl", "cpp_grpc_library", "cpp_proto_library")

cc_proto_library(
    name = "envoy_proto",
    deps = ['@envoy_api//:v3_protos']
)

cpp_grpc_library(
    name = "envoy_cpp",
    protos = ['@envoy_api//envoy/service/ext_proc/v3:pkg'],
    deps = [':envoy_proto']
)

# cc_test(
#     name = "tests",
#     plugins = [
#         ":callout_service_cpp",
#     ],
#     tests = ":tests.textpb",
# )
