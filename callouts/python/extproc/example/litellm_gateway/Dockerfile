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
FROM bufbuild/buf AS BUF
RUN apk add --no-cache git
COPY ./buf.gen.yaml ./buf.gen.yaml
ARG proto_path="envoy/service/ext_proc/v3/external_processor.proto"
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api \
      --path $proto_path --include-imports

# Service image. We preserve the package layout (extproc/example/litellm_gateway/...)
# rather than flattening, because our service module imports siblings via the full
# package path and relies on running as `python -m extproc.example.litellm_gateway.*`.
FROM launcher.gcr.io/google/debian12

RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y \
 && apt-get install -y python3-pip --no-install-recommends --no-install-suggests \
 && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt --break-system-packages --root-user-action=ignore

WORKDIR /home/callouts/python

# Generated proto packages drop into WORKDIR root (envoy/, etc.).
COPY --from=BUF ./protodef .

# Framework + our example, preserving the package structure.
COPY ./extproc/__init__.py ./extproc/__init__.py
COPY ./extproc/service ./extproc/service
COPY ./extproc/ssl_creds ./extproc/ssl_creds
COPY ./extproc/example/__init__.py ./extproc/example/__init__.py
COPY ./extproc/example/litellm_gateway ./extproc/example/litellm_gateway

# Example-specific dependencies (litellm, httpx, google-cloud-aiplatform).
RUN pip install -r ./extproc/example/litellm_gateway/additional-requirements.txt \
      --break-system-packages --root-user-action=ignore

EXPOSE 80 443 8080

ENTRYPOINT ["python3", "-um", "extproc.example.litellm_gateway.service_callout_example"]
