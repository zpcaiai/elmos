"""Asymmetric, single-use job tokens for the hosted generation Runner.

The control plane signs. The Runner holds only the public key and cannot mint
tokens. A used ``jti`` is rejected forever for that key id. Production refuses
HMAC and any token longer than 15 minutes.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOKEN_TYPE = "ELMOS-JOB"
TOKEN_ALGORITHM = "EdDSA"
TOKEN_ISSUER = "elmos-job-dispatcher"
TOKEN_AUDIENCE = "elmos-runner-agent"
MAX_LIFETIME_SECONDS = 15 * 60
CLOCK_SKEW_SECONDS = 30
IMAGE_DIGEST = r"^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$"
IDENTITY = r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$"
JTI = r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,199}$"
SCOPE_VALUES = frozenset({"generate", "build", "probe", "preview", "archive"})

_IMAGE_RE = re.compile(IMAGE_DIGEST)
_IDENTITY_RE = re.compile(IDENTITY)
_JTI_RE = re.compile(JTI)


class JobTokenError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class JobTokenClaims:
    jti: str
    tenant: str
    actor: str
    job: str
    scope: tuple[str, ...]
    image: str
    cpu_millis: int
    memory_mib: int
    pids: int
    wallclock_seconds: int
    issued_at: int
    expires_at: int

    def as_mapping(self) -> dict[str, Any]:
        return {
            "jti": self.jti,
            "tenant": self.tenant,
            "actor": self.actor,
            "job": self.job,
            "scope": list(self.scope),
            "image": self.image,
            "limits": {
                "cpu_millis": self.cpu_millis,
                "memory_mib": self.memory_mib,
                "pids": self.pids,
                "wallclock_seconds": self.wallclock_seconds,
            },
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": self.issued_at,
            "exp": self.expires_at,
            "v": 1,
        }


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _require_owner_only_file(path: Path, *, minimum: int = 32, public: bool = False) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise JobTokenError("JOB_TOKEN_KEY_UNSAFE")
    info = path.stat()
    if info.st_size < minimum or info.st_size > 16_384:
        raise JobTokenError("JOB_TOKEN_KEY_UNSAFE")
    if public:
        if info.st_mode & 0o022:
            raise JobTokenError("JOB_TOKEN_KEY_UNSAFE")
    elif info.st_mode & 0o077:
        raise JobTokenError("JOB_TOKEN_KEY_UNSAFE")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise JobTokenError("JOB_TOKEN_KEY_UNSAFE")
    return path


def generate_ed25519_keypair(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    private = directory / "job-token.ed25519.private.pem"
    public = directory / "job-token.ed25519.public.pem"
    created = subprocess.run(  # noqa: S603
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0 or not private.is_file():
        raise JobTokenError("JOB_TOKEN_KEYGEN_FAILED")
    os.chmod(private, 0o600)
    exported = subprocess.run(  # noqa: S603
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
        check=False,
        capture_output=True,
        text=True,
    )
    if exported.returncode != 0 or not public.is_file():
        raise JobTokenError("JOB_TOKEN_KEYGEN_FAILED")
    os.chmod(public, 0o644)
    return private, public


def _sign(private_key: Path, message: bytes) -> bytes:
    scratch = private_key.parent / ".job-token-sign-input"
    scratch.write_bytes(message)
    os.chmod(scratch, 0o600)
    signed = subprocess.run(  # noqa: S603
        ["openssl", "pkeyutl", "-sign", "-inkey", str(private_key), "-rawin", "-in", str(scratch)],
        check=False,
        capture_output=True,
    )
    scratch.unlink(missing_ok=True)
    if signed.returncode != 0 or len(signed.stdout) != 64:
        raise JobTokenError("JOB_TOKEN_SIGN_FAILED")
    return signed.stdout


def _verify_with_sigfile(public_key: Path, message: bytes, signature: bytes, scratch: Path) -> bool:
    sig = scratch / "job-token.sig"
    inbound = scratch / "job-token.msg"
    sig.write_bytes(signature)
    inbound.write_bytes(message)
    os.chmod(sig, 0o600)
    os.chmod(inbound, 0o600)
    verified = subprocess.run(  # noqa: S603
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-rawin",
            "-in",
            str(inbound),
            "-sigfile",
            str(sig),
        ],
        check=False,
        capture_output=True,
    )
    sig.unlink(missing_ok=True)
    inbound.unlink(missing_ok=True)
    return verified.returncode == 0 and b"Signature Verified Successfully" in verified.stdout


def issue_job_token(
    claims: JobTokenClaims,
    *,
    private_key: Path,
    key_id: str,
    now: int | None = None,
) -> str:
    observed = int(now if now is not None else time.time())
    if claims.expires_at - claims.issued_at > MAX_LIFETIME_SECONDS:
        raise JobTokenError("JOB_TOKEN_LIFETIME_EXCEEDS_15M")
    if claims.expires_at <= observed:
        raise JobTokenError("JOB_TOKEN_ALREADY_EXPIRED")
    if not _JTI_RE.match(claims.jti) or not _IDENTITY_RE.match(claims.tenant):
        raise JobTokenError("JOB_TOKEN_IDENTITY_INVALID")
    if not _IDENTITY_RE.match(claims.actor) or not _IDENTITY_RE.match(claims.job):
        raise JobTokenError("JOB_TOKEN_IDENTITY_INVALID")
    if not claims.scope or set(claims.scope) - SCOPE_VALUES:
        raise JobTokenError("JOB_TOKEN_SCOPE_INVALID")
    if not _IMAGE_RE.match(claims.image):
        raise JobTokenError("JOB_TOKEN_IMAGE_NOT_DIGEST_PINNED")
    if claims.cpu_millis < 100 or claims.memory_mib < 64 or claims.pids < 8:
        raise JobTokenError("JOB_TOKEN_LIMITS_INVALID")
    header = {"alg": TOKEN_ALGORITHM, "typ": TOKEN_TYPE, "kid": key_id}
    encoded_header = _b64(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64(
        json.dumps(claims.as_mapping(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    message = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = _sign(_require_owner_only_file(private_key, minimum=16), message)
    return f"{encoded_header}.{encoded_payload}.{_b64(signature)}"


class ReplayCache:
    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise JobTokenError("JOB_TOKEN_REPLAY_STORE_INVALID")
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        info = root.stat()
        if info.st_mode & 0o077 or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
            raise JobTokenError("JOB_TOKEN_REPLAY_STORE_INVALID")
        self.root = root

    def consume(self, jti: str, expires_at: int) -> None:
        if not _JTI_RE.match(jti):
            raise JobTokenError("JOB_TOKEN_IDENTITY_INVALID")
        digest_name = f"{expires_at:010d}-{jti}"
        path = self.root / digest_name
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError as error:
            raise JobTokenError("JOB_TOKEN_REPLAYED") from error
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(jti + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._expire(int(time.time()))

    def _expire(self, now: int) -> None:
        for entry in self.root.iterdir():
            match = re.match(r"^(\d{10})-", entry.name)
            if match and int(match.group(1)) <= now:
                entry.unlink(missing_ok=True)


def verify_job_token(
    token: str,
    *,
    public_key: Path,
    key_id: str,
    replay: ReplayCache,
    required_scope: str,
    expected_tenant: str | None = None,
    expected_job: str | None = None,
    now: int | None = None,
    scratch: Path | None = None,
) -> JobTokenClaims:
    if os.environ.get("ELMOS_ENVIRONMENT") == "production" and os.environ.get(
        "ELMOS_LOCAL_RUNNER_AUTH_TOKEN"
    ):
        raise JobTokenError("LOCAL_RUNNER_TOKEN_FORBIDDEN_IN_PRODUCTION")
    parts = token.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise JobTokenError("JOB_TOKEN_MALFORMED")
    try:
        header = json.loads(_unb64(parts[0]))
        payload = json.loads(_unb64(parts[1]))
        signature = _unb64(parts[2])
    except (ValueError, json.JSONDecodeError) as error:
        raise JobTokenError("JOB_TOKEN_MALFORMED") from error
    if (
        not isinstance(header, dict)
        or header.get("alg") != TOKEN_ALGORITHM
        or header.get("typ") != TOKEN_TYPE
        or header.get("kid") != key_id
    ):
        raise JobTokenError("JOB_TOKEN_HEADER_INVALID")
    if not isinstance(payload, dict) or payload.get("iss") != TOKEN_ISSUER:
        raise JobTokenError("JOB_TOKEN_CLAIMS_INVALID")
    if payload.get("aud") != TOKEN_AUDIENCE or payload.get("v") != 1:
        raise JobTokenError("JOB_TOKEN_CLAIMS_INVALID")
    observed = int(now if now is not None else time.time())
    try:
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
        limits = payload["limits"]
        if not isinstance(limits, dict):
            raise TypeError("limits")
        claims = JobTokenClaims(
            jti=str(payload["jti"]),
            tenant=str(payload["tenant"]),
            actor=str(payload["actor"]),
            job=str(payload["job"]),
            scope=tuple(str(item) for item in payload["scope"]),
            image=str(payload["image"]),
            cpu_millis=int(limits["cpu_millis"]),
            memory_mib=int(limits["memory_mib"]),
            pids=int(limits["pids"]),
            wallclock_seconds=int(limits["wallclock_seconds"]),
            issued_at=issued_at,
            expires_at=expires_at,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise JobTokenError("JOB_TOKEN_CLAIMS_INVALID") from error
    if expires_at <= observed - CLOCK_SKEW_SECONDS:
        raise JobTokenError("JOB_TOKEN_EXPIRED")
    if issued_at > observed + CLOCK_SKEW_SECONDS:
        raise JobTokenError("JOB_TOKEN_NOT_YET_VALID")
    if expires_at - issued_at > MAX_LIFETIME_SECONDS:
        raise JobTokenError("JOB_TOKEN_LIFETIME_EXCEEDS_15M")
    if required_scope not in claims.scope:
        raise JobTokenError("JOB_TOKEN_SCOPE_DENIED")
    if expected_tenant is not None and expected_tenant != claims.tenant:
        raise JobTokenError("JOB_TOKEN_TENANT_MISMATCH")
    if expected_job is not None and expected_job != claims.job:
        raise JobTokenError("JOB_TOKEN_JOB_MISMATCH")
    if not _IMAGE_RE.match(claims.image):
        raise JobTokenError("JOB_TOKEN_IMAGE_NOT_DIGEST_PINNED")
    workspace = scratch or Path(os.environ.get("TMPDIR", "/tmp"))
    if not _verify_with_sigfile(
        _require_owner_only_file(public_key, minimum=16, public=True),
        f"{parts[0]}.{parts[1]}".encode("ascii"),
        signature,
        workspace,
    ):
        raise JobTokenError("JOB_TOKEN_SIGNATURE_INVALID")
    replay.consume(claims.jti, claims.expires_at)
    return claims
