load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

# Release: https://github.com/REPO/releases/tag/YYY
# Get SHA256: `wget https://github.com/$REPO/archive/$COMMIT.tar.gz && sha256sum $COMMIT.tar.gz`
#
# To override with local branches, pass `--override_repository=REPO=/local/path` to Bazel
# or persist the option in `.bazelrc`.

PROXY_WASM_HOST_COMMIT = "5574daf453888e50e7f5ef53e05ad425a0b7fb5c"  # 2023-05-09
PROXY_WASM_HOST_SHA256 = "dd92ac24f3ce58aa15276f90c8a1ee727a867e158dd5bdd03d61cd2eabf21043"

http_archive(
    name = "proxy_wasm_cpp_host",
    sha256 = PROXY_WASM_HOST_SHA256,
    strip_prefix = "proxy-wasm-cpp-host-" + PROXY_WASM_HOST_COMMIT,
    url = "https://github.com/proxy-wasm/proxy-wasm-cpp-host/archive/" + PROXY_WASM_HOST_COMMIT + ".tar.gz",
)

PROXY_WASM_CPP_COMMIT = "921039ae983ce053bf5cba78a85a3c08ff9791e5"  # 2023-05-01
PROXY_WASM_CPP_SHA256 = "a11adfe4e6346d3318ff72643aa5569dc8439d7e8927ed148f93226fa255cc7a"

http_archive(
    name = "proxy_wasm_cpp_sdk",
    sha256 = PROXY_WASM_CPP_SHA256,
    strip_prefix = "proxy-wasm-cpp-sdk-" + PROXY_WASM_CPP_COMMIT,
    url = "https://github.com/proxy-wasm/proxy-wasm-cpp-sdk/archive/" + PROXY_WASM_CPP_COMMIT + ".tar.gz",
)

PROXY_WASM_RUST_COMMIT = "0.2.1"
PROXY_WASM_RUST_SHA256 = "23f3f2d8c4c8069a2e72693b350d7442b7722d334f73169eea78804ff70cde20"

http_archive(
    name = "proxy_wasm_rust_sdk",
    sha256 = PROXY_WASM_RUST_SHA256,
    strip_prefix = "proxy-wasm-rust-sdk-" + PROXY_WASM_RUST_COMMIT,
    url = "https://github.com/proxy-wasm/proxy-wasm-rust-sdk/archive/v" + PROXY_WASM_RUST_COMMIT + ".tar.gz",
)

# Upgrade googletest to v1.13.0 to support bazel 6.0.0
# TODO merge upstream to proxy-wasm-cpp-host/bazel/repositories.bzl
http_archive(
    name = "com_google_googletest",
    sha256 = "ad7fdba11ea011c1d925b3289cf4af2c66a352e18d4c7264392fead75e919363",
    strip_prefix = "googletest-1.13.0",
    url = "https://github.com/google/googletest/archive/v1.13.0.tar.gz",
)

# Duplicate ProxyWasm WORKSPACE files (dependencies)
# Consider adopting bzlmod for this: https://docs.bazel.build/versions/5.0.0/bzlmod.html

load("@proxy_wasm_cpp_host//bazel:repositories.bzl", "proxy_wasm_cpp_host_repositories")
proxy_wasm_cpp_host_repositories()

load("@proxy_wasm_cpp_host//bazel:dependencies.bzl", "proxy_wasm_cpp_host_dependencies")
proxy_wasm_cpp_host_dependencies()

load("@proxy_wasm_cpp_sdk//bazel:repositories.bzl", "proxy_wasm_cpp_sdk_repositories")
proxy_wasm_cpp_sdk_repositories()

load("@proxy_wasm_cpp_sdk//bazel:dependencies.bzl", "proxy_wasm_cpp_sdk_dependencies")
proxy_wasm_cpp_sdk_dependencies()

load("@proxy_wasm_cpp_sdk//bazel:dependencies_extra.bzl", "proxy_wasm_cpp_sdk_dependencies_extra")
proxy_wasm_cpp_sdk_dependencies_extra()

load("@proxy_wasm_rust_sdk//bazel:repositories.bzl", "proxy_wasm_rust_sdk_repositories")
proxy_wasm_rust_sdk_repositories()

load("@proxy_wasm_rust_sdk//bazel:dependencies.bzl", "proxy_wasm_rust_sdk_dependencies")
proxy_wasm_rust_sdk_dependencies()

# Fetch raze-generated Cargo crates
load("//cargo:crates.bzl", "raze_fetch_remote_crates")
raze_fetch_remote_crates()
