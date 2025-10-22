/*
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "test/dynamic_test.h"

#include <boost/filesystem/path.hpp>

#include "absl/random/distributions.h"
#include "absl/strings/str_cat.h"
#include "absl/strings/substitute.h"
#include "benchmark/benchmark.h"
#include "dynamic_test.h"
#include "framework.h"
#include "google/protobuf/text_format.h"
#include "gtest/gtest.h"
#include "quiche/balsa/balsa_frame.h"
#include "quiche/balsa/balsa_headers.h"
#include "quiche/common/platform/api/quiche_googleurl.h"
#include "re2/re2.h"
#include "test/framework.h"
#include "test/runner.pb.h"

namespace service_extensions_samples {
namespace {

// Helper to read data from a path which may be relative to the test config.
absl::StatusOr<std::string> ReadContent(const std::string& path,
                                        const pb::Env& env) {
  boost::filesystem::path in(path);
  boost::filesystem::path cfg(env.test_path());
  // If relative path, resolve relative to test config file.
  if (!in.is_absolute()) {
    in = cfg.parent_path() / in;
  }
  return ReadDataFile(in.string());
}

// Helper class to support string/regex positive/negative matching.
class StringMatcher {
 public:
  // Factory method. Creates a matcher or returns invalid argument status.
  static absl::StatusOr<StringMatcher> Create(const pb::StringMatcher& expect,
                                              const pb::Env& env) {
    StringMatcher sm;
    sm.invert_ = expect.invert();
    if (expect.has_exact()) {
      sm.exact_ = expect.exact();
    } else if (expect.has_file()) {
      absl::StatusOr<std::string> file_content =
          ReadContent(expect.file(), env);
      if (file_content.ok()) {
        sm.exact_ = *file_content;
      } else {
        return absl::InvalidArgumentError(
            absl::StrCat("Bad file: ", file_content.status()));
      }
    } else if (expect.has_regex()) {
      sm.re_ = std::make_unique<RE2>(expect.regex(), RE2::Quiet);
      if (!sm.re_->ok()) {
        return absl::InvalidArgumentError(
            absl::StrCat("Bad regex: ", sm.re_->error()));
      }
    } else {
      return absl::InvalidArgumentError(
          "StringMatcher must specify 'exact' or 'regex' field.");
    }
    return sm;
  }

  // Check expectations against a list of strings.
  bool Matches(const std::vector<std::string>& contents) {
    for (const auto& msg : contents) {
      bool match = re_ ? RE2::FullMatch(msg, *re_) : msg == exact_;
      if (match) return !invert_;
    }
    return invert_;
  };

  std::string getExact() { return exact_; }

 private:
  StringMatcher() = default;

  bool invert_;
  std::string exact_;
  std::unique_ptr<RE2> re_ = nullptr;
};

// Helper to add some logging at construction and teardown.
class LogTestBounds {
 public:
  LogTestBounds(ContextOptions& options) : options_(options) {
    if (options_.log_file) {
      const auto* test = testing::UnitTest::GetInstance()->current_test_info();
      options_.log_file << "--- Starting test: " << test->name() << " ---"
                        << std::endl;
    }
  }
  ~LogTestBounds() {
    if (options_.log_file) {
      const auto* test = testing::UnitTest::GetInstance()->current_test_info();
      options_.log_file << "--- Finished test: " << test->name() << " ---"
                        << std::endl;
    }
  }

 private:
  ContextOptions& options_;
};

// Class that manages the state for an additional stream running in a
// benchmark.
class AdditionalStream {
 public:
  enum class NextAction {
    kCreate,
    kSendRequestHeaders,
    kSendRequestBody,
    kSendResponseHeaders,
    kSendResponseBody,
    kDestroy,
  };

  AdditionalStream(std::shared_ptr<proxy_wasm::PluginHandleBase> handle,
                   const TestHttpContext::Headers* request_headers,
                   const TestHttpContext::Headers* response_headers,
                   const std::vector<std::string>* request_body_chunks,
                   const std::vector<std::string>* response_body_chunks)
      : handle_(handle),
        request_headers_(request_headers),
        response_headers_(response_headers),
        request_body_chunks_(request_body_chunks),
        response_body_chunks_(response_body_chunks) {}
  AdditionalStream(AdditionalStream&& other) = default;
  ~AdditionalStream() = default;

  // Advance the state of the AdditionalStream, e.g. by writing headers or a
  // body chunk.
  absl::Status Advance();

  NextAction next_action() { return next_action_; }

 private:
  std::shared_ptr<proxy_wasm::PluginHandleBase> handle_;

  // These fields are owned by the caller, and assumed to remain valid and not
  // change over the lifetime of the AdditionalStream.
  const TestHttpContext::Headers* request_headers_;
  const TestHttpContext::Headers* response_headers_;
  const std::vector<std::string>* request_body_chunks_;
  const std::vector<std::string>* response_body_chunks_;

  // Mutable fields that change as the stream advances state.
  std::deque<std::string> remaining_request_body_chunks_;
  std::deque<std::string> remaining_response_body_chunks_;
  std::unique_ptr<TestHttpContext> stream_;
  NextAction next_action_ = NextAction::kCreate;
};

absl::Status AdditionalStream::Advance() {
  while (true) {  // cycle through actions until one is performed
    switch (next_action_) {
      case NextAction::kCreate:
        stream_ = std::make_unique<TestHttpContext>(handle_);
        if (request_body_chunks_ != nullptr) {
          remaining_request_body_chunks_.assign(request_body_chunks_->begin(),
                                                request_body_chunks_->end());
        }
        if (response_body_chunks_ != nullptr) {
          remaining_response_body_chunks_.assign(response_body_chunks_->begin(),
                                                 response_body_chunks_->end());
        }
        next_action_ = NextAction::kSendRequestHeaders;
        return absl::OkStatus();

      case NextAction::kSendRequestHeaders: {
        if (request_headers_ == nullptr) {
          next_action_ = NextAction::kSendRequestBody;
          continue;
        }
        auto res = stream_->SendRequestHeaders(*request_headers_);
        benchmark::DoNotOptimize(res);
        next_action_ = NextAction::kSendRequestBody;
        return handle_->wasm()->isFailed() ? absl::InternalError("VM failed!")
                                           : absl::OkStatus();
      }

      case NextAction::kSendRequestBody: {
        if (!remaining_request_body_chunks_.empty()) {
          std::string chunk = std::move(remaining_request_body_chunks_.front());
          remaining_request_body_chunks_.pop_front();
          auto res = stream_->SendRequestBody(
              chunk, /*end_of_stream=*/remaining_request_body_chunks_.empty());
          benchmark::DoNotOptimize(res);
          return handle_->wasm()->isFailed() ? absl::InternalError("VM failed!")
                                             : absl::OkStatus();
        }
        next_action_ = NextAction::kSendResponseHeaders;
        continue;
      }

      case NextAction::kSendResponseHeaders: {
        if (response_headers_ == nullptr) {
          next_action_ = NextAction::kSendResponseBody;
          continue;
        }
        auto res = stream_->SendResponseHeaders(*response_headers_);
        benchmark::DoNotOptimize(res);
        next_action_ = NextAction::kSendResponseBody;
        return handle_->wasm()->isFailed() ? absl::InternalError("VM failed!")
                                           : absl::OkStatus();
      }

      case NextAction::kSendResponseBody: {
        if (!remaining_response_body_chunks_.empty()) {
          std::string chunk =
              std::move(remaining_response_body_chunks_.front());
          remaining_response_body_chunks_.pop_front();
          auto res = stream_->SendResponseBody(
              chunk, /*end_of_stream=*/remaining_response_body_chunks_.empty());
          benchmark::DoNotOptimize(res);
          return handle_->wasm()->isFailed() ? absl::InternalError("VM failed!")
                                             : absl::OkStatus();
        }
        next_action_ = NextAction::kDestroy;
        continue;
      }

      case NextAction::kDestroy:
        stream_.reset();
        next_action_ = NextAction::kCreate;
        return handle_->wasm()->isFailed() ? absl::InternalError("VM failed!")
                                           : absl::OkStatus();

      default:
        return absl::InternalError(
            absl::StrCat("Unexpected next_action_: ", next_action_));
    }
  }
}

}  // namespace

