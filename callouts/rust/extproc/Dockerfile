# Copyright 2025 Google LLC.
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

# Stage 1: Build the Rust application
FROM rust:1.82-slim-bullseye AS builder

# Install required dependencies
RUN apt-get update && apt-get install -y \
    curl \
    pkg-config \
    libssl-dev \
    protobuf-compiler \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install buf
RUN curl -sSL \
    "https://github.com/bufbuild/buf/releases/download/v1.29.0/buf-$(uname -s)-$(uname -m)" \
    -o "/usr/local/bin/buf" && \
    chmod +x "/usr/local/bin/buf"

# Set environment variables
ENV RUST_LOG=info

# Set default example and allow override via build-arg
ARG EXAMPLE=basic
ENV EXAMPLE=${EXAMPLE}

# Create a new empty shell project
WORKDIR /usr/src/app
COPY . .

# Build specific example with release optimizations
RUN cargo build --release --example ${EXAMPLE}

# Stage 2: Create the runtime image
FROM debian:bullseye-slim

# Set default example and allow override via build-arg
ARG EXAMPLE=basic
ENV EXAMPLE=${EXAMPLE}

# Install necessary dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libssl1.1 \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV RUST_LOG=info

# Set the working directory
WORKDIR /app

# Copy the built example
COPY --from=builder /usr/src/app/target/release/examples/${EXAMPLE} /app/server

# Create the directory structure expected by the server
RUN mkdir -p /app/extproc/ssl_creds

# Copy certificates to the expected location
COPY --from=builder /usr/src/app/ssl_creds/* /app/extproc/ssl_creds/

# Expose necessary ports
EXPOSE 80 443 8080

# Create a non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Change ownership and switch to non-root user
RUN chown -R appuser:appgroup /app
USER appuser

ENTRYPOINT ["/app/server"]