"""Plugin build wrappers."""

load("@proxy_wasm_cpp_host//bazel:wasm.bzl", "wasm_rust_binary")
load("@proxy_wasm_cpp_sdk//bazel:defs.bzl", "proxy_wasm_cc_binary")

def proxy_wasm_plugin_rust(**kwargs):
    wasm_rust_binary(
        rustc_flags = [
            "-Copt-level=2",  # Optimize for binary size
            "-Cstrip=debuginfo",  # Strip debug info, but leave symbols
            "-Clto=yes",  # Link time optimization of the whole binary
        ],
        **kwargs
    )

def proxy_wasm_plugin_cpp(**kwargs):
    proxy_wasm_cc_binary(
        **kwargs
    )