absl::StatusOr<std::shared_ptr<proxy_wasm::PluginHandleBase>>
DynamicTest::LoadWasm(bool benchmark) {
  // Set log level. Default to INFO. Disable in benchmarks.
  auto ll = env_.log_level();
  if (ll == pb::Env::UNDEFINED) {
    ll = pb::Env::INFO;
  }
  if (benchmark) {
    ll = pb::Env::CRITICAL;  // disable logs in benchmarks
  }
  auto log_level = proxy_wasm::LogLevel(ll - 1);  // enum conversion, yuck

  // Load wasm bytes.
  auto wasm = ReadDataFile(env_.wasm_path());
  if (!wasm.ok()) return wasm.status();

  // Load plugin config from disk, if configured.
  std::string plugin_config = "";
  if (!env_.config_path().empty()) {
    auto config = ReadDataFile(env_.config_path());
    if (!config.ok()) return config.status();
    plugin_config = *config;
  }

  // Context options: logging to file, setting the clock.
  ContextOptions opt;
  if (!benchmark && !env_.log_path().empty()) {
    opt.log_file.open(env_.log_path(), std::ofstream::out | std::ofstream::app);
  }
  if (env_.time_secs()) {
    opt.clock_time = absl::FromUnixSeconds(env_.time_secs());
  }

  // Create VM and load wasm.
  return CreatePluginVm(engine_, *wasm, plugin_config, log_level,
                        std::move(opt));
}

