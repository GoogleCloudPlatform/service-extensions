# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Plugin build wrappers."""

load("@io_bazel_rules_go//go:def.bzl", "go_binary")
load("@proxy_wasm_cpp_host//bazel:wasm.bzl", "wasm_rust_binary")
load("@proxy_wasm_cpp_sdk//bazel:defs.bzl", "proxy_wasm_cc_binary")
load("@rules_cc//cc:defs.bzl", "cc_test")

def proxy_wasm_plugin_rust(**kwargs):
    wasm_rust_binary(
        wasi = True,
        rustc_flags = [
            "-Copt-level=3",  # Optimize for binary speed
            "-Cstrip=debuginfo",  # Strip debug info, but leave symbols
            "-Clto=yes",  # Link time optimization of the whole binary
        ],
        **kwargs
    )

def proxy_wasm_plugin_go(name, srcs, deps = [], **kwargs):
    """Generates a go binary from the provided main package srcs.

    Args:
      name: Name for the wasm module.
      srcs: Source files containing a main package.
      deps: Optional dependencies of the go binary.
    """

    go_binary(
        name = name,
        srcs = srcs,
        deps = deps + [
            "@com_github_proxy_wasm_proxy_wasm_go_sdk//proxywasm:go_default_library",
            "@com_github_proxy_wasm_proxy_wasm_go_sdk//proxywasm/types:go_default_library",
        ],
        goarch = "wasm",
        goos = "wasip1",
        linkmode = "c-shared",
        **kwargs
    )

def proxy_wasm_plugin_cpp(copts = [], **kwargs):
    proxy_wasm_cc_binary(
        copts = copts + ["-Werror=return-type"],
        **kwargs
    )

def proxy_wasm_tests(
        name,
        tests,
        plugins = [],
        data = [],
        config = None):
    """Generates cc_test targets for each provided wasm plugin.

    Args:
      name: Base name for the test targets.
      tests: TestSuite textproto config file that contains the tests to run.
      plugins: List of plugins (wasm build targets) to run tests on.
      data: Supplementary inputs, such as test data payloads.
      config: Optional path to plugin config file.
    """
    for plugin in plugins:
        cc_test(
            name = "%s_%s" % (plugin.removeprefix(":").removesuffix(".wasm"), name),
            args = [
                "--proto=$(rootpath %s)" % tests,
                "--plugin=$(rootpath %s)" % plugin,
                "--config=$(rootpath %s)" % config if config else "",
            ],
            data = [tests, plugin] + ([config] if config else []) + data,
            deps = ["//test:runner_lib"],
        )
