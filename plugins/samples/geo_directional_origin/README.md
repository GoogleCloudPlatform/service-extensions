# Geo Routing Plugin

This plugin reads the client's geographic region from the proxy's request metadata and adds it as a request header (`x-country-code`). This enables upstream services to implement geo-specific logic such as routing requests to regional backends, applying country-specific business rules, or customizing content based on the user's location. The plugin also prevents header spoofing by always replacing any existing `x-country-code` header with the authoritative value from the proxy. It operates during the **request headers** processing phase.

## How It Works

1. The proxy receives an HTTP request from a client and invokes the plugin's `on_http_request_headers` callback.

2. The plugin reads the `request.client_region` property from the proxy's request metadata using `proxywasm.GetProperty()`. This property is populated by the proxy based on the client's IP address using GeoIP lookup.

3. **If a country code is available** (non-empty):
   - The plugin sets the `x-country-code` header to the country code value (e.g., `"US"`, `"DE"`, `"JP"`, `"BR"`).
   - If an `x-country-code` header already exists in the request (potentially spoofed by the client), it is replaced with the authoritative value from the proxy.

4. **If no country code is available** (property is missing or empty):
   - The plugin removes any existing `x-country-code` header from the request to prevent spoofing.

5. The plugin logs warnings if header operations fail but continues processing regardless.

6. The plugin returns `types.ActionContinue`, forwarding the modified request to the upstream server.

## Implementation Notes

- **Metadata retrieval**: Reads the client's country code dynamically assigned by proxy metadata via `proxywasm.GetProperty()`.
- **Authoritative routing header**: Replaces any existing `x-country-code` header to prevent spoofed client origins.
- **Spoofing mitigation**: Completely removes the header if valid proxy geo-metadata cannot be retrieved.

## Configuration

No configuration required. The property path (`request.client_region`) and header name (`x-country-code`) are hardcoded in the plugin source.

**Property source**: The `request.client_region` property is populated by the proxy (e.g., Envoy, Google Cloud Service Extensions) based on GeoIP lookup of the client's source IP address. The property must be made available by the proxy environment for this plugin to function correctly.

## Build

Build the plugin for Go from the `plugins/` directory:

```bash
# Go
bazelisk build //samples/geo_routing:plugin_go.wasm
```

**Note**: Only Go implementation is available for this plugin.

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/geo_routing/tests.textpb \
    --plugin /mnt/bazel-bin/samples/geo_routing/plugin_go.wasm

# Using Bazel
bazelisk test --test_output=all //samples/geo_routing:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **SetHeaderForUS** | Injects the US country code into the request header when identified by the proxy. |
| **SetHeaderForGermany** | Injects the DE country code into the request header when identified by the proxy. |
| **SetHeaderForJapan** | Injects the JP country code into the request header when identified by the proxy. |
| **SetHeaderForBrazil** | Injects the BR country code into the request header when identified by the proxy. |
| **NoGeoInformationAvailable** | Strips the header out entirely when no geo information property exists. |
| **EmptyCountryCode** | Strips the header out entirely when the provided geo property is empty. |
| **SetHeaderForSouthAfrica** | Injects the ZA country code into the request header when identified by the proxy. |
| **SecuritySpoofedHeaderRemoved** | Safely overwrites fake user-provided country codes with the authoritative proxy value. |
| **BenchmarkGeoRouting** | Validates performance baseline during standard header injection. |

## Available Languages

- [ ] Rust (not available)
- [ ] C++ (not available)
- [x] [Go](plugin.go)
