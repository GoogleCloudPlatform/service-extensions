// Copyright 2023 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


// NOTE: This is a test for snippet-bot
// Snippet Bot - https://github.com/googleapis/repo-automation-bots/tree/main/packages/snippet-bot

// [START serviceextensions_example_test1_123]
use std::fmt;

struct Circle {
    radius: i32
}
// [END serviceextensions_example_test1_123]


// [START serviceextensions_example_test2_123]
impl fmt::Display for Circle {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "Circle of radius {}", self.radius)
    }
}
// Note: Tag below is not `END` tag
// [START serviceextensions_example_test2_123]


// [START serviceextensions_example_test3_123]
fn main() {
    let circle = Circle { radius: 6 };
    println!("{}", circle.to_string());
}
// Note: Tag below ends with _456.
// [END serviceextensions_example_test3_456]
