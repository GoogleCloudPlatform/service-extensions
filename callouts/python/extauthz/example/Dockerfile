# Copyright 2026 Google LLC.
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

# Build the proto libraries from the envoy git repo using buf.
FROM bufbuild/buf as BUF
RUN apk add git
COPY ./buf.gen.yaml ./buf.gen.yaml
# L7 extauthz proto path:
ARG proto_path="envoy/service/auth/v3/external_auth.proto"
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path $proto_path --include-imports

# Build the callout service.
FROM launcher.gcr.io/google/debian12 as service-callout-common-python
RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y

# Install pip for package management.
RUN apt-get install -y python3-pip --no-install-recommends --no-install-suggests

# Use pip to install requirements.
COPY ./requirements.txt .
RUN pip install -r requirements.txt --break-system-packages --root-user-action=ignore

WORKDIR /home/callouts/python

# Copy over the protobuf files from the buf build.
COPY --from=BUF ./protodef .

# Setup the service callout files.
COPY ./extauthz ./extauthz

# Set up communication ports.
EXPOSE 443
EXPOSE 80
EXPOSE 8080

ARG run_module="extauthz.example.block_ip.service_callout_example"
ENV run_module ${run_module}

# Start the service.
ENTRYPOINT /usr/bin/python3 -um ${run_module} "$@"
