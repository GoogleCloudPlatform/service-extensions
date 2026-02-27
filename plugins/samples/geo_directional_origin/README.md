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

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_http_request_headers` | Reads the `request.client_region` property and sets/removes the `x-country-code` header accordingly |

## Key Code Walkthrough

This plugin is only available in Go:

- **Property path** — The plugin defines the path to the client region property:
  ```go
  const clientRegionProperty = "request.client_region"
  var clientRegionPropertyPath = []string{clientRegionProperty}
  ```
  The property path is represented as a slice of strings for use with `proxywasm.GetProperty()`.

- **Reading proxy metadata** — The plugin retrieves the client region from the proxy:
  ```go
  countryCode, err := proxywasm.GetProperty(clientRegionPropertyPath)
  ```
  The `GetProperty()` function returns the property value as a byte slice. If the property doesn't exist or is unavailable, it returns an error.

- **Conditional header setting** — The plugin checks if a valid country code was retrieved:
  ```go
  if err == nil && len(countryCode) > 0 {
      if err := proxywasm.ReplaceHttpRequestHeader(countryCodeHeader, string(countryCode)); err != nil {
          proxywasm.LogWarnf("failed to set country code header: %v", err)
      }
      return types.ActionContinue
  }
  ```
  - The check `len(countryCode) > 0` ensures that empty strings are treated as "no country code available".
  - `ReplaceHttpRequestHeader()` overwrites any existing header with the same name, preventing header spoofing.

- **Header removal for missing geo data** — If no country code is available, the plugin removes any existing header:
  ```go
  if err := proxywasm.RemoveHttpRequestHeader(countryCodeHeader); err != nil {
      proxywasm.LogWarnf("failed to remove country code header: %v", err)
  }
  ```
  This prevents clients from injecting fake country codes when the proxy cannot determine the actual location.

- **Security consideration** — By always using `ReplaceHttpRequestHeader()` (not `AddHttpRequestHeader()`), the plugin ensures that only the proxy's authoritative country code is present in the request. This prevents clients from spoofing their location by adding an `x-country-code` header in the original request.

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

| Scenario | Input | Output |
|---|---|---|
| **SetHeaderForUS** | `request.client_region` property = `"US"` | `x-country-code: US` header added |
| **SetHeaderForGermany** | `request.client_region` property = `"DE"` | `x-country-code: DE` header added |
| **SetHeaderForJapan** | `request.client_region` property = `"JP"` | `x-country-code: JP` header added |
| **SetHeaderForBrazil** | `request.client_region` property = `"BR"` | `x-country-code: BR` header added |
| **NoGeoInformationAvailable** | No `request.client_region` property | No `x-country-code` header (any existing header removed) |
| **EmptyCountryCode** | `request.client_region` property = `""` (empty string) | No `x-country-code` header (treated as unavailable) |
| **SetHeaderForSouthAfrica** | `request.client_region` property = `"ZA"` | `x-country-code: ZA` header added |
| **SecuritySpoofedHeaderRemoved** | `request.client_region` property = `"GB"`; client sent `x-country-code: XX` | `x-country-code: GB` (spoofed `XX` value replaced with authoritative `GB`) |
| **BenchmarkGeoRouting** | `request.client_region` property = `"GB"` | `x-country-code: GB` header added (performance benchmark test) |

## Available Languages

- [ ] Rust (not available)
- [ ] C++ (not available)
- [x] [Go](plugin.go)
