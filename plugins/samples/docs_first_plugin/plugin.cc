#include "proxy_wasm_intrinsics.h"

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    LOG_INFO("onRequestHeaders: hello from wasm");

    // Route Extension example: host rewrite
    replaceRequestHeader(":host", "service-extensions.com");
    replaceRequestHeader(":path", "/");
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    LOG_INFO("onResponseHeaders: hello from wasm");

    // Traffic Extension example: add response header
    addResponseHeader("hello", "service-extensions");
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(RootContext));
