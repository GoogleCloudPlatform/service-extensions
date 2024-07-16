# Copyright 2024 Google LLC.
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

# Use the Debian 9 Clang base image for both stages
FROM marketplace.gcr.io/google/debian12 AS builder

# Install bazelisk
RUN apt-get update \
&& apt-get install -y wget \
&& wget https://github.com/bazelbuild/bazelisk/releases/download/v1.20.0/bazelisk-linux-amd64 \
&& chmod +x bazelisk-linux-amd64 \
&& mv bazelisk-linux-amd64 /usr/local/bin/bazel

# Install Clang
RUN apt-get install -y clang

# Set the compiler env var for bazel
ENV CC /usr/bin/clang

# Set the Current Working Directory inside the container
WORKDIR /app

# Copy the source from the current directory to the Working Directory inside the container
COPY . .

# Build the C++ app
RUN bazel build //:callout_service_cpp

# Use the same image for the final stage
FROM marketplace.gcr.io/google/debian12

# Copy the Pre-built binary file from the previous stage
COPY --from=builder /app/bazel-bin .

# Copy SSL certificates
#COPY extproc/ssl_creds ./extproc/ssl_creds

#Set environment variable for runtine
# ARG EXAMPLE_TYPE
# ENV EXAMPLE_TYPE=${EXAMPLE_TYPE}

# Expose port 8443, 8181, and 8000
EXPOSE 8443 8181 8000

# Command to run the executable
CMD ["./callout_service_cpp"]