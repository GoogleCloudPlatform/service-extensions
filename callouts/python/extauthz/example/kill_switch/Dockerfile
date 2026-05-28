# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

# Stage 1: Generate Python stubs from Envoy protobuf definitions
FROM bufbuild/buf AS BUF
RUN apk add --no-cache git
COPY ./buf.gen.yaml ./buf.gen.yaml
ARG proto_path="envoy/service/auth/v3/external_auth.proto"
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api \
      --path $proto_path --include-imports

# Stage 2: Final production image
FROM python:3.12-slim

RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y \
 && apt-get install -y --no-install-recommends --no-install-suggests \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /home/callouts/python

# Copy base requirements and install
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy generated protobufs (envoy/ and google/ directories)
COPY --from=BUF ./protodef .

# Copy application source code
COPY ./extauthz/__init__.py ./extauthz/__init__.py
COPY ./extauthz/service ./extauthz/service
COPY ./extauthz/example/kill_switch ./extauthz/example/kill_switch

# Install service-specific dependencies (e.g., redis, google-cloud-aiplatform)
RUN pip install --no-cache-dir -r ./extauthz/example/kill_switch/additional-requirements.txt

EXPOSE 8453 8080

ENTRYPOINT ["python3", "-m", "extauthz.example.kill_switch.run_authz"]
