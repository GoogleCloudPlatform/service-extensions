load("//:plugins.bzl", "proxy_wasm_plugin_cpp")
load(":test_defs.bzl", "lua_integration_test")

licenses(["notice"])

cc_library(
    name = "stream_state_interface",
    hdrs = ["stream_state_interface.h"],
)

cc_library(
    name = "coroutine",
    srcs = ["coroutine.cc"],
    hdrs = ["coroutine.h"],
    deps = [
        ":envoy_lua_api",
        ":lua_state",
        ":stream_state_interface",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_absl//absl/strings",
        "@luabridge3//:luabridge3",
        "@lua//:lua",
        "@proxy_wasm_cpp_sdk//:proxy_wasm_intrinsics",
    ],
)

cc_library(
    name = "envoy_lua_api",
    srcs = [
        "envoy_lua_api.cc",
    ],
    hdrs = [
        "envoy_lua_api.h",
    ],
    deps = [
        ":stream_state_interface",
        "@com_google_absl//absl/container:flat_hash_map",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/strings:cord",
        "@com_google_absl//absl/strings:str_format",
        "@com_google_absl//absl/time",
        "@luabridge3//:luabridge3",
        "@lua//:lua",
        "@proxy_wasm_cpp_sdk//:proxy_wasm_intrinsics",
    ],
)

cc_library(
    name = "lua_plugin_lib",
    srcs = ["lua_plugin.cc"],
    hdrs = ["lua_plugin.h"],
    deps = [
        ":coroutine",
        ":lua_state",
        "@com_google_absl//absl/base",
        "@com_google_absl//absl/base:nullability",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_absl//absl/strings",
        "@lua//:lua",
        "@proxy_wasm_cpp_sdk//:proxy_wasm_intrinsics",
    ],
)

proxy_wasm_plugin_cpp(
    name = "plugin_cpp.wasm",
    srcs = [
        "lua_plugin_registration.cc",
    ],
    linkopts = ["-sINITIAL_MEMORY=33554432"],
    deps = [
        ":lua_plugin_lib",
    ],
)

cc_library(
    name = "lua_state",
    srcs = [
        "envoy_lua_api_registration.cc",
        "lua_state.cc",
    ],
    hdrs = [
        "envoy_lua_api_registration.h",
        "envoy_lua_api_shims.h",
        "lua_state.h",
        "status_macros.h",
    ],
    deps = [
        ":envoy_lua_api",
        ":stream_state_interface",
        "@com_google_absl//absl/base:core_headers",
        "@com_google_absl//absl/base:nullability",
        "@com_google_absl//absl/container:flat_hash_map",
        "@com_google_absl//absl/functional:any_invocable",
        "@com_google_absl//absl/memory",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/status:statusor",
        "@com_google_absl//absl/strings",
        "@com_google_absl//absl/strings:str_format",
        "@com_google_absl//absl/types:span",
        "@luabridge3//:luabridge3",
        "@lua//:lua",
    ],
)

cc_library(
    name = "proxy_wasm_test_stubs",
    testonly = True,
    srcs = ["proxy_wasm_test_stubs.cc"],
    hdrs = ["proxy_wasm_test_stubs.h"],
    deps = [
        ":stream_state_interface",
        "@com_google_googletest//:gtest",
        "@com_google_absl//absl/base:nullability",
        "@com_google_absl//absl/strings",
        "@proxy_wasm_cpp_sdk//:proxy_wasm_intrinsics",
    ],
    alwayslink = True,
)

cc_test(
    name = "coroutine_test",
    linkstatic = True,
    linkopts = ["-Wl,--allow-shlib-undefined"],
    srcs = ["coroutine_test.cc"],
    deps = [
        ":coroutine",
        ":lua_state",
        ":proxy_wasm_test_stubs",
        "@com_google_googletest//:gtest_main",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/strings",
        "@luabridge3//:luabridge3",
        "@lua//:lua",
        "@proxy_wasm_cpp_sdk//:proxy_wasm_intrinsics",
    ],
)

cc_test(
    name = "lua_state_test",
    linkstatic = True,
    linkopts = ["-Wl,--allow-shlib-undefined"],
    srcs = ["lua_state_test.cc"],
    deps = [
        ":envoy_lua_api",
        ":lua_state",
        ":proxy_wasm_test_stubs",
        "@com_google_googletest//:gtest_main",
        "@com_google_absl//absl/functional:any_invocable",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/strings",
        "@luabridge3//:luabridge3",
        "@lua//:lua",
        "@proxy_wasm_cpp_sdk//:proxy_wasm_intrinsics",
    ],
)

cc_test(
    name = "envoy_lua_api_test",
    linkstatic = True,
    linkopts = ["-Wl,--allow-shlib-undefined"],
    srcs = ["envoy_lua_api_test.cc"],
    deps = [
        ":envoy_lua_api",
        ":proxy_wasm_test_stubs",
        "@com_google_googletest//:gtest",
        "@com_google_googletest//:gtest_main",
        "@com_google_absl//absl/status",
        "@com_google_absl//absl/strings",
        "@proxy_wasm_cpp_host//:base_lib",
        "@proxy_wasm_cpp_sdk//:common_lib",
    ],
)


# TEST TARGETS

lua_integration_test(
    name = "plugin_cpp_lua_base_library_tests",
    tests = "integration_tests/lua_base_library_test.textpb",
    config = "integration_tests/lua_base_library_test.lua",
)

lua_integration_test(
    name = "plugin_cpp_headers_tests",
    tests = "integration_tests/headers_test.textpb",
    config = "integration_tests/headers_test.lua",
)

lua_integration_test(
    name = "plugin_cpp_ssl_stream_info_tests",
    tests = "integration_tests/ssl_stream_info_test.textpb",
    config = "integration_tests/ssl_stream_info_test.lua",
)

lua_integration_test(
    name = "plugin_cpp_lifecycle_e2e_tests",
    tests = "integration_tests/lifecycle_e2e_test.textpb",
    config = "integration_tests/lifecycle_e2e_test.lua",
)

lua_integration_test(
    name = "plugin_cpp_multichunk_tests",
    tests = "integration_tests/multichunk_test.textpb",
    config = "integration_tests/multichunk_test.lua",
)
