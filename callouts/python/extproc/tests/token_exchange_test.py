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

"""Pure unit tests for the token cache and JWT claim helper.

No gRPC server, no network -- matches the testing style of the other
examples in this collection (e.g. litellm_gateway_test.py). Note that,
like litellm_gateway_test.py, importing service_callout_example still
requires grpc and the generated Envoy proto stubs to be installed (it's
the module under test, not a dependency of these tests specifically) --
run via `pytest extproc/tests/` with the framework's requirements.txt
installed.

Lives in the shared `extproc/tests/` tree (flat `<name>_test.py` naming),
not under `extproc/example/token_exchange/`, so `pytest extproc/tests/`
picks it up along with every other example's tests.
"""
import base64
import json
import time
import unittest

from extproc.example.token_exchange.service_callout_example import (
    CachedToken, TokenCache, _decode_jwt_claims_unverified)


class TestTokenCache(unittest.TestCase):

  def test_key_is_sha256_not_raw_token(self):
    key = TokenCache.key_for("super-secret-jwt")
    self.assertNotEqual(key, "super-secret-jwt")
    self.assertEqual(len(key), 64)

  def test_set_then_get(self):
    cache = TokenCache()
    key = TokenCache.key_for("token-a")
    cache.set(key, CachedToken(
        mutations={"authorization": "Bearer x"}, expires_at=time.time() + 60))
    result = cache.get(key)
    self.assertIsNotNone(result)
    self.assertEqual(result.mutations["authorization"], "Bearer x")

  def test_expired_entry_returns_none(self):
    cache = TokenCache()
    key = TokenCache.key_for("token-b")
    cache.set(key, CachedToken(mutations={}, expires_at=time.time() - 1))
    self.assertIsNone(cache.get(key))

  def test_missing_key_returns_none(self):
    cache = TokenCache()
    self.assertIsNone(cache.get(TokenCache.key_for("never-set")))


def _fake_jwt(claims: dict) -> str:
  header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
  payload = base64.urlsafe_b64encode(
      json.dumps(claims).encode()).rstrip(b"=").decode()
  return f"{header}.{payload}.sig"


class TestJwtClaimExtraction(unittest.TestCase):

  def test_extracts_known_claims(self):
    jwt = _fake_jwt(
        {"sub": "user-1", "email": "user@example.com", "groups": ["a", "b"]})
    claims = _decode_jwt_claims_unverified(jwt)
    self.assertEqual(claims["sub"], "user-1")
    self.assertEqual(claims["email"], "user@example.com")
    self.assertEqual(claims["groups"], ["a", "b"])

  def test_malformed_jwt_returns_empty_dict(self):
    self.assertEqual(_decode_jwt_claims_unverified("not-a-jwt"), {})

  def test_non_json_payload_returns_empty_dict(self):
    bad = "aaaa." + base64.urlsafe_b64encode(b"not json").decode() + ".sig"
    self.assertEqual(_decode_jwt_claims_unverified(bad), {})


if __name__ == "__main__":
  unittest.main()
