function envoy_on_request(h)
  local chunk_num = 0
  local all_chunks = ""
  for chunk in h:bodyChunks() do
     local len = chunk:length()
     chunk_num = chunk_num + 1
     all_chunks = all_chunks .. chunk:getBytes(0, len)
  end
  print("processed all chunks: " .. all_chunks)
  print("successfully finished iterating bodyChunks over multiple chunks, total: " .. tostring(chunk_num))
end
