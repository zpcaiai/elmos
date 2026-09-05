#!/usr/bin/env python3
"""Issue one short-lived, request-bound local Runner service credential."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time


ISSUER = "elmos-local-runner-controller"
AUDIENCE = "elmos-generation-runner"
TOKEN_TYPE = "ELMOS-RUNNER-SVC"
MAX_TTL_SECONDS = 300
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
PATH_RE = re.compile(r"^/api/generation(?:/[-A-Za-z0-9._~%!$&'()*+,;=:@/]*)?$")
PERMISSIONS = {"generation:execute", "repository:push"}
METHODS = {"GET", "POST", "DELETE"}


class CredentialIssueError(RuntimeError):
    pass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _load_key(raw_path: str) -> bytes:
    path = Path(raw_path)
    if not path.is_absolute() or path.is_symlink():
        raise CredentialIssueError("SIGNING_KEY_PATH_INVALID")
    try:
        resolved = path.resolve(strict=True)
        info = path.stat()
    except OSError as error:
        raise CredentialIssueError("SIGNING_KEY_PATH_INVALID") from error
    if (
        resolved != path
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
        or not 32 <= info.st_size <= 4096
    ):
        raise CredentialIssueError("SIGNING_KEY_FILE_UNSAFE")
    value = path.read_bytes().strip()
    if not 32 <= len(value) <= 4096:
        raise CredentialIssueError("SIGNING_KEY_VALUE_INVALID")
    return value


def issue(args: argparse.Namespace, *, now: int | None = None) -> str:
    if not IDENTITY_RE.fullmatch(args.tenant) or not IDENTITY_RE.fullmatch(args.actor):
        raise CredentialIssueError("IDENTITY_INVALID")
    if args.permission not in PERMISSIONS:
        raise CredentialIssueError("PERMISSION_INVALID")
    method = args.method.upper()
    if method not in METHODS or not PATH_RE.fullmatch(args.path) or "?" in args.path or "#" in args.path:
        raise CredentialIssueError("REQUEST_SCOPE_INVALID")
    if not KEY_ID_RE.fullmatch(args.key_id):
        raise CredentialIssueError("KEY_ID_INVALID")
    if not 1 <= args.ttl_seconds <= MAX_TTL_SECONDS:
        raise CredentialIssueError("TTL_INVALID")
    key = _load_key(args.key_file)
    issued_at = int(time.time() if now is None else now)
    header = {"alg": "HS256", "typ": TOKEN_TYPE, "kid": args.key_id}
    claims = {
        "v": 1,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "tenant_id": args.tenant,
        "actor_id": args.actor,
        "permission": args.permission,
        "method": method,
        "path": args.path,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + args.ttl_seconds,
        "jti": "request-" + secrets.token_urlsafe(24),
    }
    encoded_header = _b64(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_claims = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = _b64(hmac.new(key, signing_input, hashlib.sha256).digest())
    return f"{encoded_header}.{encoded_claims}.{signature}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--permission", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        print(issue(args))
        return 0
    except (CredentialIssueError, OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error).split(":", 1)[0]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
