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

def proxy_wasm_plugin_cpp(**kwargs):
    proxy_wasm_cc_binary(
        **kwargs
    )

def proxy_wasm_tests(
        name,
        tests,
        plugins = [],
        config = None):
    """Generates cc_test targets for each provided wasm plugin.

    Args:
      name: Base name for the test targets.
      tests: TestSuite textproto config file that contains the tests to run.
      plugins: List of plugins (wasm build targets) to run tests on.
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
            data = [tests, plugin] + ([config] if config else []),
            deps = ["//test:runner_lib"],
        )

def proxy_wasm_cc_test(deps = [], **kwargs):
    """Wraps cc_test to select benchmarks or unit tests based on build attributes."""
    cc_test(
        deps = deps + [
            "@com_google_benchmark//:benchmark",
            "@com_google_googletest//:gtest",
        ] + select({
            "//:benchmarks": ["@com_google_benchmark//:benchmark_main"],
            "//conditions:default": ["@com_google_googletest//:gtest_main"],
        }),
        **kwargs
    )
