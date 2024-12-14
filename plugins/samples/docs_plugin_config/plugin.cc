#include <string>
#include <string_view>

#include "proxy_wasm_intrinsics.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onConfigure(size_t config_len) override {
    secret_ = getBufferBytes(WasmBufferType::PluginConfiguration, 0, config_len)
                  ->toString();
    return true;
  }

  const std::string& secret() const { return secret_; }

 private:
  std::string secret_;
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root)
      : Context(id, root),
        secret_(static_cast<MyRootContext*>(root)->secret()) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Use secret here...
    LOG_INFO("secret: " + secret_);
    return FilterHeadersStatus::Continue;
  }

 private:
  const std::string& secret_;
};

static RegisterContextFactory register_MyHttpContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
