"""Sigstore / Cosign / Rekor / DSSE physical signing driver.

Constructs real Cosign CLI argv, DSSE envelopes, and Rekor hashedrekord
entries. Cryptographic signatures are produced with OpenSSL ECDSA-P256
(or Cosign when the binary is present). Rekor submission is a real HTTP POST.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from elmos_mature_platform.physical.protocol import (
    PhysicalCallResult,
    env_url,
    http_call,
    json_dumps,
    run_cli,
    which,
)


DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
REKOR_HASHEDREKORD_KIND = "hashedrekord"


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def is_usable_public_pem(pem: str) -> bool:
    return (
        "BEGIN PUBLIC KEY" in pem
        and "END PUBLIC KEY" in pem
        and len(pem) >= 160
    )


@dataclass
class SigstoreAttestation:
    artifact_digest: str
    dsse_envelope: Dict[str, Any]
    rekor_entry: Dict[str, Any]
    cosign_sign_argv: List[str]
    cosign_verify_argv: List[str]
    signature_base64: str
    public_key_pem: str
    certificate_pem: str = ""
    rekor_uuid: str = ""
    openssl_applied: bool = False
    rekor_applied: bool = False
    cosign_applied: bool = False
    receipts: List[PhysicalCallResult] = field(default_factory=list)

    @property
    def applied(self) -> bool:
        return self.openssl_applied and self.rekor_applied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_digest": self.artifact_digest,
            "dsse_envelope": self.dsse_envelope,
            "rekor_entry": self.rekor_entry,
            "cosign_sign_argv": self.cosign_sign_argv,
            "cosign_verify_argv": self.cosign_verify_argv,
            "signature_base64": self.signature_base64,
            "public_key_pem": self.public_key_pem,
            "certificate_pem": self.certificate_pem,
            "rekor_uuid": self.rekor_uuid,
            "openssl_applied": self.openssl_applied,
            "rekor_applied": self.rekor_applied,
            "cosign_applied": self.cosign_applied,
            "applied": self.applied,
            "receipts": [item.to_dict() for item in self.receipts],
        }


class SigstoreCosignDriver:
    """Physical Sigstore driver: OpenSSL ECDSA + Cosign CLI + Rekor HTTP."""

    def __init__(
        self,
        rekor_url: str = "",
        fulcio_url: str = "",
        timeout: float = 2.5,
    ) -> None:
        self.rekor_url = rekor_url.rstrip("/")
        self.fulcio_url = fulcio_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "SigstoreCosignDriver":
        return cls(
            rekor_url=env_url("ELMOS_REKOR_URL"),
            fulcio_url=env_url("ELMOS_FULCIO_URL"),
        )

    def generate_ephemeral_ecdsa_p256(self) -> tuple[str, str, PhysicalCallResult]:
        """Create a real P-256 key pair via OpenSSL."""
        openssl = which("openssl")
        if not openssl:
            empty = PhysicalCallResult(
                backend="openssl",
                operation="ecparam_genkey",
                method="CLI",
                url="",
                request_body=None,
                error="binary_not_found:openssl",
            )
            return "", "", empty

        with tempfile.TemporaryDirectory(prefix="elmos-sigstore-") as tmp:
            key_path = os.path.join(tmp, "key.pem")
            pub_path = os.path.join(tmp, "pub.pem")
            gen = run_cli(
                backend="openssl",
                operation="ecparam_genkey",
                argv=[openssl, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", key_path],
                timeout=self.timeout,
            )
            if not gen.applied:
                return "", "", gen
            pub = run_cli(
                backend="openssl",
                operation="ec_pubout",
                argv=[openssl, "ec", "-in", key_path, "-pubout", "-out", pub_path],
                timeout=self.timeout,
            )
            if not pub.applied:
                return "", "", pub
            with open(key_path, "r", encoding="utf-8") as handle:
                private_pem = handle.read()
            with open(pub_path, "r", encoding="utf-8") as handle:
                public_pem = handle.read()
        gen.extras["public_key_pem"] = public_pem
        return private_pem, public_pem, gen

    def sign_digest(self, digest_hex: str, private_key_pem: str) -> tuple[str, PhysicalCallResult]:
        """ECDSA-SHA256 sign a hex digest with OpenSSL."""
        openssl = which("openssl")
        if not openssl:
            return "", PhysicalCallResult(
                backend="openssl",
                operation="dgst_sign",
                method="CLI",
                url="",
                request_body=digest_hex,
                error="binary_not_found:openssl",
            )
        digest_bytes = bytes.fromhex(digest_hex)
        with tempfile.TemporaryDirectory(prefix="elmos-sigstore-sign-") as tmp:
            key_path = os.path.join(tmp, "key.pem")
            sig_path = os.path.join(tmp, "sig.bin")
            blob_path = os.path.join(tmp, "blob.bin")
            with open(key_path, "w", encoding="utf-8") as handle:
                handle.write(private_key_pem)
            with open(blob_path, "wb") as handle:
                handle.write(digest_bytes)
            signed = run_cli(
                backend="openssl",
                operation="dgst_sign",
                argv=[
                    openssl,
                    "dgst",
                    "-sha256",
                    "-sign",
                    key_path,
                    "-out",
                    sig_path,
                    blob_path,
                ],
                timeout=self.timeout,
            )
            if not signed.applied:
                return "", signed
            with open(sig_path, "rb") as handle:
                signature = handle.read()
        signed.extras["signature_base64"] = _b64e(signature)
        return _b64e(signature), signed

    def verify_digest(
        self,
        digest_hex: str,
        signature_base64: str,
        public_key_pem: str,
    ) -> PhysicalCallResult:
        """ECDSA-SHA256 verify with OpenSSL."""
        openssl = which("openssl")
        if not openssl:
            return PhysicalCallResult(
                backend="openssl",
                operation="dgst_verify",
                method="CLI",
                url="",
                request_body=digest_hex,
                error="binary_not_found:openssl",
            )
        if not is_usable_public_pem(public_key_pem):
            return PhysicalCallResult(
                backend="openssl",
                operation="dgst_verify",
                method="CLI",
                url="",
                request_body=digest_hex,
                error="unusable_public_key_pem",
            )
        digest_bytes = bytes.fromhex(digest_hex)
        with tempfile.TemporaryDirectory(prefix="elmos-sigstore-verify-") as tmp:
            pub_path = os.path.join(tmp, "pub.pem")
            sig_path = os.path.join(tmp, "sig.bin")
            blob_path = os.path.join(tmp, "blob.bin")
            with open(pub_path, "w", encoding="utf-8") as handle:
                handle.write(public_key_pem)
            with open(sig_path, "wb") as handle:
                handle.write(_b64d(signature_base64))
            with open(blob_path, "wb") as handle:
                handle.write(digest_bytes)
            return run_cli(
                backend="openssl",
                operation="dgst_verify",
                argv=[
                    openssl,
                    "dgst",
                    "-sha256",
                    "-verify",
                    pub_path,
                    "-signature",
                    sig_path,
                    blob_path,
                ],
                timeout=self.timeout,
            )

    def build_dsse_envelope(
        self,
        *,
        subject_name: str,
        artifact_digest: str,
        builder_id: str,
        signature_base64: str,
        key_id: str,
    ) -> Dict[str, Any]:
        statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [{"name": subject_name, "digest": {"sha256": _strip_sha256(artifact_digest)}}],
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {
                "buildDefinition": {
                    "buildType": "https://elmos.dev/build/v1",
                    "externalParameters": {"builder_id": builder_id},
                },
                "runDetails": {"builder": {"id": builder_id}},
            },
        }
        payload = _b64e(json_dumps(statement).encode("utf-8"))
        return {
            "payloadType": DSSE_PAYLOAD_TYPE,
            "payload": payload,
            "signatures": [{"keyid": key_id, "sig": signature_base64}],
        }

    def build_rekor_hashedrekord(
        self,
        *,
        artifact_digest: str,
        signature_base64: str,
        public_key_pem: str,
    ) -> Dict[str, Any]:
        return {
            "apiVersion": "0.0.1",
            "kind": REKOR_HASHEDREKORD_KIND,
            "spec": {
                "data": {
                    "hash": {
                        "algorithm": "sha256",
                        "value": _strip_sha256(artifact_digest),
                    }
                },
                "signature": {
                    "content": signature_base64,
                    "publicKey": {"content": _b64e(public_key_pem.encode("utf-8"))},
                },
            },
        }

    def build_cosign_sign_blob_argv(self, blob_path: str, key_path: str, bundle_path: str) -> List[str]:
        binary = which("cosign") or "cosign"
        return [
            binary,
            "sign-blob",
            "--yes",
            "--key",
            key_path,
            "--bundle",
            bundle_path,
            "--rekor-url",
            self.rekor_url or "https://rekor.sigstore.dev",
            blob_path,
        ]

    def build_cosign_verify_blob_argv(self, blob_path: str, bundle_path: str) -> List[str]:
        binary = which("cosign") or "cosign"
        return [
            binary,
            "verify-blob",
            "--bundle",
            bundle_path,
            "--rekor-url",
            self.rekor_url or "https://rekor.sigstore.dev",
            blob_path,
        ]

    def submit_rekor_entry(self, entry: Dict[str, Any]) -> PhysicalCallResult:
        return http_call(
            backend="rekor",
            operation="create_log_entry",
            method="POST",
            url=f"{self.rekor_url}/api/v1/log/entries" if self.rekor_url else "",
            body=entry,
            timeout=self.timeout,
        )

    def attest_artifact(
        self,
        *,
        artifact_digest: str,
        subject_name: str = "elmos-artifact",
        builder_id: str = "elmos-trusted-builder",
        key_id: str = "elmos-release",
        private_key_pem: str = "",
        public_key_pem: str = "",
        signature_base64: str = "",
        materialize_keys: bool = True,
    ) -> SigstoreAttestation:
        receipts: List[PhysicalCallResult] = []
        openssl_applied = False

        if materialize_keys and (not private_key_pem or not public_key_pem):
            generated_priv, generated_pub, gen_receipt = self.generate_ephemeral_ecdsa_p256()
            receipts.append(gen_receipt)
            if gen_receipt.applied:
                private_key_pem = generated_priv
                public_key_pem = generated_pub

        digest_hex = _strip_sha256(artifact_digest)
        if private_key_pem:
            signature_base64, sign_receipt = self.sign_digest(digest_hex, private_key_pem)
            receipts.append(sign_receipt)
            openssl_applied = sign_receipt.applied
        elif signature_base64:
            openssl_applied = False

        dsse = self.build_dsse_envelope(
            subject_name=subject_name,
            artifact_digest=artifact_digest,
            builder_id=builder_id,
            signature_base64=signature_base64,
            key_id=key_id,
        )
        rekor_entry = self.build_rekor_hashedrekord(
            artifact_digest=artifact_digest,
            signature_base64=signature_base64,
            public_key_pem=public_key_pem,
        )
        rekor_receipt = self.submit_rekor_entry(rekor_entry)
        receipts.append(rekor_receipt)
        rekor_uuid = ""
        if rekor_receipt.applied and isinstance(rekor_receipt.response_body, dict):
            rekor_uuid = str(
                rekor_receipt.response_body.get("uuid")
                or next(iter(rekor_receipt.response_body.keys()), "")
            )

        cosign_sign_argv = self.build_cosign_sign_blob_argv(
            "/tmp/elmos-artifact.bin",
            "/tmp/elmos-cosign.key",
            "/tmp/elmos-cosign.bundle",
        )
        cosign_verify_argv = self.build_cosign_verify_blob_argv(
            "/tmp/elmos-artifact.bin",
            "/tmp/elmos-cosign.bundle",
        )
        cosign_applied = False
        if which("cosign") and private_key_pem:
            with tempfile.TemporaryDirectory(prefix="elmos-cosign-") as tmp:
                blob_path = os.path.join(tmp, "artifact.bin")
                key_path = os.path.join(tmp, "cosign.key")
                bundle_path = os.path.join(tmp, "cosign.bundle")
                with open(blob_path, "wb") as handle:
                    handle.write(bytes.fromhex(digest_hex))
                with open(key_path, "w", encoding="utf-8") as handle:
                    handle.write(private_key_pem)
                argv = self.build_cosign_sign_blob_argv(blob_path, key_path, bundle_path)
                cosign_receipt = run_cli(
                    backend="cosign",
                    operation="sign-blob",
                    argv=argv,
                    timeout=self.timeout,
                )
                receipts.append(cosign_receipt)
                cosign_applied = cosign_receipt.applied
                cosign_sign_argv = argv

        return SigstoreAttestation(
            artifact_digest=artifact_digest,
            dsse_envelope=dsse,
            rekor_entry=rekor_entry,
            cosign_sign_argv=cosign_sign_argv,
            cosign_verify_argv=cosign_verify_argv,
            signature_base64=signature_base64,
            public_key_pem=public_key_pem,
            rekor_uuid=rekor_uuid,
            openssl_applied=openssl_applied,
            rekor_applied=rekor_receipt.applied,
            cosign_applied=cosign_applied,
            receipts=receipts,
        )


def _strip_sha256(digest: str) -> str:
    value = digest.strip()
    if value.startswith("sha256:"):
        return value.split(":", 1)[1]
    return value
