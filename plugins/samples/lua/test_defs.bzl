# Copyright 2026 Google LLC
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

"""Module providing testing macros for Lua proxy-wasm integration tests."""

load("//:plugins.bzl", "proxy_wasm_tests")

def lua_integration_test(name, config, tests, tags = []):
    native.genrule(
        name = name + "_config_gen",
        srcs = ["integration_tests/utils.lua", config],
        outs = [name + "_config_combined.lua"],
        cmd = "cat $(location integration_tests/utils.lua) $(location %s) > $@" % config,
    )
    proxy_wasm_tests(
        name = name,
        config = name + "_config_combined.lua",
        plugins = [":plugin_cpp.wasm"],
        tests = tests,
        tags = tags,
    )
