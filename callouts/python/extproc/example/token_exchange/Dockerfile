# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

FROM bufbuild/buf AS BUF
RUN apk add --no-cache git
COPY ./buf.gen.yaml ./buf.gen.yaml
ARG proto_path="envoy/service/ext_proc/v3/external_processor.proto"
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path $proto_path --include-imports

FROM python:3.12-slim
WORKDIR /home/callouts/python
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY --from=BUF ./protodef .

COPY ./extproc/__init__.py ./extproc/__init__.py
COPY ./extproc/service ./extproc/service
COPY ./extproc/example/token_exchange ./extproc/example/token_exchange
RUN pip install --no-cache-dir -r ./extproc/example/token_exchange/additional-requirements.txt

EXPOSE 8080
ENTRYPOINT ["python3", "-u", "-m", "extproc.example.token_exchange.run"]