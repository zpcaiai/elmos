"""Content-bound webhook signing and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .errors import AuthorizationError, ValidationError


class WebhookReplayStore(Protocol):
    """Atomic replay claim shared by every verifier process for one endpoint."""

    def claim(
        self,
        scope_id: str,
        delivery_id: str,
        *,
        now: int,
        expires_at: int,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class SqliteWebhookReplayStore:
    """Transactional cross-process replay claims storing only hashed identities."""

    database: Path
    maximum_claims: int = 100_000

    def __post_init__(self) -> None:
        database = Path(self.database).expanduser()
        if not database.is_absolute() or database == Path(database.anchor):
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_INVALID")
        parent = database.parent
        existed = parent.exists() or parent.is_symlink()
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_INVALID")
        if not existed:
            parent.chmod(0o700)
        parent_metadata = parent.stat()
        wrong_parent_owner = hasattr(os, "geteuid") and parent_metadata.st_uid != os.geteuid()
        if wrong_parent_owner or parent_metadata.st_mode & 0o077:
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_PERMISSIONS_INVALID")
        if database.is_symlink() or database.exists() and not database.is_file():
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_INVALID")
        if database.exists():
            existing_metadata = database.stat()
            wrong_database_owner = (
                hasattr(os, "geteuid") and existing_metadata.st_uid != os.geteuid()
            )
            if wrong_database_owner or existing_metadata.st_mode & 0o077:
                raise ValidationError("WEBHOOK_REPLAY_DATABASE_PERMISSIONS_INVALID")
        if (
            not isinstance(self.maximum_claims, int)
            or isinstance(self.maximum_claims, bool)
            or not 1 <= self.maximum_claims <= 1_000_000
        ):
            raise ValidationError("WEBHOOK_REPLAY_CAPACITY_INVALID")
        object.__setattr__(self, "database", database)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_replay_claims (
                    claim_id TEXT PRIMARY KEY CHECK (length(claim_id)=64),
                    expires_at INTEGER NOT NULL CHECK (expires_at >= 0)
                ) WITHOUT ROWID
                """
            )
        finally:
            connection.close()
        try:
            database.chmod(0o600)
            metadata = database.stat()
        except OSError as error:
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_UNAVAILABLE") from error
        wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
        if database.is_symlink() or wrong_owner or metadata.st_mode & 0o077:
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_PERMISSIONS_INVALID")

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.database, timeout=5, isolation_level=None)
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            return connection
        except sqlite3.Error as error:
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_UNAVAILABLE") from error

    def claim(
        self,
        scope_id: str,
        delivery_id: str,
        *,
        now: int,
        expires_at: int,
    ) -> bool:
        if (
            not _printable_identifier(scope_id, maximum_bytes=200)
            or not _printable_identifier(delivery_id, maximum_bytes=128)
            or not isinstance(now, int)
            or isinstance(now, bool)
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or now < 0
            or expires_at <= now
            or expires_at - now > 7201
        ):
            raise ValidationError("WEBHOOK_REPLAY_CLAIM_INVALID")
        claim_id = hashlib.sha256(
            scope_id.encode("ascii") + b"\0" + delivery_id.encode("ascii")
        ).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM webhook_replay_claims WHERE expires_at <= ?", (now,))
            existing = connection.execute(
                "SELECT expires_at FROM webhook_replay_claims WHERE claim_id=?",
                (claim_id,),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                return False
            count = int(connection.execute("SELECT count(*) FROM webhook_replay_claims").fetchone()[0])
            if count >= self.maximum_claims:
                connection.execute("ROLLBACK")
                raise ValidationError("WEBHOOK_REPLAY_STORE_CAPACITY_EXCEEDED")
            connection.execute(
                "INSERT INTO webhook_replay_claims(claim_id,expires_at) VALUES (?,?)",
                (claim_id, expires_at),
            )
            connection.execute("COMMIT")
            return True
        except ValidationError:
            raise
        except sqlite3.Error as error:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise ValidationError("WEBHOOK_REPLAY_DATABASE_UNAVAILABLE") from error
        finally:
            connection.close()


def _printable_identifier(value: object, *, maximum_bytes: int) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and 1 <= len(value.encode("ascii")) <= maximum_bytes
        and all(33 <= ord(character) <= 126 for character in value)
    )


