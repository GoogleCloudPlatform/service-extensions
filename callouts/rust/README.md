# Rust Callout Server

## Pre-requirements

### Install Rust

Before you can build this project, you need to have Rust installed. Here's how to install Rust:

- **All Platforms**: Visit [rustup.rs](https://rustup.rs/) and follow the instructions, or run:
  ```sh
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```

- **Windows**: You can also download the installer from [rust-lang.org](https://www.rust-lang.org/tools/install)

After installation, verify that Rust is properly installed:
```sh
rustc --version
cargo --version
```

### Dependencies

This project requires:
- Rust 1.70 or newer
- Protobuf compiler (for generating gRPC code)

#### Installing Protobuf Compiler

- **Windows**:
  1. Download the latest release from [GitHub](https://github.com/protocolbuffers/protobuf/releases)
  2. Add the binary to your PATH

- **macOS**:
  ```sh
  brew install protobuf
  ```

- **Linux**:
  ```sh
  sudo apt update
  sudo apt install protobuf-compiler
  ```

Verify the installation:
```sh
protoc --version
```

## Build Instructions

This project uses Cargo, Rust's package manager and build system.

From the main directory, build with:

```sh
cargo build
```

For a release build:

```sh
cargo build --release
```

## Running Examples

The project includes several example processors that demonstrate different functionalities:

### Running a Specific Example

```sh
cargo run --example basic
```

Available examples:
- `add_body` - Demonstrates body content modification
- `add_header` - Shows how to add/modify HTTP headers
- `basic` - A comprehensive example showing both header and body modifications
- `jwt_auth` - Implements JWT authentication and validation
- `redirect` - Shows how to create HTTP redirects

### Running with Custom Configuration

You can customize the server configuration by modifying the example code or by setting environment variables:

```sh
RUST_LOG=info cargo run --example basic
```

## Server Configuration

The server runs three endpoints by default:
- **Plaintext gRPC** on port `8080` (enabled by default)
- **Health check HTTP** on port `80` (enabled by default)
- **TLS gRPC** on port `443` (disabled by default)

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enable_plaintext_server` | `true` | Enable plaintext gRPC server on port 8080 |
| `enable_tls` | `false` | Enable TLS gRPC server on port 443 |
| `address` | `0.0.0.0:443` | TLS server address |
| `plaintext_address` | `0.0.0.0:8080` | Plaintext server address |
| `health_check_address` | `0.0.0.0:80` | Health check server address |

### Enabling TLS

To enable the TLS server, set `enable_tls: true` in your configuration:

```rust
use ext_proc::server::{CalloutServer, Config};

let config = Config {
    enable_tls: true,
    ..Config::default()
};
let server = CalloutServer::new(config);
```

> **Note**: For production deployments, you should enable TLS to encrypt traffic between your load balancer and the callout server. The plaintext server is intended for local development and testing only.

## Docker

### Build the Docker Image

Execute the following command to build the Docker image:

```sh
docker build -t rust-callout:latest .
```

### Running the Docker Container

To run an example in Docker:

```sh
docker run -p 80:80 -p 443:443 -p 8080:8080 rust-callout:latest basic
```

### Running with Environment Variables

```sh
docker run -p 80:80 -p 443:443 -p 8080:8080 \
  -e RUST_LOG=debug \
  rust-callout:latest basic
```

## Developing Callouts

This repository provides a framework for creating Envoy external processors in Rust.

### Making a New Processor

1. Create a new Rust file in the `examples` directory
2. Import the necessary components:

```rust
use ext_proc::{
    processor::ExtProcessor,
    envoy::service::ext_proc::v3::{
        ProcessingRequest,
        ProcessingResponse,
        processing_request::Request as ProcessingRequestVariant,
    },
    server::CalloutServer,
    utils::mutations,
};
use async_trait::async_trait;
```

3. Create a struct for your processor:

```rust
#[derive(Clone)]
struct MyProcessor;

impl MyProcessor {
    fn new() -> Self {
        Self
    }
}
```

4. Implement the `ExtProcessor` trait:

```rust
#[async_trait]
impl ExtProcessor for MyProcessor {
    async fn process_request_headers(&self, req: &ProcessingRequest) -> Result<ProcessingResponse, ProcessingError> {
        // Your implementation here
        Ok(ProcessingResponse::default())
    }
    
    // Implement other methods as needed:
    // - process_response_headers
    // - process_request_body
    // - process_response_body
}
```

5. Create a main function to run your processor:

```rust
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();
    
    let server = CalloutServer::with_default_config();
    let processor = MyProcessor::new();
    
    // Plaintext server starts by default, TLS is disabled
    let plaintext_handle = server.spawn_plaintext_grpc(processor.clone()).await;
    let secure_handle = server.spawn_grpc(processor.clone()).await;
    let health_handle = server.spawn_health_check().await;
    
    tokio::select! {
        _ = plaintext_handle => {},
        _ = secure_handle => {},
        _ = health_handle => {},
    }
    
    Ok(())
}
```

### Available Utility Functions

The `mutations` module provides several utility functions to simplify common tasks:

- `add_header_mutation` - Adds or removes HTTP headers
- `add_body_string_mutation` - Replaces the body with a string
- `add_body_clear_mutation` - Clears the body completely
- `add_immediate_response` - Creates an immediate response with custom status code
- `add_redirect_response` - Creates a redirect response

## Documentation

### Generate Documentation

To generate documentation for the project:

```sh
cargo doc --no-deps --open
```

This will build the documentation and open it in your default web browser.

### Project Structure

- `src/` - Core library code
  - `utils/` - Utility functions and helpers
    - `mutations.rs` - Functions for creating common mutations
  - `processor.rs` - The `ExtProcessor` trait definition
  - `server.rs` - The `CalloutServer` implementation
  - `service.rs` - The gRPC service implementation
- `examples/` - Example processors
  - `add_body/` - Body modification example
  - `add_header/` - Header modification example
  - `basic/` - Comprehensive example
  - `jwt_auth/` - JWT authentication example
  - `redirect/` - HTTP redirect example
- `proto/` - Protocol buffer definitions
- `ssl_creds/` - SSL certificates for secure communication

## Testing

Run the tests with:

```sh
cargo test
```

For more verbose output:

```sh
cargo test -- --nocapture
```