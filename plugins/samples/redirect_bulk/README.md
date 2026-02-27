# Redirect Bulk Plugin

This plugin implements bulk domain redirects by reading domain mappings from a configuration file and redirecting all requests from source domains to target domains with 301 Moved Permanently responses. It preserves the request path and scheme while replacing only the hostname. Use this plugin when you need to manage multiple domain migrations, consolidate domains, or implement domain aliasing at scale. It operates during the **request headers** processing phase with configuration loading during **plugin initialization**.

## How It Works

### Plugin Initialization

1. The proxy loads the plugin and invokes `on_configure` (C++/Rust) or `OnPluginStart` (Go).

2. The plugin reads the configuration file containing domain mappings in the format:
   ```
   source_domain target_domain
   ```

3. The plugin parses each line:
   - Skips empty lines and comments (lines starting with `#`)
   - Splits each line on whitespace to extract source and target domains
   - Converts source domains to lowercase for case-insensitive matching
   - Stores mappings in a hash map for O(1) lookup

4. The plugin logs the number of loaded mappings.

### Request Processing

1. The proxy receives an HTTP request and invokes `on_http_request_headers`.

2. The plugin reads the `:authority` header (which contains the hostname, e.g., `example.com` or `example.com:8080`).

3. **Port stripping**: If the authority contains a port (`:8080`), the plugin extracts only the domain part.

4. **Case-insensitive lookup**: The plugin converts the domain to lowercase and looks it up in the mappings.

5. **If a mapping exists**:
   - The plugin reads `:path` (e.g., `/images/picture.png`) and `:scheme` (e.g., `https`)
   - Constructs the new URL: `scheme://target_domain/path`
   - Sends a 301 redirect response with `Location` header
   - Returns `ContinueAndEndStream` / `ActionPause` to stop processing

6. **If no mapping exists**: The request continues normally to the upstream server.

## Proxy-Wasm Callbacks Used

| Callback | Purpose |
|---|---|
| `on_configure` (C++/Rust) / `OnPluginStart` (Go) | Reads and parses the domain mappings configuration file |
| `on_http_request_headers` | Checks if the request domain should be redirected and sends 301 if matched |

## Key Code Walkthrough

### Configuration Parsing

All implementations parse a simple text format:

- **C++**:
  ```cpp
  for (absl::string_view line : absl::StrSplit(config_str, '\n')) {
      absl::string_view stripped = absl::StripAsciiWhitespace(line);
      if (stripped.empty() || stripped[0] == '#') continue;
      
      std::vector<absl::string_view> parts = absl::StrSplit(stripped, ' ');
      if (parts.size() != 2) continue;
      
      std::string source = absl::AsciiStrToLower(parts[0]);
      domain_mappings_[source] = std::string(parts[1]);
  }
  ```
  Uses Abseil for string processing and converts source to lowercase.

- **Go**:
  ```go
  for _, line := range bytes.Split(config, []byte("\n")) {
      line = bytes.TrimSpace(line)
      if len(line) == 0 || bytes.HasPrefix(line, []byte("#")) {
          continue
      }
      
      parts := bytes.Fields(line)
      if len(parts) == 2 {
          mappings[strings.ToLower(string(parts[0]))] = string(parts[1])
      }
  }
  ```
  Uses standard library `bytes` and `strings` packages.

- **Rust**:
  ```rust
  for line in config_str.lines() {
      let line = line.trim();
      if line.is_empty() || line.starts_with('#') {
          continue;
      }
      
      let parts: Vec<&str> = line.split_whitespace().collect();
      if parts.len() == 2 {
          mappings.insert(parts[0].to_lowercase(), parts[1].to_string());
      }
  }
  ```
  Uses Rust's iterator-based string processing.

### Domain Extraction and Port Handling

- **C++**:
  ```cpp
  absl::string_view host_view = authority->view();
  size_t colon_pos = host_view.find(':');
  std::string domain = absl::AsciiStrToLower(host_view.substr(0, colon_pos));
  ```
  Finds the `:` and extracts the substring before it.

- **Go**:
  ```go
  domain := authority
  if idx := strings.Index(authority, ":"); idx != -1 {
      domain = authority[:idx]
  }
  domainLowercase := strings.ToLower(domain)
  ```

- **Rust**:
  ```rust
  let domain = host.split(':').next().unwrap_or(&host);
  let domain_lowercase = domain.to_lowercase();
  ```
  Uses `split()` iterator to extract the first part.

### URL Construction and Redirect

All implementations construct the new URL from three parts:

- **C++**:
  ```cpp
  const std::string new_url = absl::StrCat(scheme, "://", it->second, path);
  sendLocalResponse(301, "", "Redirecting to " + new_url,
                   {{"Location", new_url}});
  ```

