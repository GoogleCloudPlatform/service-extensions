# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

# Estágio 1: gerar stubs Python dos protos do Envoy
FROM bufbuild/buf AS BUF
RUN apk add --no-cache git
COPY ./buf.gen.yaml ./buf.gen.yaml
ARG proto_path="envoy/service/auth/v3/external_auth.proto"
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api \
      --path $proto_path --include-imports

# Estágio 2: imagem final
FROM python:3.12-slim

RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y \
 && apt-get install -y --no-install-recommends --no-install-suggests \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /home/callouts/python

# Copia requirements raiz
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copia os protos gerados (pasta envoy/ e google/)
COPY --from=BUF ./protodef .

# Copia o código fonte
COPY ./extauthz/__init__.py ./extauthz/__init__.py
COPY ./extauthz/service ./extauthz/service
COPY ./extauthz/example/kill_switch ./extauthz/example/kill_switch

# Instala dependências adicionais (redis, aiplatform, etc.)
RUN pip install --no-cache-dir -r ./extauthz/example/kill_switch/additional-requirements.txt

EXPOSE 8453 8080

ENTRYPOINT ["python3", "-m", "extauthz.example.kill_switch.run_authz"]