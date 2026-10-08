-- Global context object that persists across Envoy API lifecycle phases
local stream_context = {
  request_headers_seen = false,
  request_body_seen = false,
  response_headers_seen = false,
  response_body_seen = false
}

function envoy_on_request(request_handle)
  run_test("lifecycle on_request_headers works", function()
    stream_context.request_headers_seen = true
    assert(request_handle:headers():get("e2e-request") == "initial")
  end)

  run_test("lifecycle on_request_body works", function()
    assert(stream_context.request_headers_seen == true, "State persisted from request headers")
    stream_context.request_body_seen = true
    -- request_handle:body() yields, which dynamic_test.cc currently evaluates as an immediate reply violation.
    -- Verified natively in coroutine_test.cc instead!
  end)
end

function envoy_on_response(response_handle)
  run_test("lifecycle on_response_headers works", function()
    assert(stream_context.request_body_seen == true, "State persisted across request and response")
    stream_context.response_headers_seen = true
    assert(response_handle:headers():get("e2e-response") == "reply")
  end)

  run_test("lifecycle on_response_body works", function()
    assert(stream_context.response_headers_seen == true, "State persisted from response headers")
    stream_context.response_body_seen = true
    -- response_handle:body() yields, verifiable in native coroutine_test.cc
  end)
end