// Macro to stop test execution if the VM has failed.
// Includes logs in the output so that panic reasons are printed.
#define ASSERT_VM_HEALTH(phase, handle, context)                           \
  if (handle->wasm()->isFailed()) {                                        \
    FAIL() << absl::Substitute("[$0] Wasm VM failed! Logs: \n$1\n", phase, \
                               absl::StrJoin(context.phase_logs(), "\n")); \
  }

void DynamicTest::TestBody() {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/false);
  ASSERT_TRUE(load_wasm.ok()) << load_wasm.status();
  auto handle = *load_wasm;

  // Log start and end of test to log file output.
  LogTestBounds test_log(
      static_cast<TestWasm*>(handle->wasm().get())->options());

  // Initialize plugin.
  auto plugin_init = InitializePlugin(handle);
  ASSERT_TRUE(plugin_init.ok()) << plugin_init;
  TestContext* root_context = static_cast<TestContext*>(
      handle->wasm()->getRootContext(handle->plugin(),
                                     /*allow_closed=*/false));
  ASSERT_NE(root_context, nullptr);
  ASSERT_VM_HEALTH("plugin_init", handle, (*root_context));
  CheckSideEffects("plugin_init", cfg_.plugin_init(), *root_context);

  // Initialize stream.
  auto stream = TestHttpContext(handle);
  ASSERT_VM_HEALTH("stream_init", handle, stream);
  CheckSideEffects("stream_init", cfg_.stream_init(), stream);

  // Exercise phase tests in sequence.
  if (cfg_.has_request_headers()) {
    const auto& invoke = cfg_.request_headers();
    auto headers = ParseHeaders(invoke.input(), /*is_request=*/true);
    ASSERT_TRUE(headers.ok()) << headers.status();
    auto res = stream.SendRequestHeaders(*headers);
    ASSERT_VM_HEALTH("request_headers", handle, stream);
    CheckPhaseResults("request_headers", invoke.result(), stream, res);
  }
  auto run_body_test = [&handle, &stream, this](
                           std::string phase,
                           google::protobuf::RepeatedPtrField<pb::Invocation>
                               invocations,
                           auto invoke_wasm) {
    if (invocations.size() == 0) return;
    auto body_chunking_plan = cfg_.body_chunking_plan_case();
    if (invocations.size() != 1 &&
        body_chunking_plan !=
            pb::Test::BodyChunkingPlanCase::BODY_CHUNKING_PLAN_NOT_SET) {
      FAIL()
          << "Cannot specify body_chunking_plan with multiple body invocations";
      return;
    }
    for (const pb::Invocation& invocation : invocations) {
      TestHttpContext::Result body_result = TestHttpContext::Result{};
      absl::StatusOr<std::string> complete_input_body =
          ParseBodyInput(invocation.input());
      if (!complete_input_body.ok()) {
        FAIL() << complete_input_body.status();
      }

      std::vector<std::string> chunks;
      if (body_chunking_plan !=
          pb::Test::BodyChunkingPlanCase::BODY_CHUNKING_PLAN_NOT_SET) {
        chunks = ChunkBody(*complete_input_body, cfg_);
      } else {
        chunks = {*complete_input_body};
      }
      for (int i = 0; i < chunks.size(); ++i) {
        // When there are no trailers, the last body chunk is end of stream.
        TestHttpContext::Result res =
            invoke_wasm(std::move(chunks[i]), i == chunks.size() - 1);
        ASSERT_VM_HEALTH(phase, handle, stream);
        body_result.body = body_result.body.append(res.body);
      }
      CheckPhaseResults(phase, invocation.result(), stream, body_result);
    }
  };

  ASSERT_NO_FATAL_FAILURE(
      run_body_test("request_body", cfg_.request_body(),
                    [&stream](std::string chunk, bool end_of_stream) {
                      return stream.SendRequestBody(chunk, end_of_stream);
                    }));

  if (cfg_.has_response_headers()) {
    const auto& invoke = cfg_.response_headers();
    auto headers = ParseHeaders(invoke.input(), /*is_request=*/false);
    ASSERT_TRUE(headers.ok()) << headers.status();
    auto res = stream.SendResponseHeaders(*headers);
    ASSERT_VM_HEALTH("response_headers", handle, stream);
    CheckPhaseResults("response_headers", invoke.result(), stream, res);
  }

  ASSERT_NO_FATAL_FAILURE(
      run_body_test("response_body", cfg_.response_body(),
                    [&stream](std::string chunk, bool end_of_stream) {
                      return stream.SendResponseBody(chunk, end_of_stream);
                    }));

  // Tear down HTTP context.
  stream.TearDown();
  ASSERT_VM_HEALTH("stream_destroy", handle, stream);
  CheckSideEffects("stream_destroy", cfg_.stream_destroy(), stream);

  // Tear down the root contexts. We can't easily test side effects here because
  // WasmBase uniquely owns these objects and cleans them up.
  handle->wasm()->startShutdown(handle->plugin()->key());
  if (handle->wasm()->isFailed()) {
    FAIL() << "[plugin_destroy] Wasm VM failed!\n";
  }
}

