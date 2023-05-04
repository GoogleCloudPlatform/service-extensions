#include "proxy_wasm_intrinsics.h"

class MyRootContext : public RootContext {
 public:
  explicit MyRootContext(uint32_t id, std::string_view root_id)
      : RootContext(id, root_id) {}

  bool onStart(size_t) override {
    LOG_INFO("root onStart called");
    return true;
  }
  bool onConfigure(size_t) override {
    LOG_INFO("root onConfigure called");
    return true;
  }
  void onCreate() override { LOG_INFO("root onCreate called"); }
  void onDelete() override { LOG_INFO("root onDelete called"); }
  bool onDone() override {
    LOG_INFO("root onDone called");
    return true;
  }
};

class MyHttpContext : public Context {
 public:
  explicit MyHttpContext(uint32_t id, RootContext* root) : Context(id, root) {}

  void onCreate() override { LOG_INFO("http onCreate called"); }
  void onDelete() override { LOG_INFO("http onDelete called"); }
  void onDone() override { LOG_INFO("http onDone called"); }

  FilterHeadersStatus onRequestHeaders(uint32_t headers,
                                       bool end_of_stream) override {
    LOG_INFO("http onRequestHeaders called");
    return FilterHeadersStatus::Continue;
  }

  FilterHeadersStatus onResponseHeaders(uint32_t headers,
                                        bool end_of_stream) override {
    LOG_INFO("http onResponseHeaders called");
    return FilterHeadersStatus::Continue;
  }
};

static RegisterContextFactory register_StaticContext(
    CONTEXT_FACTORY(MyHttpContext), ROOT_FACTORY(MyRootContext));
