# plugins/test/tools/wasmtime_precompiler/BUILD

cc_binary(
    name = "wasmtime_precompiler",
    srcs = ["wasmtime_precompiler.cc"],
    # Explicitly add the include path for the Wasmtime C++ API headers.
    includes = [
        "external/com_github_bytecodealliance_wasmtime/crates/c-api/include",
    ],
    deps = [
        # Rely entirely on the proxy_wasm_cpp_host target to expose the Wasmtime
        # C/C++ API headers and link the compiled library.
        "@proxy_wasm_cpp_host//:wasmtime_lib",
        
        # Keep this for base types/utilities if needed.
        "@proxy_wasm_cpp_host//:base_lib", 
    ],
)