#define BM_RETURN_IF_ERROR(status)          \
  if (!status.ok()) {                       \
    state.SkipWithError(status.ToString()); \
    return;                                 \
  }
#define BM_RETURN_IF_FAILED(handle)           \
  if (handle && handle->wasm()->isFailed()) { \
    state.SkipWithError("VM failed!");        \
    return;                                   \
  }

void DynamicTest::EmitStats(benchmark::State& state,
                            proxy_wasm::PluginHandleBase& handle,
                            const TestContext& context) {
  state.counters["WasmMemoryB"] = benchmark::Counter(
      handle.wasm()->wasm_vm()->getMemorySize(), benchmark::Counter::kDefaults,
      benchmark::Counter::kIs1024);
  state.counters["LogsSizeB"] =
      benchmark::Counter(context.logging_bytes(), benchmark::Counter::kDefaults,
                         benchmark::Counter::kIs1024);
  state.counters["LogEntries"] = context.logging_entries();
  state.counters["WasmSizeB"] = benchmark::Counter(
      std::filesystem::file_size(env_.wasm_path()),
      benchmark::Counter::kDefaults, benchmark::Counter::kIs1024);
}

void DynamicTest::BenchPluginLifecycle(benchmark::State& state) {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/true);
  BM_RETURN_IF_ERROR(load_wasm.status());
  auto handle = *load_wasm;

  // Benchmark plugin initialization and teardown.
  bool first = true;
  for (auto _ : state) {
    // Create root context (start) and call configure on it.
    auto plugin_init = InitializePlugin(handle);
    BM_RETURN_IF_ERROR(plugin_init);

    // Emit root stats before teardown. After teardown the context is gone.
    if (first) {
      first = false;
      TestContext* root = static_cast<TestContext*>(
          handle->wasm()->getRootContext(handle->plugin(),
                                         /*allow_closed=*/false));
      EmitStats(state, *handle, *root);
    }

    // Explicit shutdown; required to recreate root context in the next loop.
    handle->wasm()->startShutdown(handle->plugin()->key());
    BM_RETURN_IF_FAILED(handle);
  }
}

