// Copyright 2025 Google LLC
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
use std::process::Command;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Download Envoy protos if they don't exist
    if !std::path::Path::new("proto").exists() {
        println!("Downloading Envoy protos...");
        std::fs::create_dir_all("proto")?;
        Command::new("buf")
            .args(&["export", "buf.build/envoyproxy/envoy", "-o", "proto"])
            .status()?;
    }

    let protos = [
        "envoy/service/ext_proc/v3/external_processor.proto",
        "envoy/config/core/v3/base.proto",
        "envoy/extensions/filters/http/ext_proc/v3/processing_mode.proto",
        "envoy/type/v3/http_status.proto",
        "envoy/type/v3/percent.proto",
        "envoy/type/v3/semantic_version.proto",
        "xds/core/v3/context_params.proto",
    ];

    // Configure tonic-build
    tonic_build::configure()
        .build_server(true)
        .out_dir("src/gen")
        .compile(
            &protos
                .iter()
                .map(|p| format!("proto/{}", p))
                .collect::<Vec<_>>(),
            &["proto"],
        )?;

    println!("cargo:rerun-if-changed=proto");
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=src/gen");

    Ok(())
}
