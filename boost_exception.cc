/*
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <boost/throw_exception.hpp>

// NOTE: Ideally we would undefine BOOST_NO_EXCEPTIONS so we don't have to
// implement custom handlers here. I can't make it work. It's probably because
// Boost library Bazel targets are defined by rules_boost, and their copts
// cannot be overridden by copts for the wasm cc_binary:
// https://github.com/emscripten-core/emsdk/issues/972

namespace boost {

void throw_exception(std::exception const& e) { exit(1); }
void throw_exception(std::exception const& e,
                     boost::source_location const& loc) {
  exit(1);
}

}  // namespace boost
