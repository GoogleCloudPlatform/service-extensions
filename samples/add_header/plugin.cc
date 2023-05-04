#include <string_view>

#include "proxy_wasm_intrinsics.h"

class StreamContext : public Context {
 public:
  explicit StreamContext(uint32_t id, RootContext* root) : Context(id, root) {}

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    // Always be a friendly proxy.
    addRequestHeader("Message", "hello");
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    // Conditionally add to a header value.
    auto msg = getResponseHeader("Message");
    if (msg && msg->view() == "foo") {
      addResponseHeader("Message", "bar");
    }
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(StreamContext), ROOT_FACTORY(RootContext));
