#!/usr/bin/env python3
"""TLS service for independently evaluating immutable external-gate reports."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import ssl
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from external_verifier_crypto import (
    VerifierCryptoError,
    verify_receipt_signature,
)
from independent_verifier import issue_receipt


class VerifierServiceError(ValueError):
    pass


def read_secret(path: Path, *, owner_only: bool = False) -> str:
    if path.is_symlink() or not path.is_file():
        raise VerifierServiceError("secret must be a regular non-symlink file")
    mode = path.stat().st_mode & 0o777
    forbidden = 0o077 if owner_only else 0o027
    if mode & forbidden:
        raise VerifierServiceError("secret file permissions are too broad")
    size = path.stat().st_size
    if size < 1 or size > 16_384:
        raise VerifierServiceError("secret file size is invalid")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise VerifierServiceError("secret must contain exactly one non-empty line")
    return value


def validate_key_pair(private_key: Path, public_key: Path) -> None:
    for path in (private_key, public_key):
        if path.is_symlink() or not path.is_file():
            raise VerifierServiceError("signing key must be a regular non-symlink file")
    if private_key.stat().st_mode & 0o077:
        raise VerifierServiceError("signing private key must be owner-only")
    private = subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout"],
        capture_output=True,
        check=False,
    )
    public = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(public_key), "-pubout"],
        capture_output=True,
        check=False,
    )
    if private.returncode != 0 or public.returncode != 0 or private.stdout != public.stdout:
        raise VerifierServiceError("signing public/private key pair does not match")


class VerificationService:
    def __init__(
        self,
        *,
        bearer_token: str,
        producer_actor: str,
        verifier_actor: str,
        private_key: Path,
        public_key: Path,
        receipt_store: Path,
        maximum_report_bytes: int,
    ) -> None:
        if len(bearer_token) < 32 or len(bearer_token) > 4096:
            raise VerifierServiceError("verifier bearer token length is invalid")
        if not producer_actor or not verifier_actor or producer_actor == verifier_actor:
            raise VerifierServiceError("producer and verifier actors must be distinct")
        if maximum_report_bytes < 1024 or maximum_report_bytes > 64 * 1024 * 1024:
            raise VerifierServiceError("maximum report size is invalid")
        validate_key_pair(private_key, public_key)
        if receipt_store.is_symlink():
            raise VerifierServiceError("receipt store may not be a symlink")
        receipt_store.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not receipt_store.is_dir() or receipt_store.stat().st_mode & 0o022:
            raise VerifierServiceError("receipt store must not be group/world writable")
        self._token = bearer_token
        self.producer_actor = producer_actor
        self.verifier_actor = verifier_actor
        self.private_key = private_key
        self.public_key = public_key
        self.receipt_store = receipt_store
        self.maximum_report_bytes = maximum_report_bytes
        self._lock = threading.Lock()

    def authenticate(self, authorization: str | None) -> None:
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if not authorization or not authorization.startswith("Bearer ") \
                or not hmac.compare_digest(self._token, supplied):
            raise VerifierServiceError("verifier authorization failed")

    def verify(
        self,
        report_bytes: bytes,
        claimed_sha256: str,
        producer_actor: str,
    ) -> dict[str, Any]:
        if len(report_bytes) < 2 or len(report_bytes) > self.maximum_report_bytes:
            raise VerifierServiceError("external report size is invalid")
        actual = hashlib.sha256(report_bytes).hexdigest()
        if not hmac.compare_digest(actual, claimed_sha256):
            raise VerifierServiceError("external report digest header mismatch")
        if producer_actor != self.producer_actor:
            raise VerifierServiceError("producer actor is not allowlisted")
        receipt_path = self.receipt_store / f"{actual}.json"
        with self._lock:
            if receipt_path.exists():
                if receipt_path.is_symlink() or not receipt_path.is_file():
                    raise VerifierServiceError("stored verifier receipt is invalid")
                try:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise VerifierServiceError("stored verifier receipt cannot be read") from exc
                if not isinstance(receipt, dict) \
                        or receipt.get("report_sha256") != actual \
                        or receipt.get("producer_actor") != self.producer_actor \
                        or receipt.get("verifier_actor") != self.verifier_actor:
                    raise VerifierServiceError("stored verifier receipt binding is invalid")
                verify_receipt_signature(
                    receipt, self.public_key, receipt["signing_key_sha256"])
                return receipt
            receipt = issue_receipt(
                report_bytes,
                self.producer_actor,
                self.verifier_actor,
                self.private_key,
                self.public_key,
            )
            encoded = (
                json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            temporary = self.receipt_store / f".{actual}.{os.getpid()}.tmp"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, receipt_path)
                directory = os.open(self.receipt_store, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if temporary.exists():
                    temporary.unlink()
            return receipt


class VerifierRequestHandler(BaseHTTPRequestHandler):
    server_version = "ELMOSIndependentVerifier/1"
    protocol_version = "HTTP/1.1"

    @property
    def service(self) -> VerificationService:
        return self.server.verification_service  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self._json(HTTPStatus.NOT_FOUND, {"status": "NOT_FOUND"})
            return
        self._json(HTTPStatus.OK, {"status": "READY"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path != "/v1/verify":
                self._json(HTTPStatus.NOT_FOUND, {"status": "NOT_FOUND"})
                return
            self.service.authenticate(self.headers.get("Authorization"))
            if self.headers.get_content_type() != "application/json":
                raise VerifierServiceError("content type must be application/json")
            value = self.headers.get("Content-Length")
            if value is None or not value.isdigit():
                raise VerifierServiceError("Content-Length is required")
            length = int(value)
            if length < 2 or length > self.service.maximum_report_bytes:
                raise VerifierServiceError("external report size is invalid")
            report = self.rfile.read(length)
            if len(report) != length:
                raise VerifierServiceError("external report body is truncated")
            receipt = self.service.verify(
                report,
                self.headers.get("X-ELMOS-Report-SHA256", ""),
                self.headers.get("X-ELMOS-Producer-Actor", ""),
            )
            self._json(HTTPStatus.OK, receipt)
        except (VerifierServiceError, VerifierCryptoError):
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"status": "REJECTED"})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "UNKNOWN"})

    def _json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
        body = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Never write bearer credentials or report bytes. Method/path/status are
        # available from the reverse proxy's independently managed access log.
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8443)
    parser.add_argument("--tls-certificate", type=Path, required=True)
    parser.add_argument("--tls-private-key", type=Path, required=True)
    parser.add_argument("--bearer-token-file", type=Path, required=True)
    parser.add_argument("--signing-private-key", type=Path, required=True)
    parser.add_argument("--signing-public-key", type=Path, required=True)
    parser.add_argument("--producer-actor", required=True)
    parser.add_argument("--verifier-actor", required=True)
    parser.add_argument("--receipt-store", type=Path, required=True)
    parser.add_argument("--maximum-report-bytes", type=int, default=16 * 1024 * 1024)
    args = parser.parse_args()
    try:
        if not 1 <= args.listen_port <= 65535:
            raise VerifierServiceError("listen port is invalid")
        tls_token = read_secret(args.bearer_token_file)
        if args.tls_private_key.is_symlink() or not args.tls_private_key.is_file() \
                or args.tls_private_key.stat().st_mode & 0o077:
            raise VerifierServiceError("TLS private key must be owner-only and non-symlink")
        if args.tls_certificate.is_symlink() or not args.tls_certificate.is_file():
            raise VerifierServiceError("TLS certificate must be a regular non-symlink file")
        service = VerificationService(
            bearer_token=tls_token,
            producer_actor=args.producer_actor,
            verifier_actor=args.verifier_actor,
            private_key=args.signing_private_key,
            public_key=args.signing_public_key,
            receipt_store=args.receipt_store,
            maximum_report_bytes=args.maximum_report_bytes,
        )
        server = ThreadingHTTPServer(
            (args.listen_host, args.listen_port), VerifierRequestHandler)
        server.verification_service = service  # type: ignore[attr-defined]
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        context.load_cert_chain(args.tls_certificate, args.tls_private_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.serve_forever(poll_interval=0.5)
        return 0
    except (OSError, VerifierServiceError, VerifierCryptoError) as exc:
        print(f"independent verifier service: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
