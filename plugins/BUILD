package(default_visibility = ["//visibility:public"])

cc_library(
    name = "boost_exception",
    srcs = ["boost_exception.cc"],
    deps = ["@boost//:throw_exception"],
    alwayslink = 1,
)

config_setting(
    name = "benchmarks",
    values = {"define": "run_benchmarks=1"},
)
