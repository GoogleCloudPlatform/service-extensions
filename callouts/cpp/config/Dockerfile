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

ARG EXAMPLE_TYPE=basic

FROM debian:12-slim AS builder

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget clang g++ git python3 python3-pip \
    libssl-dev libboost-all-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Bazelisk
RUN wget -O /usr/local/bin/bazel https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64 \
    && chmod +x /usr/local/bin/bazel

WORKDIR /app
COPY . .

# Build with explicit output path
RUN EXAMPLE_TYPE=${EXAMPLE_TYPE:-basic} && \
    bazel build --config=clang --cxxopt='-std=c++17' //examples/${EXAMPLE_TYPE}:custom_callout_server_cpp && \
    mkdir -p /app/build_output && \
    cp bazel-bin/examples/${EXAMPLE_TYPE}/custom_callout_server_cpp /app/build_output/

# Runtime image
FROM debian:12-slim

RUN apt-get update && apt-get install -y \
    libssl3 libboost-system1.74.0 \
    && rm -rf /var/lib/apt/lists/*

# Copy artifacts from builder
COPY --from=builder /app/build_output/custom_callout_server_cpp /app/
COPY --from=builder /app/ssl_creds /app/ssl_creds

EXPOSE 443 8080 80
WORKDIR /app
CMD ["./custom_callout_server_cpp"]