// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef NET_TURING_WASM_LUA_ENVOY_LUA_API_SHIMS_H_
#define NET_TURING_WASM_LUA_ENVOY_LUA_API_SHIMS_H_

#include "absl/strings/string_view.h"

namespace sample::lua {

constexpr absl::string_view kLua51CompatShims = R"lua(
  if table then
    _G.unpack = table.unpack
    if not table.maxn then
      table.maxn = function(t)
        local max = 0
        for k, v in pairs(t) do
          if type(k) == "number" and k > max then
            max = k
          end
        end
        return max
      end
    end
    if not table.getn then
      table.getn = function(t) return #t end
    end
  end
  if math then
    if not math.pow then
      math.pow = function(x, y) return x^y end

    end
    if not math.log10 then
      math.log10 = function(x) return math.log(x, 10) end
    end
    if not math.mod then
      math.mod = math.fmod
    end
  end
)lua";

constexpr absl::string_view kStatusUnwrapperFunctionShim = R"lua(
  function attach_status_unwrapper(class_name)
      local class_table = _G[class_name]
      if not class_table then return end

      local getter = __raw_getmetatable or getmetatable
      local class_meta = getter(class_table)
      if not class_meta then return end

      local function wrap_index(meta)
          local orig_index = meta.__index
          if type(orig_index) ~= "function" then return end

          meta.__index = function(self, key)
              local property = orig_index(self, key)
              if type(property) ~= "function" then return property end

              return function(self_arg, ...)
                  local res = property(self_arg, ...)
                  if type(res) ~= "userdata" then return res end

                  local ok, is_status = pcall(function() return res.is_status_node end)
                  if not (ok and is_status) then return res end

                  if not res:ok() then error(res:message(), 2) end

                  local ok_val, has_val = pcall(function() return res.has_value end)
                  if ok_val and has_val then return res:value() end
                  return nil
              end
          end
      end

      -- Wrap static methods
      wrap_index(class_meta)

      -- Wrap instance methods by scanning the metatable for instance metatables
      for k, v in pairs(class_meta) do
          if type(v) == "table" and type(v.__index) == "function" then
              wrap_index(v)
          end
      end
  end
)lua";

}  // namespace sample::lua
#endif  // NET_TURING_WASM_LUA_ENVOY_LUA_API_SHIMS_H_