def _signature_input(
    scope_id: str,
    key_id: str,
    delivery_id: str,
    timestamp: int,
    body: bytes,
) -> bytes:
    return b"\0".join(
        (
            b"elmos-webhook-v2",
            scope_id.encode("ascii"),
            key_id.encode("ascii"),
            delivery_id.encode("ascii"),
            str(timestamp).encode("ascii"),
            body,
        )
    )


@dataclass(slots=True)
class WebhookSigner:
    secret: bytes = field(repr=False)
    clock: Callable[[], float] = time.time
    maximum_body_bytes: int = 4 * 1024 * 1024
    scope_id: str = "default"
    key_id: str = "primary"

    def __post_init__(self) -> None:
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise ValidationError("WEBHOOK_SECRET_TOO_SHORT")
        if (
            type(self.maximum_body_bytes) is not int
            or not 1 <= self.maximum_body_bytes <= 64 * 1024 * 1024
        ):
            raise ValidationError("WEBHOOK_BODY_LIMIT_INVALID")
        if not _printable_identifier(self.scope_id, maximum_bytes=200):
            raise ValidationError("WEBHOOK_SCOPE_INVALID")
        if not _printable_identifier(self.key_id, maximum_bytes=128):
            raise ValidationError("WEBHOOK_KEY_ID_INVALID")

    @property
    def execution_identity_digest(self) -> str:
        """Bind runtime receipts to the public signing-key epoch, never the secret.

        Operators must rotate ``key_id`` whenever the underlying secret rotates;
        keeping a key ID while changing key material is an invalid deployment.
        """

        return hashlib.sha256(
            b"\0".join(
                (
                    b"elmos-webhook-signer-identity-v1",
                    self.scope_id.encode("ascii"),
                    self.key_id.encode("ascii"),
                    str(self.maximum_body_bytes).encode("ascii"),
                )
            )
        ).hexdigest()

    def sign(self, delivery_id: str, body: bytes, *, timestamp: int | None = None) -> dict[str, str]:
        if not _printable_identifier(delivery_id, maximum_bytes=128):
            raise ValidationError("WEBHOOK_DELIVERY_ID_INVALID")
        try:
            stamp = int(self.clock()) if timestamp is None else timestamp
        except (OverflowError, TypeError, ValueError) as error:
            raise ValidationError("WEBHOOK_TIMESTAMP_INVALID") from error
        if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp < 0:
            raise ValidationError("WEBHOOK_TIMESTAMP_INVALID")
        if not isinstance(body, bytes) or len(body) > self.maximum_body_bytes:
            raise ValidationError("WEBHOOK_BODY_INVALID")
        signature = hmac.new(
            self.secret,
            _signature_input(self.scope_id, self.key_id, delivery_id, stamp, body),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-ELMOS-Delivery-Id": delivery_id,
            "X-ELMOS-Key-Id": self.key_id,
            "X-ELMOS-Timestamp": str(stamp),
            "X-ELMOS-Signature": f"v2={signature}",
        }


