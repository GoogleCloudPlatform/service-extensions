# Regex Rewrite Plugin

This plugin demonstrates advanced URL path manipulation using regular expressions. It matches path segments with the pattern `/foo-{capture}/` and rewrites them to `/{capture}/`, effectively removing the `foo-` prefix while preserving the captured content. Use this plugin when you need flexible path transformations, complex URL rewriting rules, or pattern-based routing changes that go beyond simple string replacement. It operates during the **request headers** processing phase with regex compilation during **plugin initialization**.

## How It Works

### Plugin Initialization

1. The proxy loads the plugin and invokes `on_configure` (C++/Rust) or `OnPluginStart` (Go).

2. The plugin compiles the regular expression `/foo-([^/]+)/` at startup:
   - **Pattern**: `/foo-([^/]+)/`
   - **Explanation**:
     - `/foo-` - Literal match: forward slash, "foo", hyphen
     - `([^/]+)` - Capture group: one or more characters that are not forward slash
     - `/` - Literal match: forward slash
   - **Example matches**: `/foo-one/`, `/foo-test/`, `/foo-123abc/`
   - **Example non-matches**: `/foo/` (no content after hyphen), `/foo-one` (no trailing slash)

3. The compiled regex is stored for reuse across all requests (efficient, avoids recompilation).

4. If regex compilation fails, the plugin initialization fails (C++/Rust return false, Go returns `OnPluginStartStatusFailed`).

### Request Processing

1. The proxy receives an HTTP request and invokes `on_http_request_headers`.

2. The plugin reads the `:path` pseudo-header (e.g., `/pre/foo-one/foo-two/post?a=b`).

3. **Regex replacement**: The plugin applies the regex replacement:
   - **Pattern**: `/foo-([^/]+)/`
   - **Replacement**: `/$1/` (where `$1` or `\1` is the captured group)
   - **Example**: `/foo-one/` → `/one/`

4. **First match only**: The replacement only affects the first match:
   - Input: `/pre/foo-one/foo-two/post?a=b`
   - Output: `/pre/one/foo-two/post?a=b`
   - Only the first `/foo-one/` is replaced

5. **Conditional update**: The plugin only updates the `:path` header if a replacement was made:
   - **C++**: `RE2::Replace()` returns `true` if replacement occurred
   - **Go**: Compares lengths of original and replaced strings
   - **Rust**: Compares lengths of original and replaced strings

6. The plugin returns `Continue` / `ActionContinue`, forwarding the (potentially modified) request.

## Implementation Notes

- **Pre-compiled efficiency**: Compiles the regular expression exactly once during `on_configure` / `OnPluginStart` to avoid per-request processing overhead.
- **Regex engine usage**: Specifically utilizes `RE2` in C++, `regexp` in Go, and the `regex` crate in Rust to perform matching and capture-group replacement.
- **Selective replacement**: Triggers a rewrite of the `:path` pseudo-header only if the compiled regex effectively matches and modifies the string.

## Configuration

No configuration required. The regex pattern is hardcoded in the plugin source.

**Customization examples**:

1. **Different pattern**:
   ```cpp
   // Remove /api/v1/ prefix
   path_match.emplace("^/api/v1/(.*)$");
   // Replacement: "/$1"
   ```

2. **Multiple capture groups**:
   ```cpp
   // Swap path segments: /foo/bar/ → /bar/foo/
   path_match.emplace("/([^/]+)/([^/]+)/");
   // Replacement: "/$2/$1/"
   ```

3. **Case-insensitive matching** (C++):
   ```cpp
   // (?i) prefix enables case-insensitive mode
   path_match.emplace("(?i)/foo-([^/]+)/");
   ```

4. **Replace all matches** (Go):
   ```go
   // Go's ReplaceAllString already replaces all matches
   // To match C++/Rust behavior (first only), use:
   edit := ctx.pluginContext.pathMatch.ReplaceAllStringFunc(path, func(match string) string {
       // Custom logic here
   })
   ```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/regex_rewrite:plugin_rust.wasm

# C++
bazelisk build //samples/regex_rewrite:plugin_cpp.wasm

# Go
bazelisk build //samples/regex_rewrite:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/regex_rewrite/tests.textpb \
    --plugin /mnt/bazel-bin/samples/regex_rewrite/plugin_rust.wasm

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/regex_rewrite:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb):

| Scenario | Description |
|---|---|
| **NoMatch** | Leaves the path unmodified when the regex pattern does not match. |
| **MatchAndReplace** | Successfully catches the pattern, extracts the capture group, and manipulates the path using the extracted substring. |

**Note**: Both tests include `benchmark: true` for performance testing.

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Regex Pattern Breakdown

**Pattern**: `/foo-([^/]+)/`

```
/           - Literal forward slash
foo-        - Literal "foo" followed by hyphen
(           - Start capture group 1
  [^/]+     - One or more characters that are NOT forward slash
)           - End capture group 1
/           - Literal forward slash
```

**Replacement**: `/$1/` or `/\1/`

```
/           - Literal forward slash
$1 or \1    - Contents of capture group 1
/           - Literal forward slash
```

**Examples**:
- `/foo-one/` → `/one/` (captures "one")
- `/foo-test/` → `/test/` (captures "test")
- `/foo-123abc/` → `/123abc/` (captures "123abc")
- `/foo-/` → No match (capture group requires at least 1 char)
- `/foo-one` → No match (missing trailing slash)

## Use Cases

1. **API versioning cleanup**: Remove version prefixes from URLs for internal routing.

2. **Legacy URL migration**: Transform old URL patterns to new ones without changing backend.

3. **Namespace removal**: Strip organizational prefixes from paths.

4. **Dynamic routing**: Extract path segments for header injection or routing decisions.

5. **URL normalization**: Standardize URLs with varying formats.

## Performance Considerations

- **Regex compilation**: Done once at plugin startup, not per-request (very efficient)
- **First match only**: C++ and Rust replace only the first match (more efficient than global replace)
- **Conditional update**: Only updates header if replacement occurred (avoids unnecessary writes)
- **Shared regex**: All HTTP contexts share the same compiled regex (memory efficient)

## Regex Libraries Used

| Language | Library | Features |
|----------|---------|----------|
| **C++** | RE2 | Fast, safe, supports full regex syntax, compiled regex reuse |
| **Go** | regexp (stdlib) | POSIX ERE compliant, compiled regex reuse |
| **Rust** | regex crate | Fast, safe, Unicode-aware, compiled regex reuse |

All libraries compile the regex at startup for optimal performance.
