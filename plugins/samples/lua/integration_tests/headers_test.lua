function envoy_on_request(request_handle)
  run_test("request headers adds and gets headers correctly", function()
     request_handle:headers():add("request-test1", "abc")
     request_handle:headers():add("request-test2", "def")
     assert(request_handle:headers():get("request-test2") == "def")
  end)

  run_test("request headers replaces headers correctly", function()
     request_handle:headers():add("replace-test", "some-value")
     request_handle:headers():replace("replace-test", "replaced")
     assert(request_handle:headers():get("replace-test") == "replaced")
  end)

  run_test("request headers handles headers case insensitively", function()
     request_handle:headers():add("FOO-case", "bar")
     request_handle:headers():replace("fOo-case", "replaced-bar")
     assert(request_handle:headers():get("FoO-case") == "replaced-bar")
     request_handle:headers():remove("FOO-case")
     assert(request_handle:headers():get("FOO-case") == nil)
  end)

  run_test("request headers iterates headers correctly using pairs", function()
     request_handle:headers():add("integration-test", "some-value")
     local found = false
     for k, v in pairs(request_handle:headers()) do
       if k == "integration-test" and v == "some-value" then
         found = true
         break
       end
     end
     assert(found, "pairs evaluation failed to find integration-test")
  end)

  run_test("request headers handles missing headers gracefully", function()
     assert(request_handle:headers():get("non-existent-header") == nil)
     request_handle:headers():replace("non-existent-replace", "new-val")
     assert(request_handle:headers():get("non-existent-replace") == "new-val")
     request_handle:headers():remove("non-existent-remove")
     assert(request_handle:headers():get("non-existent-remove") == nil)
  end)
end

function envoy_on_response(response_handle)
  run_test("response headers adds and gets headers correctly", function()
     response_handle:headers():add("response-test1", "v1")
     response_handle:headers():add("response-test2", "v2")
     assert(response_handle:headers():get("response-test2") == "v2")
  end)

  run_test("response headers replaces headers correctly", function()
     response_handle:headers():add("replace-test", "some-value")
     response_handle:headers():replace("replace-test", "replaced")
     assert(response_handle:headers():get("replace-test") == "replaced")
  end)

  run_test("response headers handles headers case insensitively", function()
     response_handle:headers():add("FOO-case", "bar")
     response_handle:headers():replace("fOo-case", "replaced-bar")
     assert(response_handle:headers():get("FoO-case") == "replaced-bar")
     response_handle:headers():remove("FOO-case")
     assert(response_handle:headers():get("FOO-case") == nil)
  end)

  run_test("response headers iterates headers correctly using pairs", function()
     response_handle:headers():add("integration-test", "some-value")
     local found = false
     for k, v in pairs(response_handle:headers()) do
       if k == "integration-test" and v == "some-value" then
         found = true
         break
       end
     end
     assert(found, "pairs evaluation failed to find integration-test")
  end)

  run_test("response headers handles missing headers gracefully", function()
     assert(response_handle:headers():get("non-existent-header") == nil)
     response_handle:headers():replace("non-existent-replace", "new-val")
     assert(response_handle:headers():get("non-existent-replace") == "new-val")
     response_handle:headers():remove("non-existent-remove")
     assert(response_handle:headers():get("non-existent-remove") == nil)
  end)
end