- **Go**:
  ```go
  newURL := scheme + "://" + targetDomain + path
  headers := [][2]string{{"Location", newURL}}
  body := []byte("Redirecting to " + newURL)
  proxywasm.SendHttpResponse(301, headers, body, -1)
  ```

- **Rust**:
  ```rust
  let new_url = format!("{}://{}{}", scheme, target_domain, path);
  self.send_http_response(
      301,
      vec![("Location", new_url.as_str())],
      Some(format!("Redirecting to {}", new_url).as_bytes()),
  );
  ```

### Shared State

- **C++**: Uses `MyRootContext*` pointer in HTTP context to access domain mappings
- **Go**: Copies `map[string]string` reference from plugin context to HTTP context
- **Rust**: Uses `Rc<HashMap<String, String>>` for efficient shared ownership

## Configuration

The plugin requires a configuration file with domain mappings in plain text format.

**Example configuration** (`config.data`):
```
# Domain redirects
# source_domain target_domain
abc.com xyz.com
old-domain.com new-domain.com
legacy.example.org example.org
```

**Format rules**:
- One mapping per line
- Format: `source_domain target_domain` (space-separated)
- Lines starting with `#` are comments (ignored)
- Empty lines are ignored
- Source domains are case-insensitive
- Target domains preserve their case

**Invalid configurations**:
```
# Invalid: more than 2 fields
abc.com xyz.com extra-field

# Invalid: only one field
single-domain

# Valid comment
# This is a comment

# Valid mapping
example.com target.com
```

## Build

Build the plugin for any supported language from the `plugins/` directory:

```bash
# Rust
bazelisk build //samples/redirect_bulk:plugin_rust.wasm

# C++
bazelisk build //samples/redirect_bulk:plugin_cpp.wasm

# Go
bazelisk build //samples/redirect_bulk:plugin_go.wasm
```

## Test

Run the unit tests defined in `tests.textpb`:

```bash
# Using Docker (recommended)
docker run -it -v $(pwd):/mnt \
    us-docker.pkg.dev/service-extensions-samples/plugins/wasm-tester:main \
    --proto /mnt/samples/redirect_bulk/tests.textpb \
    --plugin /mnt/bazel-bin/samples/redirect_bulk/plugin_rust.wasm \
    --config /mnt/samples/redirect_bulk/config.data

# Using Bazel (all languages)
bazelisk test --test_output=all //samples/redirect_bulk:tests
```

## Expected Behavior

Derived from [`tests.textpb`](tests.textpb) with configuration `abc.com → xyz.com`:

| Scenario | Input | Output |
|---|---|---|
| **NoRedirect** | `:authority: example.com`, `:path: /main/somepage/otherpage`, `:scheme: https` (domain not in mappings) | Request continues unchanged; no `Location` header |
| **DomainRedirect** | `:authority: abc.com`, `:path: /images/picture.png`, `:scheme: https` | 301 redirect with `Location: https://xyz.com/images/picture.png` |
| **DomainWithPortRedirect** | `:authority: abc.com:8080`, `:path: /api/v1/data`, `:scheme: http` (port stripped) | 301 redirect with `Location: http://xyz.com/api/v1/data` |
| **CaseInsensitiveDomainMatch** | `:authority: ABC.com` (uppercase), `:path: /case-test`, `:scheme: https` | 301 redirect with `Location: https://xyz.com/case-test` (case-insensitive match works) |

## Available Languages

- [x] [Rust](plugin.rs)
- [x] [C++](plugin.cc)
- [x] [Go](plugin.go)

## Use Cases

1. **Domain migration**: Migrate multiple domains to new domains during rebranding or consolidation.

2. **Domain consolidation**: Redirect multiple legacy domains to a single canonical domain.

3. **Subdomain migration**: Move subdomains to new hostnames (e.g., `blog.old.com` → `blog.new.com`).

4. **Environment mapping**: Redirect staging/dev domains to production equivalents.

5. **Geographic domain routing**: Redirect country-specific domains to unified global domains.

## Example Configurations

**Simple domain migration**:
```
old-site.com new-site.com
www.old-site.com new-site.com
```

**Multiple brand consolidation**:
```
brand-a.com unified-brand.com
brand-b.com unified-brand.com
brand-c.com unified-brand.com
```

**Subdomain reorganization**:
```
blog.old.com blog.new.com
shop.old.com shop.new.com
docs.old.com docs.new.com
```

**Environment-specific redirects**:
```
staging.example.com production.example.com
dev.example.com production.example.com
```

## Comparison with Single Redirect Plugin

| Feature | redirect | redirect_bulk |
|---------|----------|---------------|
| **Configuration** | Hardcoded in source | External file |
| **Scalability** | 1 redirect | Unlimited redirects |
| **Matching** | Path prefix | Domain |
| **Path handling** | Rewrites path | Preserves path |
| **Use case** | URL structure changes | Domain migrations |