void DynamicTest::BenchStreamLifecycle(benchmark::State& state) {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/true);
  BM_RETURN_IF_ERROR(load_wasm.status());
  auto handle = *load_wasm;

  // Initialize plugin.
  auto plugin_init = InitializePlugin(handle);
  BM_RETURN_IF_ERROR(plugin_init);
  BM_RETURN_IF_FAILED(handle);

  std::vector<AdditionalStream> additional_streams;
  for (int i = 0; i < env_.num_additional_streams(); ++i) {
    additional_streams.emplace_back(handle, /*request_headers=*/nullptr,
                                    /*response_headers=*/nullptr,
                                    /*request_body_chunks=*/nullptr,
                                    /*response_body_chunks=*/nullptr);
    BM_RETURN_IF_ERROR(additional_streams.back().Advance());
  }

  // Benchmark stream initialization and teardown.
  bool first = true;
  for (auto _ : state) {
    auto stream = TestHttpContext(handle);
    benchmark::DoNotOptimize(stream);
    BM_RETURN_IF_FAILED(handle);
    stream.TearDown();

    if (first) {
      first = false;
      EmitStats(state, *handle, stream);
    }
  }
}

void DynamicTest::BenchHttpHandlers(benchmark::State& state) {
  // Initialize VM.
  auto load_wasm = LoadWasm(/*benchmark=*/true);
  BM_RETURN_IF_ERROR(load_wasm.status());
  auto handle = *load_wasm;

  // Initialize plugin.
  auto plugin_init = InitializePlugin(handle);
  BM_RETURN_IF_ERROR(plugin_init);
  BM_RETURN_IF_FAILED(handle);

  // Benchmark all configured HTTP handlers.
  std::optional<TestHttpContext::Headers> request_headers;
  if (cfg_.has_request_headers()) {
    auto headers = ParseHeaders(cfg_.request_headers().input(), true);
    BM_RETURN_IF_ERROR(headers.status());
    request_headers = *headers;
  }
  std::optional<TestHttpContext::Headers> response_headers;
  if (cfg_.has_response_headers()) {
    auto headers = ParseHeaders(cfg_.request_headers().input(), false);
    BM_RETURN_IF_ERROR(headers.status());
    response_headers = *headers;
  }
  absl::StatusOr<std::vector<std::string>> request_body_chunks =
      PrepBodyCallbackBenchmark(cfg_, cfg_.request_body());
  BM_RETURN_IF_ERROR(request_body_chunks.status());
  absl::StatusOr<std::vector<std::string>> response_body_chunks =
      PrepBodyCallbackBenchmark(cfg_, cfg_.response_body());
  BM_RETURN_IF_ERROR(response_body_chunks.status());

  std::vector<AdditionalStream> additional_streams;
  for (int i = 0; i < env_.num_additional_streams(); ++i) {
    additional_streams.emplace_back(
      handle, request_headers.has_value() ? &*request_headers : nullptr,
      response_headers.has_value() ? &*response_headers : nullptr,
      &*request_body_chunks, &*response_body_chunks);
    // Advance twice, once to create the TestHttpContext and once to perform
    // an HTTP handler callback.
    BM_RETURN_IF_ERROR(additional_streams.back().Advance());
    BM_RETURN_IF_ERROR(additional_streams.back().Advance());
  }

  int additional_stream_advance_rate =
    (env_.additional_stream_advance_rate() > 0)
          ? env_.additional_stream_advance_rate()
          : 3;

  std::optional<TestHttpContext> stream;
  for (auto _ : state) {
    // Pausing timing is not recommended. One way we could avoid it:
    // - include stream context create/destroy cost in handler benchmarks
    // - don't hand ownership of body chunks to stream context
    state.PauseTiming();
    stream.emplace(handle);  // create/destroy TestHttpContext
    std::vector<std::string> request_body_chunks_copies = *request_body_chunks;
    std::vector<std::string> response_body_chunks_copies =
        *response_body_chunks;

    // Advance a fraction of additional streams, if present.
    if (!additional_streams.empty()) {
      for (int i = 0; i < additional_stream_advance_rate; ++i) {
        BM_RETURN_IF_ERROR(
            additional_streams[absl::Uniform(bitgen_, 0U,
                                             additional_streams.size())]
                .Advance());
      }
    }
    state.ResumeTiming();

    if (request_headers) {
      auto res = stream->SendRequestHeaders(*request_headers);
      benchmark::DoNotOptimize(res);
      BM_RETURN_IF_FAILED(handle);
    }
    for (int i = 0; i < request_body_chunks_copies.size(); ++i) {
      std::string& body = request_body_chunks_copies[i];
      auto res = stream->SendRequestBody(
        std::move(body), i == request_body_chunks_copies.size() - 1);
      benchmark::DoNotOptimize(res);
      BM_RETURN_IF_FAILED(handle);
    }
    if (response_headers) {
      auto res = stream->SendResponseHeaders(*response_headers);
      benchmark::DoNotOptimize(res);
      BM_RETURN_IF_FAILED(handle);
    }
    for (int i = 0; i < response_body_chunks_copies.size(); ++i) {
      std::string& body = response_body_chunks_copies[i];
      auto res = stream->SendResponseBody(
        std::move(body), i == response_body_chunks_copies.size() - 1);
      benchmark::DoNotOptimize(res);
      BM_RETURN_IF_FAILED(handle);
    }
  }

  EmitStats(state, *handle, *stream);
}