@dataclass(slots=True)
class WebhookVerifier:
    secret: bytes = field(repr=False)
    tolerance_seconds: int = 300
    clock: Callable[[], float] = time.time
    maximum_body_bytes: int = 4 * 1024 * 1024
    scope_id: str = "default"
    key_id: str = "primary"
    replay_store: WebhookReplayStore | None = None
    allow_process_local_replay: bool = False
    maximum_process_local_claims: int = 10_000
    _seen: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise ValidationError("WEBHOOK_SECRET_TOO_SHORT")
        if (
            type(self.tolerance_seconds) is not int
            or not 1 <= self.tolerance_seconds <= 3600
        ):
            raise ValidationError("WEBHOOK_TOLERANCE_INVALID")
        if (
            type(self.maximum_body_bytes) is not int
            or not 1 <= self.maximum_body_bytes <= 64 * 1024 * 1024
        ):
            raise ValidationError("WEBHOOK_BODY_LIMIT_INVALID")
        if not _printable_identifier(self.scope_id, maximum_bytes=200):
            raise ValidationError("WEBHOOK_SCOPE_INVALID")
        if not _printable_identifier(self.key_id, maximum_bytes=128):
            raise ValidationError("WEBHOOK_KEY_ID_INVALID")
        if self.replay_store is None and not self.allow_process_local_replay:
            raise ValidationError("WEBHOOK_DURABLE_REPLAY_STORE_REQUIRED")
        if (
            not isinstance(self.maximum_process_local_claims, int)
            or isinstance(self.maximum_process_local_claims, bool)
            or not 1 <= self.maximum_process_local_claims <= 100_000
        ):
            raise ValidationError("WEBHOOK_REPLAY_CAPACITY_INVALID")

    def verify(self, headers: dict[str, str], body: bytes) -> str:
        normalized: dict[str, str] = {}
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise AuthorizationError("WEBHOOK_SIGNATURE_HEADERS_INVALID")
            normalized_key = key.lower()
            if normalized_key in normalized:
                raise AuthorizationError("WEBHOOK_SIGNATURE_HEADERS_INVALID")
            normalized[normalized_key] = value
        delivery_id = normalized.get("x-elmos-delivery-id", "")
        supplied_key_id = normalized.get("x-elmos-key-id", "")
        raw_stamp = normalized.get("x-elmos-timestamp", "")
        supplied = normalized.get("x-elmos-signature", "")
        if (
            not _printable_identifier(delivery_id, maximum_bytes=128)
            or not _printable_identifier(supplied_key_id, maximum_bytes=128)
            or not hmac.compare_digest(supplied_key_id, self.key_id)
            or not raw_stamp.isdigit()
            or len(raw_stamp) > 20
            or len(supplied) != 67
            or not supplied.startswith("v2=")
            or any(character not in "0123456789abcdef" for character in supplied[3:])
            or not isinstance(body, bytes)
            or len(body) > self.maximum_body_bytes
        ):
            raise AuthorizationError("WEBHOOK_SIGNATURE_HEADERS_INVALID")
        stamp = int(raw_stamp)
        try:
            now = int(self.clock())
        except (OverflowError, TypeError, ValueError) as error:
            raise ValidationError("WEBHOOK_CLOCK_INVALID") from error
        if now < 0:
            raise ValidationError("WEBHOOK_CLOCK_INVALID")
        if abs(now - stamp) > self.tolerance_seconds:
            raise AuthorizationError("WEBHOOK_SIGNATURE_EXPIRED")
        expected = hmac.new(
            self.secret,
            _signature_input(self.scope_id, self.key_id, delivery_id, stamp, body),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied.removeprefix("v2="), expected):
            raise AuthorizationError("WEBHOOK_SIGNATURE_INVALID")
        if self.replay_store is not None:
            if not self.replay_store.claim(
                self.scope_id,
                delivery_id,
                now=now,
                expires_at=stamp + self.tolerance_seconds + 1,
            ):
                raise AuthorizationError("WEBHOOK_REPLAY_BLOCKED")
        else:
            with self._lock:
                self._seen = {
                    identifier: expires_at
                    for identifier, expires_at in self._seen.items()
                    if expires_at > now
                }
                scoped_delivery = f"{self.scope_id}\0{delivery_id}"
                if scoped_delivery in self._seen:
                    raise AuthorizationError("WEBHOOK_REPLAY_BLOCKED")
                if len(self._seen) >= self.maximum_process_local_claims:
                    raise AuthorizationError("WEBHOOK_REPLAY_CAPACITY_EXCEEDED")
                self._seen[scoped_delivery] = stamp + self.tolerance_seconds + 1
        return delivery_id
