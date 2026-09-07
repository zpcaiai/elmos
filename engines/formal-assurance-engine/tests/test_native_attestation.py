"""Unit tests for the optional, digest-bound native attestation bridge."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest

from elmos_formal_assurance.native_attestation_bridge import (
    NativeAttestationBridge,
    NativeAttestationError,
    NativeHmacLocalAttestationSigner,
)


class _FakeFunction:
    def __init__(self, callback: object) -> None:
        self.callback = callback
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *arguments: object) -> object:
        return self.callback(*arguments)  # type: ignore[operator]


class _FakeNativeLibrary:
    def __init__(self, *, corrupt_signature: bool = False) -> None:
        self.corrupt_signature = corrupt_signature
        self.buffers: dict[int, ctypes.Array[ctypes.c_char]] = {}
        self.elmos_attestation_sign = _FakeFunction(self._sign)
        self.elmos_merkle_root = _FakeFunction(self._merkle)
        self.elmos_free_string = _FakeFunction(self._free)

    def _allocate(self, value: str) -> int:
        buffer = ctypes.create_string_buffer(value.encode("utf-8"))
        address = ctypes.addressof(buffer)
        self.buffers[address] = buffer
        return address

    def _sign(
        self,
        payload_pointer: object,
        payload_length: object,
        key: object,
    ) -> int:
        payload = ctypes.string_at(payload_pointer, int(payload_length))
        if not isinstance(key, bytes):
            raise AssertionError("fake native key must be bytes")
        signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
        if self.corrupt_signature:
            signature = "0" * 64
        return self._allocate(
            json.dumps(
                {
                    "status": "OK",
                    "payload_digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "signature": signature,
                    "signer_id": "elmos-local-engineering-signer/v1",
                    "algorithm": "HMAC-SHA256",
                }
            )
        )

    def _merkle(self, csv_value: object) -> int:
        if not isinstance(csv_value, bytes):
            raise AssertionError("fake native Merkle input must be bytes")
        digests = csv_value.decode("ascii").split(",") if csv_value else []
        if not digests:
            root = hashlib.sha256(b"").hexdigest()
        else:
            level = [bytes.fromhex(value) for value in digests]
            while len(level) > 1:
                next_level = []
                for index in range(0, len(level), 2):
                    left = level[index]
                    right = level[index + 1] if index + 1 < len(level) else left
                    next_level.append(hashlib.sha256(left + right).digest())
                level = next_level
            root = level[0].hex()
        return self._allocate(root)

    def _free(self, pointer: object) -> None:
        address = pointer.value if isinstance(pointer, ctypes.c_void_p) else int(pointer)
        self.buffers.pop(address, None)


class NativeAttestationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.library_path = self.root / "libelmos_native.fixture"
        self.library_path.write_bytes(b"digest-bound-native-library-fixture")
        self.library_path.chmod(0o500)
        self.library_digest = "sha256:" + hashlib.sha256(
            self.library_path.read_bytes()
        ).hexdigest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _bridge(
        self, *, corrupt_signature: bool = False
    ) -> NativeAttestationBridge:
        library = _FakeNativeLibrary(corrupt_signature=corrupt_signature)
        return NativeAttestationBridge(
            self.library_path,
            self.library_digest,
            _loader=lambda _: library,
        )

    def test_unconfigured_native_path_remains_explicitly_unavailable(self) -> None:
        self.assertIsNone(NativeAttestationBridge.from_configuration(None, None))
        with self.assertRaisesRegex(NativeAttestationError, "supplied together"):
            NativeAttestationBridge.from_configuration(self.library_path, None)
        with self.assertRaisesRegex(NativeAttestationError, "supplied together"):
            NativeAttestationBridge.from_configuration(None, self.library_digest)

    def test_library_identity_and_permissions_fail_closed(self) -> None:
        with self.assertRaisesRegex(NativeAttestationError, "must be absolute"):
            NativeAttestationBridge("relative-library", self.library_digest)
        with self.assertRaisesRegex(NativeAttestationError, "digest mismatch"):
            NativeAttestationBridge(
                self.library_path,
                "sha256:" + "0" * 64,
                _loader=lambda _: _FakeNativeLibrary(),
            )

        link_path = self.root / "native-link"
        link_path.symlink_to(self.library_path)
        with self.assertRaisesRegex(NativeAttestationError, "missing or unsafe"):
            NativeAttestationBridge(
                link_path,
                self.library_digest,
                _loader=lambda _: _FakeNativeLibrary(),
            )

        self.library_path.chmod(0o720)
        with self.assertRaisesRegex(NativeAttestationError, "writable"):
            NativeAttestationBridge(
                self.library_path,
                self.library_digest,
                _loader=lambda _: _FakeNativeLibrary(),
            )

    def test_native_signer_and_merkle_results_are_independently_checked(self) -> None:
        bridge = self._bridge()
        self.assertEqual(bridge.identity.sha256, self.library_digest)
        key = os.urandom(32)
        payload = b'{"artifact":"elmos-core","version":"1.0.0"}'
        signer = NativeHmacLocalAttestationSigner(
            bridge,
            key,
            key_id="native-local-key-v1",
        )
        signature = signer.sign(payload)
        expected = hmac.new(
            base64.urlsafe_b64encode(key), payload, hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature.value, "hmac-sha256:" + expected)
        self.assertEqual(signature.classification, "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertTrue(signer.verify(payload, signature))
        self.assertFalse(signer.verify(payload + b"!", signature))

        digests = [
            hashlib.sha256(b"first").hexdigest(),
            hashlib.sha256(b"second").hexdigest(),
            hashlib.sha256(b"third").hexdigest(),
        ]
        root = bridge.merkle_root(digests)
        self.assertRegex(root, r"^[0-9a-f]{64}$")

    def test_corrupt_native_signature_is_never_promoted(self) -> None:
        bridge = self._bridge(corrupt_signature=True)
        with self.assertRaisesRegex(
            NativeAttestationError, "failed independent validation"
        ):
            bridge.sign_attestation(b"payload", b"k" * 32)


if __name__ == "__main__":
    unittest.main()
