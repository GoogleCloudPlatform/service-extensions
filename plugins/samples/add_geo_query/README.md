# Add Geo Query Plugin

This plugin modifies the incoming request path by appending a `country` query parameter based on the client's geographic region. It uses the `request.client_region` property provided by the proxy. If the region is unavailable, it defaults to `unknown`. It also prevents spoofing by overwriting any existing `country` parameter in the request URL. Use this plugin when backend services need client geographic data passed explicitly via query string.

## Implementation Notes

- **Property Extraction**: Retrieves the `request.client_region` property to determine the client's country of origin.
- **URL Parsing and Modification**: Utilizes `boost::url` to parse the `:path` header, safely append or replace the `country` query parameter, and encode the new generated URL.
- **Spoofing Protection**: Replaces any client-provided `country` query parameter with the trusted value from the proxy to prevent end-user spoofing.
- **Fallback Mechanism**: Uses `unknown` as the default value if the geographic property is missing or empty.

## Build

Build the plugin for C++ from the `plugins/` directory:

```bash
bazelisk build //samples/add_geo_query:plugin_cpp.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/add_geo_query/tests.textpb \
    --plugin /mnt/bazel-bin/samples/add_geo_query/plugin_cpp.wasm

# Using Bazel
bazelisk test --test_output=all //samples/add_geo_query:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **AddCountryParameterWithClientRegion** | Appends the `country` parameter based on the `request.client_region` property. |
| **FallbackToUnknownWhenNoClientRegion** | Appends `country=unknown` when the region property is missing. |
| **FallbackToUnknownWhenClientRegionEmpty** | Appends `country=unknown` when the region property is empty. |
| **AppendCountryToExistingQueryString** | Safely adds the geographic context to a URL that already contains other query parameters. |
| **AddCountryToRootPath** | Correctly appends the parameter when the path is exactly `/`. |
| **HandleClientRegionCountryCodeUK** | Handles special or standard region codes successfully. |
| **HandleEmptyPath** | Appends the parameter even if the original path is missing or empty. |
| **RemoveExistingCountryParameter** | Prevents spoofing by overwriting an existing `country` parameter. |

## Available Languages

- [x] [C++](plugin.cc)
