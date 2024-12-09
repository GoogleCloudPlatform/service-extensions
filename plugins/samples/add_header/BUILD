load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_plugin_rust", "proxy_wasm_tests", "cmake_dep")


licenses(["notice"])  # Apache 2

proxy_wasm_plugin_rust(
    name = "plugin_rust.wasm",
    srcs = ["plugin.rs"],
    deps = [
        "@crate_index//:log",
        "@crate_index//:proxy-wasm",
    ],
)

cmake_dep(
  name = "lexbor",
  cache_entries = {
       "LEXBOR_BUILD_SHARED" : "OFF",
       "LEXBOR_BUILD_STATIC" : "ON",
       "LEXBOR_MAKE_PACKAGES_FILES" : "ON",
       "LEXBOR_BUILD_TESTS_CPP" : "ON",
       "CMAKE_INSTALL_LIBDIR": "lib",
    },
  out_static_libs = ["liblexbor_static.a"],
  lib_source = "@com_github_lexbor//:all_srcs",
)
cmake_dep(
  name = "libsxg",
    cache_entries = {
        "CMAKE_BUILD_TYPE": "Release",
        "SXG_BUILD_EXECUTABLES": "off",
        "SXG_BUILD_SHARED": "off",
        "SXG_BUILD_STATIC": "on",
        "SXG_WITH_CERT_CHAIN": "off",
        "RUN_TEST": "off",
        "CMAKE_INSTALL_LIBDIR": "lib",
    },
    lib_source = "@libsxg//:all_srcs",
    out_static_libs = ["libsxg.a"],
    # tags = ["skip_on_windows"],
    # # Use boringssl alias to select fips vs non-fips version.
    # deps = ["//bazel:boringssl"],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@proxy_wasm_cpp_sdk//contrib:contrib_lib",
        ":libsxg",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
        ":plugin_rust.wasm",
    ],
    tests = ":tests.textpb",
)
