FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /root/

COPY main .
COPY extproc/ssl_creds ./extproc/ssl_creds

EXPOSE 443 8080 80

CMD ["./main"]