void DynamicTest::CheckSideEffects(const std::string& phase,
                                   const pb::Expectation& expect,
                                   const TestContext& context) {
  // Check logging.
  for (const auto& match : expect.log()) {
    FindString(phase, "log", match, context.phase_logs());
  }
}

void DynamicTest::CheckPhaseResults(const std::string& phase,
                                    const pb::Expectation& expect,
                                    const TestContext& context,
                                    const TestHttpContext::Result& result) {
  // Check header values.
  for (const auto& header : expect.has_header()) {
    ASSERT_TRUE(!header.key().empty()) << absl::Substitute(
        "[$0] Missing has_header.key: '$1'", phase, header.ShortDebugString());
    auto it = result.headers.find(header.key());
    if (it == result.headers.end()) {
      ADD_FAILURE() << absl::Substitute("[$0] Missing header '$1'", phase,
                                        header.key());
    } else if (it->second != header.value()) {
      ADD_FAILURE() << absl::Substitute(
          "[$0] Header '$1' value is '$2', expected '$3'", phase, header.key(),
          it->second, header.value());
    }
  }
  // Check header removals.
  for (const auto& header : expect.no_header()) {
    ASSERT_TRUE(!header.key().empty()) << absl::Substitute(
        "[$0] Missing no_header.key: '$1'", phase, header.ShortDebugString());
    auto it = result.headers.find(header.key());
    if (it != result.headers.end()) {
      ADD_FAILURE() << absl::Substitute(
          "[$0] Header '$1' value is '$2', expected removed", phase,
          header.key(), it->second);
    }
  }
  // Check serialized headers.
  if (expect.headers_size() > 0) {
    std::vector<std::string> headers;
    for (const auto& kv : result.headers) {
      headers.emplace_back(absl::StrCat(kv.first, ": ", kv.second));
    }
    for (const auto& match : expect.headers()) {
      FindString(phase, "header", match, headers);
    }
  }
  // Check body content.
  for (const auto& match : expect.body()) {
    FindString(phase, "body", match, {result.body});
  }
  // Check immediate response.
  bool is_continue =
      result.header_status == proxy_wasm::FilterHeadersStatus::Continue ||
      result.header_status ==
          proxy_wasm::FilterHeadersStatus::ContinueAndEndStream;
  if (expect.has_immediate() == is_continue) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] Expected $1, status is $2", phase,
        expect.has_immediate() ? "immediate reply (stop filters status)"
                               : "no immediate reply (continue status)",
        result.header_status);
  }
  if (expect.has_immediate() == (result.http_code == 0)) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] Expected $1, HTTP code is $2", phase,
        expect.has_immediate() ? "immediate reply (HTTP code > 0)"
                               : "no immediate reply (HTTP code == 0)",
        result.http_code);
  }
  const auto& imm = expect.immediate();
  if (imm.has_http_status() && imm.http_status() != result.http_code) {
    ADD_FAILURE() << absl::Substitute("[$0] HTTP status is $1, expected $2",
                                      phase, result.http_code,
                                      imm.http_status());
  }
  if (imm.has_grpc_status() && imm.grpc_status() != result.grpc_code) {
    ADD_FAILURE() << absl::Substitute("[$0] gRPC status is $1, expected $2",
                                      phase, result.grpc_code,
                                      imm.grpc_status());
  }
  if (imm.has_details() && imm.details() != result.details) {
    ADD_FAILURE() << absl::Substitute("[$0] gRPC detail is $1, expected $2",
                                      phase, result.details, imm.details());
  }
  // Check logging.
  for (const auto& match : expect.log()) {
    FindString(phase, "log", match, context.phase_logs());
  }
}

