# syntax=docker/dockerfile:1

# Example use, mounting local artifacts into the container:
#
# docker run -it -v $(pwd):/mnt <container-artifact> \
#  --proto /mnt/local/path/to/tests.textpb \
#  --plugin /mnt/local/path/to/plugin.wasm

# TODO consider compiling statically, then using FROM scratch or FROM busybox
FROM ubuntu:22.04
COPY licenses/* /opt/licenses/
COPY runner /opt/
ENTRYPOINT ["/opt/runner"]
