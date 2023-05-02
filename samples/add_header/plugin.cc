#include <string_view>

#include "proxy_wasm_intrinsics.h"

class AddHeaderStreamContext : public Context {
 public:
  explicit AddHeaderStreamContext(uint32_t id, RootContext* root)
      : Context(id, root) {}

  void onCreate() override {
    LOG_INFO("AddHeaderStreamContext::onCreate called");
  }

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    LOG_INFO("AddHeaderStreamContext::onRequestHeaders called");
    addRequestHeader("example", "this is a test");
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    LOG_INFO("AddHeaderStreamContext::onResponseHeaders called");
    addResponseHeader("response", "example response header");
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(AddHeaderStreamContext), ROOT_FACTORY(RootContext));
