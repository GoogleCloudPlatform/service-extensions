# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Body-chunk reassembly state machine for the Prompt-Amender callout.

Envoy's ext_proc streamed mode forwards each body chunk to the upstream as
soon as the callout responds to it -- returning "no mutation" for an
intermediate chunk does not withhold it, it sends that chunk's raw bytes
on immediately. That means a naive "accumulate chunks, mutate on the
last one" implementation corrupts multi-chunk requests: the unmodified
early chunks already went out, and then the final chunk's mutation
response replaces only the final chunk with the *entire* amended body,
producing `<early raw chunks><entire amended body>` upstream -- invalid
JSON, roughly the original size plus the amended size.

The fix is to explicitly withhold every non-final chunk (`clear_body =
true`, which tells Envoy not to forward that chunk's bytes) and emit the
single, fully-assembled body only on the final chunk. This module is that
state machine, kept free of any protobuf/gRPC import so the tricky
withhold/emit/fail-open transitions can be unit tested directly rather
than only through a live ext_proc stream.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class BodyTooLargeError(Exception):
  pass


class ChunkAction(str, Enum):
  WITHHOLD = "withhold"          # clear_body: true -- do not forward yet
  EMIT_MUTATED = "emit_mutated"  # final chunk, amendment succeeded
  EMIT_ORIGINAL = "emit_original"  # amendment failed, fail-open: emit
                                    # the untouched buffer so the request
                                    # -- reconstructed from whatever was
                                    # withheld plus this chunk -- survives
                                    # intact rather than truncated
  REJECT = "reject"              # amendment failed, fail-closed
  PASS_THROUGH = "pass_through"  # already gave up earlier in this stream;
                                  # nothing was withheld for this chunk, so
                                  # forward it raw


@dataclass
class ChunkResult:
  action: ChunkAction
  body: bytes = b""
  original_len: int = 0
  new_len: int = 0
  error: Optional[Exception] = None


@dataclass
class BodyAssemblyState:
  """Per-stream scratch state. One instance per request."""
  buffer: bytes = field(default_factory=bytes)
  failed: bool = False


def process_chunk(
    state: BodyAssemblyState,
    chunk: bytes,
    end_of_stream: bool,
    max_body_bytes: int,
    fail_open: bool,
    mutate: Callable[[bytes], tuple[bytes, int, int]],
) -> ChunkResult:
  """Advances the body-assembly state machine by one chunk.

  `mutate` is called with the fully assembled buffer only once
  `end_of_stream` is reached and no earlier chunk of this request has
  already failed; it must return `(mutated_body, original_len, new_len)`
  or raise. Any exception from `mutate` is treated as an amendment
  failure and caught here -- deliberately broad, since an unexpected
  exception type must still trigger fail-open/fail-closed handling
  rather than propagate and abort the whole gRPC stream.

  Once a chunk fails (oversized buffer, or a `mutate` exception on the
  final chunk), every later chunk of the same stream returns
  `PASS_THROUGH` unconditionally: the failing chunk's response already
  reconstructed everything received so far (`EMIT_ORIGINAL`) or rejected
  the request outright (`REJECT`), so nothing further should be withheld
  or re-processed.
  """
  if state.failed:
    return ChunkResult(action=ChunkAction.PASS_THROUGH)

  state.buffer += chunk

  if len(state.buffer) > max_body_bytes:
    state.failed = True
    error = BodyTooLargeError(
        f"body size exceeds max_body_bytes={max_body_bytes}")
    if fail_open:
      return ChunkResult(
          action=ChunkAction.EMIT_ORIGINAL, body=state.buffer, error=error)
    return ChunkResult(action=ChunkAction.REJECT, error=error)

  if not end_of_stream:
    return ChunkResult(action=ChunkAction.WITHHOLD)

  try:
    mutated_body, original_len, new_len = mutate(state.buffer)
  except Exception as exc:  # noqa: broad on purpose -- see docstring
    state.failed = True
    if fail_open:
      return ChunkResult(
          action=ChunkAction.EMIT_ORIGINAL, body=state.buffer, error=exc)
    return ChunkResult(action=ChunkAction.REJECT, error=exc)

  return ChunkResult(
      action=ChunkAction.EMIT_MUTATED, body=mutated_body,
      original_len=original_len, new_len=new_len)
