# Use the Debian 12 base image for both stages
FROM marketplace.gcr.io/google/debian12 AS builder

# Set the Go version
ENV GO_VERSION 1.22.3

# Install Go
RUN apt-get update && apt-get install -y wget \
    && wget https://golang.org/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz \
    && rm go${GO_VERSION}.linux-amd64.tar.gz

# Set up Go environment variables
ENV PATH $PATH:/usr/local/go/bin
ENV GOPATH /go
ENV PATH $GOPATH/bin:$PATH

# Set the Current Working Directory inside the container
WORKDIR /app

# Copy go mod and sum files
COPY go.mod go.sum ./

# Download all dependencies. Dependencies will be cached if the go.mod and go.sum files are not changed
RUN go mod download

# Copy the source from the current directory to the Working Directory inside the container
COPY . .

# Build the Go app
ARG EXAMPLE_TYPE
ENV EXAMPLE_TYPE=${EXAMPLE_TYPE}
RUN GOOS=linux GOARCH=amd64 go build -o main ./extproc/cmd/example/main.go

# Use the same image for the final stage
FROM marketplace.gcr.io/google/debian12

# Set the Current Working Directory inside the container
WORKDIR /root/

# Copy the Pre-built binary file from the previous stage
COPY --from=builder /app/main .

# Copy SSL certificates
COPY extproc/ssl_creds ./extproc/ssl_creds

#Set environment variable for runtine
ARG EXAMPLE_TYPE
ENV EXAMPLE_TYPE=${EXAMPLE_TYPE}

# Expose port 8443, 8181, and 8000
EXPOSE 8443 8181 8000

# Command to run the executable
CMD ["./main"]
