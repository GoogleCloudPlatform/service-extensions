# Copyright 2025 Google LLC
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

.PHONY: build clean test deploy update update-config check-rust setup fmt lint info help

PLUGIN_NAME := jwt_generator
WASM_FILE := target/wasm32-wasi/release/jwt_generator_plugin.wasm
CONFIG_FILE := config.json

# Build the WebAssembly plugin
build:
	@echo "Building JWT Generator Plugin (Rust)..."
	cargo build --target=wasm32-wasi --release
	@echo "Build complete: $(WASM_FILE)"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	cargo clean
	@echo "Clean complete"

# Run tests
test:
	@echo "Running tests..."
	cargo test

# Build with debug symbols
build-debug:
	@echo "Building JWT Generator Plugin with debug symbols..."
	cargo build --target=wasm32-wasi
	@echo "Debug build complete"

# Check code without building
check:
	@echo "Checking code..."
	cargo check --target=wasm32-wasi

# Validate the configuration file
validate-config:
	@echo "Validating configuration..."
	@if [ ! -f $(CONFIG_FILE) ]; then \
		echo "Error: $(CONFIG_FILE) not found"; \
		exit 1; \
	fi
	@jq empty $(CONFIG_FILE) 2>/dev/null && echo "Configuration valid" || (echo "Error: Invalid JSON in $(CONFIG_FILE)" && exit 1)

# Deploy to Google Cloud (requires gcloud CLI)
deploy: build validate-config
	@echo "Deploying JWT Generator Plugin to Google Cloud..."
	@if [ -z "$(EXTENSION_NAME)" ]; then \
		echo "Error: EXTENSION_NAME not set. Usage: make deploy EXTENSION_NAME=jwt-extension"; \
		exit 1; \
	fi
	gcloud service-extensions deploy $(EXTENSION_NAME) \
		--wasm-file=$(WASM_FILE) \
		--config-file=$(CONFIG_FILE) \
		--location=us-central1
	@echo "Deployment complete"

# Update existing deployment
update: build validate-config
	@echo "Updating JWT Generator Plugin deployment..."
	@if [ -z "$(EXTENSION_NAME)" ]; then \
		echo "Error: EXTENSION_NAME not set. Usage: make update EXTENSION_NAME=jwt-extension"; \
		exit 1; \
	fi
	gcloud service-extensions update $(EXTENSION_NAME) \
		--wasm-file=$(WASM_FILE) \
		--config-file=$(CONFIG_FILE) \
		--location=us-central1
	@echo "Update complete"

# Update only configuration (no code changes)
update-config: validate-config
	@echo "Updating configuration only..."
	@if [ -z "$(EXTENSION_NAME)" ]; then \
		echo "Error: EXTENSION_NAME not set. Usage: make update-config EXTENSION_NAME=jwt-extension"; \
		exit 1; \
	fi
	gcloud service-extensions update $(EXTENSION_NAME) \
		--config-file=$(CONFIG_FILE) \
		--location=us-central1
	@echo "Configuration update complete"

# Check if Rust and wasm32-wasi target are installed
check-rust:
	@which cargo > /dev/null || (echo "Error: Rust not found. Install from https://rustup.rs/" && exit 1)
	@echo "Rust found: $$(rustc --version)"
	@rustup target list --installed | grep -q wasm32-wasi || (echo "Installing wasm32-wasi target..." && rustup target add wasm32-wasi)
	@echo "wasm32-wasi target installed"

# Setup development environment
setup: check-rust
	@echo "Setting up development environment..."
	rustup target add wasm32-wasi
	cargo fetch
	@echo "Setup complete"

# Format Rust code
fmt:
	@echo "Formatting Rust code..."
	cargo fmt
	@echo "Formatting complete"

# Run Rust linter
lint:
	@echo "Running linter..."
	cargo clippy --target=wasm32-wasi -- -D warnings

# Run cargo fix
fix:
	@echo "Running cargo fix..."
	cargo fix --target=wasm32-wasi --allow-dirty

# Build documentation
doc:
	@echo "Building documentation..."
	cargo doc --no-deps --open

# Display plugin information
info:
	@echo "Plugin Information:"
	@echo "  Name: $(PLUGIN_NAME)"
	@echo "  WASM File: $(WASM_FILE)"
	@echo "  Config File: $(CONFIG_FILE)"
	@if [ -f $(WASM_FILE) ]; then \
		echo "  WASM Size: $$(wc -c < $(WASM_FILE)) bytes"; \
		echo "  WASM Size (Human): $$(ls -lh $(WASM_FILE) | awk '{print $$5}')"; \
	else \
		echo "  WASM Size: Not built yet"; \
	fi

# Optimize WASM file (additional optimization with wasm-opt)
optimize: build
	@echo "Optimizing WASM file..."
	@which wasm-opt > /dev/null || (echo "Warning: wasm-opt not found. Install from https://github.com/WebAssembly/binaryen" && exit 0)
	wasm-opt -Oz $(WASM_FILE) -o $(WASM_FILE).opt
	mv $(WASM_FILE).opt $(WASM_FILE)
	@echo "Optimization complete"

# Run benchmarks
bench:
	@echo "Running benchmarks..."
	cargo bench --target=wasm32-wasi

# Update dependencies
update-deps:
	@echo "Updating dependencies..."
	cargo update
	@echo "Dependencies updated"

# Security audit
audit:
	@echo "Running security audit..."
	@which cargo-audit > /dev/null || cargo install cargo-audit
	cargo audit

# Show outdated dependencies
outdated:
	@echo "Checking for outdated dependencies..."
	@which cargo-outdated > /dev/null || cargo install cargo-outdated
	cargo outdated

# Show help
help:
	@echo "JWT Generator Plugin (Rust) - Makefile Commands"
	@echo ""
	@echo "Build Commands:"
	@echo "  make build              Build the WASM plugin (release)"
	@echo "  make build-debug        Build with debug symbols"
	@echo "  make check              Check code without building"
	@echo "  make clean              Remove build artifacts"
	@echo "  make optimize           Build and optimize with wasm-opt"
	@echo ""
	@echo "Test Commands:"
	@echo "  make test               Run Rust tests"
	@echo "  make bench              Run benchmarks"
	@echo "  make validate-config    Validate configuration file"
	@echo ""
	@echo "Deployment Commands:"
	@echo "  make deploy EXTENSION_NAME=jwt-extension    Deploy to Google Cloud"
	@echo "  make update EXTENSION_NAME=jwt-extension    Update existing deployment"
	@echo "  make update-config EXTENSION_NAME=jwt-extension  Update configuration only"
	@echo ""
	@echo "Development Commands:"
	@echo "  make setup              Setup development environment"
	@echo "  make fmt                Format Rust code"
	@echo "  make lint               Run clippy linter"
	@echo "  make fix                Run cargo fix"
	@echo "  make doc                Build and open documentation"
	@echo "  make info               Display plugin information"
	@echo ""
	@echo "Maintenance Commands:"
	@echo "  make update-deps        Update dependencies"
	@echo "  make audit              Run security audit"
	@echo "  make outdated           Check for outdated dependencies"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make deploy EXTENSION_NAME=my-jwt-extension"
	@echo "  make update-config EXTENSION_NAME=my-jwt-extension"

.DEFAULT_GOAL := help