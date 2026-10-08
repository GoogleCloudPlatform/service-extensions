function envoy_on_request(request_handle)
  run_test("base library loads and evaluates correct numbers", function()
    local x = 5
    local y = 10
    assert(x + y == 15, "basic math functionality is verified")
  end)

  run_test("table library validates operations", function()
    local my_table = {}
    table.insert(my_table, "first")
    table.insert(my_table, "second")
    assert(#my_table == 2, "table operations successful")
  end)

  run_test("string library formats and structures", function()
    local s = "hello world"
    assert(string.find(s, "world") ~= nil, "string functions successful")
  end)

  run_test("math library performs calculations", function()
    local result = math.sqrt(16)
    assert(result == 4, "math functions successful")
  end)

  run_test("blocked base functions panic properly", function()
    local s, err = pcall(function() dofile("fake.lua") end)
    assert(not s, "blocked function execution successfully panics")
  end)

  run_test("io library functions are completely isolated", function()
    local s, err = pcall(function() io.open("fake.txt") end)
    assert(not s, "io operations successfully panic")
  end)

  run_test("os library functions are completely isolated", function()
    local s, err = pcall(function() os.execute("echo test") end)
    assert(not s, "os operations successfully panic")
  end)

  run_test("complex iterations between modules evaluate", function()
    local counter = 0
    for i=1,10 do
      if i % 2 == 0 then counter = counter + 1 end
    end
    assert(counter == 5)
  end)

  run_test("string limits overflow panic properly", function()
    local s, err = pcall(function() string.rep("x", 1024 ^ 3) end)
    assert(not s, "string overflow rep properly aborts")
  end)
end
