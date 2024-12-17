load("//:plugins.bzl", "proxy_wasm_plugin_cpp", "proxy_wasm_tests", "cmake_dep", "configure_make_dep")


licenses(["notice"])  # Apache 2

cmake_dep(
  name = "lexbor",
  cache_entries = {
       "CMAKE_CXX_COMPILER_FORCED": "on",
       "CMAKE_C_COMPILER_FORCED": "on",
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
  name = "libxml2",
  cache_entries = {
      #  "CMAKE_CXX_COMPILER_FORCED": "on",
       "CMAKE_C_COMPILER_FORCED": "on",
       "BUILD_SHARED_LIBS" : "OFF",
       "CMAKE_INSTALL_LIBDIR": "lib",
       "LIBXML2_WITH_PYTHON":"OFF",
       "LIBXML2_WITH_ICONV":"OFF",
       "LIBXML2_WITH_LZMA":"OFF",
       "LIBXML2_WITH_ZLIB":"OFF",
       "LIBXML2_WITH_THREADS":"OFF",
       "LIBXML2_OUTPUT_ENABLED": "OFF",
      #  "CMAKE_CXX_FLAGS":"-stdlib=libc++",
       "CMAKE_C_COMPILER":"clang",
    },
  out_static_libs = ["libxml2.a"],
  lib_source = "@org_gnome_gitlab_libxml2//:all_srcs",
)

# configure_make_dep(
#   name = "libxml2",
#   autogen = True,
#   lib_source = "@org_gnome_gitlab_libxml2//:all_srcs",
#   configure_in_place = True,
#   out_headers_only = True,
#   autogen_options = ["--with-python=no"],
#   configure_options = ["--with-python=no"],
#   targets = [
#     "install"
#     ],
# )

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = ["plugin.cc"],
    deps = [
        "@proxy_wasm_cpp_sdk//contrib:contrib_lib",
        ":libxml2",
    ],
)

proxy_wasm_tests(
    name = "tests",
    plugins = [
        ":plugin_cpp.wasm",
    ],
    tests = ":tests.textpb",
)