// plugins/test/tools/wasmtime_precompiler/wasmtime_precompiler.cc

#include <stdio.h>
#include <stdlib.h>
#include <fstream>
#include <iostream>
#include <vector>
#include <cstring>
#include <span>

// Include the new Wasmtime C++ API header
#include "crates/c-api/include/wasmtime.hh" 

namespace wasmtime {
  using namespace ::wasmtime;
}
using wasmtime::Config;
using wasmtime::Engine;
using wasmtime::Module;
using wasmtime::Result;
using wasmtime::Span;
using wasmtime::Error;

// Helper function to read a file into a vector of bytes
bool read_file(const char* path, std::vector<uint8_t>& out) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file.is_open()) {
    std::cerr << "Error: Could not open file: " << path << std::endl;
    return false;
  }

  size_t size = file.tellg();
  file.seekg(0, std::ios::beg);

  out.resize(size);
  if (!file.read(reinterpret_cast<char*>(out.data()), size)) {
    std::cerr << "Error: Could not read file: " << path << std::endl;
    out.clear();
    return false;
  }
  return true;
}

// Ensure this engine configuration is IDENTICAL to the one in wasmtime.cc
Engine *precompiler_engine() {
  static auto *const engine = []() {
    Config config;
    // Set to true to match the wasmtime.cc implementation (wasmtime_v39_patch branch)
    config.epoch_interruption(true); 
    return new Engine(std::move(config));
  }();
  return engine;
}


int main(int argc, char* argv[]) {
  if (argc != 3) {
    std::cerr << "Usage: " << argv[0] << " <input_wasm_file> <output_cwasm_file>" << std::endl;
    return 1;
  }

  const char* input_wasm_path = argv[1];
  const char* output_cwasm_path = argv[2];

  Engine* engine = precompiler_engine();

  // Load the original .wasm file into a vector
  std::vector<uint8_t> input_wasm_bytes;
  if (!read_file(input_wasm_path, input_wasm_bytes)) {
    return 1;
  }
  
  // Create a mutable span for the input data, as required by the API.
  // We use const_cast because the `compile` and `deserialize` functions
  // only read the bytes but are incorrectly typed to accept a mutable Span.
  uint8_t* input_data = const_cast<uint8_t*>(input_wasm_bytes.data());
  size_t input_size = input_wasm_bytes.size();
  
  // Use the wasmtime::Span type expected by the API.
  ::wasmtime::Span<uint8_t> input_code_span(input_data, input_size);

  // 1. Compile the module (Slow Path)
  std::cout << "Compiling WASM module from: " << input_wasm_path << std::endl;
  
  Result<Module> module = Module::compile(*engine, input_code_span); 
  
  if (!module) {
    std::cerr << "Error: Failed to compile WASM module: " << module.err().message() << std::endl;
    return 1;
  }
  Module compiled_module = module.ok();

  // 2. Serialize the module (Precompile)
  std::cout << "Serializing module to cwasm format..." << std::endl;
  Result<std::vector<uint8_t>> cwasm_result = compiled_module.serialize();
  
  if (!cwasm_result) {
    std::cerr << "Error: Failed to serialize WASM module: " << cwasm_result.err().message() << std::endl;
    return 1;
  }
  std::vector<uint8_t> cwasm_bytes = cwasm_result.ok();

  // Write the serialized bytes to the output file
  std::cout << "Writing precompiled cwasm to: " << output_cwasm_path << std::endl;
  std::ofstream outfile(output_cwasm_path, std::ios::binary);
  
  if (!outfile.is_open()) {
    std::cerr << "Error: Could not open output file: " << output_cwasm_path << std::endl;
    return 1;
  }
  outfile.write(reinterpret_cast<const char*>(cwasm_bytes.data()), cwasm_bytes.size());

  std::cout << "Precompilation successful. Size: " << cwasm_bytes.size() << " bytes." << std::endl;

  // 3. Test Deserialization (Fast Path)
  std::cout << "Testing deserialization..." << std::endl;
  
  // Create a span for the serialized bytes (cwasm_bytes) for the deserialize function.
  // Since cwasm_bytes is non-const, we don't need const_cast here, but we still need the Span.
  ::wasmtime::Span<uint8_t> cwasm_span(cwasm_bytes.data(), cwasm_bytes.size());

  Result<Module> deserialized = Module::deserialize(*engine, cwasm_span);

  if (!deserialized) {
    std::cerr << "Error: Deserialization failed: " << deserialized.err().message() << std::endl;
    return 1;
  }
  std::cout << "Deserialization test successful." << std::endl;

  return 0;
}