void DynamicTest::FindString(const std::string& phase, const std::string& type,
                             const pb::StringMatcher& expect,
                             const std::vector<std::string>& contents) {
  auto matcher = StringMatcher::Create(expect, env_);
  if (!matcher.ok()) {
    ADD_FAILURE() << absl::Substitute("[$0] $1", phase,
                                      matcher.status().ToString());
    return;
  }
  if (!matcher->Matches(contents)) {
    ADD_FAILURE() << absl::Substitute(
        "[$0] expected $1 of $2 $3: '$4', actual: \n$5", phase,
        expect.invert() ? "absence" : "presence",
        expect.has_regex() ? "regex" : "exact", type,
        expect.has_regex() ? expect.regex() : matcher->getExact(),
        absl::StrJoin(contents, "\n"));
  }
}

namespace {
absl::Status ParseHTTP1Headers(const std::string& content, bool is_request,
                               TestHttpContext::Headers& hdrs) {
  const std::string end_headers = "\r\n\r\n";
  quiche::BalsaHeaders headers;
  quiche::BalsaFrame frame;
  frame.set_balsa_headers(&headers);
  frame.set_is_request(is_request);
  frame.ProcessInput(content.c_str(), content.size());
  frame.ProcessInput(end_headers.data(), end_headers.size());
  if (frame.Error() ||
      frame.ParseState() ==
          quiche::BalsaFrameEnums::READING_HEADER_AND_FIRSTLINE) {
    return absl::InvalidArgumentError(absl::StrCat(
        "Header parse error: ",
        quiche::BalsaFrameEnums::ErrorCodeToString(frame.ErrorCode())));
  }

  // Emit HTTP2 pseudo headers based on HTTP1 input.
  if (is_request) {
    hdrs.InsertOrAppend(":method", headers.request_method());
    // Parse URI to see if it's in "absolute form" (scheme://host/path?query)
    GURL uri(static_cast<std::string>(headers.request_uri()));
    if (uri.is_valid()) {
      // Emit everything from the URI.
      hdrs.InsertOrAppend(":scheme", uri.scheme());
      hdrs.InsertOrAppend(":path", uri.PathForRequest());
      hdrs.InsertOrAppend(":authority",
                          uri.IntPort() > 0
                              ? absl::StrCat(uri.host(), ":", uri.IntPort())
                              : uri.host());
      headers.RemoveAllOfHeader("Host");
    } else {
      // Validate URI assuming "origin form" (absolute path and query only).
      GURL base("http://example.com");
      GURL join = base.Resolve(static_cast<std::string>(headers.request_uri()));
      if (!join.is_valid() || join.PathForRequest() != headers.request_uri()) {
        return absl::InvalidArgumentError(
            absl::StrCat("Invalid URI: ", headers.request_uri()));
      }
      // Emit path as is. Emit authority if present. No scheme.
      hdrs.InsertOrAppend(":path", headers.request_uri());
      if (!headers.Authority().empty()) {
        hdrs.InsertOrAppend(":authority", headers.Authority());
        headers.RemoveAllOfHeader("Host");
      }
    }
  } else {
    hdrs.InsertOrAppend(":status", headers.response_code());
  }

  // Emit normal headers to map, coalescing as we go. Convert header keys to
  // lowercase like Envoy does. The wasm header map is also case insensitive.
  for (const auto& [key, value] : headers.lines()) {
    hdrs.InsertOrAppend(absl::AsciiStrToLower(key), value);
  }
  return absl::OkStatus();
}
}  // namespace

