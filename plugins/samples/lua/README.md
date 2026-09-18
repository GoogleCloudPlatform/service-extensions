# Lua Wasm Plugin

This plugin executes Lua scripts dynamically inside a Proxy-Wasm sandbox to manipulate streaming traffic.
It is designed for **Envoy Lua HTTP filter compatibility**, with some caveats (see the [Envoy documentation](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter)).

## Configuration
The plugin configuration requires an inline string containing the Lua script to execute.

For example, to configure a script that injects a header:
```lua
function envoy_on_request(request_handle)
  request_handle:headers():add("foo", "bar")
end
```

## Unsupported Features
Because of limitations within Envoy and the Proxy Wasm sandbox scope, select properties return an explicit `absl::UnimplementedError("... is unsupported.")` and will trigger a traceback if invoked:
- **`ParsedName` APIs**: `commonName()`, `organizationName()`.
- **`SslConnection` certificate traversal limitations**: `issuerPeerCertificate()`, `sha256PeerCertificateIssuerDigest()`, `serialNumberPeerCertificateIssuer()`, `parsedSubjectPeerCertificate()`, `oidsPeerCertificate()`, `oidsLocalCertificate()`, `sessionId()`, `ciphersuiteString()`.
- **HTTP/1 mutation**: `Header::SetHttp1ReasonPhrase()`.

## Build

```bash
# C++
bazelisk build //samples/lua:plugin_cpp.wasm
```

## Test

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/lua/tests.textpb \
    --plugin /mnt/bazel-bin/samples/lua/plugin_cpp.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/lua:tests
```