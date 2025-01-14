load("@bazel_gazelle//:def.bzl", "gazelle")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "boost_exception",
    srcs = ["boost_exception.cc"],
    deps = ["@boost//:throw_exception"],
    alwayslink = 1,
)

# gazelle:prefix github.com/GoogleCloudPlatform/service-extensions/plugins
gazelle(name = "gazelle")