absl::StatusOr<TestHttpContext::Headers> DynamicTest::ParseHeaders(
    const pb::Input& input, bool is_request) {
  TestHttpContext::Headers hdrs;

  if (!input.file().empty()) {
    // Handle file input.
    auto content = ReadContent(input.file(), env_);
    if (!content.ok()) return content.status();
    auto parse = ParseHTTP1Headers(*content, is_request, hdrs);
    if (!parse.ok()) return parse;
  } else if (!input.content().empty()) {
    // Handle string input.
    auto parse = ParseHTTP1Headers(input.content(), is_request, hdrs);
    if (!parse.ok()) return parse;
  } else {
    // Handle proto input.
    for (const auto& header : input.header()) {
      hdrs.InsertOrAppend(header.key(), header.value());
    }
  }
  return hdrs;
}
absl::StatusOr<std::string> DynamicTest::ParseBodyInput(
    const pb::Input& input) {
  if (!input.file().empty()) {
    // Handle file input.
    return ReadContent(input.file(), env_);
  } else {
    return input.content();
  }
}

std::vector<std::string> DynamicTest::ChunkBody(
    const std::string& complete_body, const pb::Test& test) {
  if (test.has_num_chunks()) {
    int chunk_length = complete_body.size() / test.num_chunks();
    std::vector<std::string> body_chunks = absl::StrSplit(
        complete_body,
        absl::MaxSplits(absl::ByLength(chunk_length), test.num_chunks() - 1));
    return body_chunks;
  } else {
    std::vector<std::string> body_chunks =
        absl::StrSplit(complete_body, absl::ByLength(test.chunk_size()));
    return body_chunks;
  }
}

absl::StatusOr<std::vector<std::string>> DynamicTest::PrepBodyCallbackBenchmark(
    const pb::Test& test,
    google::protobuf::RepeatedPtrField<pb::Invocation> invocations) {
  if (invocations.size() == 0) return std::vector<std::string>{};
  auto body_chunking_plan = test.body_chunking_plan_case();
  if (invocations.size() != 1 &&
      body_chunking_plan !=
          pb::Test::BodyChunkingPlanCase::BODY_CHUNKING_PLAN_NOT_SET) {
    return absl::InvalidArgumentError(
        "Cannot specify body_chunking_plan with multiple body invocations");
  }
  std::vector<std::string> chunks;
  for (const pb::Invocation& invocation : invocations) {
    absl::StatusOr<std::string> complete_input_body =
        ParseBodyInput(invocation.input());
    if (!complete_input_body.ok()) {
      return complete_input_body.status();
    }
    if (body_chunking_plan !=
        pb::Test::BodyChunkingPlanCase::BODY_CHUNKING_PLAN_NOT_SET) {
      chunks = ChunkBody(*complete_input_body, cfg_);
    } else {
      chunks.emplace_back(*complete_input_body);
    }
  }
  return chunks;
}

}  // namespace service_extensions_samples
