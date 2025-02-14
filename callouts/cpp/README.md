# Service Extensions Samples (C++)

This repository contains samples for service extensions using gRPC external
processing in C++. It demonstrates how to set up and run different examples
dynamically using Docker and Docker Compose.

## Copyrights and Licenses

Files using Copyright 2025 Google LLC & Apache License Version 2.0:

* [callout_server.h](./service/callout_server.h)
* [examples](./examples)

## Requirements

* Clang
* Bazel
* Docker
* Docker Compose

## Quick Start

The minimal operation of this C++ based ext_proc server requires Bazel, Clang and Docker.

### Running Without Docker

You can run the examples directly with Bazel and Clang without using Docker.

### Install Bazel

The recommended way to install Bazel is from the
[Bazelisk](https://bazel.build/install/bazelisk#installing_bazel) which can manage different Bazel
versions.

### Set Environment Variable

Set the `EXAMPLE_TYPE` environment variable to the example you want to build and run (e.g `basic`).

#### For Linux/macOS

```sh
export EXAMPLE_TYPE=basic
```

#### For Windows (Command Prompt)

```sh
set EXAMPLE_TYPE=basic
```

#### For Windows (PowerShell)

```sh
$env:EXAMPLE_TYPE="basic"
```

### Build the application

Make sure you have Clang installed and then download and build the dependencies:

>**Note**: Given that on the C++ environment the dependencies should be compiled before linked,
the compiling process may take a while in the first time.

```sh
bazel build --config=clang //examples/${EXAMPLE_TYPE}:${EXAMPLE_TYPE}_cpp
```

## Run the Application

```sh
./bazel-bin/examples/${EXAMPLE_TYPE}/${EXAMPLE_TYPE}_cpp
```

## Building and Running the Examples with Docker

You can run different examples by setting the `EXAMPLE_TYPE` environment variable and
using Docker Compose.

### Building Basic Example

Running from the [./config](./config)

```sh
EXAMPLE_TYPE=basic docker-compose build
```

### Running Basic Example

Running from the [./config](./config)

```sh
EXAMPLE_TYPE=basic docker-compose up
```

## Running Tests

To run the unit tests, use the following command from the project root:

```sh
bazel test --test_summary=detailed --config=clang //...
```

## Developing Callouts

This repository provides the following files to be extended to fit the needs of the user:

[CalloutServer](./service/callout_server.h): Baseline service callout server.

### Making a New Server

TODO

### Extend the CalloutServer

TODO

### Override the callback methods

TODO

### Run the Server

TODO

## Additional Details

TODO

## Using the Proto Files

TODO
