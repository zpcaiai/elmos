"""Unit tests for native attestation bridge."""

from __future__ import annotations

import unittest
from elmos_formal_assurance.native_attestation_bridge import (
    fast_merkle_root,
    fast_sign_attestation,
)


class NativeAttestationTest(unittest.TestCase):
    def test_native_sign(self) -> None:
        payload = b'{"artifact":"elmos-core","version":"1.0.0"}'
        res = fast_sign_attestation(payload, "test-secret-key-1234")
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "OK")
        self.assertTrue(res["payload_digest"].startswith("sha256:"))
        self.assertEqual(len(res["signature"]), 64)

    def test_native_merkle_root(self) -> None:
        digests = [
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        ]
        root = fast_merkle_root(digests)
        self.assertIsNotNone(root)
        self.assertEqual(len(root), 64)


if __name__ == "__main__":
    unittest.main()
