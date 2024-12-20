# syntax=docker/dockerfile:1

# Example use, mounting local artifacts into the container:
#
# docker run -it -v $(pwd):/mnt <container-artifact> \
#  --proto /mnt/local/path/to/tests.textpb \
#  --plugin /mnt/local/path/to/plugin.wasm
#
# Future improvements:
# - use hermetic C++ toolchains (toolchains_llvm, hermetic_cc_toolchain)
# - cross-compile for aarch64 (arm)
# - use a bazel-public base image (e.g. gcr.io/bazel-public/bazel:5.2.0)
# - compile statically, use FROM scratch or FROM busybox

# Base build image
FROM launcher.gcr.io/google/ubuntu2204 as build
RUN apt update && apt upgrade -y
RUN apt autoremove -y

# Install go for bazelisk
# Install git/py for v8
# Install clang/stdc++ for c++
RUN apt install -y \
  ca-certificates \
  openssl \
  golang-go \
  git \
  python3-distutils \
  clang \
  libstdc++6

# Get certificate from "github.com"
ARG cert_location=/usr/local/share/ca-certificates
RUN openssl s_client -showcerts -connect github.com:443 \
  </dev/null 2>/dev/null | \
  openssl x509 -outform PEM > ${cert_location}/github.crt
RUN update-ca-certificates

# Install bazelisk
RUN go install github.com/bazelbuild/bazelisk@v1.21.0
ENV PATH="${PATH}:/root/go/bin"

# Debug environment
#RUN go env GOPATH
#RUN echo $PATH
#RUN find / -name "libstdc++.so*"

# Build runner
COPY . /src
WORKDIR /src
RUN bazelisk --version
RUN bazelisk build --verbose_failures --config=clang --config=bench //test:runner

################################################################################

# Base runtime image
FROM launcher.gcr.io/google/ubuntu2204 as runtime
RUN apt update && apt upgrade -y
RUN apt autoremove -y

# Install a missing runtime dependency.
RUN apt install -y libicu70

# Copy output from build image.
COPY --from=build /src/bazel-bin/test/runner /opt/
COPY --from=build /src/test/package/licenses/* /opt/licenses/
ENTRYPOINT ["/opt/runner"]
