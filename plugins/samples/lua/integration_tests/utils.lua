function run_test(name, fn)
  fn()
  print("LUA_TEST " .. name .. ": PASS")
end
