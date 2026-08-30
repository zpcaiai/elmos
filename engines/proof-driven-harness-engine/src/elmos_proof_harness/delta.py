"""Repository-owned runtime for the v3.1 harness-runtime-assurance delta.

The delta is deliberately implemented as a small, dependency-free control
plane.  It does not call a provider, execute a plugin, or turn an untrusted
payload into authority.  Every object below is a typed, immutable (or
monotonically stateful) boundary with explicit identity, epoch and evidence
semantics.  The source ZIP is only a contract/data source; this module is the
implementation used by the installed Skill wrappers.

The public classes retain the compact names used by the upstream contract so
existing integrations can migrate without importing the untrusted reference
implementation.  Newer callers should prefer the ``*Manager``, ``*Broker``
and ``*Store`` names, which expose the lifecycle checks explicitly.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import CancelledError as FuturesCancelledError
import dataclasses
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hashlib
import hmac
import os
from pathlib import Path
from pathlib import PurePosixPath
import stat
import threading
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
import unicodedata

from .canonical import canonical_json_bytes, digest_bytes, digest_object, freeze_json
from .assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeRegistry,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from .contracts import SecurityContext
from .delta_storage import RuntimeAssuranceScopeSnapshot
from .errors import IntegrityError as AssurancePolicyIntegrityError
from .errors import ValidationError as AssurancePolicyValidationError


DELTA_VERSION = "3.1.0"
DELTA_API_VERSION = "elmos.ai/v3delta1"
MAX_COLLECTION_ITEMS = 1024
MAX_INVOCATION_BYTES = 1_048_576
MAX_TRUSTED_SKILL_BYTES = 32 * 1024 * 1024
MAX_CAPABILITY_LEASE_DURATION = timedelta(minutes=15)


class ContractError(RuntimeError):
    """A fail-closed contract or lifecycle violation."""


class UnsupportedContractError(ContractError):
    """The requested exact provider/transport mapping is not supported."""


class ReviewRequiredError(ContractError):
    """The operation cannot continue without an independently governed review."""


class MappingResult(StrEnum):
    EXACT = "EXACT"
    LOSSY = "LOSSY"
    UNSUPPORTED = "UNSUPPORTED"


class ResultStatus(StrEnum):
    COMMITTED = "COMMITTED"
    DENIED = "DENIED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class CommitState(StrEnum):
    RAW_CAPTURED = "RAW_CAPTURED"
    INTERCEPTING = "INTERCEPTING"
    COMMITTED = "COMMITTED"
    PUBLISHED = "PUBLISHED"
    ABORTED = "ABORTED"


class ToolFailureKind(StrEnum):
    INTERCEPTOR_REJECTED = "INTERCEPTOR_REJECTED"
    INTERCEPTOR_ERROR = "INTERCEPTOR_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AUTHORITY_REVOKED = "AUTHORITY_REVOKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} is required")
    if len(value) > 1024:
        raise ContractError(f"{field_name} is too long")
    if value != value.strip() or unicodedata.normalize("NFC", value) != value:
        raise ContractError(f"{field_name} must use canonical text")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ContractError(f"{field_name} contains control characters")
    return value


def _nonnegative(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field_name} must be a non-negative integer")
    return int(value)


def _positive(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field_name} must be a positive integer")
    return int(value)


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{field_name} must be boolean")
    return value


def _strings(
    value: Any, field_name: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ContractError(f"{field_name} must be an array of strings")
    if len(value) > MAX_COLLECTION_ITEMS:
        raise ContractError(f"{field_name} has too many items")
    result = tuple(_text(item, field_name) for item in value)
    if not allow_empty and not result:
        raise ContractError(f"{field_name} must not be empty")
    if len(set(result)) != len(result):
        raise ContractError(f"{field_name} contains duplicates")
    return result


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ContractError(f"{field_name} must be an object with string keys")
    if len(value) > MAX_COLLECTION_ITEMS:
        raise ContractError(f"{field_name} has too many properties")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _parse_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError as exc:
        raise ContractError(f"{field_name} must be an RFC 3339 timestamp") from exc
    return _aware(parsed, field_name)


def _decimal_budget(value: Any, field_name: str = "cost_budget") -> str:
    candidate = _text(value, field_name)
    if len(candidate) > 128:
        raise ContractError(f"{field_name} is too long")
    integer, separator, fraction = candidate.partition(".")
    if (
        not integer.isdigit()
        or (len(integer) > 1 and integer.startswith("0"))
        or (separator and (not fraction or not fraction.isdigit()))
    ):
        raise ContractError(f"{field_name} must be canonical non-exponent decimal text")
    try:
        amount = Decimal(candidate)
    except InvalidOperation as exc:
        raise ContractError(f"{field_name} is invalid") from exc
    if not amount.is_finite() or amount <= 0:
        raise ContractError(f"{field_name} must be positive and finite")
    return candidate


def _wire_time(value: datetime, field_name: str) -> str:
    aware = _aware(value, field_name)
    assert aware is not None
    return aware.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC) if value is not None else None


def _workspace_scope(value: Any) -> str:
    scope = _text(value, "write_scope")
    if "\\" in scope or scope.startswith("/") or "\x00" in scope:
        raise ContractError("write_scope must be a relative POSIX path")
    path = PurePosixPath(scope)
    if scope in {".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError("write_scope contains unsafe path segments")
    return path.as_posix().rstrip("/")


def _canonical_absolute_posix_path(value: Any, field_name: str) -> str:
    candidate = _text(value, field_name)
    path = PurePosixPath(candidate)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or "\\" in candidate
        or "\x00" in candidate
        or path.as_posix() != candidate
    ):
        raise ContractError(f"{field_name} must be a canonical absolute POSIX path")
    return candidate


def _path_is_within(candidate: str, root: str) -> bool:
    return candidate == root or candidate.startswith(root.rstrip("/") + "/")


def _settings_are_equal_or_narrower(candidate: Any, previous: Any) -> bool:
    if isinstance(candidate, Mapping) and isinstance(previous, Mapping):
        return set(candidate) <= set(previous) and all(
            _settings_are_equal_or_narrower(candidate[key], previous[key])
            for key in candidate
        )
    if isinstance(candidate, (tuple, list)) and isinstance(previous, (tuple, list)):
        previous_items = {canonical_json_bytes(item) for item in previous}
        return all(canonical_json_bytes(item) in previous_items for item in candidate)
    if isinstance(candidate, bool) and isinstance(previous, bool):
        return candidate is previous or (candidate is False and previous is True)
    if (
        isinstance(candidate, (int, float))
        and not isinstance(candidate, bool)
        and isinstance(previous, (int, float))
        and not isinstance(previous, bool)
    ):
        return candidate <= previous
    return bool(candidate == previous)


def _sha256(value: Any, field_name: str) -> str:
    candidate = _text(value, field_name)
    raw = candidate.removeprefix("sha256:")
    if len(raw) != 64 or raw.lower() != raw:
        raise ContractError(f"{field_name} must be a canonical SHA-256 digest")
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise ContractError(f"{field_name} must be a canonical SHA-256 digest") from exc
    return candidate


def _field_text(
    value: Mapping[str, Any], name: str, *, default: str | None = None
) -> str:
    if name not in value:
        if default is None:
            raise ContractError(f"{name} is required")
        return _text(default, name)
    return _text(value[name], name)


def _field_bool(
    value: Mapping[str, Any], name: str, *, default: bool | None = None
) -> bool:
    if name not in value:
        if default is None:
            raise ContractError(f"{name} is required")
        return default
    return _boolean(value[name], name)


def _field_int(
    value: Mapping[str, Any],
    name: str,
    *,
    default: int | None = None,
    positive: bool = False,
) -> int:
    if name not in value:
        if default is None:
            raise ContractError(f"{name} is required")
        candidate = default
    else:
        candidate = value[name]
    return _positive(candidate, name) if positive else _nonnegative(candidate, name)


def _field_mapping(
    value: Mapping[str, Any], name: str, *, default_empty: bool = False
) -> Mapping[str, Any]:
    if name not in value and default_empty:
        return MappingProxyType({})
    return _mapping(value.get(name), name)


def _field_strings(
    value: Mapping[str, Any],
    name: str,
    *,
    default_empty: bool = False,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if name not in value and default_empty:
        return ()
    return _strings(value.get(name), name, allow_empty=allow_empty)


def _optional_field_text(value: Mapping[str, Any], name: str) -> str | None:
    return _optional_text(value.get(name), name)


def _exact_fields(
    value: Mapping[str, Any],
    *,
    allowed: Iterable[str],
    required: Iterable[str] = (),
    label: str,
) -> None:
    permitted = frozenset(allowed)
    required_set = frozenset(required)
    unknown = set(value) - permitted
    missing = required_set - set(value)
    if unknown:
        raise ContractError(f"{label} contains unsupported fields: {sorted(unknown)}")
    if missing:
        raise ContractError(f"{label} is missing required fields: {sorted(missing)}")


def _normalize_sha256(value: Any, field_name: str) -> str:
    candidate = _sha256(value, field_name)
    return candidate if candidate.startswith("sha256:") else "sha256:" + candidate


def _secure_regular_bytes(
    path: Path, trusted_root: Path, *, limit: int
) -> tuple[Path, bytes]:
    """Read a regular file beneath ``trusted_root`` without following links.

    Resolution is used only to calculate the intended relative name.  Every
    component is subsequently reopened with ``O_NOFOLLOW`` and inode checked,
    closing the usual resolve-then-open replacement window.
    """

    root = trusted_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError("skill path escapes trust root or is unavailable") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ContractError("skill path must identify a regular file")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    root_fd = os.open(root, directory_flags)
    descriptor = root_fd
    opened: list[int] = []
    try:
        root_stat = os.stat(root, follow_symlinks=False)
        fd_stat = os.fstat(root_fd)
        if (root_stat.st_dev, root_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
            raise ContractError("trusted root changed while opening")
        for component in relative.parts[:-1]:
            child = os.open(component, directory_flags, dir_fd=descriptor)
            opened.append(child)
            descriptor = child
        file_fd = os.open(
            relative.parts[-1],
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=descriptor,
        )
        opened.append(file_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ContractError("skill path must be a single-link regular file")
        if metadata.st_size < 0 or metadata.st_size > limit:
            raise ContractError("trusted Skill file exceeds the byte limit")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(file_fd, min(remaining, 1024 * 1024))
            if not chunk:
                raise ContractError("trusted Skill file changed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            raise ContractError("trusted Skill file grew while reading")
        after = os.fstat(file_fd)
        if (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ContractError("trusted Skill file changed while reading")
        return root.joinpath(relative), b"".join(chunks)
    except OSError as exc:
        raise ContractError("trusted Skill file could not be opened safely") from exc
    finally:
        for item in reversed(opened):
            os.close(item)
        os.close(root_fd)


def _digest(value: Any, *, domain: str = "delta-contract") -> str:
    """Return a stable hexadecimal digest for upstream-compatible hashes."""

    return hashlib.sha256(
        domain.encode("utf-8") + b"\x00" + canonical_json_bytes(value)
    ).hexdigest()


def digest(value: Any) -> str:
    """Compatibility helper matching the compact source contract."""

    return _digest(value)


def _cas_digest(value: Any, *, domain: str) -> str:
    return digest_object(value, domain=domain)


def _tool_result_commit_key(
    invocation_id: Any,
    call_id: Any,
    attempt: Any,
    execution_epoch: Any,
) -> str:
    """Return the unambiguous identity of one tool-result lifecycle.

    IDs are caller/host-controlled canonical strings and may legally contain
    delimiters.  A canonical, domain-separated tuple digest prevents distinct
    invocation/call pairs from aliasing the same lifecycle key.
    """

    return digest_object(
        {
            "invocationId": _text(invocation_id, "tool result invocation id"),
            "callId": _text(call_id, "tool result call id"),
            "attempt": _nonnegative(attempt, "tool result attempt"),
            "executionEpoch": _nonnegative(
                execution_epoch, "tool result execution epoch"
            ),
        },
        domain="delta-tool-result-commit-key",
    )


def _freeze(value: Any) -> Any:
    """Freeze a JSON-shaped value while retaining mapping/index semantics."""

    try:
        return freeze_json(value)
    except (
        Exception
    ) as exc:  # canonical errors should not leak as implementation details
        raise ContractError(
            f"value is not JSON-shaped: {type(value).__name__}"
        ) from exc


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(item[:1].upper() + item[1:] for item in parts[1:])


def _wire_dataclass(value: Any, *, exclude: Iterable[str] = ()) -> dict[str, Any]:
    excluded = set(exclude)
    output: dict[str, Any] = {}
    for field_info in dataclasses.fields(value):
        key = field_info.name
        item = getattr(value, key)
        if key in excluded:
            continue
        if isinstance(item, MappingProxyType):
            item = _thaw(item)
        elif isinstance(item, tuple):
            item = [_thaw(part) for part in item]
        elif isinstance(item, StrEnum):
            item = item.value
        elif isinstance(item, datetime):
            item = item.astimezone(UTC).isoformat().replace("+00:00", "Z")
        output[_camel(key)] = item
    return output


@dataclass(frozen=True, slots=True)
class CallIdentity:
    invocation_id: str
    call_id: str
    execution_plan_hash: str
    environment_id: str
    authority_snapshot_id: str

    def __post_init__(self) -> None:
        for name in (
            "invocation_id",
            "call_id",
            "environment_id",
            "authority_snapshot_id",
        ):
            _text(getattr(self, name), name)
        _sha256(self.execution_plan_hash, "execution_plan_hash")

    def to_wire(self) -> dict[str, Any]:
        return _wire_dataclass(self)


@dataclass(frozen=True, slots=True)
class ToolResult:
    identity: CallIdentity
    ok: bool
    content: Any

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CallIdentity) or not isinstance(self.ok, bool):
            raise ContractError("tool result identity and ok flag are invalid")
        frozen = _freeze(self.content)
        if len(canonical_json_bytes(frozen)) > MAX_INVOCATION_BYTES:
            raise ContractError("tool result content exceeds the byte limit")

    def snapshot(self) -> "ToolResult":
        return ToolResult(self.identity, self.ok, _freeze(self.content))

    def to_wire(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_wire(),
            "ok": self.ok,
            "content": _thaw(self.content),
        }


@dataclass(frozen=True, slots=True)
class InterceptorDecision:
    interceptor_id: str
    version: str
    before_hash: str
    after_hash: str
    decision_hash: str | None = None

    def __post_init__(self) -> None:
        _text(self.interceptor_id, "interceptor_id")
        _text(self.version, "version")
        _text(self.before_hash, "before_hash")
        _text(self.after_hash, "after_hash")
        if self.decision_hash is not None:
            _text(self.decision_hash, "decision_hash")

    @property
    def effective_decision_hash(self) -> str:
        return self.decision_hash or _cas_digest(
            {
                "interceptorId": self.interceptor_id,
                "version": self.version,
                "before": self.before_hash,
                "after": self.after_hash,
            },
            domain="delta-interceptor-decision",
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "interceptorId": self.interceptor_id,
            "version": self.version,
            "decisionHash": self.effective_decision_hash,
        }


@dataclass(frozen=True, slots=True)
class CommittedToolResult:
    raw: ToolResult
    effective: ToolResult
    decisions: tuple[InterceptorDecision, ...]
    commit_key: str
    commit_state: CommitState = CommitState.COMMITTED
    raw_result_ref: str | None = None
    effective_result_ref: str | None = None
    mutation_provenance_ref: str | None = None
    failure_kind: ToolFailureKind | str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.raw.identity != self.effective.identity:
            raise ContractError("raw and effective result identity diverged")
        _text(self.commit_key, "commit_key")
        if self.commit_state not in CommitState:
            raise ContractError("invalid result commit state")
        aborted = self.commit_state is CommitState.ABORTED
        if aborted is (self.failure_kind is None) or aborted is (
            self.failure_reason is None
        ):
            raise ContractError("tool result failure details do not match commit state")
        if self.failure_kind is not None:
            try:
                kind = ToolFailureKind(self.failure_kind)
            except ValueError as exc:
                raise ContractError("unknown tool result failure kind") from exc
            object.__setattr__(self, "failure_kind", kind)
        if self.failure_reason is not None:
            _text(self.failure_reason, "failure_reason")

    @property
    def call_identity(self) -> CallIdentity:
        return self.raw.identity

    def to_wire(self) -> dict[str, Any]:
        raw_ref = self.raw_result_ref or _cas_digest(
            self.raw.to_wire(), domain="delta-raw-tool-result"
        )
        effective_ref = self.effective_result_ref or _cas_digest(
            self.effective.to_wire(), domain="delta-effective-tool-result"
        )
        output: dict[str, Any] = {
            "callIdentity": self.call_identity.to_wire(),
            "rawResultRef": raw_ref,
            "effectiveResultRef": effective_ref,
            "interceptorChain": [decision.to_wire() for decision in self.decisions],
            "commitState": self.commit_state.value,
        }
        if self.mutation_provenance_ref is not None:
            output["mutationProvenanceRef"] = self.mutation_provenance_ref
        if self.failure_kind is not None:
            output["failureKind"] = ToolFailureKind(self.failure_kind).value
            output["failureReason"] = self.failure_reason
        return output


Interceptor = tuple[str, str, Callable[[ToolResult], ToolResult]]


class ResultLifecycleCoordinator:
    """Capture, intercept, commit and publish tool results exactly once."""

    def __init__(self) -> None:
        self._committed: dict[str, CommittedToolResult] = {}
        self._captured: dict[str, ToolResult] = {}
        self._published: set[str] = set()
        self._lock = threading.RLock()

    @staticmethod
    def _key(identity: CallIdentity, attempt: int, epoch: int) -> str:
        return _tool_result_commit_key(
            identity.invocation_id,
            identity.call_id,
            attempt,
            epoch,
        )

    def capture(
        self, raw: ToolResult, *, attempt: int = 0, epoch: int = 0
    ) -> ToolResult:
        if not isinstance(raw, ToolResult):
            raise ContractError("raw result must be typed ToolResult")
        key = self._key(raw.identity, attempt, epoch)
        snap = raw.snapshot()
        with self._lock:
            existing = self._captured.get(key)
            if existing is not None and existing != snap:
                raise ContractError("conflicting RAW_CAPTURED result")
            self._captured[key] = snap
            return existing or snap

    def commit(
        self,
        raw: ToolResult,
        interceptors: Iterable[Interceptor],
        *,
        attempt: int,
        epoch: int,
    ) -> CommittedToolResult:
        key = self._key(raw.identity, attempt, epoch)
        chain = tuple(interceptors)
        if len(chain) > MAX_COLLECTION_ITEMS:
            raise ContractError("interceptor chain is too large")
        with self._lock:
            captured = self.capture(raw, attempt=attempt, epoch=epoch)
            existing = self._committed.get(key)
            if existing is not None:
                # Idempotent retry is allowed only if the entire immutable
                # result/chain is exactly the same.  Trusted interceptors are
                # not invoked again: even a nominally pure callback must not
                # become a duplicate side effect on replay.
                identities = tuple((item[0], item[1]) for item in chain)
                committed_identities = tuple(
                    (item.interceptor_id, item.version) for item in existing.decisions
                )
                if existing.raw != captured or identities != committed_identities:
                    raise ContractError("conflicting RESULT_COMMIT")
                return existing
            candidate = self._build(captured, chain, key)
            self._committed[key] = candidate
            return candidate

    def _build(
        self, raw: ToolResult, interceptors: Iterable[Interceptor], key: str
    ) -> CommittedToolResult:
        effective = raw.snapshot()
        decisions: list[InterceptorDecision] = []
        seen: set[tuple[str, str]] = set()
        for item in interceptors:
            if not isinstance(item, tuple) or len(item) != 3:
                raise ContractError("interceptor must be (id, version, callable)")
            interceptor_id, version, fn = item
            _text(interceptor_id, "interceptor_id")
            _text(version, "version")
            identity = (interceptor_id, version)
            if identity in seen:
                raise ContractError("interceptor chain contains duplicates")
            seen.add(identity)
            if not callable(fn):
                raise ContractError("interceptor callable is required")
            before = _digest(effective.to_wire(), domain="delta-interceptor-input")

            def failed(
                kind: ToolFailureKind,
                reason: str,
            ) -> CommittedToolResult:
                decisions.append(
                    InterceptorDecision(
                        interceptor_id,
                        version,
                        before,
                        before,
                        _cas_digest(
                            {
                                "interceptorId": interceptor_id,
                                "version": version,
                                "input": before,
                                "failureKind": kind.value,
                                "failureReason": reason,
                            },
                            domain="delta-interceptor-failure",
                        ),
                    )
                )
                return CommittedToolResult(
                    raw.snapshot(),
                    effective.snapshot(),
                    tuple(decisions),
                    key,
                    CommitState.ABORTED,
                    failure_kind=kind,
                    failure_reason=reason,
                )

            try:
                candidate = fn(effective)
            except (asyncio.CancelledError, FuturesCancelledError):
                return failed(
                    ToolFailureKind.CANCELLED,
                    f"interceptor {interceptor_id} was cancelled",
                )
            except TimeoutError:
                return failed(
                    ToolFailureKind.TIMED_OUT,
                    f"interceptor {interceptor_id} timed out",
                )
            except ContractError:
                return failed(
                    ToolFailureKind.INTERCEPTOR_REJECTED,
                    f"interceptor {interceptor_id} rejected the result",
                )
            except Exception:
                return failed(
                    ToolFailureKind.INTERCEPTOR_ERROR,
                    f"interceptor {interceptor_id} failed",
                )
            if (
                not isinstance(candidate, ToolResult)
                or candidate.identity != raw.identity
            ):
                return failed(
                    ToolFailureKind.VALIDATION_FAILED,
                    f"interceptor {interceptor_id} returned an invalid result",
                )
            candidate = candidate.snapshot()
            after = _digest(candidate.to_wire(), domain="delta-interceptor-output")
            decisions.append(
                InterceptorDecision(interceptor_id, version, before, after)
            )
            effective = candidate
        return CommittedToolResult(
            raw.snapshot(), effective.snapshot(), tuple(decisions), key
        )

    def publish(self, commit_key: str) -> CommittedToolResult:
        with self._lock:
            result = self._committed.get(commit_key)
            if result is None:
                raise ContractError("cannot publish unknown result commit")
            if result.commit_state is CommitState.ABORTED:
                raise ContractError("aborted result cannot be published")
            if commit_key in self._published:
                return replace(result, commit_state=CommitState.PUBLISHED)
            self._published.add(commit_key)
            published = replace(result, commit_state=CommitState.PUBLISHED)
            self._committed[commit_key] = published
            return published

    def abort(
        self,
        commit_key: str,
        *,
        failure_kind: ToolFailureKind | str = ToolFailureKind.CANCELLED,
        failure_reason: str = "tool result lifecycle was cancelled",
    ) -> CommittedToolResult:
        with self._lock:
            result = self._committed.get(commit_key)
            if result is None:
                raise ContractError("cannot abort unknown result commit")
            if result.commit_state is CommitState.PUBLISHED:
                raise ContractError("published result cannot be aborted")
            try:
                checked_kind = ToolFailureKind(failure_kind)
            except ValueError as exc:
                raise ContractError("unknown tool result failure kind") from exc
            checked_reason = _text(failure_reason, "failure_reason")
            if result.commit_state is CommitState.ABORTED:
                if (
                    result.failure_kind is checked_kind
                    and result.failure_reason == checked_reason
                ):
                    return result
                raise ContractError("aborted result failure details are immutable")
            aborted = replace(
                result,
                commit_state=CommitState.ABORTED,
                failure_kind=checked_kind,
                failure_reason=checked_reason,
            )
            self._committed[commit_key] = aborted
            return aborted

    def bind_evidence(
        self,
        commit_key: str,
        *,
        raw_result_ref: str,
        effective_result_ref: str,
        mutation_provenance_ref: str,
    ) -> CommittedToolResult:
        """Attach immutable, readable artifacts to a terminal result.

        Binding is idempotent and cannot rewrite an existing reference set.
        Publication remains a separate lifecycle transition.
        """

        refs = tuple(
            _text(value, "tool result evidence reference")
            for value in (
                raw_result_ref,
                effective_result_ref,
                mutation_provenance_ref,
            )
        )
        with self._lock:
            current = self._committed.get(commit_key)
            if current is None:
                raise ContractError(
                    "cannot bind evidence to an unavailable result commit"
                )
            existing = (
                current.raw_result_ref,
                current.effective_result_ref,
                current.mutation_provenance_ref,
            )
            if any(existing) and existing != refs:
                raise ContractError("tool result evidence binding conflict")
            bound = replace(
                current,
                raw_result_ref=refs[0],
                effective_result_ref=refs[1],
                mutation_provenance_ref=refs[2],
            )
            self._committed[commit_key] = bound
            return bound

    def replay(
        self,
        commit_key: str,
        *,
        raw: ToolResult | None = None,
        effective: ToolResult | None = None,
    ) -> CommittedToolResult:
        with self._lock:
            result = self._committed.get(commit_key)
            if result is None:
                raise ContractError("unknown result commit")
            if raw is not None and result.raw != raw.snapshot():
                raise ContractError("result replay raw divergence")
            if effective is not None and result.effective != effective.snapshot():
                raise ContractError("result replay effective divergence")
            return result

    def get(self, commit_key: str) -> CommittedToolResult | None:
        with self._lock:
            return self._committed.get(commit_key)

    def restore(
        self,
        result: CommittedToolResult,
        *,
        attempt: int,
        epoch: int,
    ) -> CommittedToolResult:
        """Restore one digest-verified durable record without rerunning interceptors."""

        if not isinstance(result, CommittedToolResult):
            raise ContractError("restored tool result must be typed")
        expected_key = self._key(result.call_identity, attempt, epoch)
        if not hmac.compare_digest(expected_key, result.commit_key):
            raise ContractError("restored tool result identity is inconsistent")
        with self._lock:
            current = self._committed.get(expected_key)
            if current is not None and current != result:
                raise ContractError("restored tool result conflicts with process state")
            self._captured[expected_key] = result.raw.snapshot()
            self._committed[expected_key] = result
            if result.commit_state is CommitState.PUBLISHED:
                self._published.add(expected_key)
            else:
                self._published.discard(expected_key)
            return result


class ResultCommitter(ResultLifecycleCoordinator):
    """Backward-compatible name for the lifecycle coordinator."""


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    provider: str
    model: str
    revision: str
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "model", "revision"):
            _text(getattr(self, name), name)
        if self.reasoning_effort is not None:
            _text(self.reasoning_effort, "reasoning_effort")

    def to_wire(self) -> dict[str, Any]:
        result = {
            "provider": self.provider,
            "model": self.model,
            "revision": self.revision,
        }
        if self.reasoning_effort is not None:
            result["reasoningEffort"] = self.reasoning_effort
        return result


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    model: ModelSnapshot
    tools: tuple[str, ...]
    environment_snapshot_id: str
    authority_snapshot_id: str
    mode: str
    state: str = "CANDIDATE"
    plan_id: str | None = None
    capabilities: tuple[str, ...] = ()
    tool_contracts: Mapping[str, Any] = field(default_factory=dict)
    handler_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model, ModelSnapshot):
            raise ContractError("execution plan model snapshot is invalid")
        for name in ("environment_snapshot_id", "authority_snapshot_id", "mode"):
            _text(getattr(self, name), name)
        if self.state not in {"CANDIDATE", "FINALIZED", "ACTIVE", "RETIRED"}:
            raise ContractError("invalid execution plan state")
        tools = _strings(self.tools, "tools")
        capabilities = _strings(self.capabilities, "capabilities")
        object.__setattr__(self, "tools", tools)
        object.__setattr__(self, "capabilities", capabilities)
        if self.plan_id is not None:
            _text(self.plan_id, "plan_id")
        contracts = _mapping(self.tool_contracts, "tool_contracts")
        handlers = _mapping(self.handler_digests, "handler_digests")
        if set(contracts) != set(tools):
            raise ContractError("tool contracts must exactly bind every planned tool")
        if set(handlers) != set(tools):
            raise ContractError("handler digests must exactly bind every planned tool")
        for tool in tools:
            _text(tool, "planned tool")
            _mapping(contracts[tool], f"tool contract {tool}")
            handler_digest = _sha256(handlers[tool], f"handler digest {tool}")
            if not handler_digest.startswith("sha256:"):
                raise ContractError("handler digests must be canonical SHA-256 digests")
        frozen_contracts = _freeze(contracts)
        frozen_handlers = _freeze(handlers)
        if not isinstance(frozen_contracts, Mapping) or not isinstance(
            frozen_handlers, Mapping
        ):
            raise ContractError("execution plan bindings must remain objects")
        if (
            len(canonical_json_bytes(frozen_contracts))
            + len(canonical_json_bytes(frozen_handlers))
            > MAX_INVOCATION_BYTES
        ):
            raise ContractError("execution plan bindings exceed the byte limit")
        object.__setattr__(self, "tool_contracts", frozen_contracts)
        object.__setattr__(self, "handler_digests", frozen_handlers)

    @property
    def plan_hash(self) -> str:
        # Mutable lifecycle state and display IDs are intentionally excluded.
        return _cas_digest(
            {
                "modelSnapshot": self.model.to_wire(),
                "tools": list(self.tools),
                "toolContracts": _thaw(self.tool_contracts),
                "handlerDigests": _thaw(self.handler_digests),
                "environmentSnapshotId": self.environment_snapshot_id,
                "authoritySnapshotId": self.authority_snapshot_id,
                "mode": self.mode,
                "capabilities": list(self.capabilities),
            },
            domain="delta-execution-plan",
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id or f"plan:{self.plan_hash}",
            "planHash": self.plan_hash,
            "modelSnapshot": self.model.to_wire(),
            "toolPlan": {"tools": list(self.tools)},
            "toolContracts": _thaw(self.tool_contracts),
            "handlerDigests": _thaw(self.handler_digests),
            "toolMode": self.mode,
            "capabilities": list(self.capabilities),
            "environmentSnapshotId": self.environment_snapshot_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "state": self.state,
        }


class StepExecutionPlanStore:
    def __init__(self) -> None:
        self._plans: dict[str, ExecutionPlan] = {}
        self.active: ExecutionPlan | None = None
        self._lock = threading.RLock()

    def build_candidate(
        self,
        model: ModelSnapshot,
        tools: Iterable[str],
        env: str,
        auth: str,
        mode: str,
        *,
        capabilities: Iterable[str] = (),
        plan_id: str | None = None,
        tool_contracts: Mapping[str, Any],
        handler_digests: Mapping[str, str],
    ) -> ExecutionPlan:
        plan = ExecutionPlan(
            model,
            tuple(tools),
            env,
            auth,
            mode,
            "CANDIDATE",
            plan_id,
            tuple(capabilities),
            tool_contracts,
            handler_digests,
        )
        key = plan.plan_id or plan.plan_hash
        with self._lock:
            prior = self._plans.get(key)
            if prior is not None:
                if prior.plan_hash != plan.plan_hash:
                    raise ContractError("plan identity/hash conflict")
                if prior.state == "RETIRED":
                    raise ContractError("retired execution plan cannot be reused")
                return prior
            self._plans[key] = plan
            return plan

    def finalize(self, candidate: ExecutionPlan) -> ExecutionPlan:
        if candidate.state != "CANDIDATE":
            if candidate.state in {"FINALIZED", "ACTIVE"}:
                key = candidate.plan_id or candidate.plan_hash
                with self._lock:
                    stored = self._plans.get(key)
                    if stored != candidate:
                        raise ContractError(
                            "execution plan was not finalized by this store"
                        )
                return candidate
            raise ContractError("only a candidate plan may be finalized")
        finalized = replace(candidate, state="FINALIZED")
        key = finalized.plan_id or finalized.plan_hash
        with self._lock:
            prior = self._plans.get(key)
            if prior is not None and prior.plan_hash != finalized.plan_hash:
                raise ContractError("plan identity/hash conflict")
            self._plans[key] = finalized
            # Compatibility with the original compact API: finalization makes
            # the plan visible, while activation remains an explicit method.
            self.active = finalized
        return finalized

    def activate(self, plan: ExecutionPlan) -> ExecutionPlan:
        if plan.state not in {"FINALIZED", "ACTIVE"}:
            raise ContractError("only a finalized plan may activate")
        active = replace(plan, state="ACTIVE")
        with self._lock:
            key = plan.plan_id or plan.plan_hash
            stored = self._plans.get(key)
            if (
                stored is None
                or stored.plan_hash != plan.plan_hash
                or stored.state not in {"FINALIZED", "ACTIVE"}
            ):
                raise ContractError("execution plan was not finalized by this store")
            if (
                self.active is not None
                and (self.active.plan_id or self.active.plan_hash) != key
            ):
                self._plans[self.active.plan_id or self.active.plan_hash] = replace(
                    self.active, state="RETIRED"
                )
            self._plans[key] = active
            self.active = active
        return active

    def retire(self, plan_id: str) -> ExecutionPlan:
        with self._lock:
            current = self._plans.get(plan_id)
            if current is None:
                raise ContractError("unknown execution plan")
            retired = replace(current, state="RETIRED")
            self._plans[plan_id] = retired
            if (
                self.active is not None
                and (self.active.plan_id or self.active.plan_hash) == plan_id
            ):
                self.active = None
            return retired

    def get(self, plan_id: str) -> ExecutionPlan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def restore(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Restore a durable plan while preserving the single-active invariant."""

        if not isinstance(plan, ExecutionPlan) or plan.plan_id is None:
            raise ContractError("restored execution plan requires an exact plan id")
        with self._lock:
            current = self._plans.get(plan.plan_id)
            if current is not None and current != plan:
                raise ContractError(
                    "restored execution plan conflicts with process state"
                )
            if plan.state == "ACTIVE":
                if self.active is not None and self.active.plan_id != plan.plan_id:
                    raise ContractError("durable scope contains multiple active plans")
                self.active = plan
            self._plans[plan.plan_id] = plan
            return plan


class PlanStore(StepExecutionPlanStore):
    pass


@dataclass(frozen=True, slots=True)
class PermissionProfile:
    filesystem_roots: tuple[str, ...]
    network: str
    mutable: bool
    working_directory: str | None = None
    extra: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.mutable, bool):
            raise ContractError("mutable must be boolean")
        _strings(self.filesystem_roots, "filesystem_roots")
        roots = tuple(
            _canonical_absolute_posix_path(root, "filesystem root")
            for root in self.filesystem_roots
        )
        if len(set(roots)) != len(roots):
            raise ContractError("filesystem roots must be exact and unique")
        working_directory = self.working_directory
        if working_directory is None:
            raise ContractError("working_directory is required")
        checked_working_directory = _canonical_absolute_posix_path(
            working_directory, "working_directory"
        )
        if not any(_path_is_within(checked_working_directory, root) for root in roots):
            raise ContractError(
                "working_directory must be contained by a filesystem root"
            )
        object.__setattr__(self, "filesystem_roots", roots)
        object.__setattr__(self, "working_directory", checked_working_directory)
        if self.network not in {"deny", "loopback", "allowlisted"}:
            raise ContractError("network permission mode is unsupported")
        if len(self.extra) > MAX_COLLECTION_ITEMS:
            raise ContractError("permission extra has too many entries")
        keys: set[str] = set()
        for pair in self.extra:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ContractError("permission extra must be a key/value tuple")
            key, item = pair
            _text(key, "permission extra key")
            _text(item, "permission extra value")
            if key in keys:
                raise ContractError("permission extra contains duplicate keys")
            keys.add(key)

    def to_wire(self) -> dict[str, Any]:
        return {
            "filesystemRoots": list(self.filesystem_roots),
            "network": self.network,
            "mutable": self.mutable,
            "workingDirectory": self.working_directory,
            "extra": {key: value for key, value in self.extra},
        }


@dataclass(frozen=True, slots=True)
class PermissionReplay:
    profile_id: str
    canonical_profile: Mapping[str, Any]
    provider: str
    version: str
    mapping: MappingResult
    value: Any = None
    resume_allowed: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        _text(self.profile_id, "profile_id")
        _text(self.provider, "provider")
        _text(self.version, "version")
        if not isinstance(self.mapping, MappingResult):
            raise ContractError("permission mapping result is invalid")
        if self.resume_allowed is not (self.mapping is MappingResult.EXACT):
            raise ContractError("permission replay resume flag contradicts mapping")
        if self.reason:
            _text(self.reason, "reason")

    def to_wire(self) -> dict[str, Any]:
        projection: dict[str, Any] = {
            "provider": self.provider,
            "version": self.version,
            "mapping": self.mapping.value,
        }
        if self.value is not None:
            projection["value"] = _thaw(self.value)
        return {
            "profileId": self.profile_id,
            "canonicalProfile": _thaw(self.canonical_profile),
            "providerProjection": projection,
            "resumeAllowed": self.resume_allowed,
            "reason": self.reason,
        }


class PermissionProjectionAdapter:
    @staticmethod
    def project(
        profile: PermissionProfile, representable: Mapping[str, PermissionProfile]
    ) -> tuple[MappingResult, str | None]:
        for value, exact in representable.items():
            if not isinstance(value, str) or not isinstance(exact, PermissionProfile):
                raise ContractError("permission adapter map is invalid")
            if exact == profile:
                return MappingResult.EXACT, value
        return (
            (MappingResult.UNSUPPORTED, None)
            if not representable
            else (MappingResult.LOSSY, None)
        )

    @classmethod
    def replay(
        cls,
        profile_id: str,
        profile: PermissionProfile,
        *,
        provider: str,
        version: str,
        representable: Mapping[str, PermissionProfile],
    ) -> PermissionReplay:
        mapping, value = cls.project(profile, representable)
        return PermissionReplay(
            profile_id,
            MappingProxyType(profile.to_wire()),
            _text(provider, "provider"),
            _text(version, "version"),
            mapping,
            value,
            mapping is MappingResult.EXACT,
            "exact mapping"
            if mapping is MappingResult.EXACT
            else f"permission mapping is {mapping.value}",
        )

    @staticmethod
    def require_exact(result: MappingResult | PermissionReplay) -> None:
        mapping = result.mapping if isinstance(result, PermissionReplay) else result
        if mapping is not MappingResult.EXACT:
            raise UnsupportedContractError(f"permission mapping is {mapping.value}")


class PermissionAdapter(PermissionProjectionAdapter):
    pass


@dataclass(slots=True)
class CapabilityLease:
    lease_id: str
    invocation_id: str
    environment_id: str
    authority_snapshot_id: str
    execution_epoch: int
    capabilities: frozenset[str]
    active: bool = True
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    delegation_allowed: bool = False
    state: str = "ACTIVE"

    def __post_init__(self) -> None:
        for name in (
            "lease_id",
            "invocation_id",
            "environment_id",
            "authority_snapshot_id",
        ):
            _text(getattr(self, name), name)
        _positive(self.execution_epoch, "execution_epoch")
        if not self.capabilities:
            raise ContractError("capability lease must grant at least one capability")
        for capability in self.capabilities:
            _text(capability, "capability")
        if self.state not in {"ACTIVE", "REVOKED", "EXPIRED"}:
            raise ContractError("invalid capability lease state")
        if not isinstance(self.active, bool) or not isinstance(
            self.delegation_allowed, bool
        ):
            raise ContractError("invalid capability lease flags")
        self.issued_at = _aware(self.issued_at, "issued_at")
        self.expires_at = _aware(self.expires_at, "expires_at")
        if self.issued_at and self.expires_at and self.expires_at <= self.issued_at:
            raise ContractError("expires_at must follow issued_at")
        if self.issued_at is None or self.expires_at is None:
            raise ContractError("capability lease requires an exact validity window")
        if self.expires_at - self.issued_at > MAX_CAPABILITY_LEASE_DURATION:
            raise ContractError("capability lease exceeds maximum duration")
        if not self.active:
            self.state = "REVOKED" if self.state == "ACTIVE" else self.state
        elif self.state != "ACTIVE":
            self.active = False

    def _expire_if_needed(self, now: datetime) -> None:
        if self.state != "ACTIVE":
            return
        if self.expires_at is not None and now.astimezone(UTC) >= self.expires_at:
            self.state = "EXPIRED"
            self.active = False

    def use(
        self,
        invocation_id: str,
        epoch: int,
        capability: str,
        *,
        now: datetime | None = None,
    ) -> None:
        check_now = (now or datetime.now(UTC)).astimezone(UTC)
        self._expire_if_needed(check_now)
        if self.state != "ACTIVE" or not self.active:
            raise ContractError("capability lease is not active")
        if invocation_id != self.invocation_id or epoch != self.execution_epoch:
            raise ContractError("capability lease scope mismatch")
        if capability not in self.capabilities:
            raise ContractError("capability not leased")

    def delegate(
        self,
        lease_id: str,
        invocation_id: str,
        *,
        capabilities: Iterable[str],
        execution_epoch: int,
    ) -> "CapabilityLease":
        if not self.delegation_allowed:
            raise ContractError("capability delegation is not allowed")
        requested = frozenset(capabilities)
        if not requested:
            raise ContractError("delegated capability set must not be empty")
        if not requested <= self.capabilities:
            raise ContractError("delegated capabilities widen parent lease")
        if _positive(execution_epoch, "execution_epoch") != self.execution_epoch:
            raise ContractError("delegated capability lease epoch mismatch")
        for capability in sorted(requested):
            self.use(self.invocation_id, self.execution_epoch, capability)
        return CapabilityLease(
            lease_id,
            invocation_id,
            self.environment_id,
            self.authority_snapshot_id,
            execution_epoch,
            requested,
            True,
            datetime.now(UTC),
            self.expires_at,
            False,
        )

    def revoke(self) -> None:
        if self.state != "EXPIRED":
            self.state = "REVOKED"
        self.active = False

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "leaseId": self.lease_id,
            "invocationId": self.invocation_id,
            "environmentId": self.environment_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "executionEpoch": self.execution_epoch,
            "capabilities": sorted(self.capabilities),
            "state": self.state,
            "delegationAllowed": self.delegation_allowed,
        }
        if self.issued_at is not None:
            output["issuedAt"] = self.issued_at.isoformat().replace("+00:00", "Z")
        if self.expires_at is not None:
            output["expiresAt"] = self.expires_at.isoformat().replace("+00:00", "Z")
        return output


class CapabilityLeaseBroker:
    def __init__(self) -> None:
        self._leases: dict[str, CapabilityLease] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        *,
        lease_id: str,
        invocation_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        execution_epoch: int,
        capabilities: Iterable[str],
        expires_at: datetime | None = None,
        delegation_allowed: bool = False,
        now: datetime | None = None,
    ) -> CapabilityLease:
        issued_at = _aware(now or datetime.now(UTC), "now")
        expiry = _aware(expires_at, "expires_at")
        if expiry is None:
            raise ContractError("expires_at is required for capability lease")
        lease = CapabilityLease(
            lease_id,
            invocation_id,
            environment_id,
            authority_snapshot_id,
            execution_epoch,
            frozenset(capabilities),
            True,
            issued_at,
            expiry,
            delegation_allowed,
        )
        with self._lock:
            current = self._leases.get(lease_id)
            if current is not None:
                immutable_current = current.to_wire() | {"issuedAt": None}
                immutable_candidate = lease.to_wire() | {"issuedAt": None}
                if immutable_current != immutable_candidate:
                    raise ContractError("conflicting capability lease")
                return current
            self._leases[lease_id] = lease
            return lease

    def get(self, lease_id: str) -> CapabilityLease | None:
        with self._lock:
            return self._leases.get(lease_id)

    def revoke(self, lease_id: str) -> CapabilityLease:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                raise ContractError("unknown capability lease")
            lease.revoke()
            return lease

    def restore(self, lease: CapabilityLease) -> CapabilityLease:
        """Restore one validated durable lease without changing its timestamps."""

        if not isinstance(lease, CapabilityLease):
            raise ContractError("restored capability lease must be typed")
        with self._lock:
            current = self._leases.get(lease.lease_id)
            if current is not None and current.to_wire() != lease.to_wire():
                raise ContractError(
                    "restored capability lease conflicts with process state"
                )
            self._leases[lease.lease_id] = lease
            return lease


@dataclass(frozen=True, slots=True)
class VerifiedSecurityContext:
    context_id: str
    issuer: str
    bindings: Mapping[str, str]
    status: str
    entitlements: Mapping[str, Any] = field(default_factory=dict)
    signature: str | None = None

    REQUIRED_BINDINGS = frozenset(
        {
            "pluginId",
            "toolId",
            "accountId",
            "tenantId",
            "environmentId",
            "invocationId",
            "policyVersion",
        }
    )

    def __post_init__(self) -> None:
        _text(self.context_id, "context_id")
        _text(self.issuer, "issuer")
        if self.status not in {"VERIFIED", "UNKNOWN", "DENIED"}:
            raise ContractError("invalid security context status")
        if set(self.bindings) != self.REQUIRED_BINDINGS:
            raise ContractError("security context bindings are not exact")
        for key, value in self.bindings.items():
            _text(key, "binding key")
            _text(value, f"binding {key}")
        _mapping(self.entitlements, "entitlements")
        if self.status == "VERIFIED" and not self.signature:
            raise ContractError("verified security context requires signature")
        if self.signature is not None and not self.signature.startswith("hmac-sha256:"):
            raise ContractError("security context signature format is invalid")

    def to_wire(self) -> dict[str, Any]:
        output = {
            "contextId": self.context_id,
            "issuer": self.issuer,
            "bindings": dict(self.bindings),
            "entitlements": _thaw(self.entitlements),
            "status": self.status,
        }
        if self.signature is not None:
            output["signature"] = self.signature
        return output


class SecurityContextBroker:
    RESERVED = frozenset(
        {
            "verifiedSecurityContext",
            "entitlementContext",
            "executionAuthority",
            "securityContext",
            "authorization",
        }
    )

    def __init__(self, signer: HostSecurityContextSigner | None = None) -> None:
        if signer is not None and not isinstance(signer, HostSecurityContextSigner):
            raise ContractError("host security-context signer is invalid")
        self._signer = signer

    @classmethod
    def sanitize_caller_metadata(cls, metadata: Mapping[str, Any]) -> dict[str, Any]:
        value = _mapping(metadata, "caller metadata")
        return {
            key: _thaw(_freeze(item))
            for key, item in value.items()
            if key not in cls.RESERVED
        }

    @staticmethod
    def _claim(
        *,
        issuer: str,
        context_id: str,
        bindings: Mapping[str, str],
        entitlements: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "issuer": issuer,
            "contextId": context_id,
            "bindings": {key: bindings[key] for key in sorted(bindings)},
            "entitlements": _thaw(entitlements),
        }

    @property
    def trusted_for_production(self) -> bool:
        return bool(
            self._signer is not None
            and getattr(self._signer, "trusted_for_production", False)
        )

    def mint_context(
        self,
        *,
        eligible: bool,
        account_stable: bool,
        bindings: Mapping[str, str],
        entitlements: Mapping[str, Any],
        issuer: str | None = None,
        context_id: str | None = None,
    ) -> VerifiedSecurityContext:
        if not isinstance(bindings, Mapping) or any(
            not isinstance(key, str) for key in bindings
        ):
            raise ContractError("security context bindings must be an object")
        exact = set(bindings) == VerifiedSecurityContext.REQUIRED_BINDINGS and all(
            isinstance(v, str) and v.strip() for v in bindings.values()
        )
        safe_bindings: dict[str, str] = {}
        for key in sorted(VerifiedSecurityContext.REQUIRED_BINDINGS):
            binding = bindings.get(key)
            safe_bindings[key] = (
                binding if isinstance(binding, str) and binding.strip() else "UNKNOWN"
            )
        cid = (
            context_id
            or f"ctx:{_digest(safe_bindings, domain='delta-security-context-id')[:24]}"
        )
        frozen_entitlements = _freeze(_mapping(entitlements, "entitlements"))
        actual_issuer = (
            self._signer.issuer
            if self._signer is not None
            else (issuer or "UNCONFIGURED")
        )
        if issuer is not None and issuer != actual_issuer:
            raise ContractError("security context issuer is not host-selected")
        if not eligible or not account_stable or not exact or self._signer is None:
            return VerifiedSecurityContext(
                cid,
                actual_issuer,
                safe_bindings,
                "UNKNOWN",
                MappingProxyType({}),
                None,
            )
        claim = self._claim(
            issuer=actual_issuer,
            context_id=cid,
            bindings=safe_bindings,
            entitlements=frozen_entitlements,
        )
        signature = self._signer.sign(claim)
        return VerifiedSecurityContext(
            cid,
            actual_issuer,
            safe_bindings,
            "VERIFIED",
            frozen_entitlements,
            signature,
        )

    def mint(
        self,
        *,
        eligible: bool,
        account_stable: bool,
        bindings: Mapping[str, str],
        entitlements: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.mint_context(
            eligible=eligible,
            account_stable=account_stable,
            bindings=bindings,
            entitlements=entitlements,
        ).to_wire()

    def verify(
        self, context: VerifiedSecurityContext | Mapping[str, Any]
    ) -> VerifiedSecurityContext:
        if not isinstance(context, VerifiedSecurityContext):
            try:
                context = VerifiedSecurityContext(
                    _field_text(context, "contextId"),
                    _field_text(context, "issuer"),
                    dict(context["bindings"]),
                    _field_text(context, "status"),
                    dict(context.get("entitlements", {})),
                    context.get("signature"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ContractError("invalid security context") from exc
        if context.status == "VERIFIED":
            if self._signer is None or context.issuer != self._signer.issuer:
                raise ContractError(
                    "verified security context lacks its explicit Host signer"
                )
            claim = self._claim(
                issuer=context.issuer,
                context_id=context.context_id,
                bindings=context.bindings,
                entitlements=context.entitlements,
            )
            try:
                verified = bool(
                    context.signature and self._signer.verify(claim, context.signature)
                )
            except AssurancePolicyValidationError as exc:
                raise ContractError("security context signature is invalid") from exc
            if not verified:
                raise ContractError("security context signature mismatch")
        return context


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    snapshot_id: str
    permissions: frozenset[str]
    owner_id: str = ""
    environment_id: str = ""
    permission_profile_version: str = ""
    effective_policy_hash: str = ""
    parent_snapshot_id: str | None = None
    widening: bool = False

    def __post_init__(self) -> None:
        _sha256(self.snapshot_id, "snapshot_id")
        for name in (
            "owner_id",
            "environment_id",
            "permission_profile_version",
            "effective_policy_hash",
        ):
            _text(getattr(self, name), name)
        _sha256(self.effective_policy_hash, "effective_policy_hash")
        if any(
            not isinstance(permission, str) or not permission
            for permission in self.permissions
        ):
            raise ContractError("authority permission is invalid")
        if self.parent_snapshot_id is not None:
            _sha256(self.parent_snapshot_id, "parent_snapshot_id")
        if self.widening:
            raise ContractError("authority snapshot cannot declare widening")

    @staticmethod
    def intersect(
        owner: "AuthoritySnapshot",
        parent: "AuthoritySnapshot",
        policy: frozenset[str],
        snapshot_id: str,
        *,
        environment_id: str | None = None,
        permission_profile_version: str | None = None,
        effective_policy_hash: str | None = None,
    ) -> "AuthoritySnapshot":
        if (
            owner.environment_id
            and parent.environment_id
            and owner.environment_id != parent.environment_id
        ):
            raise ContractError("authority environment mismatch")
        if owner.permission_profile_version != parent.permission_profile_version:
            raise ContractError("authority permission profile version mismatch")
        permissions = owner.permissions & parent.permissions & frozenset(policy)
        policy_hash = effective_policy_hash or _cas_digest(
            {
                "ownerPolicy": owner.effective_policy_hash,
                "parentPolicy": parent.effective_policy_hash,
                "permissions": sorted(permissions),
            },
            domain="delta-effective-attachment-policy",
        )
        return AuthoritySnapshot(
            snapshot_id,
            permissions,
            owner.owner_id,
            environment_id or owner.environment_id or parent.environment_id,
            permission_profile_version or owner.permission_profile_version,
            policy_hash,
            parent.snapshot_id,
            False,
        )

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "snapshotId": self.snapshot_id,
            "ownerId": self.owner_id,
            "environmentId": self.environment_id,
            "permissionProfileVersion": self.permission_profile_version,
            "effectivePolicyHash": self.effective_policy_hash,
            "parentSnapshotId": self.parent_snapshot_id,
            "widening": False,
        }
        return output


class AuthorityCalculator:
    @staticmethod
    def calculate(
        owner: AuthoritySnapshot,
        parent: AuthoritySnapshot,
        policy_permissions: Iterable[str],
        snapshot_id: str,
    ) -> AuthoritySnapshot:
        if not isinstance(policy_permissions, (tuple, list, frozenset, set)):
            raise ContractError("policy permissions must be a collection")
        permissions = tuple(policy_permissions)
        if len(permissions) > MAX_COLLECTION_ITEMS or any(
            not isinstance(item, str) for item in permissions
        ):
            raise ContractError("policy permissions are invalid")
        return AuthoritySnapshot.intersect(
            owner, parent, frozenset(permissions), snapshot_id
        )


class GenerationFence:
    def __init__(
        self,
        generation: int = 0,
        connection_epoch: int = 0,
        *,
        environment_id: str = "",
        executor_identity: str = "",
    ) -> None:
        self.generation = _nonnegative(generation, "generation")
        self.connection_epoch = _nonnegative(connection_epoch, "connection_epoch")
        self.environment_id = _text(environment_id, "environment_id")
        self.executor_identity = _text(executor_identity, "executor_identity")
        self.state = "CONNECTING"
        self.live_probe_evidence_ref: str | None = None
        self.retired_predecessor: Mapping[str, Any] | None = None
        self.replacement_effects: tuple[Mapping[str, Any], ...] = ()
        self.replacement_reconciled = True
        self._lock = threading.RLock()

    def require_reconciliation(self, predecessor: "GenerationFence") -> None:
        if predecessor.state != "RETIRED":
            raise ContractError("executor predecessor must be retired first")
        predecessor_wire = predecessor.to_wire()
        kinds = (
            "CAPABILITY_REVOCATION",
            "WORKSPACE_RECONCILIATION",
            "EXTERNAL_EFFECT_RECONCILIATION",
        )
        effects = tuple(
            MappingProxyType(
                {
                    "effectId": "effect-"
                    + _cas_digest(
                        {
                            "environmentId": self.environment_id,
                            "executorGeneration": self.generation,
                            "connectionEpoch": self.connection_epoch,
                            "kind": kind,
                        },
                        domain="delta-executor-replacement-effect",
                    ).removeprefix("sha256:")[:40],
                    "kind": kind,
                    "state": "PENDING",
                }
            )
            for kind in kinds
        )
        self.retired_predecessor = MappingProxyType(predecessor_wire)
        self.replacement_effects = effects
        self.replacement_reconciled = False

    def restore_reconciliation(self, effects: Iterable[Mapping[str, Any]]) -> None:
        checked = tuple(
            _freeze(_mapping(item, "executor replacement effect")) for item in effects
        )
        kinds = {str(item.get("kind")) for item in checked}
        required = {
            "CAPABILITY_REVOCATION",
            "WORKSPACE_RECONCILIATION",
            "EXTERNAL_EFFECT_RECONCILIATION",
        }
        if kinds != required:
            raise ContractError("executor replacement effects are not exact")
        self.replacement_effects = checked
        self.replacement_reconciled = all(
            item.get("state") == "SUCCEEDED" for item in checked
        )

    def reconnect_same(self) -> tuple[int, int]:
        with self._lock:
            if self.state != "ACTIVE":
                raise ContractError("only an active executor may reconnect")
            self.connection_epoch += 1
            self.state = "CONNECTING"
            self.live_probe_evidence_ref = None
            return self.generation, self.connection_epoch

    def replace_executor(self) -> tuple[int, int]:
        with self._lock:
            if self.state != "ACTIVE":
                raise ContractError("only an active executor may be replaced")
            self.generation += 1
            self.connection_epoch += 1
            self.state = "CONNECTING"
            self.live_probe_evidence_ref = None
            return self.generation, self.connection_epoch

    def activate(
        self, *, live_probe_evidence_ref: str | None = None
    ) -> tuple[int, int]:
        with self._lock:
            if (
                live_probe_evidence_ref is None
                or not str(live_probe_evidence_ref).strip()
            ):
                raise ContractError("live probe evidence is required before activation")
            checked_probe = _text(live_probe_evidence_ref, "live_probe_evidence_ref")
            if not self.replacement_reconciled:
                raise ContractError(
                    "executor replacement effects are not durably reconciled"
                )
            if self.state == "ACTIVE":
                if self.live_probe_evidence_ref != checked_probe:
                    raise ContractError("active executor probe evidence is immutable")
                return self.generation, self.connection_epoch
            if self.state != "CONNECTING":
                raise ContractError("only a connecting executor may activate")
            self.live_probe_evidence_ref = checked_probe
            self.state = "ACTIVE"
            return self.generation, self.connection_epoch

    def retire(self) -> None:
        with self._lock:
            if self.state == "RETIRED":
                return
            if self.state not in {"ACTIVE", "CONNECTING"}:
                raise ContractError("executor is not eligible for retirement")
            self.state = "RETIRED"

    def fail(self) -> None:
        with self._lock:
            if self.state == "FAILED":
                return
            if self.state not in {"ACTIVE", "CONNECTING"}:
                raise ContractError("executor is not eligible for failure")
            self.state = "FAILED"

    def accept(self, generation: int, connection_epoch: int) -> None:
        with self._lock:
            _nonnegative(generation, "generation")
            _nonnegative(connection_epoch, "connection_epoch")
            if self.state != "ACTIVE":
                raise ContractError("executor is not active")
            if (generation, connection_epoch) != (
                self.generation,
                self.connection_epoch,
            ):
                raise ContractError("stale executor result")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "environmentId": self.environment_id,
            "executorIdentity": self.executor_identity,
            "executorGeneration": self.generation,
            "connectionEpoch": self.connection_epoch,
            "state": self.state,
            "liveProbeEvidenceRef": self.live_probe_evidence_ref,
        }
        if self.retired_predecessor is not None:
            output["retiredPredecessor"] = _thaw(self.retired_predecessor)
        if self.replacement_effects:
            output["reconciliationEffects"] = [
                _thaw(item) for item in self.replacement_effects
            ]
            output["activationAllowed"] = self.replacement_reconciled
        return output


class ExecutorGenerationManager(GenerationFence):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceLease:
    workspace_id: str
    owner_execution_id: str
    generation: int
    repository_id: str
    base_revision: str
    write_scopes: tuple[str, ...] = ()
    state: str = "ACTIVE"
    crash_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "workspace_id",
            "owner_execution_id",
            "repository_id",
            "base_revision",
        ):
            _text(getattr(self, name), name)
        _positive(self.generation, "generation")
        if self.state not in {
            "ACTIVE",
            "HANDOFF_PENDING",
            "RETIRED",
            "TAKEOVER_PENDING",
        }:
            raise ContractError("invalid workspace lease state")
        if (self.state == "TAKEOVER_PENDING") is not (
            self.crash_evidence_ref is not None
        ):
            raise ContractError(
                "crash evidence is required only for TAKEOVER_PENDING leases"
            )
        if self.crash_evidence_ref is not None:
            _text(self.crash_evidence_ref, "crash evidence reference")
        normalized = tuple(_workspace_scope(scope) for scope in self.write_scopes)
        if (
            not normalized
            or len(normalized) > MAX_COLLECTION_ITEMS
            or len(set(normalized)) != len(normalized)
        ):
            raise ContractError("workspace write scopes must be exact and non-empty")
        object.__setattr__(self, "write_scopes", normalized)

    def owns(self, execution_id: str, *, scope: str | None = None) -> bool:
        if self.state != "ACTIVE" or execution_id != self.owner_execution_id:
            return False
        if scope is None:
            return True
        requested = _workspace_scope(scope)
        return any(
            requested == owned or requested.startswith(owned.rstrip("/") + "/")
            for owned in self.write_scopes
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "workspaceId": self.workspace_id,
            "ownerExecutionId": self.owner_execution_id,
            "generation": self.generation,
            "repositoryId": self.repository_id,
            "baseRevision": self.base_revision,
            "writeScopes": list(self.write_scopes),
            "state": self.state,
            "crashEvidenceRef": self.crash_evidence_ref,
        }


class WorkspaceLeaseManager:
    def __init__(self) -> None:
        self._active: dict[str, WorkspaceLease] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _overlap(left: Sequence[str], right: Sequence[str]) -> bool:
        if not left or not right:
            raise ContractError("workspace overlap requires exact non-empty scopes")

        def covered(a: str, b: str) -> bool:
            return (
                a == b
                or a.startswith(b.rstrip("/") + "/")
                or b.startswith(a.rstrip("/") + "/")
            )

        return any(covered(a, b) for a in left for b in right)

    def bind(self, lease: WorkspaceLease) -> WorkspaceLease:
        with self._lock:
            current = self._active.get(lease.workspace_id)
            if current is None or current.state == "RETIRED":
                self._active[lease.workspace_id] = lease
                return lease
            if current == lease:
                return current
            if current.owner_execution_id != lease.owner_execution_id and self._overlap(
                current.write_scopes, lease.write_scopes
            ):
                raise ContractError("workspace owner/write-scope conflict")
            raise ContractError("workspace owner conflict")

    def request_handoff(self, workspace_id: str) -> WorkspaceLease:
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            if current.state == "HANDOFF_PENDING":
                return current
            if current.state != "ACTIVE":
                raise ContractError("workspace is not eligible for handoff")
            pending = replace(current, state="HANDOFF_PENDING")
            self._active[workspace_id] = pending
            return pending

    def mark_takeover_pending(
        self, workspace_id: str, *, crash_evidence_ref: str
    ) -> WorkspaceLease:
        evidence = _text(crash_evidence_ref, "crash evidence reference")
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            if current.state == "TAKEOVER_PENDING":
                if current.crash_evidence_ref != evidence:
                    raise ContractError("workspace crash evidence is immutable")
                return current
            if current.state != "ACTIVE":
                raise ContractError("only an active workspace can enter crash takeover")
            pending = replace(
                current,
                state="TAKEOVER_PENDING",
                crash_evidence_ref=evidence,
            )
            self._active[workspace_id] = pending
            return pending

    def takeover(
        self,
        workspace_id: str,
        new_owner: str,
        *,
        expected_generation: int,
        base_revision: str | None = None,
        write_scopes: Iterable[str] | None = None,
    ) -> WorkspaceLease:
        _text(new_owner, "new_owner")
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            if current.state != "TAKEOVER_PENDING":
                raise ContractError("crash takeover requires TAKEOVER_PENDING")
            if current.generation != _positive(
                expected_generation, "expected_generation"
            ):
                raise ContractError("workspace takeover generation is stale")
            if current.owner_execution_id == new_owner:
                raise ContractError("workspace takeover requires a different owner")
            requested_base = base_revision or current.base_revision
            requested_scopes = (
                tuple(write_scopes)
                if write_scopes is not None
                else current.write_scopes
            )
            if (
                requested_base != current.base_revision
                or requested_scopes != current.write_scopes
            ):
                raise ContractError(
                    "workspace takeover cannot widen or mutate the registered checkout"
                )
            replacement = replace(
                current,
                owner_execution_id=new_owner,
                generation=current.generation + 1,
                base_revision=current.base_revision,
                write_scopes=current.write_scopes,
                state="ACTIVE",
                crash_evidence_ref=None,
            )
            self._active[workspace_id] = replacement
            return replacement

    def accept_handoff(
        self,
        workspace_id: str,
        new_owner: str,
        *,
        expected_generation: int,
        base_revision: str | None = None,
        write_scopes: Iterable[str] | None = None,
    ) -> WorkspaceLease:
        _text(new_owner, "new_owner")
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            if current.state != "HANDOFF_PENDING":
                raise ContractError("normal handoff requires HANDOFF_PENDING")
            if current.generation != _positive(
                expected_generation, "expected_generation"
            ):
                raise ContractError("workspace handoff generation is stale")
            if current.owner_execution_id == new_owner:
                raise ContractError("workspace handoff requires a different owner")
            requested_base = base_revision or current.base_revision
            requested_scopes = (
                tuple(write_scopes)
                if write_scopes is not None
                else current.write_scopes
            )
            if (
                requested_base != current.base_revision
                or requested_scopes != current.write_scopes
            ):
                raise ContractError(
                    "workspace handoff cannot widen or mutate the registered checkout"
                )
            replacement = replace(
                current,
                owner_execution_id=new_owner,
                generation=current.generation + 1,
                state="ACTIVE",
                crash_evidence_ref=None,
            )
            self._active[workspace_id] = replacement
            return replacement

    def retire(self, workspace_id: str) -> WorkspaceLease:
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            if current.state == "RETIRED":
                return current
            if current.state not in {
                "ACTIVE",
                "HANDOFF_PENDING",
                "TAKEOVER_PENDING",
            }:
                raise ContractError("workspace is not eligible for retirement")
            retired = replace(current, state="RETIRED", crash_evidence_ref=None)
            self._active[workspace_id] = retired
            return retired

    def get(self, workspace_id: str) -> WorkspaceLease | None:
        with self._lock:
            return self._active.get(workspace_id)

    def restore(self, lease: WorkspaceLease) -> WorkspaceLease:
        """Restore the newest durable generation for a managed workspace."""

        if not isinstance(lease, WorkspaceLease):
            raise ContractError("restored workspace lease must be typed")
        with self._lock:
            current = self._active.get(lease.workspace_id)
            if current is not None:
                if current.generation > lease.generation:
                    return current
                if current.generation == lease.generation and current != lease:
                    raise ContractError("restored workspace generation conflicts")
            self._active[lease.workspace_id] = lease
            return lease


@dataclass(frozen=True, slots=True)
class ProtocolCapabilities:
    provider: str
    version: str
    features: frozenset[str]
    transport: str = "CUSTOM"
    history_mode: str = "NONE"
    typed_tool_result: bool = False
    schema_dialect: str = "json-schema"
    consistency_model: str = "UNKNOWN"
    auth_scheme: str | None = None
    unsupported_required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.provider, "provider")
        _text(self.version, "version")
        for feature in self.features:
            _text(feature, "protocol feature")
        if len(self.features) > MAX_COLLECTION_ITEMS:
            raise ContractError("protocol feature set is too large")
        if self.transport not in {
            "LOCAL_STDIO",
            "REMOTE_GATEWAY",
            "HTTP",
            "WEBSOCKET",
            "ACP",
            "CUSTOM",
        }:
            raise ContractError("invalid protocol transport")
        if self.history_mode not in {"LEGACY_EMBEDDED", "PAGINATED", "BOTH", "NONE"}:
            raise ContractError("invalid history mode")
        if self.consistency_model not in {"STRONG", "EVENTUAL", "UNKNOWN"}:
            raise ContractError("invalid consistency model")
        _text(self.schema_dialect, "schema_dialect")
        if self.auth_scheme is not None:
            _text(self.auth_scheme, "auth_scheme")
        for feature in self.unsupported_required:
            _text(feature, "unsupported required feature")
        if len(set(self.unsupported_required)) != len(self.unsupported_required):
            raise ContractError("unsupported required features contain duplicates")

    def require(self, required: Iterable[str]) -> None:
        requested = tuple(_text(item, "required protocol feature") for item in required)
        if len(requested) > MAX_COLLECTION_ITEMS:
            raise ContractError("required protocol feature set is too large")
        if len(set(requested)) != len(requested):
            raise ContractError("required protocol features contain duplicates")
        requested_set = set(requested)
        missing = requested_set - set(self.features)
        missing.update(requested_set.intersection(self.unsupported_required))
        if "typedToolResult" in requested_set and not self.typed_tool_result:
            missing.add("typedToolResult")
        if missing:
            raise UnsupportedContractError(
                f"unsupported protocol capabilities: {sorted(missing)}"
            )

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "provider": self.provider,
            "version": self.version,
            "transport": self.transport,
            "historyMode": self.history_mode,
            "typedToolResult": self.typed_tool_result,
            "schemaDialect": self.schema_dialect,
            "consistencyModel": self.consistency_model,
            "features": sorted(self.features),
            "unsupportedRequired": list(self.unsupported_required),
        }
        if self.auth_scheme is not None:
            output["authScheme"] = self.auth_scheme
        return output


def _builtin_protocol_profiles() -> dict[tuple[str, str], ProtocolCapabilities]:
    profiles = (
        ProtocolCapabilities(
            "openai-codex",
            "main@2026-08-28",
            frozenset(
                {
                    "resultInterception",
                    "modelSpecificFinalizedPlan",
                    "canonicalPermissionProfile",
                    "invocationScopedExtensionCapabilities",
                    "hostVerifiedSecurityContext",
                    "skillTrustEvidence",
                    "standaloneToolOutputIngress",
                    "typedToolResult",
                }
            ),
            "LOCAL_STDIO",
            "BOTH",
            True,
            "json-schema-2020-12",
            "STRONG",
        ),
        ProtocolCapabilities(
            "openai-codex",
            "0.150.1",
            frozenset({"canonicalPermissionProfile", "typedToolResult"}),
            "LOCAL_STDIO",
            "BOTH",
            True,
            "json-schema-2020-12",
            "STRONG",
            unsupported_required=(
                "resultInterception",
                "invocationScopedExtensionCapabilities",
                "standaloneToolOutputIngress",
            ),
        ),
        ProtocolCapabilities(
            "deepseek-harness",
            "0.1.2-alpha.1",
            frozenset(
                {
                    "sessionControl",
                    "modelSettings",
                    "mcp",
                    "permissions",
                    "cancellation",
                    "ToolCallId",
                }
            ),
            "REMOTE_GATEWAY",
            "PAGINATED",
            True,
            "json-schema-2020-12",
            "UNKNOWN",
            "one-time-token-for-network-web",
            ("ApiProxy",),
        ),
        ProtocolCapabilities(
            "deepseek-harness",
            "0.1.1-rc.2",
            frozenset({"codeMode", "ToolCallId"}),
            "CUSTOM",
            "LEGACY_EMBEDDED",
            False,
            "json-schema-draft-07",
            "UNKNOWN",
        ),
    )
    return {(item.provider, item.version): item for item in profiles}


class ProtocolNegotiator:
    def __init__(
        self,
        profiles: Mapping[tuple[str, str], ProtocolCapabilities] | None = None,
        *,
        allow_unregistered: bool = False,
    ) -> None:
        self._profiles: dict[tuple[str, str], ProtocolCapabilities] = {}
        for key, profile in (profiles or {}).items():
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or not isinstance(profile, ProtocolCapabilities)
            ):
                raise ContractError("protocol profile registry is invalid")
            if key != (profile.provider, profile.version):
                raise ContractError("protocol profile registry key is inconsistent")
            self._profiles[key] = profile
        self._allow_unregistered = allow_unregistered
        self._epochs: dict[tuple[str, str, int], ProtocolCapabilities] = {}
        self._lock = threading.RLock()

    def register(self, profile: ProtocolCapabilities) -> None:
        key = (profile.provider, profile.version)
        with self._lock:
            current = self._profiles.get(key)
            if current is not None and current != profile:
                raise ContractError("conflicting protocol profile")
            self._profiles[key] = profile

    def negotiate(
        self,
        offered: ProtocolCapabilities,
        *,
        required_features: Iterable[str] = (),
        required_version: str | None = None,
        connection_epoch: int = 0,
    ) -> ProtocolCapabilities:
        _nonnegative(connection_epoch, "connection_epoch")
        with self._lock:
            profile = self._profiles.get((offered.provider, offered.version))
        if profile is None:
            if not self._allow_unregistered:
                raise UnsupportedContractError(
                    "protocol provider/version profile is not registered"
                )
            profile = offered
        if required_version is not None and offered.version != required_version:
            raise ContractError("protocol version mismatch")
        mismatches = [
            name
            for name, observed, expected in (
                ("features", offered.features, profile.features),
                ("transport", offered.transport, profile.transport),
                ("historyMode", offered.history_mode, profile.history_mode),
                (
                    "typedToolResult",
                    offered.typed_tool_result,
                    profile.typed_tool_result,
                ),
                ("schemaDialect", offered.schema_dialect, profile.schema_dialect),
                (
                    "consistencyModel",
                    offered.consistency_model,
                    profile.consistency_model,
                ),
                ("authScheme", offered.auth_scheme, profile.auth_scheme),
            )
            if observed != expected
        ]
        if mismatches:
            raise UnsupportedContractError(
                "protocol offer differs from the registered exact profile: "
                + ", ".join(mismatches)
            )
        profile.require(required_features)
        key = (offered.provider, offered.version, connection_epoch)
        with self._lock:
            prior = self._epochs.get(key)
            if prior is not None and prior != profile:
                raise ContractError(
                    "protocol capability changed within connection epoch"
                )
            self._epochs[key] = profile
        return profile


@dataclass(frozen=True, slots=True)
class SkillProvenance:
    skill_id: str
    publisher: str
    origin: str
    canonical_uri: str
    package_digest: str
    trust_domain: str
    install_scope: str
    authorization_semantics: tuple[str, ...]
    signature: str | None = None
    verified: bool = False

    def __post_init__(self) -> None:
        for name in (
            "skill_id",
            "publisher",
            "origin",
            "canonical_uri",
            "package_digest",
            "install_scope",
        ):
            _text(getattr(self, name), name)
        if self.trust_domain not in {
            "USER",
            "ENTERPRISE",
            "MARKETPLACE",
            "REPOSITORY",
            "EPHEMERAL",
        }:
            raise ContractError("invalid Skill trust domain")
        _sha256(self.package_digest, "package_digest")
        _strings(self.authorization_semantics, "authorization_semantics")
        if self.signature is not None:
            _text(self.signature, "signature")
        if (
            self.verified
            and self.trust_domain in {"MARKETPLACE", "ENTERPRISE"}
            and not self.signature
        ):
            raise ContractError("verified Skill provenance requires signature")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "skillId": self.skill_id,
            "publisher": self.publisher,
            "origin": self.origin,
            "canonicalUri": self.canonical_uri,
            "packageDigest": self.package_digest,
            "trustDomain": self.trust_domain,
            "installScope": self.install_scope,
            "authorizationSemantics": list(self.authorization_semantics),
            "verified": self.verified,
        }
        if self.signature is not None:
            output["signature"] = self.signature
        return output


class SkillTrustVerifier:
    @staticmethod
    def verify(skill_path: Path, trusted_root: Path) -> Path:
        actual, _ = _secure_regular_bytes(
            Path(skill_path), trusted_root, limit=MAX_TRUSTED_SKILL_BYTES
        )
        return actual

    @classmethod
    def verify_provenance(
        cls,
        provenance: SkillProvenance,
        *,
        skill_path: Path,
        trust_policy: SkillTrustDomainPolicy,
        signature_verifier: Callable[[bytes, str], bool] | None = None,
    ) -> SkillProvenance:
        if not isinstance(trust_policy, SkillTrustDomainPolicy):
            raise ContractError("Skill trust-domain policy is not configured")
        try:
            trusted_root = trust_policy.authorize(
                domain=provenance.trust_domain,
                publisher=provenance.publisher,
            )
        except AssurancePolicyValidationError as exc:
            raise ContractError("Skill trust-domain authorization failed") from exc
        actual, content = _secure_regular_bytes(
            Path(skill_path), trusted_root, limit=MAX_TRUSTED_SKILL_BYTES
        )
        actual_uri = actual.as_uri()
        if provenance.canonical_uri != actual_uri:
            raise ContractError("Skill canonical URI does not match the trusted file")
        expected = digest_bytes(content, domain="delta-skill-package")
        alternative = digest_bytes(content, domain="artifact")
        normalized_claim = _normalize_sha256(
            provenance.package_digest, "package_digest"
        )
        if not any(
            hmac.compare_digest(normalized_claim, candidate)
            for candidate in (expected, alternative)
        ):
            raise ContractError("Skill package digest mismatch")
        if provenance.trust_domain == "MARKETPLACE" and signature_verifier is None:
            raise ContractError(
                "marketplace provenance requires an independent signature verifier"
            )
        envelope = trust_policy.signature_envelope(
            skill_id=provenance.skill_id,
            publisher=provenance.publisher,
            origin=provenance.origin,
            canonical_uri=actual_uri,
            package_digest=provenance.package_digest,
            trust_domain=provenance.trust_domain,
            install_scope=provenance.install_scope,
            authorization_semantics=provenance.authorization_semantics,
        )
        try:
            verified = bool(
                provenance.signature
                and signature_verifier
                and signature_verifier(envelope, provenance.signature)
            )
        except Exception as exc:
            raise ContractError("Skill provenance signature verifier failed") from exc
        if provenance.trust_domain in {"MARKETPLACE", "ENTERPRISE"} and not verified:
            raise ContractError("Skill provenance signature is not verified")
        authorizing = any(
            semantic != "guidance-only"
            for semantic in provenance.authorization_semantics
        )
        if authorizing and not verified:
            raise ReviewRequiredError(
                "authorizing Skill semantics require an independently verified signature"
            )
        rooted_verification = provenance.trust_domain == "REPOSITORY"
        return replace(
            provenance,
            canonical_uri=actual_uri,
            verified=verified or rooted_verification,
        )


@dataclass(frozen=True, slots=True)
class EventRegistration:
    event_type: str
    owner: str
    schema_version: int
    semantics: str
    validator: Callable[[Mapping[str, Any]], bool] | str = field(
        compare=False, repr=False
    )
    upgrader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | str = field(
        compare=False, repr=False
    )
    projections: tuple[str, ...] = ()
    compatibility: str = "STRICT"

    def __post_init__(self) -> None:
        _text(self.event_type, "event_type")
        _text(self.owner, "owner")
        if self.schema_version < 1 or isinstance(self.schema_version, bool):
            raise ContractError("schema_version must be >= 1")
        if self.semantics not in {"OPTIONAL_OBSERVATION", "REQUIRED_STATE"}:
            raise ContractError("invalid event semantics")
        if self.compatibility not in {"STRICT", "BACKWARD", "FORWARD", "FULL"}:
            raise ContractError("invalid event compatibility")
        _strings(self.projections, "projections")
        if isinstance(self.validator, str):
            _text(self.validator, "validator")
        elif not callable(self.validator):
            raise ContractError(
                "event validator must be a registered identifier or callable"
            )
        if isinstance(self.upgrader, str):
            _text(self.upgrader, "upgrader")
        elif not callable(self.upgrader):
            raise ContractError(
                "event upgrader must be a registered identifier or callable"
            )

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": self.event_type,
            "owner": self.owner,
            "schemaVersion": self.schema_version,
            "semantics": self.semantics,
            "validator": self.validator
            if isinstance(self.validator, str)
            else "callable",
            "upgrader": self.upgrader if isinstance(self.upgrader, str) else "callable",
            "projections": list(self.projections),
            "compatibility": self.compatibility,
        }


@dataclass(frozen=True, slots=True)
class DurableEventEnvelope:
    """One typed event in an exact causal replay stream."""

    event_id: str
    event_type: str
    schema_version: int
    payload: Mapping[str, Any]
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("event_id", "event_type", "correlation_id"):
            _text(getattr(self, name), name)
        _positive(self.schema_version, "schema_version")
        if self.causation_id is not None:
            _text(self.causation_id, "causation_id")
            if self.causation_id == self.event_id:
                raise ContractError("durable event cannot cause itself")
        frozen = _freeze(_mapping(self.payload, "event payload"))
        if not isinstance(frozen, Mapping):
            raise ContractError("event payload must remain an object")
        object.__setattr__(self, "payload", frozen)

    def to_wire(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "type": self.event_type,
            "schemaVersion": self.schema_version,
            "payload": _thaw(self.payload),
            "correlationId": self.correlation_id,
            "causationId": self.causation_id,
        }


def _event_object_validator(payload: Mapping[str, Any]) -> bool:
    return isinstance(payload, Mapping)


def _event_identity_upgrader(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return dict(payload)


class DurableEventRegistry:
    def __init__(
        self,
        *,
        validators: Mapping[str, Callable[[Mapping[str, Any]], bool]] | None = None,
        upgraders: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]
        | None = None,
        optional_unknown_types: Iterable[str] = (),
    ) -> None:
        self._items: dict[tuple[str, int], EventRegistration] = {}
        self._validators: dict[str, Callable[[Mapping[str, Any]], bool]] = {
            "elmos.object.v1": _event_object_validator,
        }
        self._upgraders: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = {
            "elmos.identity.v1": _event_identity_upgrader,
        }
        self._optional_unknown_types = frozenset(
            _text(item, "optional event type") for item in optional_unknown_types
        )
        self._audit: list[Mapping[str, Any]] = []
        self._lock = threading.RLock()
        for name, validator in (validators or {}).items():
            self.register_validator(name, validator)
        for name, upgrader in (upgraders or {}).items():
            self.register_upgrader(name, upgrader)

    def register_validator(
        self,
        name: str,
        validator: Callable[[Mapping[str, Any]], bool],
    ) -> None:
        identifier = _text(name, "durable event validator")
        if not callable(validator):
            raise ContractError("durable event validator registry is invalid")
        with self._lock:
            current = self._validators.get(identifier)
            if current is not None and current is not validator:
                raise ContractError("conflicting durable event validator")
            self._validators[identifier] = validator

    def register_upgrader(
        self,
        name: str,
        upgrader: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        identifier = _text(name, "durable event upgrader")
        if identifier == "none" or not callable(upgrader):
            raise ContractError("durable event upgrader registry is invalid")
        with self._lock:
            current = self._upgraders.get(identifier)
            if current is not None and current is not upgrader:
                raise ContractError("conflicting durable event upgrader")
            self._upgraders[identifier] = upgrader

    def _audit_record(self, record: Mapping[str, Any]) -> None:
        frozen = _freeze(record)
        if not isinstance(frozen, Mapping):
            raise ContractError("durable event audit record is invalid")
        self._audit.append(frozen)

    def audit_records(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(self._audit)

    def register(self, item: EventRegistration) -> None:
        key = (item.event_type, item.schema_version)
        with self._lock:
            if (
                isinstance(item.validator, str)
                and item.validator not in self._validators
            ):
                raise UnsupportedContractError(
                    "durable event validator is not registered"
                )
            if (
                item.schema_version > 1
                and isinstance(item.upgrader, str)
                and item.upgrader not in self._upgraders
            ):
                raise UnsupportedContractError(
                    "durable event upgrader is not registered"
                )
            if (
                item.schema_version == 1
                and isinstance(item.upgrader, str)
                and item.upgrader not in {"none", *self._upgraders}
            ):
                raise UnsupportedContractError(
                    "durable event upgrader is not registered"
                )
            current = self._items.get(key)
            if current is not None:
                handler_conflict = (
                    callable(current.validator)
                    and current.validator is not item.validator
                ) or (
                    callable(current.upgrader) and current.upgrader is not item.upgrader
                )
                if current.to_wire() != item.to_wire() or handler_conflict:
                    raise ContractError("conflicting event registration")
            self._items[key] = item

    def _preflight(
        self,
        operation: str,
        event_type: str,
        *,
        target_version: int | None,
        persisted_events: Iterable[DurableEventEnvelope],
    ) -> dict[str, Any]:
        checked_type = _text(event_type, "event_type")
        persisted = tuple(persisted_events)
        if len(persisted) > MAX_COLLECTION_ITEMS or any(
            not isinstance(event, DurableEventEnvelope) for event in persisted
        ):
            raise ContractError("durable event preflight inventory is invalid")
        with self._lock:
            registrations = tuple(
                item
                for (registered_type, _), item in sorted(self._items.items())
                if registered_type == checked_type
            )
            if not registrations:
                raise ContractError("durable event preflight type is not registered")
            relevant = tuple(
                event for event in persisted if event.event_type == checked_type
            )
            blockers: list[str] = []
            if operation == "UNINSTALL":
                if checked_type not in self._optional_unknown_types:
                    blockers.append("event type is not allowlisted as optional")
                if relevant:
                    blockers.append("persisted event history remains")
                if any(item.semantics == "REQUIRED_STATE" for item in registrations):
                    blockers.append("required state depends on the event type")
                if any(item.projections for item in registrations):
                    blockers.append("registered projections remain")
                from_version = max(item.schema_version for item in registrations)
            elif operation == "DOWNGRADE":
                if target_version is None:
                    raise ContractError("durable event downgrade target is required")
                target = _positive(target_version, "target_version")
                versions = {item.schema_version for item in registrations}
                from_version = max(versions)
                if target not in versions or target >= from_version:
                    raise ContractError("invalid durable event downgrade target")
                newer = tuple(
                    item for item in registrations if item.schema_version > target
                )
                if any(event.schema_version > target for event in relevant):
                    blockers.append("newer persisted events require migration")
                if checked_type not in self._optional_unknown_types:
                    blockers.append("event type is not allowlisted as optional")
                if any(item.semantics == "REQUIRED_STATE" for item in newer):
                    blockers.append("newer required state registration remains")
                if any(item.projections for item in newer):
                    blockers.append("newer registered projections remain")
                if any(item.compatibility != "FULL" for item in newer):
                    blockers.append("newer registration is not fully compatible")
            else:
                raise ContractError("unknown durable event preflight operation")
            record = {
                "operation": operation,
                "type": checked_type,
                "fromVersion": from_version,
                "targetVersion": target_version,
                "persistedEventCount": len(relevant),
                "decision": "ALLOW" if not blockers else "BLOCK",
                "blockers": blockers,
            }
            self._audit_record(record)
            if blockers:
                raise ContractError(
                    f"durable event {operation.lower()} preflight blocked: "
                    + "; ".join(blockers)
                )
            return record

    def preflight_uninstall(
        self,
        event_type: str,
        *,
        persisted_events: Iterable[DurableEventEnvelope],
    ) -> dict[str, Any]:
        return self._preflight(
            "UNINSTALL",
            event_type,
            target_version=None,
            persisted_events=persisted_events,
        )

    def preflight_downgrade(
        self,
        event_type: str,
        target_version: int,
        *,
        persisted_events: Iterable[DurableEventEnvelope],
    ) -> dict[str, Any]:
        return self._preflight(
            "DOWNGRADE",
            event_type,
            target_version=target_version,
            persisted_events=persisted_events,
        )

    def _validate(
        self, item: EventRegistration, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise ContractError("event payload must be an object")
        validator = (
            self._validators.get(item.validator)
            if isinstance(item.validator, str)
            else item.validator
        )
        if validator is None:
            raise UnsupportedContractError("durable event validator is unavailable")
        if callable(validator):
            try:
                valid = bool(validator(payload))
            except Exception as exc:
                raise ContractError("event schema validator failed") from exc
            if not valid:
                raise ContractError("event schema validation failed")
        return payload

    def replay(
        self,
        event_type: str,
        version: int,
        payload: Mapping[str, Any],
        *,
        unknown_optional: bool = False,
        target_version: int | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get((event_type, version))
            if item is None:
                if unknown_optional and event_type in self._optional_unknown_types:
                    self._audit_record(
                        {
                            "operation": "REPLAY",
                            "type": event_type,
                            "schemaVersion": version,
                            "decision": "SKIP_OPTIONAL_UNKNOWN",
                        }
                    )
                    return None
                raise ContractError("unknown required durable event")
            value: Mapping[str, Any] = self._validate(item, payload)
            target = target_version or version
            if target < version or target - version > MAX_COLLECTION_ITEMS:
                raise ContractError("invalid durable event target version")
            while version < target:
                next_item = self._items.get((event_type, version + 1))
                if next_item is None:
                    raise ContractError("missing durable event upgrader")
                upgrader = (
                    self._upgraders.get(next_item.upgrader)
                    if isinstance(next_item.upgrader, str)
                    else next_item.upgrader
                )
                if callable(upgrader):
                    try:
                        value = upgrader(value)
                    except Exception as exc:
                        raise ContractError("event upgrade failed") from exc
                elif not isinstance(next_item.upgrader, str):
                    raise ContractError("event upgrader is unavailable")
                value = self._validate(next_item, value)
                version += 1
            return dict(value)

    def _replay_causal(
        self,
        events: Sequence[DurableEventEnvelope],
        *,
        operation: str,
        operation_id: str,
        target_versions: Mapping[str, int] | None,
    ) -> tuple[DurableEventEnvelope, ...]:
        identifier = _text(operation_id, f"{operation.lower()}_id")
        sequence = tuple(events)
        if (
            not sequence
            or len(sequence) > MAX_COLLECTION_ITEMS
            or any(not isinstance(event, DurableEventEnvelope) for event in sequence)
        ):
            raise ContractError("causal replay requires a bounded typed event stream")
        observed_types = {event.event_type for event in sequence}
        targets: dict[str, int] = {}
        if target_versions is not None:
            if set(target_versions) != observed_types:
                raise ContractError(
                    "migration targets must cover the exact causal event types"
                )
            targets = {
                _text(event_type, "migration event type"): _positive(
                    version, "migration target version"
                )
                for event_type, version in target_versions.items()
            }
        seen: dict[str, str] = {}
        output: list[DurableEventEnvelope] = []
        with self._lock:
            for event in sequence:
                if event.event_id in seen:
                    raise ContractError("causal replay event IDs contain duplicates")
                if event.causation_id is not None:
                    parent_correlation = seen.get(event.causation_id)
                    if parent_correlation is None:
                        raise ContractError("causal replay predecessor is missing")
                    if parent_correlation != event.correlation_id:
                        raise ContractError(
                            "causal replay crosses correlation boundaries"
                        )
                target = (
                    targets[event.event_type]
                    if target_versions is not None
                    else event.schema_version
                )
                value = self.replay(
                    event.event_type,
                    event.schema_version,
                    event.payload,
                    unknown_optional=True,
                    target_version=target,
                )
                seen[event.event_id] = event.correlation_id
                if value is None:
                    continue
                output.append(
                    DurableEventEnvelope(
                        event.event_id,
                        event.event_type,
                        target,
                        value,
                        event.correlation_id,
                        event.causation_id,
                    )
                )
            self._audit_record(
                {
                    "operation": operation,
                    "operationId": identifier,
                    "inputCount": len(sequence),
                    "outputCount": len(output),
                    "eventIds": [event.event_id for event in sequence],
                    "decision": "REPLAYED",
                }
            )
        return tuple(output)

    def replay_for_fork(
        self,
        events: Sequence[DurableEventEnvelope],
        *,
        fork_id: str,
    ) -> tuple[DurableEventEnvelope, ...]:
        return self._replay_causal(
            events,
            operation="FORK_REPLAY",
            operation_id=fork_id,
            target_versions=None,
        )

    def replay_for_migration(
        self,
        events: Sequence[DurableEventEnvelope],
        *,
        migration_id: str,
        target_versions: Mapping[str, int],
    ) -> tuple[DurableEventEnvelope, ...]:
        return self._replay_causal(
            events,
            operation="MIGRATION_REPLAY",
            operation_id=migration_id,
            target_versions=target_versions,
        )


class IngressKind(StrEnum):
    USER_INPUT = "USER_INPUT"
    TOOL_RESULT = "TOOL_RESULT"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"
    APPROVAL_INPUT = "APPROVAL_INPUT"
    CONTROL_INPUT = "CONTROL_INPUT"


EXTERNAL_PRODUCER_DEFAULT_KINDS = frozenset(
    {
        IngressKind.TOOL_RESULT.value,
        IngressKind.EXTERNAL_EVENT.value,
        IngressKind.APPROVAL_INPUT.value,
        IngressKind.CONTROL_INPUT.value,
    }
)


@dataclass(frozen=True, slots=True)
class TypedIngress:
    ingress_id: str
    kind: str
    producer_execution_id: str
    event_id: str
    causation_id: str
    correlation_id: str
    content: str | tuple[Mapping[str, Any], ...]
    originating_call_id: str | None = None
    deduplication_key: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "ingress_id",
            "producer_execution_id",
            "event_id",
            "causation_id",
            "correlation_id",
        ):
            _text(getattr(self, name), name)
        if self.kind not in {item.value for item in IngressKind}:
            raise ContractError("unknown ingress kind")
        if self.originating_call_id is not None:
            _text(self.originating_call_id, "originating_call_id")
        if self.deduplication_key is not None:
            _text(self.deduplication_key, "deduplication_key")
        if not isinstance(self.content, str) and not isinstance(
            self.content, (tuple, list)
        ):
            raise ContractError(
                "ingress content must remain typed text or content parts"
            )
        if isinstance(self.content, (tuple, list)):
            for part in self.content:
                if not isinstance(part, Mapping):
                    raise ContractError("typed ingress content parts must be objects")
                _freeze(part)
        if len(canonical_json_bytes(self.to_wire())) > MAX_INVOCATION_BYTES:
            raise ContractError("typed ingress exceeds the byte limit")

    def to_wire(self) -> dict[str, Any]:
        return {
            "ingressId": self.ingress_id,
            "kind": self.kind,
            "producerExecutionId": self.producer_execution_id,
            "originatingCallId": self.originating_call_id,
            "eventId": self.event_id,
            "causationId": self.causation_id,
            "correlationId": self.correlation_id,
            "content": _thaw(self.content),
            **(
                {"deduplicationKey": self.deduplication_key}
                if self.deduplication_key
                else {}
            ),
        }


@dataclass(frozen=True, slots=True)
class IngressHistoryPage:
    events: tuple[TypedIngress, ...]
    next_cursor: str | None
    has_more: bool

    def __post_init__(self) -> None:
        if any(not isinstance(event, TypedIngress) for event in self.events):
            raise ContractError("ingress history page contains an invalid event")
        if self.next_cursor is not None:
            _sha256(self.next_cursor, "ingress history cursor")
        if not isinstance(self.has_more, bool):
            raise ContractError("ingress history continuation flag must be boolean")

    def to_wire(self) -> dict[str, Any]:
        return {
            "events": [event.to_wire() for event in self.events],
            "nextCursor": self.next_cursor,
            "hasMore": self.has_more,
        }


def _typed_ingress_content(
    value: Any,
) -> str | tuple[Mapping[str, Any], ...]:
    if isinstance(value, str):
        return value
    if not isinstance(value, (list, tuple)):
        raise ContractError("ingress content must remain typed text or content parts")
    parts: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ContractError("typed ingress content parts must be objects")
        frozen = _freeze(item)
        if not isinstance(frozen, Mapping):
            raise ContractError("typed ingress content part did not remain an object")
        parts.append(frozen)
    return tuple(parts)


class IngressLedger:
    def __init__(self) -> None:
        self._seen: dict[str, tuple[str, str]] = {}
        self._lock = threading.RLock()

    def accept(
        self, key: str, kind: str, *, envelope_digest: str | None = None
    ) -> bool:
        _text(key, "deduplication key")
        if kind not in {item.value for item in IngressKind}:
            raise ContractError("unknown ingress kind")
        fingerprint = envelope_digest or ""
        with self._lock:
            current = self._seen.get(key)
            if current is not None:
                if current != (kind, fingerprint):
                    raise ContractError("conflicting duplicate ingress")
                return False
            self._seen[key] = (kind, fingerprint)
            return True


class IngressRouter:
    def __init__(self, ledger: IngressLedger | None = None) -> None:
        self.ledger = ledger or IngressLedger()
        self._events: dict[tuple[str, str, str], TypedIngress] = {}
        self._event_ids: dict[tuple[str, str, str], tuple[str, str, str]] = {}
        self._event_order: dict[tuple[str, str, str], int] = {}
        self._event_digests: dict[tuple[str, str, str], str] = {}
        self._producers: dict[tuple[str, str, str], set[str]] = {}
        self._next_sequence = 1
        self._lock = threading.RLock()

    @staticmethod
    def _producer_policy(
        value: Mapping[str, Iterable[str]] | Iterable[str],
    ) -> dict[str, frozenset[str]]:
        raw: Iterable[tuple[str, Iterable[str]]]
        if isinstance(value, Mapping):
            raw = value.items()
        else:
            if isinstance(value, (str, bytes)):
                raise ContractError("ingress producer policy must be a collection")
            raw = ((producer, EXTERNAL_PRODUCER_DEFAULT_KINDS) for producer in value)
        output: dict[str, frozenset[str]] = {}
        for producer, allowed in raw:
            name = _text(producer, "authorized producer")
            if name in output:
                raise ContractError("ingress producer policy contains duplicates")
            if isinstance(allowed, (str, bytes)):
                raise ContractError("ingress producer kinds must be a collection")
            kinds = frozenset(_text(item, "allowed ingress kind") for item in allowed)
            if not kinds or not kinds <= {item.value for item in IngressKind}:
                raise ContractError("ingress producer kind policy is invalid")
            if IngressKind.USER_INPUT.value in kinds:
                raise ContractError(
                    "external ingress producers cannot be granted USER_INPUT"
                )
            output[name] = kinds
        return output

    @staticmethod
    def _scope(tenant_id: str, project_id: str) -> tuple[str, str]:
        return (_text(tenant_id, "tenant_id"), _text(project_id, "project_id"))

    @staticmethod
    def _deduplication_identity(scope: tuple[str, str], ingress: TypedIngress) -> str:
        return _cas_digest(
            {
                "tenantId": scope[0],
                "projectId": scope[1],
                "producerExecutionId": ingress.producer_execution_id,
                "deduplicationKey": ingress.deduplication_key or ingress.event_id,
            },
            domain="delta-typed-ingress-deduplication",
        )

    def _validate_causation_locked(
        self,
        scope: tuple[str, str],
        ingress: TypedIngress,
        event_key: tuple[str, str, str],
    ) -> None:
        event_identity = (*scope, ingress.event_id)
        current_identity = self._event_ids.get(event_identity)
        if current_identity is not None and current_identity != event_key:
            raise ContractError("ingress event ID is already bound in this scope")
        seen = {ingress.event_id}
        cursor: str | None = ingress.causation_id
        while cursor is not None:
            if cursor in seen:
                raise ContractError("ingress causation contains a cycle")
            seen.add(cursor)
            parent_key = self._event_ids.get((*scope, cursor))
            if parent_key is None:
                break
            parent = self._events[parent_key]
            if parent.correlation_id != ingress.correlation_id:
                raise ContractError("ingress causation crosses correlation boundaries")
            cursor = parent.causation_id
        for candidate_key, candidate in self._events.items():
            if (
                candidate_key[:2] == scope
                and candidate.causation_id == ingress.event_id
                and candidate.correlation_id != ingress.correlation_id
            ):
                raise ContractError("ingress causal descendants change correlation")

    def _history_cursor(
        self,
        scope: tuple[str, str],
        correlation_id: str,
        event_key: tuple[str, str, str],
    ) -> str:
        return _cas_digest(
            {
                "tenantId": scope[0],
                "projectId": scope[1],
                "correlationId": correlation_id,
                "sequence": self._event_order[event_key],
                "envelopeDigest": self._event_digests[event_key],
            },
            domain="delta-typed-ingress-history-cursor",
        )

    def accept(
        self,
        ingress: TypedIngress,
        *,
        tenant_id: str,
        project_id: str,
        authorized_producers: Mapping[str, Iterable[str]] | Iterable[str],
        pending_calls: Iterable[str] = (),
    ) -> bool:
        if not isinstance(ingress, TypedIngress):
            raise ContractError("typed ingress is required")
        scope = self._scope(tenant_id, project_id)
        producer_policy = self._producer_policy(authorized_producers)
        allowed_kinds = producer_policy.get(ingress.producer_execution_id)
        if allowed_kinds is None:
            raise ContractError(
                "ingress producer is not authorized for this resource scope"
            )
        if ingress.kind not in allowed_kinds:
            raise ContractError("ingress kind is not authorized for this producer")
        if (
            ingress.kind == IngressKind.TOOL_RESULT
            and ingress.originating_call_id is None
        ):
            raise ContractError("tool result ingress requires originating call")
        pending = frozenset(_text(item, "pending call") for item in pending_calls)
        if (
            ingress.kind == IngressKind.TOOL_RESULT
            and ingress.originating_call_id not in pending
        ):
            raise ContractError(
                "tool result ingress has no pending or reconciled origin"
            )
        envelope_digest = _cas_digest(ingress.to_wire(), domain="delta-typed-ingress")
        event_key = (*scope, ingress.ingress_id)
        with self._lock:
            current = self._events.get(event_key)
            if current is not None and current != ingress:
                raise ContractError("ingress identity replay diverged")
            self._validate_causation_locked(scope, ingress, event_key)
            if (
                current is None
                and sum(key[:2] == scope for key in self._events)
                >= MAX_COLLECTION_ITEMS
            ):
                raise ContractError("typed ingress history exceeds the bounded limit")
            accepted = self.ledger.accept(
                self._deduplication_identity(scope, ingress),
                ingress.kind,
                envelope_digest=envelope_digest,
            )
            if accepted:
                self._events[event_key] = ingress
                self._event_ids[(*scope, ingress.event_id)] = event_key
                self._event_order[event_key] = self._next_sequence
                self._event_digests[event_key] = envelope_digest
                self._next_sequence += 1
                self._producers.setdefault(
                    (*scope, ingress.producer_execution_id), set()
                ).add(ingress.ingress_id)
            elif current is None:
                raise ContractError("deduplicated ingress lacks its bound identity")
        return accepted

    def history_page(
        self,
        correlation_id: str,
        *,
        tenant_id: str,
        project_id: str,
        after_cursor: str | None = None,
        page_size: int = 100,
    ) -> IngressHistoryPage:
        if page_size < 1 or page_size > 1000 or isinstance(page_size, bool):
            raise ContractError("invalid ingress page size")
        checked_correlation = _text(correlation_id, "correlation_id")
        scope = self._scope(tenant_id, project_id)
        if after_cursor is not None:
            _sha256(after_cursor, "ingress history cursor")
        with self._lock:
            event_keys = sorted(
                (
                    key
                    for key, item in self._events.items()
                    if key[:2] == scope and item.correlation_id == checked_correlation
                ),
                key=self._event_order.__getitem__,
            )
            start = 0
            if after_cursor is not None:
                matched = [
                    index
                    for index, key in enumerate(event_keys)
                    if hmac.compare_digest(
                        self._history_cursor(scope, checked_correlation, key),
                        after_cursor,
                    )
                ]
                if len(matched) != 1:
                    raise ContractError(
                        "ingress history cursor is stale or scope-mismatched"
                    )
                start = matched[0] + 1
            selected_keys = event_keys[start : start + page_size]
            events = tuple(self._events[key] for key in selected_keys)
            next_cursor = (
                self._history_cursor(scope, checked_correlation, selected_keys[-1])
                if selected_keys
                else None
            )
            return IngressHistoryPage(
                events,
                next_cursor,
                start + len(selected_keys) < len(event_keys),
            )

    def history(
        self,
        correlation_id: str,
        *,
        tenant_id: str,
        project_id: str,
        page: int | None = None,
        page_size: int = 100,
        cursor: str | None = None,
    ) -> tuple[TypedIngress, ...]:
        if page not in {None, 0}:
            raise ContractError(
                "offset ingress pagination is unsupported; use a stable cursor"
            )
        return self.history_page(
            correlation_id,
            tenant_id=tenant_id,
            project_id=project_id,
            after_cursor=cursor,
            page_size=page_size,
        ).events

    def restore(
        self,
        ingress: TypedIngress,
        *,
        tenant_id: str,
        project_id: str,
        envelope_digest: str,
    ) -> TypedIngress:
        """Restore a host-authorized durable ingress record without re-admission."""

        if not isinstance(ingress, TypedIngress):
            raise ContractError("restored ingress must be typed")
        expected = _cas_digest(ingress.to_wire(), domain="delta-typed-ingress")
        if not hmac.compare_digest(
            _text(envelope_digest, "ingress envelope digest"), expected
        ):
            raise ContractError("restored ingress envelope digest is invalid")
        scope = self._scope(tenant_id, project_id)
        event_key = (*scope, ingress.ingress_id)
        with self._lock:
            current = self._events.get(event_key)
            if current is not None and current != ingress:
                raise ContractError("restored ingress identity conflicts")
            self._validate_causation_locked(scope, ingress, event_key)
            if (
                current is None
                and sum(key[:2] == scope for key in self._events)
                >= MAX_COLLECTION_ITEMS
            ):
                raise ContractError("typed ingress history exceeds the bounded limit")
            accepted = self.ledger.accept(
                self._deduplication_identity(scope, ingress),
                ingress.kind,
                envelope_digest=expected,
            )
            if accepted:
                self._events[event_key] = ingress
                self._event_ids[(*scope, ingress.event_id)] = event_key
                self._event_order[event_key] = self._next_sequence
                self._event_digests[event_key] = expected
                self._next_sequence += 1
                self._producers.setdefault(
                    (*scope, ingress.producer_execution_id), set()
                ).add(ingress.ingress_id)
            elif current is None:
                raise ContractError(
                    "restored ingress deduplication identity is missing"
                )
        return ingress


@dataclass(frozen=True, slots=True)
class SubagentSpec:
    provider: str
    model: str
    reasoning_effort: str
    max_output_tokens: int
    authority: frozenset[str]
    tools: frozenset[str]
    invocation_id: str
    parent_execution_id: str
    environment_id: str
    authority_snapshot_id: str
    budget_reservation_id: str
    tool_plan_hash: str
    cost_budget: str
    wall_clock_deadline: datetime

    def __post_init__(self) -> None:
        for name in (
            "provider",
            "model",
            "reasoning_effort",
            "invocation_id",
            "parent_execution_id",
            "environment_id",
            "authority_snapshot_id",
            "budget_reservation_id",
        ):
            _text(getattr(self, name), name)
        if self.reasoning_effort not in {
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "ultra",
        }:
            raise UnsupportedContractError("subagent reasoning effort is unsupported")
        if (
            isinstance(self.max_output_tokens, bool)
            or self.max_output_tokens < 1
            or self.max_output_tokens > 1_000_000
        ):
            raise ContractError("max_output_tokens is outside the supported range")
        for value in (*self.authority, *self.tools):
            _text(value, "subagent scope")
        plan_hash = _sha256(self.tool_plan_hash, "tool_plan_hash")
        if not plan_hash.startswith("sha256:"):
            raise ContractError("tool_plan_hash must be a canonical SHA-256 digest")
        object.__setattr__(self, "cost_budget", _decimal_budget(self.cost_budget))
        checked_deadline = _aware(self.wall_clock_deadline, "wall_clock_deadline")
        assert checked_deadline is not None
        object.__setattr__(self, "wall_clock_deadline", checked_deadline)

    def validate_under(
        self,
        parent_authority: frozenset[str],
        parent_tools: frozenset[str],
        max_tokens: int,
        *,
        environment_id: str | None = None,
        parent_environment_id: str | None = None,
        reserved_budget: bool = True,
    ) -> None:
        if not self.authority <= parent_authority:
            raise ContractError("subagent authority widening")
        if not self.tools <= parent_tools:
            raise ContractError("subagent tool widening")
        if self.max_output_tokens > max_tokens:
            raise ContractError("subagent output budget exceeded")
        if (
            environment_id is not None
            and parent_environment_id is not None
            and environment_id != parent_environment_id
        ):
            raise ContractError("subagent environment widening")
        if not reserved_budget:
            raise ContractError("subagent budget is not reserved")

    def to_wire(self) -> dict[str, Any]:
        return {
            "invocationId": self.invocation_id,
            "parentExecutionId": self.parent_execution_id,
            "provider": self.provider,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "authoritySnapshotId": self.authority_snapshot_id,
            "environmentId": self.environment_id,
            "budgetReservationId": self.budget_reservation_id,
            "maxOutputTokens": self.max_output_tokens,
            "toolPlanHash": self.tool_plan_hash,
            "childAuthority": sorted(self.authority),
            "childTools": sorted(self.tools),
            "costBudget": self.cost_budget,
            "wallClockDeadline": _wire_time(
                self.wall_clock_deadline, "wall_clock_deadline"
            ),
        }


SubagentExecutionSpec = SubagentSpec


class SubagentSpecCompiler:
    @staticmethod
    def compile(
        *,
        provider: str,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        invocation_id: str,
        parent_execution_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        budget_reservation_id: str,
        parent_authority: Iterable[str] = (),
        child_authority: Iterable[str] = (),
        parent_tools: Iterable[str] = (),
        child_tools: Iterable[str] = (),
        parent_max_output_tokens: int,
        parent_environment_id: str,
        allowed_models: Iterable[tuple[str, str]],
        tool_plan_hash: str,
        cost_budget: str,
        wall_clock_deadline: datetime,
    ) -> SubagentSpec:
        allowed = frozenset(allowed_models)
        if (provider, model) not in allowed:
            raise UnsupportedContractError(
                "subagent provider/model tuple is not allowlisted"
            )
        checked_deadline = _aware(wall_clock_deadline, "wall_clock_deadline")
        assert checked_deadline is not None
        if checked_deadline <= datetime.now(UTC):
            raise ContractError("subagent wall-clock deadline has expired")
        spec = SubagentSpec(
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            authority=frozenset(child_authority),
            tools=frozenset(child_tools),
            invocation_id=invocation_id,
            parent_execution_id=parent_execution_id,
            environment_id=environment_id,
            authority_snapshot_id=authority_snapshot_id,
            budget_reservation_id=budget_reservation_id,
            tool_plan_hash=tool_plan_hash,
            cost_budget=cost_budget,
            wall_clock_deadline=checked_deadline,
        )
        spec.validate_under(
            frozenset(parent_authority),
            frozenset(parent_tools),
            _positive(parent_max_output_tokens, "parent_max_output_tokens"),
            environment_id=environment_id,
            parent_environment_id=_text(parent_environment_id, "parent_environment_id"),
            reserved_budget=bool(budget_reservation_id),
        )
        return spec


@dataclass(frozen=True, slots=True)
class WorkspaceAuthority:
    """Host-owned authorization for one managed workspace.

    Merely naming a path or repository in an invocation never creates write
    authority.  The host must register the exact managed checkout, immutable
    base revision, owners and bounded write scopes before a lease can be
    issued or transferred.
    """

    workspace_id: str
    repository_id: str
    base_revision: str
    write_scopes: tuple[str, ...]
    owners: frozenset[str]
    checkout_kind: str = "MANAGED_WORKTREE"

    def __post_init__(self) -> None:
        for name in ("workspace_id", "repository_id", "base_revision"):
            _text(getattr(self, name), name)
        if self.checkout_kind != "MANAGED_WORKTREE":
            raise ContractError(
                "only a registered managed worktree may receive a lease"
            )
        scopes = tuple(_workspace_scope(value) for value in self.write_scopes)
        if (
            not scopes
            or len(scopes) > MAX_COLLECTION_ITEMS
            or len(set(scopes)) != len(scopes)
        ):
            raise ContractError(
                "workspace authority requires exact non-empty write scopes"
            )
        if not self.owners or len(self.owners) > MAX_COLLECTION_ITEMS:
            raise ContractError("workspace authority requires at least one exact owner")
        for owner in self.owners:
            _text(owner, "workspace owner")
        object.__setattr__(self, "write_scopes", scopes)

    def permits_scopes(self, requested: Iterable[str]) -> bool:
        values = tuple(_workspace_scope(value) for value in requested)
        if not values:
            return False
        return all(
            any(
                value == allowed or value.startswith(allowed.rstrip("/") + "/")
                for allowed in self.write_scopes
            )
            for value in values
        )


@dataclass(frozen=True, slots=True)
class PendingToolCallBinding:
    call_id: str
    attempt: int
    invocation_id: str
    execution_plan_hash: str
    environment_id: str
    tool_id: str
    authority_snapshot_id: str

    def __post_init__(self) -> None:
        _text(self.call_id, "pending call id")
        _positive(self.attempt, "pending call attempt")
        _text(self.invocation_id, "pending invocation id")
        _sha256(self.execution_plan_hash, "pending execution plan hash")
        _text(self.environment_id, "pending environment id")
        _text(self.tool_id, "pending tool id")
        _sha256(self.authority_snapshot_id, "pending authority snapshot id")

    def to_wire(self) -> dict[str, Any]:
        return _wire_dataclass(self)


@dataclass(frozen=True, slots=True)
class SubagentBudgetReservation:
    reservation_id: str
    invocation_id: str
    parent_execution_id: str
    environment_id: str
    authority_snapshot_id: str
    provider: str
    model: str
    reasoning_effort: str
    child_authority: frozenset[str]
    child_tools: frozenset[str]
    max_output_tokens: int
    max_cost_budget: str
    wall_clock_deadline: datetime
    tool_plan_hash: str

    def __post_init__(self) -> None:
        _text(self.reservation_id, "budget reservation id")
        for name in (
            "invocation_id",
            "parent_execution_id",
            "environment_id",
            "provider",
            "model",
            "reasoning_effort",
        ):
            _text(getattr(self, name), f"budget reservation {name}")
        if self.reasoning_effort not in {
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "ultra",
        }:
            raise UnsupportedContractError(
                "budget reservation reasoning effort is unsupported"
            )
        _sha256(
            self.authority_snapshot_id,
            "budget reservation authority snapshot id",
        )
        for value in (*self.child_authority, *self.child_tools):
            _text(value, "budget reservation child scope")
        _positive(self.max_output_tokens, "budget reservation tokens")
        object.__setattr__(
            self,
            "max_cost_budget",
            _decimal_budget(self.max_cost_budget, "budget reservation cost"),
        )
        checked_deadline = _aware(
            self.wall_clock_deadline, "budget reservation deadline"
        )
        assert checked_deadline is not None
        object.__setattr__(self, "wall_clock_deadline", checked_deadline)
        _sha256(self.tool_plan_hash, "budget reservation tool plan hash")

    def to_wire(self) -> dict[str, Any]:
        return {
            "reservationId": self.reservation_id,
            "invocationId": self.invocation_id,
            "parentExecutionId": self.parent_execution_id,
            "environmentId": self.environment_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "provider": self.provider,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "childAuthority": sorted(self.child_authority),
            "childTools": sorted(self.child_tools),
            "maxOutputTokens": self.max_output_tokens,
            "maxCostBudget": self.max_cost_budget,
            "wallClockDeadline": _wire_time(
                self.wall_clock_deadline, "budget reservation deadline"
            ),
            "toolPlanHash": self.tool_plan_hash,
        }


@dataclass(frozen=True, slots=True)
class EnvironmentSettingsBinding:
    server_id: str
    environment_id: str
    settings_authority: Mapping[str, Any]
    settings_digest: str
    previous_settings_authority: Mapping[str, Any] | None = None
    previous_settings_digest: str | None = None
    previous_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.server_id, "environment server id")
        _text(self.environment_id, "environment id")
        frozen = _freeze(_mapping(self.settings_authority, "settings authority"))
        expected = _cas_digest(frozen, domain="delta-environment-settings-authority")
        if not hmac.compare_digest(
            _normalize_sha256(self.settings_digest, "settings digest"), expected
        ):
            raise ContractError("settings digest does not bind settings authority")
        object.__setattr__(self, "settings_authority", frozen)
        if (self.previous_settings_authority is None) is not (
            self.previous_settings_digest is None
        ):
            raise ContractError(
                "previous settings authority and digest must be supplied together"
            )
        if (self.previous_settings_authority is None) is not (
            self.previous_snapshot_id is None
        ):
            raise ContractError(
                "previous settings authority and snapshot must be supplied together"
            )
        if self.previous_settings_authority is not None:
            previous = _freeze(
                _mapping(
                    self.previous_settings_authority, "previous settings authority"
                )
            )
            assert self.previous_settings_digest is not None
            expected_previous = _cas_digest(
                previous, domain="delta-environment-settings-authority"
            )
            if not hmac.compare_digest(
                _normalize_sha256(
                    self.previous_settings_digest, "previous settings digest"
                ),
                expected_previous,
            ):
                raise ContractError(
                    "previous settings digest does not bind settings authority"
                )
            object.__setattr__(self, "previous_settings_authority", previous)
            _text(self.previous_snapshot_id, "previous attachment snapshot id")

    def to_wire(self) -> dict[str, Any]:
        return {
            "serverId": self.server_id,
            "environmentId": self.environment_id,
            "settingsAuthority": _thaw(self.settings_authority),
            "settingsDigest": self.settings_digest,
            "previousSettingsAuthority": (
                None
                if self.previous_settings_authority is None
                else _thaw(self.previous_settings_authority)
            ),
            "previousSettingsDigest": self.previous_settings_digest,
            "previousSnapshotId": self.previous_snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class TurnEnvironment:
    environment_id: str
    server_id: str
    settings_authority: Mapping[str, Any]
    settings_digest: str

    def __post_init__(self) -> None:
        binding = EnvironmentSettingsBinding(
            self.server_id,
            self.environment_id,
            self.settings_authority,
            self.settings_digest,
        )
        object.__setattr__(self, "settings_authority", binding.settings_authority)

    def to_wire(self) -> dict[str, Any]:
        return {
            "environmentId": self.environment_id,
            "serverId": self.server_id,
            "settingsAuthority": _thaw(self.settings_authority),
            "settingsDigest": self.settings_digest,
        }


@dataclass(frozen=True, slots=True)
class BaseSkillOriginBinding:
    """Digest-bound Host receipt proving which v3 Skill owns an extension call."""

    skill_id: str
    skill_name: str
    owner_kernel: str
    execution_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    step_id: str
    invocation_id: str
    extension_skill: str
    environment_id: str
    receipt_ref: str
    receipt_state: str
    signing_key_id: str
    signature_algorithm: str
    receipt_digest: str
    signature: str

    ACTIVE_RECEIPT_STATES = frozenset(
        {"PLANNING", "EXECUTING", "RESUMING", "VERIFYING", "CERTIFYING"}
    )

    @classmethod
    def bind_host_receipt(
        cls,
        *,
        skill_id: str,
        skill_name: str,
        owner_kernel: str,
        execution_id: str,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        run_id: str,
        execution_epoch: int,
        fencing_generation: int,
        authority_revision: str,
        revision_set_id: str,
        step_id: str,
        invocation_id: str,
        extension_skill: str,
        environment_id: str,
        receipt_ref: str,
        receipt_state: str,
        signing_key_id: str = "local-self-attested",
        signature_algorithm: str = "LOCAL_SELF_ATTESTED",
        signature: str | None = None,
    ) -> "BaseSkillOriginBinding":
        claim = {
            "skillId": skill_id,
            "skillName": skill_name,
            "ownerKernel": owner_kernel,
            "executionId": execution_id,
            "tenantId": tenant_id,
            "projectId": project_id,
            "actorId": actor_id,
            "runId": run_id,
            "executionEpoch": execution_epoch,
            "fencingGeneration": fencing_generation,
            "authorityRevision": authority_revision,
            "revisionSetId": revision_set_id,
            "stepId": step_id,
            "invocationId": invocation_id,
            "extensionSkill": extension_skill,
            "environmentId": environment_id,
            "receiptRef": receipt_ref,
            "receiptState": receipt_state,
            "signingKeyId": signing_key_id,
            "signatureAlgorithm": signature_algorithm,
        }
        receipt_digest = _cas_digest(
            claim,
            domain="delta-base-skill-execution-receipt",
        )
        return cls(
            skill_id,
            skill_name,
            owner_kernel,
            execution_id,
            tenant_id,
            project_id,
            actor_id,
            run_id,
            execution_epoch,
            fencing_generation,
            authority_revision,
            revision_set_id,
            step_id,
            invocation_id,
            extension_skill,
            environment_id,
            receipt_ref,
            receipt_state,
            signing_key_id,
            signature_algorithm,
            receipt_digest,
            signature or f"LOCAL_SELF_ATTESTED:{receipt_digest}",
        )

    def __post_init__(self) -> None:
        for name in (
            "skill_id",
            "skill_name",
            "owner_kernel",
            "execution_id",
            "tenant_id",
            "project_id",
            "actor_id",
            "run_id",
            "revision_set_id",
            "step_id",
            "invocation_id",
            "extension_skill",
            "environment_id",
            "receipt_ref",
            "receipt_state",
            "signing_key_id",
            "signature_algorithm",
            "signature",
        ):
            _text(getattr(self, name), name)
        _positive(self.execution_epoch, "execution_epoch")
        _positive(self.fencing_generation, "fencing_generation")
        _sha256(self.authority_revision, "authority_revision")
        _sha256(self.receipt_digest, "receipt_digest")
        if self.owner_kernel not in {f"K{index}" for index in range(1, 9)}:
            raise ContractError("base Skill origin owner kernel is invalid")
        if self.receipt_state not in self.ACTIVE_RECEIPT_STATES:
            raise ContractError("base Skill execution receipt is not active")
        if self.signature_algorithm not in {
            "ED25519",
            "ECDSA_P256_SHA256",
            "RSA_PSS_SHA256",
            "LOCAL_SELF_ATTESTED",
        }:
            raise ContractError("base Skill receipt signature algorithm is unsupported")

        # Import lazily so the base registry remains the sole owner map without
        # creating a module initialization cycle through the package facade.
        from .skills import SKILL_REGISTRY

        descriptor = SKILL_REGISTRY.get(self.skill_name)
        if descriptor is None or descriptor.skill_id != self.skill_id:
            raise ContractError("base Skill origin is not in the exact v3 registry")
        if descriptor.kind == "kernel":
            allowed_kernels = {descriptor.owner}
        else:
            allowed_kernels = {
                dependency_descriptor.owner
                for dependency in descriptor.dependencies
                if (dependency_descriptor := SKILL_REGISTRY.get(dependency)) is not None
                and dependency_descriptor.kind == "kernel"
            }
        if self.owner_kernel not in allowed_kernels:
            raise ContractError(
                "base Skill origin does not extend the selected owner kernel"
            )
        if not hmac.compare_digest(self.receipt_digest, self.expected_receipt_digest):
            raise ContractError("base Skill execution receipt digest is invalid")

    def receipt_claim(self) -> dict[str, Any]:
        return {
            "skillId": self.skill_id,
            "skillName": self.skill_name,
            "ownerKernel": self.owner_kernel,
            "executionId": self.execution_id,
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "actorId": self.actor_id,
            "runId": self.run_id,
            "executionEpoch": self.execution_epoch,
            "fencingGeneration": self.fencing_generation,
            "authorityRevision": self.authority_revision,
            "revisionSetId": self.revision_set_id,
            "stepId": self.step_id,
            "invocationId": self.invocation_id,
            "extensionSkill": self.extension_skill,
            "environmentId": self.environment_id,
            "receiptRef": self.receipt_ref,
            "receiptState": self.receipt_state,
            "signingKeyId": self.signing_key_id,
            "signatureAlgorithm": self.signature_algorithm,
        }

    @property
    def expected_receipt_digest(self) -> str:
        return _cas_digest(
            self.receipt_claim(),
            domain="delta-base-skill-execution-receipt",
        )

    def to_wire(self) -> dict[str, Any]:
        return self.receipt_claim() | {
            "receiptDigest": self.receipt_digest,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceAuthority:
    """Trusted host snapshot consumed by every v3.1 extension invocation.

    It is minted by authenticated host code and resolved through a
    constructor-supplied callback; callers cannot self-assert parent grants,
    pending calls, budget reservations, security eligibility, environment
    ownership or evidence.  ``to_wire`` is the complete canonical authority
    claim used by ``authority_digest``; it is not an invocation input DTO.
    """

    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    step_id: str
    execution_id: str
    originating_base_skill: BaseSkillOriginBinding
    environment_ids: frozenset[str]
    environment_snapshot_ids: frozenset[str]
    permission_profile_versions: frozenset[str]
    capabilities: frozenset[str]
    tools: frozenset[str]
    tool_modes: frozenset[str]
    selected_models: frozenset[ModelSnapshot]
    originating_plan_hashes: frozenset[str]
    security_eligible: bool
    account_stable: bool
    security_bindings: Mapping[str, str]
    entitlements: Mapping[str, Any]
    owner_authority: AuthoritySnapshot
    parent_authority_snapshot: AuthoritySnapshot
    policy_permissions: frozenset[str]
    authority_result_snapshot_id: str
    authorized_producers: frozenset[str]
    pending_calls: frozenset[str]
    verified_evidence_refs: frozenset[str]
    executor_bindings: frozenset[tuple[str, str]]
    event_registrations: tuple[EventRegistration, ...]
    parent_execution_id: str
    parent_authority: frozenset[str]
    parent_tools: frozenset[str]
    parent_max_output_tokens: int
    budget_reservations: tuple[tuple[str, int], ...]
    allowed_subagent_models: frozenset[tuple[str, str]]
    delegation_allowed_invocations: frozenset[str]
    workspace_authorities: tuple[WorkspaceAuthority, ...]
    pending_call_bindings: tuple[PendingToolCallBinding, ...] = ()
    tool_contracts: Mapping[str, Any] = field(default_factory=dict)
    handler_digests: Mapping[str, str] = field(default_factory=dict)
    subagent_budget_reservations: tuple[SubagentBudgetReservation, ...] = ()
    environment_settings_bindings: tuple[EnvironmentSettingsBinding, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "project_id",
            "actor_id",
            "run_id",
            "authority_revision",
            "revision_set_id",
            "step_id",
            "execution_id",
            "authority_result_snapshot_id",
            "parent_execution_id",
        ):
            _text(getattr(self, name), name)
        _positive(self.execution_epoch, "execution_epoch")
        _positive(self.fencing_generation, "fencing_generation")
        _sha256(self.authority_revision, "authority_revision")
        _sha256(
            self.authority_result_snapshot_id,
            "authority_result_snapshot_id",
        )
        for name, values in (
            ("environment_ids", self.environment_ids),
            ("environment_snapshot_ids", self.environment_snapshot_ids),
            ("permission_profile_versions", self.permission_profile_versions),
            ("capabilities", self.capabilities),
            ("tools", self.tools),
            ("tool_modes", self.tool_modes),
            ("originating_plan_hashes", self.originating_plan_hashes),
            ("authorized_producers", self.authorized_producers),
            ("pending_calls", self.pending_calls),
            ("verified_evidence_refs", self.verified_evidence_refs),
            ("parent_authority", self.parent_authority),
            ("parent_tools", self.parent_tools),
            ("delegation_allowed_invocations", self.delegation_allowed_invocations),
        ):
            if len(values) > MAX_COLLECTION_ITEMS:
                raise ContractError(f"{name} contains too many values")
            for value in values:
                _text(value, name)
        if not self.environment_ids or not self.environment_snapshot_ids:
            raise ContractError("trusted authority requires environment identities")
        if not isinstance(self.originating_base_skill, BaseSkillOriginBinding):
            raise ContractError("trusted authority requires a typed base Skill origin")
        origin = self.originating_base_skill
        if (
            origin.tenant_id,
            origin.project_id,
            origin.actor_id,
            origin.run_id,
            origin.execution_epoch,
            origin.fencing_generation,
            origin.authority_revision,
            origin.revision_set_id,
            origin.step_id,
            origin.execution_id,
        ) != (
            self.tenant_id,
            self.project_id,
            self.actor_id,
            self.run_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
            self.step_id,
            self.execution_id,
        ):
            raise ContractError("base Skill origin escaped trusted authority scope")
        if origin.invocation_id != self.security_bindings.get(
            "invocationId"
        ) or origin.environment_id != self.security_bindings.get("environmentId"):
            raise ContractError(
                "base Skill origin escaped the invocation environment scope"
            )
        if origin.receipt_ref not in self.verified_evidence_refs:
            raise ContractError("base Skill execution receipt is not verified evidence")
        if len(self.selected_models) > MAX_COLLECTION_ITEMS or any(
            not isinstance(model, ModelSnapshot) for model in self.selected_models
        ):
            raise ContractError("trusted selected model inventory is invalid")
        for plan_hash in self.originating_plan_hashes:
            _sha256(plan_hash, "originating_plan_hash")
        if not isinstance(self.security_eligible, bool) or not isinstance(
            self.account_stable, bool
        ):
            raise ContractError("trusted security eligibility flags must be boolean")
        if set(self.security_bindings) != VerifiedSecurityContext.REQUIRED_BINDINGS:
            raise ContractError("trusted security bindings are not exact")
        for key, value in self.security_bindings.items():
            _text(key, "security binding key")
            _text(value, f"security binding {key}")
        frozen_entitlements = _freeze(
            _mapping(self.entitlements, "trusted entitlements")
        )
        object.__setattr__(
            self, "security_bindings", MappingProxyType(dict(self.security_bindings))
        )
        object.__setattr__(self, "entitlements", frozen_entitlements)
        if not isinstance(self.owner_authority, AuthoritySnapshot) or not isinstance(
            self.parent_authority_snapshot, AuthoritySnapshot
        ):
            raise ContractError("trusted environment authority snapshots are required")
        if self.owner_authority.snapshot_id != self.authority_revision:
            raise ContractError(
                "owner authority snapshot must equal the trusted authority revision"
            )
        if not self.policy_permissions <= self.owner_authority.permissions:
            # A global policy may only narrow an owner snapshot.  Parent
            # intersection is checked again when the result is calculated.
            raise ContractError("trusted policy permissions exceed owner authority")
        _positive(self.parent_max_output_tokens, "parent_max_output_tokens")
        executor_bindings: set[tuple[str, str]] = set()
        for binding in self.executor_bindings:
            if not isinstance(binding, tuple) or len(binding) != 2:
                raise ContractError("executor binding must be (environment, identity)")
            checked_binding = (
                _text(binding[0], "executor environment"),
                _text(binding[1], "executor identity"),
            )
            if checked_binding in executor_bindings:
                raise ContractError("duplicate executor binding")
            executor_bindings.add(checked_binding)
        registrations: set[tuple[str, int]] = set()
        if len(self.event_registrations) > MAX_COLLECTION_ITEMS:
            raise ContractError("trusted event registration inventory is too large")
        for registration in self.event_registrations:
            if not isinstance(registration, EventRegistration):
                raise ContractError("trusted event registration is invalid")
            if not isinstance(registration.validator, str) or not isinstance(
                registration.upgrader, str
            ):
                raise ContractError(
                    "trusted event registrations require stable handler identifiers"
                )
            registration_key = (
                registration.event_type,
                registration.schema_version,
            )
            if registration_key in registrations:
                raise ContractError("duplicate trusted event registration")
            registrations.add(registration_key)
        models: set[tuple[str, str]] = set()
        for model in self.allowed_subagent_models:
            if not isinstance(model, tuple) or len(model) != 2:
                raise ContractError(
                    "trusted subagent model must be a (provider, model) tuple"
                )
            checked_model = (
                _text(model[0], "subagent provider"),
                _text(model[1], "subagent model"),
            )
            if checked_model in models:
                raise ContractError("duplicate trusted subagent model")
            models.add(checked_model)
        reservations: dict[str, int] = {}
        for reservation_id, maximum in self.budget_reservations:
            key = _text(reservation_id, "budget reservation id")
            if key in reservations:
                raise ContractError("duplicate budget reservation")
            reservations[key] = _positive(maximum, "budget reservation tokens")
        workspaces: set[str] = set()
        for grant in self.workspace_authorities:
            if (
                not isinstance(grant, WorkspaceAuthority)
                or grant.workspace_id in workspaces
            ):
                raise ContractError("workspace authority inventory is invalid")
            workspaces.add(grant.workspace_id)
        pending_bindings: dict[str, PendingToolCallBinding] = {}
        for pending_binding in self.pending_call_bindings:
            if (
                not isinstance(pending_binding, PendingToolCallBinding)
                or pending_binding.call_id in pending_bindings
            ):
                raise ContractError("pending tool-call binding inventory is invalid")
            if (
                pending_binding.execution_plan_hash not in self.originating_plan_hashes
                or pending_binding.environment_id not in self.environment_ids
                or pending_binding.tool_id not in self.tools
                or pending_binding.invocation_id
                != self.security_bindings["invocationId"]
                or pending_binding.authority_snapshot_id != self.authority_revision
            ):
                raise ContractError(
                    "pending tool-call binding exceeds trusted plan/environment/tool authority"
                )
            pending_bindings[pending_binding.call_id] = pending_binding
        if set(pending_bindings) != set(self.pending_calls):
            raise ContractError(
                "pending calls and typed pending-call bindings must be exact"
            )
        checked_tool_contracts = _freeze(
            _mapping(self.tool_contracts, "trusted tool contracts")
        )
        checked_handler_digests = _mapping(
            self.handler_digests, "trusted handler digests"
        )
        if set(checked_tool_contracts) != set(checked_handler_digests):
            raise ContractError(
                "trusted tool contracts and handler digests must bind exact tools"
            )
        if set(checked_tool_contracts) - set(self.tools):
            raise ContractError("trusted tool plan bindings contain unauthorized tools")
        normalized_handler_digests: dict[str, str] = {}
        for tool_id, handler_digest in checked_handler_digests.items():
            _text(tool_id, "trusted handler tool id")
            normalized_handler_digests[tool_id] = _normalize_sha256(
                handler_digest, "trusted handler digest"
            )
        object.__setattr__(self, "tool_contracts", checked_tool_contracts)
        object.__setattr__(
            self,
            "handler_digests",
            MappingProxyType(normalized_handler_digests),
        )
        typed_reservations: set[str] = set()
        for reservation in self.subagent_budget_reservations:
            if (
                not isinstance(reservation, SubagentBudgetReservation)
                or reservation.reservation_id in typed_reservations
            ):
                raise ContractError("typed budget reservation inventory is invalid")
            if reservation.tool_plan_hash not in self.originating_plan_hashes:
                raise ContractError(
                    "typed budget reservation is not bound to a finalized tool plan"
                )
            if (
                reservation.invocation_id != self.security_bindings["invocationId"]
                or reservation.parent_execution_id != self.parent_execution_id
                or reservation.environment_id not in self.environment_ids
                or reservation.authority_snapshot_id != self.authority_revision
                or (reservation.provider, reservation.model)
                not in self.allowed_subagent_models
                or not reservation.child_authority <= self.parent_authority
                or not reservation.child_tools <= self.parent_tools
            ):
                raise ContractError(
                    "typed budget reservation exceeds trusted child execution authority"
                )
            typed_reservations.add(reservation.reservation_id)
        if typed_reservations and typed_reservations != set(reservations):
            raise ContractError(
                "legacy and typed budget reservation identities must be exact"
            )
        settings_bindings: set[tuple[str, str]] = set()
        for settings_binding in self.environment_settings_bindings:
            if not isinstance(settings_binding, EnvironmentSettingsBinding):
                raise ContractError("environment settings binding is invalid")
            settings_key = (
                settings_binding.server_id,
                settings_binding.environment_id,
            )
            if settings_key in settings_bindings:
                raise ContractError("duplicate environment settings binding")
            if settings_binding.environment_id not in self.environment_ids:
                raise ContractError(
                    "environment settings binding exceeds trusted environments"
                )
            settings_bindings.add(settings_key)

    def to_wire(self) -> dict[str, Any]:
        def snapshot(value: AuthoritySnapshot) -> dict[str, Any]:
            return {
                **value.to_wire(),
                "permissions": sorted(value.permissions),
            }

        return {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "actorId": self.actor_id,
            "runId": self.run_id,
            "executionEpoch": self.execution_epoch,
            "fencingGeneration": self.fencing_generation,
            "authorityRevision": self.authority_revision,
            "revisionSetId": self.revision_set_id,
            "stepId": self.step_id,
            "executionId": self.execution_id,
            "originatingBaseSkill": self.originating_base_skill.to_wire(),
            "environmentIds": sorted(self.environment_ids),
            "environmentSnapshotIds": sorted(self.environment_snapshot_ids),
            "permissionProfileVersions": sorted(self.permission_profile_versions),
            "capabilities": sorted(self.capabilities),
            "tools": sorted(self.tools),
            "toolModes": sorted(self.tool_modes),
            "selectedModels": sorted(
                (model.to_wire() for model in self.selected_models),
                key=canonical_json_bytes,
            ),
            "originatingPlanHashes": sorted(self.originating_plan_hashes),
            "securityEligible": self.security_eligible,
            "accountStable": self.account_stable,
            "securityBindings": {
                key: self.security_bindings[key]
                for key in sorted(self.security_bindings)
            },
            "entitlements": _thaw(self.entitlements),
            "ownerAuthority": snapshot(self.owner_authority),
            "parentAuthoritySnapshot": snapshot(self.parent_authority_snapshot),
            "policyPermissions": sorted(self.policy_permissions),
            "authorityResultSnapshotId": self.authority_result_snapshot_id,
            "authorizedProducers": sorted(self.authorized_producers),
            "pendingCalls": sorted(self.pending_calls),
            "verifiedEvidenceRefs": sorted(self.verified_evidence_refs),
            "executorBindings": [
                {
                    "environmentId": environment_id,
                    "executorIdentity": executor_identity,
                }
                for environment_id, executor_identity in sorted(self.executor_bindings)
            ],
            "eventRegistrations": [
                registration.to_wire()
                for registration in sorted(
                    self.event_registrations,
                    key=lambda item: (item.event_type, item.schema_version),
                )
            ],
            "parentExecutionId": self.parent_execution_id,
            "parentAuthority": sorted(self.parent_authority),
            "parentTools": sorted(self.parent_tools),
            "parentMaxOutputTokens": self.parent_max_output_tokens,
            "budgetReservations": [
                {"reservationId": reservation_id, "maxOutputTokens": maximum}
                for reservation_id, maximum in sorted(self.budget_reservations)
            ],
            "allowedSubagentModels": [
                {"provider": provider, "model": model}
                for provider, model in sorted(self.allowed_subagent_models)
            ],
            "delegationAllowedInvocations": sorted(self.delegation_allowed_invocations),
            "workspaceAuthorities": [
                {
                    "workspaceId": grant.workspace_id,
                    "repositoryId": grant.repository_id,
                    "baseRevision": grant.base_revision,
                    "writeScopes": list(grant.write_scopes),
                    "owners": sorted(grant.owners),
                    "checkoutKind": grant.checkout_kind,
                }
                for grant in sorted(
                    self.workspace_authorities,
                    key=lambda item: item.workspace_id,
                )
            ],
            "pendingCallBindings": [
                binding.to_wire()
                for binding in sorted(
                    self.pending_call_bindings, key=lambda item: item.call_id
                )
            ],
            "toolContracts": _thaw(self.tool_contracts),
            "handlerDigests": {
                key: self.handler_digests[key] for key in sorted(self.handler_digests)
            },
            "subagentBudgetReservations": [
                reservation.to_wire()
                for reservation in sorted(
                    self.subagent_budget_reservations,
                    key=lambda item: item.reservation_id,
                )
            ],
            "environmentSettingsBindings": [
                binding.to_wire()
                for binding in sorted(
                    self.environment_settings_bindings,
                    key=lambda item: (item.server_id, item.environment_id),
                )
            ],
        }

    @property
    def authority_digest(self) -> str:
        return _cas_digest(self.to_wire(), domain="delta-runtime-assurance-authority")

    def verify_binding(
        self, context: SecurityContext, invocation: "DeltaInvocation"
    ) -> None:
        expected = (
            self.tenant_id,
            self.project_id,
            self.actor_id,
            self.run_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
            self.step_id,
        )
        observed = (
            context.tenant_id,
            context.project_id,
            context.actor_id,
            context.run_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            invocation.revision_set_id,
            invocation.step_id,
        )
        if observed != expected:
            raise ContractError(
                "trusted runtime-assurance authority binding is stale or mismatched"
            )
        if invocation.tenant_id != self.tenant_id or invocation.run_id != self.run_id:
            raise ContractError("runtime-assurance invocation scope is mismatched")
        descriptor = DELTA_SKILL_REGISTRY.get(invocation.extension_skill or "")
        if (
            descriptor is None
            or self.originating_base_skill.extension_skill != descriptor.name
            or self.originating_base_skill.owner_kernel not in descriptor.owner_kernels
        ):
            raise ContractError(
                "base Skill origin does not own the selected internal extension"
            )
        expected_security = {
            "tenantId": self.tenant_id,
            "invocationId": invocation.invocation_id,
            "policyVersion": self.authority_revision,
        }
        if any(
            self.security_bindings.get(key) != value
            for key, value in expected_security.items()
        ):
            raise ContractError(
                "trusted security bindings do not cover this invocation"
            )

    def workspace(self, workspace_id: str) -> WorkspaceAuthority:
        for grant in self.workspace_authorities:
            if grant.workspace_id == workspace_id:
                return grant
        raise ContractError("workspace is not a registered managed checkout")

    def reserved_tokens(self, reservation_id: str) -> int:
        """Compatibility view backed only by the typed Host reservation."""

        return self.subagent_reservation(reservation_id).max_output_tokens

    def pending_call_binding(self, call_id: str) -> PendingToolCallBinding:
        checked = _text(call_id, "pending call id")
        for binding in self.pending_call_bindings:
            if hmac.compare_digest(binding.call_id, checked):
                return binding
        raise ContractError("tool result has no typed Host pending-call binding")

    def subagent_reservation(self, reservation_id: str) -> SubagentBudgetReservation:
        checked = _text(reservation_id, "budget reservation id")
        for reservation in self.subagent_budget_reservations:
            if hmac.compare_digest(reservation.reservation_id, checked):
                return reservation
        raise ContractError("subagent typed budget reservation is not host-authorized")

    def environment_settings(
        self, server_id: str, environment_id: str
    ) -> EnvironmentSettingsBinding:
        checked_server = _text(server_id, "environment server id")
        checked_environment = _text(environment_id, "environment id")
        for binding in self.environment_settings_bindings:
            if (
                binding.server_id == checked_server
                and binding.environment_id == checked_environment
            ):
                return binding
        raise ContractError(
            "environment settings are not bound by trusted Host authority"
        )

    def event_registration(
        self, event_type: str, schema_version: int
    ) -> EventRegistration:
        for registration in self.event_registrations:
            if (
                registration.event_type == event_type
                and registration.schema_version == schema_version
            ):
                return registration
        raise ContractError("plugin event registration is not host-authorized")


@dataclass(frozen=True, slots=True)
class DeltaInvocation:
    tenant_id: str
    goal_id: str
    run_id: str
    execution_epoch: int
    step_id: str
    invocation_id: str
    revision_set_id: str
    extension_skill: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "goal_id",
            "run_id",
            "step_id",
            "invocation_id",
            "revision_set_id",
        ):
            _text(getattr(self, name), name)
        _positive(self.execution_epoch, "execution_epoch")
        if self.extension_skill is not None:
            _text(self.extension_skill, "extension_skill")
        if not isinstance(self.payload, Mapping):
            raise ContractError("delta invocation payload must be an object")
        frozen_payload = _freeze(self.payload)
        if len(canonical_json_bytes(frozen_payload)) > MAX_INVOCATION_BYTES:
            raise ContractError("delta invocation payload exceeds the byte limit")
        object.__setattr__(self, "payload", frozen_payload)

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "tenantId": self.tenant_id,
            "goalId": self.goal_id,
            "runId": self.run_id,
            "executionEpoch": self.execution_epoch,
            "stepId": self.step_id,
            "invocationId": self.invocation_id,
            "revisionSetId": self.revision_set_id,
        }
        if self.extension_skill is not None:
            output["extensionSkill"] = self.extension_skill
        if self.payload:
            output["payload"] = _thaw(self.payload)
        return output


@dataclass(frozen=True, slots=True)
class DeltaResult:
    invocation_id: str
    status: ResultStatus | str
    evidence_refs: tuple[str, ...] = ()
    proof_obligation_refs: tuple[str, ...] = ()
    message: str | None = None

    def __post_init__(self) -> None:
        _text(self.invocation_id, "invocation_id")
        try:
            ResultStatus(self.status)
        except ValueError as exc:
            raise ContractError("invalid delta result status") from exc
        for value in (*self.evidence_refs, *self.proof_obligation_refs):
            _text(value, "evidence/proof reference")
        if (
            len(self.evidence_refs) > MAX_COLLECTION_ITEMS
            or len(self.proof_obligation_refs) > MAX_COLLECTION_ITEMS
        ):
            raise ContractError("delta result contains too many references")
        if len(set(self.evidence_refs)) != len(self.evidence_refs) or len(
            set(self.proof_obligation_refs)
        ) != len(self.proof_obligation_refs):
            raise ContractError("delta result contains duplicate references")
        if self.message is not None:
            _text(self.message, "message")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "invocationId": self.invocation_id,
            "status": ResultStatus(self.status).value,
            "evidenceRefs": list(self.evidence_refs),
        }
        if self.proof_obligation_refs:
            output["proofObligationRefs"] = list(self.proof_obligation_refs)
        if self.message is not None:
            output["message"] = self.message
        return output


@dataclass(frozen=True, slots=True)
class DeltaSkillDescriptor:
    skill_id: str
    name: str
    priority: str
    owner_kernels: tuple[str, ...]
    source_path: str
    routable: bool = False
    dependencies: tuple[str, ...] = ()
    handler: str = ""

    def __post_init__(self) -> None:
        for name in ("skill_id", "name", "priority", "source_path", "handler"):
            _text(getattr(self, name), name)
        if self.priority not in {"P0", "P1"} or self.routable:
            raise ContractError("delta Skill descriptor violates extension invariants")
        _strings(self.owner_kernels, "owner_kernels", allow_empty=False)
        _strings(self.dependencies, "dependencies")


def _descriptor(
    skill_id: str,
    name: str,
    priority: str,
    owners: Sequence[str],
    path: str,
    handler: str,
    deps: Sequence[str] = (),
) -> DeltaSkillDescriptor:
    return DeltaSkillDescriptor(
        skill_id, name, priority, tuple(owners), path, False, tuple(deps), handler
    )


DELTA_SKILL_REGISTRY: dict[str, DeltaSkillDescriptor] = {
    item.name: item
    for item in (
        _descriptor(
            "ELMOS-V3D-001",
            "elmos-tool-result-interception-commit",
            "P0",
            ("K7", "K6", "K8"),
            "P0/elmos-tool-result-interception-commit/SKILL.md",
            "ResultLifecycleCoordinator",
        ),
        _descriptor(
            "ELMOS-V3D-002",
            "elmos-step-finalized-execution-plan",
            "P0",
            ("K7", "K4"),
            "P0/elmos-step-finalized-execution-plan/SKILL.md",
            "StepExecutionPlanStore",
        ),
        _descriptor(
            "ELMOS-V3D-003",
            "elmos-lossless-permission-replay",
            "P0",
            ("K7", "K8"),
            "P0/elmos-lossless-permission-replay/SKILL.md",
            "PermissionProjectionAdapter",
        ),
        _descriptor(
            "ELMOS-V3D-004",
            "elmos-invocation-scoped-capability-lease",
            "P0",
            ("K7",),
            "P0/elmos-invocation-scoped-capability-lease/SKILL.md",
            "CapabilityLeaseBroker",
        ),
        _descriptor(
            "ELMOS-V3D-005",
            "elmos-host-minted-security-context",
            "P0",
            ("K7", "K8"),
            "P0/elmos-host-minted-security-context/SKILL.md",
            "SecurityContextBroker",
        ),
        _descriptor(
            "ELMOS-V3D-006",
            "elmos-environment-attachment-authority",
            "P0",
            ("K7",),
            "P0/elmos-environment-attachment-authority/SKILL.md",
            "AuthorityCalculator",
        ),
        _descriptor(
            "ELMOS-V3D-007",
            "elmos-executor-generation-fencing",
            "P0",
            ("K7",),
            "P0/elmos-executor-generation-fencing/SKILL.md",
            "ExecutorGenerationManager",
        ),
        _descriptor(
            "ELMOS-V3D-008",
            "elmos-workspace-ownership-lease",
            "P0",
            ("K7", "K5"),
            "P0/elmos-workspace-ownership-lease/SKILL.md",
            "WorkspaceLeaseManager",
        ),
        _descriptor(
            "ELMOS-V3D-009",
            "elmos-harness-transport-version-negotiation",
            "P0",
            ("K7",),
            "P0/elmos-harness-transport-version-negotiation/SKILL.md",
            "ProtocolNegotiator",
        ),
        _descriptor(
            "ELMOS-V3D-010",
            "elmos-skill-trust-domain-provenance",
            "P0",
            ("K7", "K8"),
            "P0/elmos-skill-trust-domain-provenance/SKILL.md",
            "SkillTrustVerifier",
        ),
        _descriptor(
            "ELMOS-V3D-011",
            "elmos-registered-durable-plugin-events",
            "P1",
            ("K7", "K8"),
            "P1/elmos-registered-durable-plugin-events/SKILL.md",
            "DurableEventRegistry",
        ),
        _descriptor(
            "ELMOS-V3D-012",
            "elmos-typed-external-ingress",
            "P1",
            ("K7", "K1"),
            "P1/elmos-typed-external-ingress/SKILL.md",
            "IngressRouter",
        ),
        _descriptor(
            "ELMOS-V3D-013",
            "elmos-subagent-model-execution-spec",
            "P1",
            ("K4", "K7"),
            "P1/elmos-subagent-model-execution-spec/SKILL.md",
            "SubagentSpecCompiler",
        ),
    )
}

if len(DELTA_SKILL_REGISTRY) != 13 or any(
    descriptor.routable for descriptor in DELTA_SKILL_REGISTRY.values()
):
    raise RuntimeError("v3.1 delta registry invariant failed")


def _ref(value: Any, *, domain: str) -> str:
    return "cas:" + _cas_digest(value, domain=domain)


class DeltaEvidenceStore:
    """Tenant-scoped, content-addressed local evidence ledger.

    The default implementation intentionally makes no durability claim.  It
    exists so a bounded local invocation can always re-read the exact record
    named by ``DeltaResult.evidence_refs``.  Production wiring must provide a
    durable adapter with the same ``put``/``get`` contract and advertise that
    fact through its readiness gate.
    """

    durable = False

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], Any] = {}
        self._lock = threading.RLock()

    def put(
        self,
        context: SecurityContext,
        record: Mapping[str, Any],
        *,
        domain: str = "delta-runtime-result",
    ) -> str:
        if not isinstance(context, SecurityContext):
            raise ContractError(
                "trusted SecurityContext is required for delta evidence"
            )
        frozen = _freeze(_mapping(record, "delta evidence record"))
        reference = _ref(frozen, domain=domain)
        key = (context.tenant_id, context.project_id, reference)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None and existing != frozen:
                raise ContractError("content-addressed delta evidence collision")
            self._records[key] = frozen
        return reference

    def get(self, context: SecurityContext, reference: str) -> Mapping[str, Any]:
        if not isinstance(context, SecurityContext):
            raise ContractError(
                "trusted SecurityContext is required for delta evidence"
            )
        candidate = _text(reference, "delta evidence reference")
        key = (context.tenant_id, context.project_id, candidate)
        with self._lock:
            record = self._records.get(key)
        if record is None:
            raise ContractError("delta evidence is unavailable in this resource scope")
        if not hmac.compare_digest(
            candidate, _ref(record, domain="delta-runtime-result")
        ):
            raise ContractError("delta evidence digest mismatch")
        return MappingProxyType(_thaw(record))


class DeltaEvidenceBackend(Protocol):
    """Minimal scoped CAS contract accepted by the delta runtime."""

    durable: bool

    def put(
        self,
        context: SecurityContext,
        record: Mapping[str, Any],
        *,
        domain: str = "delta-runtime-result",
    ) -> str: ...

    def get(self, context: SecurityContext, reference: str) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class _DeltaScopeState:
    result_committer: ResultLifecycleCoordinator
    plan_store: StepExecutionPlanStore
    lease_broker: CapabilityLeaseBroker
    protocol_negotiator: ProtocolNegotiator
    event_registry: DurableEventRegistry
    ingress_router: IngressRouter
    workspace_manager: WorkspaceLeaseManager
    executor_fences: dict[tuple[str, str], ExecutorGenerationManager]


class DeltaSkillRuntime:
    """Exact allowlisted internal extension runtime.

    The runtime accepts either a :class:`DeltaInvocation` or a wire-shaped
    mapping.  Unknown skills and malformed provider-shaped payloads produce a
    typed ``UNSUPPORTED``/``UNKNOWN`` result; they never fall through to a
    permissive generic handler or execute an external effect.
    """

    def __init__(
        self,
        *,
        permission_profiles: Mapping[tuple[str, str], Mapping[str, PermissionProfile]]
        | None = None,
        protocol_profiles: Mapping[tuple[str, str], ProtocolCapabilities] | None = None,
        authorized_producers: Mapping[
            tuple[str, str],
            Mapping[str, Iterable[str]] | Iterable[str],
        ]
        | None = None,
        allowed_subagent_models: Iterable[tuple[str, str]] = (),
        trusted_skill_root: Path | None = None,
        skill_trust_policy: SkillTrustDomainPolicy | None = None,
        skill_signature_verifier: Callable[[bytes, str], bool] | None = None,
        host_security_signer: HostSecurityContextSigner | None = None,
        privileged_path_policy: PrivilegedPathPolicy | None = None,
        managed_worktree_registry: ManagedWorktreeRegistry | None = None,
        interceptors: Mapping[str, tuple[str, Callable[[ToolResult], ToolResult]]]
        | None = None,
        event_validators: Mapping[str, Callable[[Mapping[str, Any]], bool]]
        | None = None,
        event_upgraders: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]
        | None = None,
        optional_unknown_event_types: Iterable[str] = (),
        authority_provider: Callable[
            [SecurityContext, DeltaInvocation], RuntimeAssuranceAuthority
        ]
        | None = None,
        evidence_store: DeltaEvidenceBackend | None = None,
        tool_result_begin_hook: Callable[
            [
                SecurityContext,
                RuntimeAssuranceAuthority,
                DeltaInvocation,
                CallIdentity,
                int,
                str,
            ],
            Any,
        ]
        | None = None,
        tool_result_terminal_hook: Callable[
            [
                SecurityContext,
                RuntimeAssuranceAuthority,
                DeltaSkillDescriptor,
                DeltaInvocation,
                Any,
            ],
            Any,
        ]
        | None = None,
        durable_commit_hook: Callable[
            [
                SecurityContext,
                RuntimeAssuranceAuthority,
                DeltaSkillDescriptor,
                DeltaInvocation,
                Any,
            ],
            Any,
        ]
        | None = None,
    ) -> None:
        self._permission_profiles: dict[
            tuple[str, str], Mapping[str, PermissionProfile]
        ] = {}
        for key, profiles in (permission_profiles or {}).items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ContractError(
                    "permission profile key must be (provider, version)"
                )
            provider, version = (_text(item, "permission profile key") for item in key)
            checked: dict[str, PermissionProfile] = {}
            for value, profile in profiles.items():
                checked[_text(value, "permission projection value")] = profile
                if not isinstance(profile, PermissionProfile):
                    raise ContractError(
                        "permission projection must contain PermissionProfile values"
                    )
            self._permission_profiles[(provider, version)] = MappingProxyType(checked)
        self._protocol_profiles = dict(
            protocol_profiles or _builtin_protocol_profiles()
        )
        if not self._protocol_profiles:
            raise ContractError("at least one trusted protocol profile is required")
        self._authorized_producers: dict[
            tuple[str, str], Mapping[str, frozenset[str]]
        ] = {}
        for key, producers in (authorized_producers or {}).items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ContractError("authorized producer key must be (tenant, project)")
            scope = (_text(key[0], "tenant_id"), _text(key[1], "project_id"))
            values = IngressRouter._producer_policy(producers)
            self._authorized_producers[scope] = MappingProxyType(values)
        models: set[tuple[str, str]] = set()
        for item in allowed_subagent_models:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ContractError("allowed model must be a (provider, model) tuple")
            models.add((_text(item[0], "provider"), _text(item[1], "model")))
        self._allowed_subagent_models = frozenset(models)
        self._trusted_skill_root = (
            trusted_skill_root.resolve(strict=True)
            if trusted_skill_root is not None
            else None
        )
        if skill_trust_policy is not None and not isinstance(
            skill_trust_policy, SkillTrustDomainPolicy
        ):
            raise ContractError("Skill trust-domain policy is invalid")
        self._skill_trust_policy = skill_trust_policy
        self._skill_signature_verifier = skill_signature_verifier
        self._security_context_broker = SecurityContextBroker(host_security_signer)
        if privileged_path_policy is not None and not isinstance(
            privileged_path_policy, PrivilegedPathPolicy
        ):
            raise ContractError("privileged path policy is invalid")
        self._privileged_path_policy = privileged_path_policy
        if managed_worktree_registry is not None and not isinstance(
            managed_worktree_registry, ManagedWorktreeRegistry
        ):
            raise ContractError("managed worktree registry is invalid")
        self._managed_worktree_registry = managed_worktree_registry
        self._authority_provider = authority_provider
        self._tool_result_begin_hook = tool_result_begin_hook
        self._tool_result_terminal_hook = tool_result_terminal_hook
        self._durable_commit_hook = durable_commit_hook
        self._evidence_store = evidence_store or DeltaEvidenceStore()
        if not callable(getattr(self._evidence_store, "put", None)) or not callable(
            getattr(self._evidence_store, "get", None)
        ):
            raise ContractError("delta evidence store must implement put/get")
        self._interceptors: dict[
            str, tuple[str, Callable[[ToolResult], ToolResult]]
        ] = {}
        for name, definition in (interceptors or {}).items():
            if (
                not isinstance(definition, tuple)
                or len(definition) != 2
                or not callable(definition[1])
            ):
                raise ContractError("interceptor registry entry is invalid")
            self._interceptors[_text(name, "interceptor_id")] = (
                _text(definition[0], "interceptor_version"),
                definition[1],
            )
        self._event_validators = dict(event_validators or {})
        self._event_upgraders = dict(event_upgraders or {})
        self._optional_unknown_event_types = tuple(
            _text(item, "optional event type") for item in optional_unknown_event_types
        )
        if len(self._optional_unknown_event_types) > MAX_COLLECTION_ITEMS or len(
            set(self._optional_unknown_event_types)
        ) != len(self._optional_unknown_event_types):
            raise ContractError("optional event type inventory is invalid")
        self._states: dict[
            tuple[str, str, str, str, int, int, str, str], _DeltaScopeState
        ] = {}
        self._lock = threading.RLock()

    def _authority(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> RuntimeAssuranceAuthority:
        if self._authority_provider is None:
            raise ContractError(
                "trusted runtime-assurance authority provider is not configured"
            )
        try:
            authority = self._authority_provider(context, invocation)
        except ContractError:
            raise
        except Exception as exc:
            raise ContractError(
                "trusted runtime-assurance authority resolution failed"
            ) from exc
        if not isinstance(authority, RuntimeAssuranceAuthority):
            raise ContractError("authority provider returned an invalid host snapshot")
        authority.verify_binding(context, invocation)
        return authority

    @staticmethod
    def _state_key(
        context: SecurityContext,
        revision_set_id: str,
    ) -> tuple[str, str, str, str, int, int, str, str]:
        if context.run_id is None or context.authority_revision is None:
            raise ContractError("runtime-assurance state requires exact run authority")
        _text(revision_set_id, "revision_set_id")
        return (
            context.tenant_id,
            context.project_id,
            context.actor_id,
            context.run_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            revision_set_id,
        )

    def _new_state(self) -> _DeltaScopeState:
        return _DeltaScopeState(
            ResultLifecycleCoordinator(),
            StepExecutionPlanStore(),
            CapabilityLeaseBroker(),
            ProtocolNegotiator(self._protocol_profiles),
            DurableEventRegistry(
                validators=self._event_validators,
                upgraders=self._event_upgraders,
                optional_unknown_types=self._optional_unknown_event_types,
            ),
            IngressRouter(),
            WorkspaceLeaseManager(),
            {},
        )

    def _state(
        self, context: SecurityContext, revision_set_id: str
    ) -> _DeltaScopeState:
        key = self._state_key(context, revision_set_id)
        with self._lock:
            current = self._states.get(key)
            if current is None:
                current = self._new_state()
                self._states[key] = current
            return current

    def restore_scope(
        self,
        context: SecurityContext,
        snapshot: RuntimeAssuranceScopeSnapshot,
    ) -> None:
        """Replace one process-local scope from digest-verified durable state.

        Restoration is deliberately explicit and fail-closed.  It never runs
        interceptors, re-admits ingress, or treats a caller payload as durable
        authority.  A wrapper must serialize load/restore/execute for the exact
        scope and obtain ``snapshot`` through ``RuntimeAssuranceStore``.
        """

        if not isinstance(snapshot, RuntimeAssuranceScopeSnapshot):
            raise ContractError("runtime-assurance snapshot must be typed")
        expected_scope = (
            context.tenant_id,
            context.project_id,
            context.actor_id,
            context.run_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
        )
        observed_scope = (
            snapshot.tenant_id,
            snapshot.project_id,
            snapshot.actor_id,
            snapshot.run_id,
            snapshot.execution_epoch,
            snapshot.fencing_generation,
            snapshot.authority_revision,
        )
        if observed_scope != expected_scope:
            raise ContractError(
                "runtime-assurance snapshot scope is stale or mismatched"
            )

        restored = self._new_state()

        def evidence_value(reference: str, expected_kind: str) -> Any:
            envelope = self._evidence_store.get(context, reference)
            if envelope.get("kind") != expected_kind:
                raise ContractError("durable evidence kind is inconsistent")
            if "content" not in envelope:
                raise ContractError("durable evidence content is missing")
            return envelope["content"]

        def evidence_content(reference: str, expected_kind: str) -> Mapping[str, Any]:
            content = evidence_value(reference, expected_kind)
            if not isinstance(content, Mapping):
                raise ContractError("durable evidence content is not an object")
            return content

        def tool_result(reference: str, expected_kind: str) -> ToolResult:
            value = evidence_content(reference, expected_kind)
            _exact_fields(
                value,
                allowed={"identity", "ok", "content"},
                required={"identity", "ok", "content"},
                label="restored tool result",
            )
            identity = _field_mapping(value, "identity")
            _exact_fields(
                identity,
                allowed={
                    "invocationId",
                    "callId",
                    "executionPlanHash",
                    "environmentId",
                    "authoritySnapshotId",
                },
                required={
                    "invocationId",
                    "callId",
                    "executionPlanHash",
                    "environmentId",
                    "authoritySnapshotId",
                },
                label="restored tool call identity",
            )
            return ToolResult(
                CallIdentity(
                    _field_text(identity, "invocationId"),
                    _field_text(identity, "callId"),
                    _field_text(identity, "executionPlanHash"),
                    _field_text(identity, "environmentId"),
                    _field_text(identity, "authoritySnapshotId"),
                ),
                _field_bool(value, "ok"),
                value["content"],
            )

        for tool_result_record in snapshot.tool_results:
            if tool_result_record.state.value in {
                CommitState.RAW_CAPTURED.value,
                CommitState.INTERCEPTING.value,
            }:
                raise ContractError(
                    "interrupted tool result requires explicit recovery; "
                    "interceptors must not be replayed during scope restore"
                )
            raw = tool_result(tool_result_record.raw_result_ref, "RAW_TOOL_RESULT")
            effective = tool_result(
                tool_result_record.effective_result_ref,
                "EFFECTIVE_TOOL_RESULT",
            )
            expected_identity = (
                tool_result_record.invocation_id,
                tool_result_record.call_id,
                tool_result_record.execution_plan_hash,
                tool_result_record.environment_id,
                tool_result_record.authority_snapshot_id,
            )
            observed_identity = (
                raw.identity.invocation_id,
                raw.identity.call_id,
                raw.identity.execution_plan_hash,
                raw.identity.environment_id,
                raw.identity.authority_snapshot_id,
            )
            if (
                observed_identity != expected_identity
                or effective.identity != raw.identity
            ):
                raise ContractError("restored tool result evidence identity diverges")
            decisions = tuple(
                InterceptorDecision(
                    item.interceptor_id,
                    item.version,
                    item.decision_hash,
                    item.decision_hash,
                    item.decision_hash,
                )
                for item in tool_result_record.interceptor_chain
            )
            provenance_ref = tool_result_record.mutation_provenance_ref
            if provenance_ref is None:
                raise ContractError(
                    "restored tool result lacks mutation provenance evidence"
                )
            provenance = evidence_value(
                provenance_ref,
                "INTERCEPTOR_DECISIONS",
            )
            if not isinstance(provenance, (list, tuple)):
                raise ContractError("restored interceptor provenance is not an array")
            observed_decisions: list[tuple[str, str, str]] = []
            for item in provenance:
                if not isinstance(item, Mapping):
                    raise ContractError(
                        "restored interceptor provenance item is not an object"
                    )
                _exact_fields(
                    item,
                    allowed={"interceptorId", "version", "decisionHash"},
                    required={"interceptorId", "version", "decisionHash"},
                    label="restored interceptor decision",
                )
                observed_decisions.append(
                    (
                        _field_text(item, "interceptorId"),
                        _field_text(item, "version"),
                        _field_text(item, "decisionHash"),
                    )
                )
            expected_decisions = tuple(
                (item.interceptor_id, item.version, item.decision_hash)
                for item in tool_result_record.interceptor_chain
            )
            if tuple(observed_decisions) != expected_decisions:
                raise ContractError(
                    "restored interceptor provenance diverges from durable chain"
                )
            commit_key = _tool_result_commit_key(
                tool_result_record.invocation_id,
                tool_result_record.call_id,
                tool_result_record.attempt,
                tool_result_record.execution_epoch,
            )
            committed = CommittedToolResult(
                raw,
                effective,
                decisions,
                commit_key,
                CommitState(tool_result_record.state.value),
                tool_result_record.raw_result_ref,
                tool_result_record.effective_result_ref,
                tool_result_record.mutation_provenance_ref,
                (
                    None
                    if tool_result_record.failure_kind is None
                    else ToolFailureKind(tool_result_record.failure_kind.value)
                ),
                tool_result_record.failure_reason,
            )
            restored.result_committer.restore(
                committed,
                attempt=tool_result_record.attempt,
                epoch=tool_result_record.execution_epoch,
            )

        for plan_record in snapshot.step_plans:
            model = plan_record.model_snapshot
            if not isinstance(model, Mapping):
                raise ContractError("restored model snapshot is invalid")
            tool_plan = plan_record.tool_plan
            if not isinstance(tool_plan, Mapping):
                raise ContractError("restored tool plan is invalid")
            plan = ExecutionPlan(
                ModelSnapshot(
                    _field_text(model, "provider"),
                    _field_text(model, "model"),
                    _field_text(model, "revision"),
                    _optional_field_text(model, "reasoningEffort"),
                ),
                _field_strings(tool_plan, "tools", allow_empty=True),
                plan_record.environment_snapshot_id,
                plan_record.authority_snapshot_id,
                _text(plan_record.tool_mode, "tool_mode"),
                plan_record.state.value,
                plan_record.plan_id,
                plan_record.capabilities,
                plan_record.tool_contracts,
                plan_record.handler_digests,
            )
            if not hmac.compare_digest(plan.plan_hash, plan_record.plan_hash):
                raise ContractError("restored execution plan hash diverges")
            restored.plan_store.restore(plan)

        for lease_record in snapshot.capability_leases:
            restored.lease_broker.restore(
                CapabilityLease(
                    lease_record.lease_id,
                    lease_record.invocation_id,
                    lease_record.environment_id,
                    lease_record.authority_snapshot_id,
                    lease_record.execution_epoch,
                    frozenset(lease_record.capabilities),
                    lease_record.state.value == "ACTIVE",
                    lease_record.issued_at,
                    lease_record.expires_at,
                    lease_record.delegation_allowed,
                    lease_record.state.value,
                )
            )

        for executor_record in snapshot.executor_generations:
            fence_key = (
                executor_record.environment_id,
                executor_record.executor_identity,
            )
            current = restored.executor_fences.get(fence_key)
            if current is not None and (
                current.generation,
                current.connection_epoch,
            ) > (
                executor_record.executor_generation,
                executor_record.connection_epoch,
            ):
                continue
            fence = ExecutorGenerationManager(
                executor_record.executor_generation,
                executor_record.connection_epoch,
                environment_id=executor_record.environment_id,
                executor_identity=executor_record.executor_identity,
            )
            fence.state = executor_record.state.value
            fence.live_probe_evidence_ref = executor_record.live_probe_evidence_ref
            restored.executor_fences[fence_key] = fence

        replacement_effects: dict[tuple[str, int, int], list[Mapping[str, Any]]] = {}
        for effect_record in snapshot.executor_replacement_effects:
            replacement_effects.setdefault(
                (
                    effect_record.environment_id,
                    effect_record.executor_generation,
                    effect_record.connection_epoch,
                ),
                [],
            ).append(
                {
                    "effectId": effect_record.effect_id,
                    "kind": effect_record.kind.value,
                    "state": effect_record.state.value,
                    "evidenceRef": effect_record.evidence_ref,
                }
            )
        for (
            environment_id,
            generation,
            connection_epoch,
        ), effects in replacement_effects.items():
            candidates = tuple(
                fence
                for fence in restored.executor_fences.values()
                if fence.environment_id == environment_id
                and fence.generation == generation
                and fence.connection_epoch == connection_epoch
            )
            if len(candidates) != 1:
                raise ContractError(
                    "durable executor replacement effects lack one exact fence"
                )
            candidates[0].restore_reconciliation(effects)

        for workspace_record in snapshot.workspace_leases:
            restored.workspace_manager.restore(
                WorkspaceLease(
                    workspace_record.workspace_id,
                    workspace_record.owner_execution_id,
                    workspace_record.generation,
                    workspace_record.repository_id,
                    workspace_record.base_revision,
                    workspace_record.write_scopes,
                    workspace_record.state.value,
                    workspace_record.takeover_evidence_ref,
                )
            )

        for event_record in snapshot.event_registrations:
            registration = EventRegistration(
                event_record.event_type,
                event_record.owner,
                event_record.schema_version,
                event_record.semantics.value,
                event_record.validator_ref,
                event_record.upgrader_ref,
                event_record.projections,
                event_record.compatibility.value,
            )
            expected_hash = digest_object(
                registration.to_wire(),
                domain="delta-event-registration",
            )
            if not hmac.compare_digest(expected_hash, event_record.registration_hash):
                raise ContractError("restored event registration digest diverges")
            restored.event_registry.register(registration)

        for ingress_record in snapshot.typed_ingress:
            value = evidence_content(ingress_record.payload_ref, "TYPED_INGRESS")
            ingress_content = _typed_ingress_content(value.get("content"))
            ingress = TypedIngress(
                _field_text(value, "ingressId"),
                _field_text(value, "kind"),
                _field_text(value, "producerExecutionId"),
                _field_text(value, "eventId"),
                _field_text(value, "causationId"),
                _field_text(value, "correlationId"),
                ingress_content,
                _optional_field_text(value, "originatingCallId"),
                _optional_field_text(value, "deduplicationKey"),
            )
            if (
                ingress.ingress_id != ingress_record.ingress_id
                or ingress.producer_execution_id != ingress_record.producer_execution_id
                or ingress.kind != ingress_record.kind.value
                or (ingress.deduplication_key or ingress.event_id)
                != ingress_record.deduplication_key
                or ingress.originating_call_id != ingress_record.originating_call_id
            ):
                raise ContractError("restored ingress evidence identity diverges")
            restored.ingress_router.restore(
                ingress,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                envelope_digest=ingress_record.envelope_digest,
            )

        key = self._state_key(context, snapshot.revision_set_id)
        with self._lock:
            self._states[key] = restored

    @staticmethod
    def _context(request: DeltaInvocation, context: Any) -> SecurityContext:
        if not isinstance(context, SecurityContext):
            raise ContractError("trusted SecurityContext is required")
        if context.tenant_id != request.tenant_id:
            raise ContractError(
                "invocation tenant does not match authenticated context"
            )
        if context.run_id != request.run_id:
            raise ContractError("invocation run does not match authenticated context")
        if context.execution_epoch != request.execution_epoch:
            raise ContractError("invocation execution epoch is stale")
        if context.authority_revision is None:
            raise ContractError("authenticated authority revision is required")
        return context

    @staticmethod
    def _invocation(
        value: DeltaInvocation | Mapping[str, Any], skill: str | None = None
    ) -> DeltaInvocation:
        if isinstance(value, DeltaInvocation):
            return value if skill is None else replace(value, extension_skill=skill)
        if not isinstance(value, Mapping):
            raise ContractError("delta invocation must be typed")
        _exact_fields(
            value,
            allowed={
                "tenantId",
                "goalId",
                "runId",
                "executionEpoch",
                "stepId",
                "invocationId",
                "revisionSetId",
                "extensionSkill",
                "payload",
            },
            required={
                "tenantId",
                "goalId",
                "runId",
                "executionEpoch",
                "stepId",
                "invocationId",
                "revisionSetId",
            },
            label="delta invocation",
        )
        return DeltaInvocation(
            _field_text(value, "tenantId"),
            _field_text(value, "goalId"),
            _field_text(value, "runId"),
            _field_int(value, "executionEpoch", positive=True),
            _field_text(value, "stepId"),
            _field_text(value, "invocationId"),
            _field_text(value, "revisionSetId"),
            skill or value.get("extensionSkill"),
            _field_mapping(value, "payload", default_empty=True),
        )

    def _record_result(
        self,
        context: SecurityContext,
        descriptor: DeltaSkillDescriptor,
        request: DeltaInvocation,
        status: ResultStatus,
        *,
        authority: RuntimeAssuranceAuthority | None = None,
        output: Any = None,
        message: str | None = None,
        proof_obligation_refs: tuple[str, ...] = (),
    ) -> DeltaResult:
        record = {
            "apiVersion": DELTA_API_VERSION,
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "actorId": context.actor_id,
            "authorityRevision": context.authority_revision,
            "skillId": descriptor.skill_id,
            "skillName": descriptor.name,
            "invocation": request.to_wire(),
            "status": status.value,
            "output": output,
            "message": message,
            "proofObligationRefs": list(proof_obligation_refs),
        }
        if authority is not None:
            record["authorityDigest"] = authority.authority_digest
            record["originatingBaseSkill"] = authority.originating_base_skill.to_wire()
        try:
            reference = self._evidence_store.put(context, record)
        except Exception:
            return DeltaResult(
                request.invocation_id,
                ResultStatus.UNKNOWN,
                message="runtime-assurance outcome could not be recorded",
            )
        return DeltaResult(
            request.invocation_id,
            status,
            (reference,),
            proof_obligation_refs,
            message,
        )

    def execute(
        self,
        invocation: DeltaInvocation | Mapping[str, Any],
        context: Any = None,
        runtime: Any = None,
        *,
        skill: str | None = None,
        trusted_authority: RuntimeAssuranceAuthority | None = None,
        deadline: datetime | None = None,
    ) -> DeltaResult:
        del runtime
        checked_deadline: datetime | None = None
        try:
            request = self._invocation(invocation, skill)
        except ContractError as exc:
            invocation_id = (
                str(invocation.get("invocationId", "unknown"))
                if isinstance(invocation, Mapping)
                else "unknown"
            )
            return DeltaResult(
                invocation_id or "unknown", ResultStatus.UNKNOWN, message=str(exc)
            )
        name = request.extension_skill
        descriptor = DELTA_SKILL_REGISTRY.get(name or "")
        if descriptor is None:
            return DeltaResult(
                request.invocation_id,
                ResultStatus.UNSUPPORTED,
                message="extension Skill is not registered",
            )
        trusted_context: SecurityContext | None = None
        resolved_authority: RuntimeAssuranceAuthority | None = None
        try:
            trusted_context = self._context(request, context)
            if deadline is not None and not isinstance(deadline, datetime):
                raise ContractError("runtime-assurance deadline must be a date-time")
            checked_deadline = _aware(deadline, "deadline")
            if checked_deadline is not None and datetime.now(UTC) >= checked_deadline:
                raise ContractError(
                    "runtime-assurance deadline expired before dispatch"
                )
            if trusted_authority is None:
                resolved_authority = self._authority(trusted_context, request)
            else:
                if not isinstance(trusted_authority, RuntimeAssuranceAuthority):
                    raise ContractError(
                        "trusted runtime-assurance authority is invalid"
                    )
                trusted_authority.verify_binding(trusted_context, request)
                resolved_authority = trusted_authority
            state = self._state(trusted_context, request.revision_set_id)
            output = self._dispatch(
                descriptor.name,
                request,
                trusted_context,
                resolved_authority,
                state,
            )
            if checked_deadline is not None and datetime.now(UTC) >= checked_deadline:
                if (
                    descriptor.name == "elmos-tool-result-interception-commit"
                    and isinstance(output, Mapping)
                    and isinstance(output.get("callIdentity"), Mapping)
                    and request.payload.get("action", "commit") == "commit"
                ):
                    call_identity = _mapping(
                        output["callIdentity"], "tool result call identity"
                    )
                    attempt = _field_int(request.payload, "attempt", positive=True)
                    commit_key = _tool_result_commit_key(
                        request.invocation_id,
                        _field_text(call_identity, "callId"),
                        attempt,
                        request.execution_epoch,
                    )
                    terminal = (
                        dict(output)
                        if output.get("commitState") == CommitState.ABORTED.value
                        else state.result_committer.abort(
                            commit_key,
                            failure_kind=ToolFailureKind.TIMED_OUT,
                            failure_reason=(
                                "runtime-assurance deadline expired during dispatch"
                            ),
                        ).to_wire()
                    )
                    if self._tool_result_terminal_hook is not None:
                        self._tool_result_terminal_hook(
                            trusted_context,
                            resolved_authority,
                            descriptor,
                            request,
                            terminal,
                        )
                raise ContractError(
                    "runtime-assurance deadline expired during dispatch"
                )
            if isinstance(output, DeltaResult):
                return self._record_result(
                    trusted_context,
                    descriptor,
                    request,
                    ResultStatus(output.status),
                    authority=resolved_authority,
                    message=output.message,
                    proof_obligation_refs=output.proof_obligation_refs,
                )
            if (
                descriptor.name == "elmos-tool-result-interception-commit"
                and isinstance(output, Mapping)
                and output.get("commitState") == CommitState.ABORTED.value
                and self._tool_result_terminal_hook is not None
            ):
                terminal_output = self._tool_result_terminal_hook(
                    trusted_context,
                    resolved_authority,
                    descriptor,
                    request,
                    output,
                )
                if terminal_output is not None:
                    output = terminal_output
            elif self._durable_commit_hook is not None:
                committed_output = self._durable_commit_hook(
                    trusted_context,
                    resolved_authority,
                    descriptor,
                    request,
                    output,
                )
                if committed_output is not None:
                    output = committed_output
            return self._record_result(
                trusted_context,
                descriptor,
                request,
                ResultStatus.COMMITTED,
                authority=resolved_authority,
                output=output,
            )
        except UnsupportedContractError as error:
            status = ResultStatus.UNSUPPORTED
            error_message = str(error)
        except ReviewRequiredError as error:
            status = ResultStatus.REQUIRES_REVIEW
            error_message = str(error)
        except ContractError as error:
            status = ResultStatus.DENIED
            error_message = str(error)
        except Exception as error:
            status = ResultStatus.UNKNOWN
            error_message = f"delta handler failed: {type(error).__name__}"
        if trusted_context is None:
            return DeltaResult(request.invocation_id, status, message=error_message)
        return self._record_result(
            trusted_context,
            descriptor,
            request,
            status,
            authority=resolved_authority,
            message=error_message,
        )

    def read_evidence(
        self,
        context: SecurityContext,
        reference: str,
    ) -> Mapping[str, Any]:
        """Re-read and digest-verify an invocation result in its exact scope."""

        return self._evidence_store.get(context, reference)

    def readiness(self, *, production: bool = False) -> tuple[bool, str]:
        if self._authority_provider is None:
            return (
                False,
                "trusted runtime-assurance authority provider is not configured",
            )
        if production:
            if not bool(getattr(self._evidence_store, "durable", False)):
                return (
                    False,
                    "production runtime assurance requires a durable evidence adapter",
                )
            if self._durable_commit_hook is None:
                return (
                    False,
                    "production runtime assurance requires a durable state commit hook",
                )
            missing_bindings: list[str] = []
            if not bool(
                getattr(
                    self._authority_provider,
                    "base_origin_receipt_verified",
                    False,
                )
            ) or not callable(
                getattr(self._authority_provider, "verify_origin_receipt", None)
            ):
                missing_bindings.append("durable base Skill origin receipt verifier")
            if not bool(
                getattr(
                    self._authority_provider,
                    "host_envelope_signatures_verified",
                    False,
                )
            ) or not callable(
                getattr(self._authority_provider, "verify_host_envelope", None)
            ):
                missing_bindings.append("Host envelope signature verifier")
            if not bool(
                getattr(
                    self._authority_provider,
                    "host_envelope_issuer_durable",
                    False,
                )
            ) or not callable(
                getattr(self._authority_provider, "issue_host_envelope", None)
            ):
                missing_bindings.append("durable Host envelope issuer")
            if not self._permission_profiles:
                missing_bindings.append("permission profiles")
            if not self._authorized_producers:
                missing_bindings.append("typed-ingress producer policy")
            if not self._allowed_subagent_models:
                missing_bindings.append("subagent model allowlist")
            if self._skill_trust_policy is None or not getattr(
                self._skill_trust_policy, "trusted_for_production", False
            ):
                missing_bindings.append("trusted Skill trust-domain policy")
            if self._skill_signature_verifier is None:
                missing_bindings.append("Skill signature verifier")
            if not self._security_context_broker.trusted_for_production:
                missing_bindings.append("restart-safe Host security-context signer")
            if self._privileged_path_policy is None or not getattr(
                self._privileged_path_policy, "trusted_for_production", False
            ):
                missing_bindings.append("trusted privileged path policy")
            if self._managed_worktree_registry is None or not getattr(
                self._managed_worktree_registry, "trusted_for_production", False
            ):
                missing_bindings.append("live managed-worktree registry")
            if not self._interceptors:
                missing_bindings.append("tool-result interceptor registry")
            elif any(
                not bool(getattr(definition[1], "trusted_for_production", False))
                or not bool(getattr(definition[1], "deadline_enforced", False))
                for definition in self._interceptors.values()
            ):
                missing_bindings.append(
                    "production-trusted deadline-enforced interceptors"
                )
            if self._tool_result_begin_hook is None:
                missing_bindings.append("tool-result RAW_CAPTURED begin hook")
            if self._tool_result_terminal_hook is None:
                missing_bindings.append("tool-result terminal abort hook")
            if missing_bindings:
                return (
                    False,
                    "production runtime assurance is missing exact bindings: "
                    + ", ".join(missing_bindings),
                )
        return (
            True,
            "runtime-assurance extensions are bound to trusted authority and readable evidence",
        )

    def _dispatch(
        self,
        name: str,
        invocation: DeltaInvocation,
        context: SecurityContext,
        authority: RuntimeAssuranceAuthority,
        state: _DeltaScopeState,
    ) -> Any:
        payload = invocation.payload
        # Each entry is explicit in this table; there is no catch-all action.
        if name == "elmos-tool-result-interception-commit":
            action = _field_text(payload, "action", default="commit")
            if action in {"publish", "abort"}:
                lifecycle_fields = {
                    "action",
                    "commitKey",
                    "callId",
                    "attempt",
                    "executionEpoch",
                }
                required_fields = set(lifecycle_fields)
                if action == "abort":
                    lifecycle_fields.update({"failureKind", "failureReason"})
                    required_fields.update({"failureKind", "failureReason"})
                _exact_fields(
                    payload,
                    allowed=lifecycle_fields,
                    required=required_fields,
                    label=f"tool result {action}",
                )
                commit_key = _field_text(payload, "commitKey")
                call_id = _field_text(payload, "callId")
                attempt = _field_int(payload, "attempt", positive=True)
                execution_epoch = _field_int(payload, "executionEpoch", positive=True)
                current_result = state.result_committer.get(commit_key)
                if current_result is None:
                    raise ContractError("tool result lifecycle commit is unavailable")
                subject_identity = current_result.call_identity
                expected_key = _tool_result_commit_key(
                    subject_identity.invocation_id,
                    call_id,
                    attempt,
                    execution_epoch,
                )
                if (
                    execution_epoch != invocation.execution_epoch
                    or not hmac.compare_digest(commit_key, expected_key)
                    or subject_identity.call_id != call_id
                ):
                    raise ContractError(
                        "tool result lifecycle identity is stale or mismatched"
                    )
                binding = authority.pending_call_binding(call_id)
                if (
                    subject_identity.execution_plan_hash != binding.execution_plan_hash
                    or subject_identity.environment_id != binding.environment_id
                    or subject_identity.authority_snapshot_id
                    != binding.authority_snapshot_id
                    or binding.authority_snapshot_id != context.authority_revision
                    or binding.attempt != attempt
                ):
                    raise ContractError(
                        "tool result lifecycle mixes pending plan/environment bindings"
                    )
                if action == "publish":
                    result = state.result_committer.publish(commit_key)
                else:
                    try:
                        failure_kind = ToolFailureKind(
                            _field_text(payload, "failureKind")
                        )
                    except ValueError as exc:
                        raise ContractError(
                            "tool result failure kind is unsupported"
                        ) from exc
                    result = state.result_committer.abort(
                        commit_key,
                        failure_kind=failure_kind,
                        failure_reason=_field_text(payload, "failureReason"),
                    )
                return result.to_wire()
            if action != "commit":
                raise ContractError("unsupported tool result lifecycle action")
            _exact_fields(
                payload,
                allowed={"action", "rawResult", "attempt", "interceptorIds"},
                required={"rawResult", "attempt"},
                label="tool result commit",
            )
            raw = _field_mapping(payload, "rawResult")
            _exact_fields(
                raw,
                allowed={"identity", "ok", "content"},
                required={"identity", "ok", "content"},
                label="raw tool result",
            )
            identity = _field_mapping(raw, "identity")
            _exact_fields(
                identity,
                allowed={
                    "invocationId",
                    "callId",
                    "executionPlanHash",
                    "environmentId",
                    "authoritySnapshotId",
                },
                required={
                    "invocationId",
                    "callId",
                    "executionPlanHash",
                    "environmentId",
                    "authoritySnapshotId",
                },
                label="tool call identity",
            )
            if _field_text(identity, "invocationId") != invocation.invocation_id:
                raise ContractError("tool result invocation identity mismatch")
            if (
                _field_text(identity, "authoritySnapshotId")
                != context.authority_revision
            ):
                raise ContractError("tool result authority snapshot is stale")
            call_id = _field_text(identity, "callId")
            plan_hash = _field_text(identity, "executionPlanHash")
            environment_id = _field_text(identity, "environmentId")
            binding = authority.pending_call_binding(call_id)
            if (
                plan_hash != binding.execution_plan_hash
                or environment_id != binding.environment_id
                or binding.invocation_id != invocation.invocation_id
                or binding.authority_snapshot_id != context.authority_revision
                or binding.attempt != _field_int(payload, "attempt", positive=True)
            ):
                raise ContractError(
                    "tool result mixes the pending call plan/environment binding"
                )
            tool = ToolResult(
                CallIdentity(
                    _field_text(identity, "invocationId"),
                    call_id,
                    plan_hash,
                    environment_id,
                    _field_text(identity, "authoritySnapshotId"),
                ),
                _field_bool(raw, "ok"),
                raw["content"],
            )
            interceptor_ids = _field_strings(
                payload, "interceptorIds", default_empty=True
            )
            chain: list[Interceptor] = []
            for interceptor_id in interceptor_ids:
                definition = self._interceptors.get(interceptor_id)
                if definition is None:
                    raise UnsupportedContractError(
                        "tool result interceptor is not registered"
                    )
                chain.append((interceptor_id, definition[0], definition[1]))
            attempt = _field_int(payload, "attempt", positive=True)
            captured = state.result_committer.capture(
                tool,
                attempt=attempt,
                epoch=invocation.execution_epoch,
            )
            commit_key = _tool_result_commit_key(
                invocation.invocation_id,
                call_id,
                attempt,
                invocation.execution_epoch,
            )
            artifact_binding = {
                "apiVersion": DELTA_API_VERSION,
                "tenantId": context.tenant_id,
                "projectId": context.project_id,
                "runId": context.run_id,
                "invocationId": invocation.invocation_id,
                "callId": call_id,
                "commitKey": commit_key,
            }
            raw_ref = self._evidence_store.put(
                context,
                artifact_binding
                | {"kind": "RAW_TOOL_RESULT", "content": captured.to_wire()},
            )
            if self._tool_result_begin_hook is not None:
                self._tool_result_begin_hook(
                    context,
                    authority,
                    invocation,
                    tool.identity,
                    attempt,
                    raw_ref,
                )
            result = state.result_committer.commit(
                tool,
                tuple(chain),
                attempt=attempt,
                epoch=invocation.execution_epoch,
            )
            effective_ref = self._evidence_store.put(
                context,
                artifact_binding
                | {
                    "kind": "EFFECTIVE_TOOL_RESULT",
                    "content": result.effective.to_wire(),
                },
            )
            mutation_ref = self._evidence_store.put(
                context,
                artifact_binding
                | {
                    "kind": "INTERCEPTOR_DECISIONS",
                    "content": [decision.to_wire() for decision in result.decisions],
                },
            )
            result = state.result_committer.bind_evidence(
                result.commit_key,
                raw_result_ref=raw_ref,
                effective_result_ref=effective_ref,
                mutation_provenance_ref=mutation_ref,
            )
            return result.to_wire()
        if name == "elmos-step-finalized-execution-plan":
            _exact_fields(
                payload,
                allowed={
                    "modelSnapshot",
                    "tools",
                    "toolPlan",
                    "toolContracts",
                    "handlerDigests",
                    "environmentSnapshotId",
                    "authoritySnapshotId",
                    "toolMode",
                    "capabilities",
                    "planId",
                },
                required={
                    "modelSnapshot",
                    "toolContracts",
                    "handlerDigests",
                    "environmentSnapshotId",
                    "authoritySnapshotId",
                    "toolMode",
                },
                label="step execution plan",
            )
            model = _field_mapping(payload, "modelSnapshot")
            _exact_fields(
                model,
                allowed={"provider", "model", "revision", "reasoningEffort"},
                required={"provider", "model", "revision"},
                label="model snapshot",
            )
            if "tools" in payload and "toolPlan" in payload:
                raise ContractError(
                    "execution plan must use exactly one tool list representation"
                )
            if "toolPlan" in payload:
                tool_plan = _field_mapping(payload, "toolPlan")
                _exact_fields(
                    tool_plan, allowed={"tools"}, required={"tools"}, label="tool plan"
                )
                tools = _field_strings(tool_plan, "tools")
            else:
                tools = _field_strings(payload, "tools", allow_empty=True)
            tool_contracts = _field_mapping(payload, "toolContracts")
            handler_digest_values = _field_mapping(payload, "handlerDigests")
            if set(tool_contracts) != set(tools):
                raise ContractError(
                    "tool contracts must exactly bind every planned tool"
                )
            if set(handler_digest_values) != set(tools):
                raise ContractError(
                    "handler digests must exactly bind every planned tool"
                )
            handler_digests: dict[str, str] = {}
            for tool_name, value in handler_digest_values.items():
                candidate = _sha256(value, f"handler digest {tool_name}")
                if not candidate.startswith("sha256:"):
                    raise ContractError(
                        "handler digests must be canonical SHA-256 digests"
                    )
                handler_digests[tool_name] = candidate
            authority_snapshot_id = _field_text(payload, "authoritySnapshotId")
            if authority_snapshot_id != context.authority_revision:
                raise ContractError("execution plan authority snapshot is stale")
            model_snapshot = ModelSnapshot(
                _field_text(model, "provider"),
                _field_text(model, "model"),
                _field_text(model, "revision"),
                _optional_field_text(model, "reasoningEffort"),
            )
            environment_snapshot_id = _field_text(payload, "environmentSnapshotId")
            mode = _field_text(payload, "toolMode")
            capabilities = _field_strings(payload, "capabilities", default_empty=True)
            if model_snapshot not in authority.selected_models:
                raise ContractError(
                    "execution plan model snapshot is not host-selected"
                )
            if not frozenset(tools) <= authority.tools:
                raise ContractError("execution plan tools widen trusted host authority")
            expected_tool_contracts = {
                tool_name: _thaw(authority.tool_contracts[tool_name])
                for tool_name in tools
                if tool_name in authority.tool_contracts
            }
            expected_handler_digests = {
                tool_name: authority.handler_digests[tool_name]
                for tool_name in tools
                if tool_name in authority.handler_digests
            }
            if (
                set(expected_tool_contracts) != set(tools)
                or _thaw(tool_contracts) != expected_tool_contracts
            ):
                raise ContractError(
                    "execution plan tool contracts differ from Host-selected bindings"
                )
            if expected_handler_digests != handler_digests:
                raise ContractError(
                    "execution plan handler digests differ from Host-selected bindings"
                )
            if not frozenset(capabilities) <= authority.capabilities:
                raise ContractError(
                    "execution plan capabilities widen trusted host authority"
                )
            if environment_snapshot_id not in authority.environment_snapshot_ids:
                raise ContractError(
                    "execution plan environment snapshot is not host-authorized"
                )
            if mode not in authority.tool_modes:
                raise ContractError("execution plan tool mode is not host-authorized")
            plan = state.plan_store.build_candidate(
                model_snapshot,
                tools,
                environment_snapshot_id,
                authority_snapshot_id,
                mode,
                capabilities=capabilities,
                plan_id=_optional_field_text(payload, "planId"),
                tool_contracts=tool_contracts,
                handler_digests=handler_digests,
            )
            return state.plan_store.activate(state.plan_store.finalize(plan)).to_wire()
        if name == "elmos-lossless-permission-replay":
            _exact_fields(
                payload,
                allowed={"profileId", "canonicalProfile", "provider", "version"},
                required={"profileId", "canonicalProfile", "provider", "version"},
                label="permission replay",
            )
            profile_data = _field_mapping(payload, "canonicalProfile")
            _exact_fields(
                profile_data,
                allowed={
                    "filesystemRoots",
                    "network",
                    "mutable",
                    "workingDirectory",
                    "extra",
                },
                required={
                    "filesystemRoots",
                    "network",
                    "mutable",
                    "workingDirectory",
                },
                label="canonical permission profile",
            )
            extra = _field_mapping(profile_data, "extra", default_empty=True)
            profile = PermissionProfile(
                _field_strings(profile_data, "filesystemRoots"),
                _field_text(profile_data, "network"),
                _field_bool(profile_data, "mutable"),
                _field_text(profile_data, "workingDirectory"),
                tuple(
                    (
                        _text(key, "permission extra key"),
                        _text(value, "permission extra value"),
                    )
                    for key, value in sorted(extra.items())
                ),
            )
            provider = _field_text(payload, "provider")
            version = _field_text(payload, "version")
            representable = self._permission_profiles.get((provider, version))
            if representable is None:
                raise UnsupportedContractError(
                    "permission provider/version adapter is not registered"
                )
            if f"{provider}@{version}" not in authority.permission_profile_versions:
                raise ContractError(
                    "permission provider/version is not host-authorized"
                )
            replay = PermissionProjectionAdapter.replay(
                _field_text(payload, "profileId"),
                profile,
                provider=provider,
                version=version,
                representable=representable,
            )
            PermissionProjectionAdapter.require_exact(replay)
            return replay.to_wire()
        if name == "elmos-invocation-scoped-capability-lease":
            _exact_fields(
                payload,
                allowed={
                    "action",
                    "leaseId",
                    "environmentId",
                    "authoritySnapshotId",
                    "capabilities",
                    "delegationAllowed",
                    "expiresAt",
                    "capability",
                    "reason",
                },
                required={"leaseId"},
                label="capability lease",
            )
            action = _field_text(payload, "action", default="issue")
            lease_id = _field_text(payload, "leaseId")
            if action == "use":
                _exact_fields(
                    payload,
                    allowed={"action", "leaseId", "capability"},
                    required={"action", "leaseId", "capability"},
                    label="capability lease use",
                )
                lease = state.lease_broker.get(lease_id)
                if lease is None:
                    raise ContractError("unknown capability lease")
                capability = _field_text(payload, "capability")
                if (
                    lease.execution_epoch != invocation.execution_epoch
                    or lease.authority_snapshot_id != context.authority_revision
                    or lease.environment_id
                    != authority.security_bindings["environmentId"]
                    or capability not in authority.capabilities
                ):
                    raise ContractError(
                        "capability lease is not authorized in this Host scope"
                    )
                lease.use(
                    lease.invocation_id,
                    invocation.execution_epoch,
                    capability,
                )
                return lease.to_wire()
            if action == "revoke":
                _exact_fields(
                    payload,
                    allowed={"action", "leaseId", "reason"},
                    required={"action", "leaseId", "reason"},
                    label="capability lease revocation",
                )
                lease = state.lease_broker.get(lease_id)
                if lease is None:
                    raise ContractError("unknown capability lease")
                if (
                    lease.execution_epoch != invocation.execution_epoch
                    or lease.authority_snapshot_id != context.authority_revision
                    or lease.environment_id
                    != authority.security_bindings["environmentId"]
                    or not lease.capabilities <= authority.capabilities
                ):
                    raise ContractError(
                        "capability lease is not authorized in this Host scope"
                    )
                reason = _field_text(payload, "reason")
                if reason not in {
                    "CANCELLED",
                    "TIMED_OUT",
                    "EXECUTOR_REPLACED",
                    "AUTHORITY_REVOKED",
                    "COMPLETED",
                }:
                    raise ContractError(
                        "capability lease revocation reason is unsupported"
                    )
                return state.lease_broker.revoke(lease_id).to_wire() | {
                    "revocationReason": reason
                }
            if action != "issue":
                raise ContractError("unsupported capability lease lifecycle action")
            required_issue = {
                "leaseId",
                "environmentId",
                "authoritySnapshotId",
                "capabilities",
                "delegationAllowed",
                "expiresAt",
            }
            if not required_issue <= set(payload):
                raise ContractError("capability lease issue is missing required fields")
            if set(payload) - (required_issue | {"action"}):
                raise ContractError(
                    "capability lease issue contains lifecycle-only fields"
                )
            authority_snapshot_id = _field_text(payload, "authoritySnapshotId")
            if authority_snapshot_id != context.authority_revision:
                raise ContractError("capability lease authority snapshot is stale")
            environment_id = _field_text(payload, "environmentId")
            lease_capabilities = frozenset(
                _field_strings(payload, "capabilities", allow_empty=False)
            )
            delegation_allowed = _field_bool(payload, "delegationAllowed")
            if environment_id not in authority.environment_ids:
                raise ContractError(
                    "capability lease environment is not host-authorized"
                )
            if not lease_capabilities <= authority.capabilities:
                raise ContractError("capability lease widens trusted host authority")
            if (
                delegation_allowed
                and invocation.invocation_id
                not in authority.delegation_allowed_invocations
            ):
                raise ContractError("capability delegation is not host-authorized")
            lease = state.lease_broker.issue(
                lease_id=lease_id,
                invocation_id=invocation.invocation_id,
                environment_id=environment_id,
                authority_snapshot_id=authority_snapshot_id,
                execution_epoch=invocation.execution_epoch,
                capabilities=lease_capabilities,
                expires_at=_parse_datetime(payload.get("expiresAt"), "expiresAt"),
                delegation_allowed=delegation_allowed,
            )
            return lease.to_wire()
        if name == "elmos-host-minted-security-context":
            _exact_fields(
                payload,
                allowed={"eligible", "accountStable", "bindings", "entitlements"},
                required={"eligible", "accountStable", "bindings", "entitlements"},
                label="host security context request",
            )
            bindings = _field_mapping(payload, "bindings")
            _exact_fields(
                bindings,
                allowed=VerifiedSecurityContext.REQUIRED_BINDINGS,
                required=VerifiedSecurityContext.REQUIRED_BINDINGS,
                label="security context bindings",
            )
            if dict(bindings) != dict(authority.security_bindings):
                raise ContractError(
                    "caller security bindings do not match the host snapshot"
                )
            caller_entitlements = _freeze(_field_mapping(payload, "entitlements"))
            if caller_entitlements != authority.entitlements:
                raise ContractError(
                    "caller entitlements do not match the host snapshot"
                )
            if (
                _field_bool(payload, "eligible") != authority.security_eligible
                or _field_bool(payload, "accountStable") != authority.account_stable
            ):
                raise ContractError(
                    "caller security eligibility does not match the host snapshot"
                )
            if self._privileged_path_policy is None:
                raise ContractError("privileged path policy is not configured")
            try:
                self._privileged_path_policy.validate_entitlements(
                    authority.entitlements
                )
            except AssurancePolicyValidationError as exc:
                raise ContractError("privileged entitlement policy denied") from exc
            minted = self._security_context_broker.mint_context(
                eligible=authority.security_eligible,
                account_stable=authority.account_stable,
                bindings=authority.security_bindings,
                entitlements=authority.entitlements,
            )
            if minted.status != "VERIFIED":
                return DeltaResult(
                    invocation.invocation_id,
                    ResultStatus.UNKNOWN,
                    message="host security eligibility is not verified",
                )
            self._security_context_broker.verify(minted)
            return minted.to_wire()
        if name == "elmos-environment-attachment-authority":
            _exact_fields(
                payload,
                allowed={
                    "action",
                    "serverId",
                    "settingsAuthority",
                    "settingsDigest",
                    "expectedSnapshotId",
                    "expectedGeneration",
                    "ownerSnapshotId",
                    "ownerPermissions",
                    "ownerId",
                    "parentSnapshotId",
                    "parentPermissions",
                    "parentOwnerId",
                    "environmentId",
                    "permissionProfileVersion",
                    "ownerEffectivePolicyHash",
                    "parentEffectivePolicyHash",
                    "policyPermissions",
                    "snapshotId",
                },
                required={
                    "action",
                    "serverId",
                    "settingsAuthority",
                    "settingsDigest",
                    "expectedSnapshotId",
                    "expectedGeneration",
                    "ownerSnapshotId",
                    "ownerPermissions",
                    "ownerId",
                    "parentSnapshotId",
                    "parentPermissions",
                    "parentOwnerId",
                    "environmentId",
                    "permissionProfileVersion",
                    "ownerEffectivePolicyHash",
                    "parentEffectivePolicyHash",
                    "policyPermissions",
                    "snapshotId",
                },
                label="environment attachment authority",
            )
            attachment_action = _field_text(payload, "action")
            if attachment_action not in {"attach", "refresh"}:
                raise ContractError("unsupported environment attachment action")
            server_id = _field_text(payload, "serverId")
            environment_id = _field_text(payload, "environmentId")
            settings = _field_mapping(payload, "settingsAuthority")
            settings_digest = _field_text(payload, "settingsDigest")
            settings_binding = authority.environment_settings(server_id, environment_id)
            if _freeze(
                settings
            ) != settings_binding.settings_authority or not hmac.compare_digest(
                _normalize_sha256(settings_digest, "settings digest"),
                settings_binding.settings_digest,
            ):
                raise ContractError(
                    "environment settings differ from trusted Host authority"
                )
            expected_generation = _field_int(payload, "expectedGeneration")
            expected_snapshot_raw = payload.get("expectedSnapshotId")
            if attachment_action == "attach":
                if expected_generation != 0 or expected_snapshot_raw is not None:
                    raise ContractError(
                        "initial attachment requires generation zero and no snapshot"
                    )
                if settings_binding.previous_settings_authority is not None:
                    raise ContractError(
                        "initial attachment cannot carry previous settings authority"
                    )
            else:
                expected_snapshot_id = _text(
                    expected_snapshot_raw, "expected snapshot id"
                )
                if expected_generation < 1:
                    raise ContractError(
                        "attachment refresh requires a positive generation"
                    )
                if (
                    settings_binding.previous_settings_authority is None
                    or settings_binding.previous_snapshot_id != expected_snapshot_id
                ):
                    raise ContractError(
                        "attachment refresh snapshot is not Host-authorized"
                    )
                if not _settings_are_equal_or_narrower(
                    settings_binding.settings_authority,
                    settings_binding.previous_settings_authority,
                ):
                    raise ContractError(
                        "attachment refresh widens Host settings authority"
                    )
            profile_version = _field_text(payload, "permissionProfileVersion")
            owner = AuthoritySnapshot(
                _field_text(payload, "ownerSnapshotId"),
                frozenset(_field_strings(payload, "ownerPermissions")),
                _field_text(payload, "ownerId"),
                environment_id,
                profile_version,
                _field_text(payload, "ownerEffectivePolicyHash"),
            )
            parent = AuthoritySnapshot(
                _field_text(payload, "parentSnapshotId"),
                frozenset(_field_strings(payload, "parentPermissions")),
                _field_text(payload, "parentOwnerId"),
                environment_id,
                profile_version,
                _field_text(payload, "parentEffectivePolicyHash"),
            )
            if environment_id not in authority.environment_ids:
                raise ContractError("attachment environment is not host-authorized")
            if profile_version not in authority.permission_profile_versions:
                raise ContractError(
                    "attachment permission profile is not host-authorized"
                )
            if (
                owner != authority.owner_authority
                or parent != authority.parent_authority_snapshot
            ):
                raise ContractError(
                    "caller authority snapshots do not match the host snapshot"
                )
            if (
                frozenset(_field_strings(payload, "policyPermissions"))
                != authority.policy_permissions
            ):
                raise ContractError(
                    "caller policy permissions do not match the host snapshot"
                )
            snapshot_id = _field_text(payload, "snapshotId")
            if snapshot_id != authority.authority_result_snapshot_id:
                raise ContractError("attachment result snapshot id is not host-minted")
            calculated = AuthorityCalculator.calculate(
                authority.owner_authority,
                authority.parent_authority_snapshot,
                authority.policy_permissions,
                snapshot_id,
            )
            turn_environment = TurnEnvironment(
                environment_id,
                server_id,
                settings_binding.settings_authority,
                settings_binding.settings_digest,
            )
            return {
                "action": attachment_action,
                "serverId": server_id,
                "environmentId": environment_id,
                "snapshotId": snapshot_id,
                "previousSnapshotId": expected_snapshot_raw,
                "generation": expected_generation + 1,
                "authority": calculated.to_wire(),
                "turnEnvironment": turn_environment.to_wire(),
                "settingsDigest": settings_binding.settings_digest,
            }
        if name == "elmos-executor-generation-fencing":
            _exact_fields(
                payload,
                allowed={
                    "generation",
                    "connectionEpoch",
                    "environmentId",
                    "executorIdentity",
                    "action",
                    "liveProbeEvidenceRef",
                },
                required={
                    "generation",
                    "connectionEpoch",
                    "environmentId",
                    "executorIdentity",
                    "action",
                },
                label="executor generation fence",
            )
            environment_id = _field_text(payload, "environmentId")
            executor_identity = _field_text(payload, "executorIdentity")
            supplied_generation = _field_int(payload, "generation", positive=True)
            supplied_epoch = _field_int(payload, "connectionEpoch", positive=True)
            action = _field_text(payload, "action")
            if (environment_id, executor_identity) not in authority.executor_bindings:
                raise ContractError(
                    "executor identity is not host-authorized for this environment"
                )
            fence_key = (environment_id, executor_identity)
            with self._lock:
                fence = state.executor_fences.get(fence_key)
                if action == "replace" and fence is None:
                    predecessors = tuple(
                        candidate
                        for candidate in state.executor_fences.values()
                        if candidate.environment_id == environment_id
                        and candidate.generation == supplied_generation
                        and candidate.connection_epoch == supplied_epoch
                        and candidate.state == "ACTIVE"
                    )
                    if len(predecessors) != 1:
                        raise ContractError(
                            "executor replacement requires one exact active predecessor"
                        )
                    predecessor = predecessors[0]
                    if predecessor.executor_identity == executor_identity:
                        raise ContractError(
                            "executor replacement requires a new identity"
                        )
                    predecessor.retire()
                    fence = ExecutorGenerationManager(
                        supplied_generation + 1,
                        supplied_epoch + 1,
                        environment_id=environment_id,
                        executor_identity=executor_identity,
                    )
                    fence.require_reconciliation(predecessor)
                    state.executor_fences[fence_key] = fence
                    return {
                        "action": "replace",
                        "retiredPredecessor": predecessor.to_wire(),
                        "replacement": fence.to_wire(),
                        "reconciliationEffects": [
                            _thaw(item) for item in fence.replacement_effects
                        ],
                        "activationAllowed": False,
                    }
                if fence is None:
                    if action not in {"activate", "fail"}:
                        raise ContractError(
                            "executor lifecycle requires an existing generation"
                        )
                    fence = ExecutorGenerationManager(
                        supplied_generation,
                        supplied_epoch,
                        environment_id=environment_id,
                        executor_identity=executor_identity,
                    )
                    state.executor_fences[fence_key] = fence
                elif (fence.generation, fence.connection_epoch) != (
                    supplied_generation,
                    supplied_epoch,
                ):
                    replayed_advance = fence.state == "CONNECTING" and (
                        (
                            action == "reconnect"
                            and fence.generation == supplied_generation
                            and fence.connection_epoch == supplied_epoch + 1
                        )
                        or (
                            action == "replace"
                            and fence.generation == supplied_generation + 1
                            and fence.connection_epoch == supplied_epoch + 1
                        )
                    )
                    if replayed_advance:
                        if action == "replace":
                            return {
                                "action": "replace",
                                "retiredPredecessor": _thaw(fence.retired_predecessor),
                                "replacement": fence.to_wire(),
                                "reconciliationEffects": [
                                    _thaw(item) for item in fence.replacement_effects
                                ],
                                "activationAllowed": fence.replacement_reconciled,
                            }
                        return fence.to_wire()
                    raise ContractError("stale executor generation or connection epoch")
                if action == "reconnect":
                    fence.reconnect_same()
                elif action == "replace":
                    raise ContractError(
                        "executor replacement identity already occupies the fence"
                    )
                elif action == "activate":
                    live_probe = _field_text(payload, "liveProbeEvidenceRef")
                    if live_probe not in authority.verified_evidence_refs:
                        raise ContractError(
                            "executor activation probe is not verified host evidence"
                        )
                    fence.activate(live_probe_evidence_ref=live_probe)
                elif action == "accept":
                    fence.accept(supplied_generation, supplied_epoch)
                elif action == "retire":
                    fence.retire()
                elif action == "fail":
                    fence.fail()
                else:
                    raise ContractError("unsupported executor lifecycle action")
                return fence.to_wire()
        if name == "elmos-workspace-ownership-lease":
            _exact_fields(
                payload,
                allowed={
                    "workspaceId",
                    "ownerExecutionId",
                    "newOwnerExecutionId",
                    "generation",
                    "repositoryId",
                    "baseRevision",
                    "writeScopes",
                    "action",
                    "crashEvidenceRef",
                },
                required={"workspaceId", "generation", "action"},
                label="workspace ownership lease",
            )
            workspace_id = _field_text(payload, "workspaceId")
            generation = _field_int(payload, "generation", positive=True)
            action = _field_text(payload, "action")
            workspace_authority = authority.workspace(workspace_id)
            if self._managed_worktree_registry is None:
                raise ContractError("managed worktree registry is not configured")
            try:
                live_identity = self._managed_worktree_registry.require(workspace_id)
            except (
                AssurancePolicyIntegrityError,
                AssurancePolicyValidationError,
            ) as exc:
                raise ContractError(
                    "managed worktree live identity is invalid"
                ) from exc
            if (
                live_identity.repository_id != workspace_authority.repository_id
                or live_identity.base_revision != workspace_authority.base_revision
            ):
                raise ContractError("managed worktree repository/base identity drifted")
            if action == "bind":
                owner_execution_id = _field_text(payload, "ownerExecutionId")
                repository_id = _field_text(payload, "repositoryId")
                base_revision = _field_text(payload, "baseRevision")
                write_scopes = _field_strings(payload, "writeScopes", allow_empty=False)
                if owner_execution_id not in workspace_authority.owners:
                    raise ContractError("workspace owner is not host-authorized")
                if (
                    repository_id != workspace_authority.repository_id
                    or base_revision != workspace_authority.base_revision
                ):
                    raise ContractError(
                        "workspace repository/base revision is not host-authorized"
                    )
                if not workspace_authority.permits_scopes(write_scopes):
                    raise ContractError("workspace write scopes widen host authority")
                workspace_lease = WorkspaceLease(
                    workspace_id,
                    owner_execution_id,
                    generation,
                    repository_id,
                    base_revision,
                    write_scopes,
                )
                return state.workspace_manager.bind(workspace_lease).to_wire()
            current = state.workspace_manager.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            if current.generation != generation:
                if (
                    action in {"takeover", "acceptHandoff"}
                    and current.generation == generation + 1
                ):
                    replay_owner = _field_text(payload, "newOwnerExecutionId")
                    if (
                        current.state == "ACTIVE"
                        and replay_owner in workspace_authority.owners
                        and current.owner_execution_id == replay_owner
                        and (
                            "baseRevision" not in payload
                            or _field_text(payload, "baseRevision")
                            == current.base_revision
                        )
                        and (
                            "writeScopes" not in payload
                            or _field_strings(payload, "writeScopes")
                            == current.write_scopes
                        )
                    ):
                        return current.to_wire()
                raise ContractError("workspace lease generation is stale")
            if action == "handoff":
                if (
                    _field_text(payload, "ownerExecutionId")
                    != current.owner_execution_id
                ):
                    raise ContractError(
                        "only the current workspace owner may request handoff"
                    )
                return state.workspace_manager.request_handoff(workspace_id).to_wire()
            if action == "resume":
                if (
                    _field_text(payload, "ownerExecutionId")
                    != current.owner_execution_id
                    or current.state != "ACTIVE"
                ):
                    raise ContractError(
                        "workspace resume requires its exact active owner"
                    )
                return current.to_wire()
            if action == "markTakeoverPending":
                crash_evidence_ref = _field_text(payload, "crashEvidenceRef")
                if crash_evidence_ref not in authority.verified_evidence_refs:
                    raise ContractError("workspace crash evidence is not Host-verified")
                return state.workspace_manager.mark_takeover_pending(
                    workspace_id,
                    crash_evidence_ref=crash_evidence_ref,
                ).to_wire()
            if action == "takeover":
                new_owner = _field_text(payload, "newOwnerExecutionId")
                if new_owner not in workspace_authority.owners:
                    raise ContractError(
                        "workspace takeover owner is not host-authorized"
                    )
                return state.workspace_manager.takeover(
                    workspace_id,
                    new_owner,
                    expected_generation=generation,
                    base_revision=_optional_field_text(payload, "baseRevision"),
                    write_scopes=_field_strings(payload, "writeScopes")
                    if "writeScopes" in payload
                    else None,
                ).to_wire()
            if action == "acceptHandoff":
                new_owner = _field_text(payload, "newOwnerExecutionId")
                if new_owner not in workspace_authority.owners:
                    raise ContractError(
                        "workspace handoff owner is not host-authorized"
                    )
                return state.workspace_manager.accept_handoff(
                    workspace_id,
                    new_owner,
                    expected_generation=generation,
                    base_revision=_optional_field_text(payload, "baseRevision"),
                    write_scopes=_field_strings(payload, "writeScopes")
                    if "writeScopes" in payload
                    else None,
                ).to_wire()
            if action == "retire":
                if (
                    _field_text(payload, "ownerExecutionId")
                    != current.owner_execution_id
                ):
                    raise ContractError(
                        "only the current workspace owner may retire the lease"
                    )
                return state.workspace_manager.retire(workspace_id).to_wire()
            raise ContractError("unsupported workspace lifecycle action")
        if name == "elmos-harness-transport-version-negotiation":
            _exact_fields(
                payload,
                allowed={
                    "provider",
                    "version",
                    "requiredVersion",
                    "requiredFeatures",
                    "offered",
                },
                required={"provider", "version", "requiredFeatures"},
                label="protocol negotiation",
            )
            provider = _field_text(payload, "provider")
            version = _field_text(payload, "version")
            protocol_profile = self._protocol_profiles.get((provider, version))
            if protocol_profile is None:
                raise UnsupportedContractError(
                    "protocol provider/version profile is not registered"
                )
            protocol_offer = protocol_profile
            if "offered" in payload:
                offer = _field_mapping(payload, "offered")
                _exact_fields(
                    offer,
                    allowed={
                        "features",
                        "transport",
                        "authScheme",
                        "historyMode",
                        "typedToolResult",
                        "schemaDialect",
                        "consistencyModel",
                    },
                    required={
                        "features",
                        "transport",
                        "authScheme",
                        "historyMode",
                        "typedToolResult",
                        "schemaDialect",
                        "consistencyModel",
                    },
                    label="protocol capability offer",
                )
                protocol_offer = ProtocolCapabilities(
                    provider,
                    version,
                    frozenset(_field_strings(offer, "features")),
                    _field_text(offer, "transport"),
                    _field_text(offer, "historyMode"),
                    _field_bool(offer, "typedToolResult"),
                    _field_text(offer, "schemaDialect"),
                    _field_text(offer, "consistencyModel"),
                    _optional_field_text(offer, "authScheme"),
                )
            return state.protocol_negotiator.negotiate(
                protocol_offer,
                required_features=_field_strings(payload, "requiredFeatures"),
                required_version=_optional_field_text(payload, "requiredVersion"),
                connection_epoch=invocation.execution_epoch,
            ).to_wire()
        if name == "elmos-skill-trust-domain-provenance":
            _exact_fields(
                payload,
                allowed={"provenance", "skillPath"},
                required={"provenance", "skillPath"},
                label="Skill provenance verification",
            )
            if self._skill_trust_policy is None:
                raise UnsupportedContractError(
                    "Skill trust-domain policy is not configured"
                )
            provenance = _field_mapping(payload, "provenance")
            _exact_fields(
                provenance,
                allowed={
                    "skillId",
                    "publisher",
                    "origin",
                    "canonicalUri",
                    "packageDigest",
                    "trustDomain",
                    "installScope",
                    "authorizationSemantics",
                    "signature",
                    "verified",
                },
                required={
                    "skillId",
                    "publisher",
                    "origin",
                    "canonicalUri",
                    "packageDigest",
                    "trustDomain",
                    "installScope",
                    "authorizationSemantics",
                },
                label="Skill provenance",
            )
            if "verified" in provenance:
                if not isinstance(provenance["verified"], bool):
                    raise ContractError(
                        "Skill provenance verified claim must be boolean"
                    )
                if provenance["verified"]:
                    raise ContractError(
                        "caller cannot self-assert verified Skill provenance"
                    )
            record = SkillProvenance(
                _field_text(provenance, "skillId"),
                _field_text(provenance, "publisher"),
                _field_text(provenance, "origin"),
                _field_text(provenance, "canonicalUri"),
                _field_text(provenance, "packageDigest"),
                _field_text(provenance, "trustDomain"),
                _field_text(provenance, "installScope"),
                _field_strings(provenance, "authorizationSemantics"),
                _optional_field_text(provenance, "signature"),
                False,
            )
            verified = SkillTrustVerifier.verify_provenance(
                record,
                skill_path=Path(_field_text(payload, "skillPath")),
                trust_policy=self._skill_trust_policy,
                signature_verifier=self._skill_signature_verifier,
            )
            return verified.to_wire()
        if name == "elmos-registered-durable-plugin-events":
            action = _field_text(payload, "action")

            def event_envelope(value: Mapping[str, Any]) -> DurableEventEnvelope:
                _exact_fields(
                    value,
                    allowed={
                        "eventId",
                        "type",
                        "schemaVersion",
                        "payload",
                        "correlationId",
                        "causationId",
                    },
                    required={
                        "eventId",
                        "type",
                        "schemaVersion",
                        "payload",
                        "correlationId",
                    },
                    label="durable event envelope",
                )
                return DurableEventEnvelope(
                    _field_text(value, "eventId"),
                    _field_text(value, "type"),
                    _field_int(value, "schemaVersion", positive=True),
                    _field_mapping(value, "payload"),
                    _field_text(value, "correlationId"),
                    _optional_field_text(value, "causationId"),
                )

            def event_sequence(field_name: str) -> tuple[DurableEventEnvelope, ...]:
                raw_events = payload.get(field_name)
                if not isinstance(raw_events, (tuple, list)):
                    raise ContractError(f"{field_name} must be an array")
                return tuple(
                    event_envelope(_mapping(item, field_name)) for item in raw_events
                )

            if action == "register":
                _exact_fields(
                    payload,
                    allowed={"action", "registration"},
                    required={"action", "registration"},
                    label="durable event registration request",
                )
                registration = _field_mapping(payload, "registration")
                _exact_fields(
                    registration,
                    allowed={
                        "type",
                        "owner",
                        "schemaVersion",
                        "semantics",
                        "validator",
                        "upgrader",
                        "projections",
                        "compatibility",
                    },
                    required={
                        "type",
                        "owner",
                        "schemaVersion",
                        "semantics",
                        "validator",
                        "upgrader",
                        "projections",
                        "compatibility",
                    },
                    label="durable event registration",
                )
                event = EventRegistration(
                    _field_text(registration, "type"),
                    _field_text(registration, "owner"),
                    _field_int(registration, "schemaVersion", positive=True),
                    _field_text(registration, "semantics"),
                    _field_text(registration, "validator"),
                    _field_text(registration, "upgrader"),
                    _field_strings(registration, "projections"),
                    _field_text(registration, "compatibility"),
                )
                trusted_registration = authority.event_registration(
                    event.event_type,
                    event.schema_version,
                )
                if event.to_wire() != trusted_registration.to_wire():
                    raise ContractError(
                        "plugin event registration differs from the host registry"
                    )
                state.event_registry.register(trusted_registration)
                return {"action": action, "registration": event.to_wire()}
            if action in {"append", "replay"}:
                allowed = {"action", "event"}
                if action == "replay":
                    allowed.update({"targetVersion", "unknownOptional"})
                _exact_fields(
                    payload,
                    allowed=allowed,
                    required=allowed,
                    label=f"durable event {action}",
                )
                envelope = event_envelope(_field_mapping(payload, "event"))
                unknown_optional = (
                    _field_bool(payload, "unknownOptional")
                    if action == "replay"
                    else False
                )
                if not unknown_optional:
                    authority.event_registration(
                        envelope.event_type, envelope.schema_version
                    )
                elif envelope.event_type not in self._optional_unknown_event_types:
                    raise ContractError("optional replay skip is not Host-authorized")
                replayed_payload = state.event_registry.replay(
                    envelope.event_type,
                    envelope.schema_version,
                    envelope.payload,
                    unknown_optional=unknown_optional,
                    target_version=(
                        _field_int(payload, "targetVersion", positive=True)
                        if action == "replay"
                        else envelope.schema_version
                    ),
                )
                return {
                    "action": action,
                    "event": (
                        None
                        if replayed_payload is None
                        else replace(
                            envelope,
                            schema_version=(
                                _field_int(payload, "targetVersion", positive=True)
                                if action == "replay"
                                else envelope.schema_version
                            ),
                            payload=replayed_payload,
                        ).to_wire()
                    ),
                    "state": (
                        "SKIPPED"
                        if replayed_payload is None
                        else ("PENDING" if action == "append" else "PROCESSED")
                    ),
                    "skipped": replayed_payload is None,
                    "durableRequired": True,
                }
            if action == "preflightOwnerChange":
                _exact_fields(
                    payload,
                    allowed={
                        "action",
                        "operation",
                        "eventType",
                        "targetVersion",
                        "persistedEvents",
                    },
                    required={"action", "operation", "eventType", "persistedEvents"},
                    label="durable event owner-change preflight",
                )
                operation = _field_text(payload, "operation")
                persisted = event_sequence("persistedEvents")
                event_type = _field_text(payload, "eventType")
                if operation == "UNINSTALL":
                    decision = state.event_registry.preflight_uninstall(
                        event_type, persisted_events=persisted
                    )
                elif operation == "DOWNGRADE":
                    decision = state.event_registry.preflight_downgrade(
                        event_type,
                        _field_int(payload, "targetVersion", positive=True),
                        persisted_events=persisted,
                    )
                else:
                    raise ContractError("unsupported durable owner-change operation")
                return {
                    "action": action,
                    "preflight": decision,
                    "durableRequired": True,
                }
            if action == "forkReplay":
                _exact_fields(
                    payload,
                    allowed={"action", "forkId", "events"},
                    required={"action", "forkId", "events"},
                    label="durable event fork replay",
                )
                replayed = state.event_registry.replay_for_fork(
                    event_sequence("events"), fork_id=_field_text(payload, "forkId")
                )
                return {
                    "action": action,
                    "forkId": payload["forkId"],
                    "events": [item.to_wire() for item in replayed],
                    "durableRequired": True,
                }
            if action == "migrationReplay":
                _exact_fields(
                    payload,
                    allowed={"action", "migrationId", "events", "targetVersions"},
                    required={"action", "migrationId", "events", "targetVersions"},
                    label="durable event migration replay",
                )
                target_versions_raw = _field_mapping(payload, "targetVersions")
                targets = {
                    _text(key, "migration event type"): _positive(
                        value, "migration target version"
                    )
                    for key, value in target_versions_raw.items()
                }
                replayed = state.event_registry.replay_for_migration(
                    event_sequence("events"),
                    migration_id=_field_text(payload, "migrationId"),
                    target_versions=targets,
                )
                return {
                    "action": action,
                    "migrationId": payload["migrationId"],
                    "events": [item.to_wire() for item in replayed],
                    "targetVersions": targets,
                    "durableRequired": True,
                }
            raise ContractError("unsupported durable event action")
        if name == "elmos-typed-external-ingress":
            action = _field_text(payload, "action")
            if action == "page":
                _exact_fields(
                    payload,
                    allowed={
                        "action",
                        "correlationId",
                        "limit",
                        "afterOccurredAt",
                        "afterIngressId",
                    },
                    required={
                        "action",
                        "correlationId",
                        "limit",
                        "afterOccurredAt",
                        "afterIngressId",
                    },
                    label="typed ingress page request",
                )
                limit = _field_int(payload, "limit", positive=True)
                if limit > 1000:
                    raise ContractError("typed ingress page limit is too large")
                after_occurred_at = payload.get("afterOccurredAt")
                after_ingress_id = payload.get("afterIngressId")
                if (after_occurred_at is None) is not (after_ingress_id is None):
                    raise ContractError(
                        "typed ingress keyset cursor fields must be supplied together"
                    )
                if after_occurred_at is not None:
                    parsed_after = _parse_datetime(after_occurred_at, "afterOccurredAt")
                    assert parsed_after is not None
                    normalized_after = _wire_time(parsed_after, "afterOccurredAt")
                    checked_after_id = _text(after_ingress_id, "afterIngressId")
                else:
                    normalized_after = None
                    checked_after_id = None
                return {
                    "action": "page",
                    "correlationId": _field_text(payload, "correlationId"),
                    "limit": limit,
                    "keysetCursor": {
                        "afterOccurredAt": normalized_after,
                        "afterIngressId": checked_after_id,
                    },
                    "readOnly": True,
                    "durableRequired": True,
                }
            if action != "ingest":
                raise ContractError("unsupported typed ingress action")
            _exact_fields(
                payload,
                allowed={"action", "ingress"},
                required={"action", "ingress"},
                label="typed ingress request",
            )
            ingress_data = _field_mapping(payload, "ingress")
            _exact_fields(
                ingress_data,
                allowed={
                    "ingressId",
                    "kind",
                    "producerExecutionId",
                    "eventId",
                    "causationId",
                    "correlationId",
                    "content",
                    "originatingCallId",
                    "deduplicationKey",
                },
                required={
                    "ingressId",
                    "kind",
                    "producerExecutionId",
                    "eventId",
                    "causationId",
                    "correlationId",
                    "content",
                },
                label="typed ingress",
            )
            ingress_content = _typed_ingress_content(ingress_data.get("content"))
            ingress = TypedIngress(
                _field_text(ingress_data, "ingressId"),
                _field_text(ingress_data, "kind"),
                _field_text(ingress_data, "producerExecutionId"),
                _field_text(ingress_data, "eventId"),
                _field_text(ingress_data, "causationId"),
                _field_text(ingress_data, "correlationId"),
                ingress_content,
                _optional_field_text(ingress_data, "originatingCallId"),
                _optional_field_text(ingress_data, "deduplicationKey"),
            )
            configured_producers = self._authorized_producers.get(
                (context.tenant_id, context.project_id), MappingProxyType({})
            )
            producers = {
                producer: kinds
                for producer, kinds in configured_producers.items()
                if producer in authority.authorized_producers
            }
            accepted = state.ingress_router.accept(
                ingress,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                authorized_producers=producers,
                pending_calls=authority.pending_calls,
            )
            return {
                "action": "ingest",
                "accepted": accepted,
                "ingress": ingress.to_wire(),
                "durableRequired": True,
            }
        if name == "elmos-subagent-model-execution-spec":
            _exact_fields(
                payload,
                allowed={
                    "provider",
                    "model",
                    "reasoningEffort",
                    "maxOutputTokens",
                    "parentExecutionId",
                    "environmentId",
                    "parentEnvironmentId",
                    "authoritySnapshotId",
                    "budgetReservationId",
                    "parentAuthority",
                    "childAuthority",
                    "parentTools",
                    "childTools",
                    "parentMaxOutputTokens",
                    "toolPlanHash",
                    "costBudget",
                    "wallClockDeadline",
                },
                required={
                    "provider",
                    "model",
                    "reasoningEffort",
                    "maxOutputTokens",
                    "parentExecutionId",
                    "environmentId",
                    "parentEnvironmentId",
                    "authoritySnapshotId",
                    "budgetReservationId",
                    "parentAuthority",
                    "childAuthority",
                    "parentTools",
                    "childTools",
                    "parentMaxOutputTokens",
                    "toolPlanHash",
                    "costBudget",
                    "wallClockDeadline",
                },
                label="subagent execution specification",
            )
            authority_snapshot_id = _field_text(payload, "authoritySnapshotId")
            if authority_snapshot_id != context.authority_revision:
                raise ContractError("subagent authority snapshot is stale")
            parent_execution_id = _field_text(payload, "parentExecutionId")
            parent_authority = frozenset(_field_strings(payload, "parentAuthority"))
            parent_tools = frozenset(_field_strings(payload, "parentTools"))
            parent_max_output_tokens = _field_int(
                payload, "parentMaxOutputTokens", positive=True
            )
            environment_id = _field_text(payload, "environmentId")
            parent_environment_id = _field_text(payload, "parentEnvironmentId")
            reservation_id = _field_text(payload, "budgetReservationId")
            requested_tokens = _field_int(payload, "maxOutputTokens", positive=True)
            if parent_execution_id != authority.parent_execution_id:
                raise ContractError("subagent parent execution is not host-authorized")
            if parent_authority != authority.parent_authority:
                raise ContractError(
                    "subagent parent authority does not match the host snapshot"
                )
            if parent_tools != authority.parent_tools:
                raise ContractError(
                    "subagent parent tools do not match the host snapshot"
                )
            if parent_max_output_tokens != authority.parent_max_output_tokens:
                raise ContractError(
                    "subagent parent budget does not match the host snapshot"
                )
            if (
                environment_id not in authority.environment_ids
                or parent_environment_id not in authority.environment_ids
            ):
                raise ContractError("subagent environment is not host-authorized")
            reservation = authority.subagent_reservation(reservation_id)
            requested_child_authority = frozenset(
                _field_strings(payload, "childAuthority")
            )
            requested_child_tools = frozenset(_field_strings(payload, "childTools"))
            if (
                reservation.invocation_id != invocation.invocation_id
                or reservation.parent_execution_id != parent_execution_id
                or reservation.environment_id != environment_id
                or reservation.authority_snapshot_id != authority_snapshot_id
                or reservation.provider != _field_text(payload, "provider")
                or reservation.model != _field_text(payload, "model")
                or reservation.reasoning_effort
                != _field_text(payload, "reasoningEffort")
                or reservation.child_authority != requested_child_authority
                or reservation.child_tools != requested_child_tools
            ):
                raise ContractError(
                    "subagent request differs from its full Host reservation"
                )
            reserved_tokens = reservation.max_output_tokens
            if requested_tokens > reservation.max_output_tokens:
                raise ContractError(
                    "subagent output exceeds the host budget reservation"
                )
            tool_plan_hash = _field_text(payload, "toolPlanHash")
            if tool_plan_hash != reservation.tool_plan_hash:
                raise ContractError(
                    "subagent tool plan differs from its Host reservation"
                )
            cost_budget = _decimal_budget(payload.get("costBudget"), "costBudget")
            if Decimal(cost_budget) > Decimal(reservation.max_cost_budget):
                raise ContractError("subagent cost exceeds its Host reservation")
            wall_clock_deadline = _parse_datetime(
                payload.get("wallClockDeadline"), "wallClockDeadline"
            )
            assert wall_clock_deadline is not None
            if wall_clock_deadline > reservation.wall_clock_deadline:
                raise ContractError("subagent deadline exceeds its Host reservation")
            allowed_models = (
                self._allowed_subagent_models & authority.allowed_subagent_models
            )
            return SubagentSpecCompiler.compile(
                provider=_field_text(payload, "provider"),
                model=_field_text(payload, "model"),
                reasoning_effort=_field_text(payload, "reasoningEffort"),
                max_output_tokens=requested_tokens,
                invocation_id=invocation.invocation_id,
                parent_execution_id=parent_execution_id,
                environment_id=environment_id,
                authority_snapshot_id=authority_snapshot_id,
                budget_reservation_id=reservation_id,
                parent_authority=parent_authority,
                child_authority=requested_child_authority,
                parent_tools=parent_tools,
                child_tools=requested_child_tools,
                parent_max_output_tokens=min(parent_max_output_tokens, reserved_tokens),
                parent_environment_id=parent_environment_id,
                allowed_models=allowed_models,
                tool_plan_hash=tool_plan_hash,
                cost_budget=cost_budget,
                wall_clock_deadline=wall_clock_deadline,
            ).to_wire()
        raise ContractError("extension handler is not allowlisted")


__all__ = [
    "AuthorityCalculator",
    "AuthoritySnapshot",
    "BaseSkillOriginBinding",
    "CallIdentity",
    "CapabilityLease",
    "CapabilityLeaseBroker",
    "CommitState",
    "CommittedToolResult",
    "ContractError",
    "DELTA_API_VERSION",
    "DELTA_SKILL_REGISTRY",
    "DELTA_VERSION",
    "DeltaInvocation",
    "DeltaResult",
    "DeltaSkillDescriptor",
    "DeltaSkillRuntime",
    "DurableEventEnvelope",
    "DurableEventRegistry",
    "EventRegistration",
    "ExecutionPlan",
    "ExecutorGenerationManager",
    "EnvironmentSettingsBinding",
    "GenerationFence",
    "IngressKind",
    "IngressHistoryPage",
    "IngressLedger",
    "IngressRouter",
    "InterceptorDecision",
    "MappingResult",
    "ModelSnapshot",
    "PermissionAdapter",
    "PermissionProfile",
    "PermissionProjectionAdapter",
    "PermissionReplay",
    "PendingToolCallBinding",
    "PlanStore",
    "ProtocolCapabilities",
    "ProtocolNegotiator",
    "ResultCommitter",
    "ResultLifecycleCoordinator",
    "ResultStatus",
    "ReviewRequiredError",
    "RuntimeAssuranceAuthority",
    "SecurityContextBroker",
    "SkillProvenance",
    "SkillTrustVerifier",
    "StepExecutionPlanStore",
    "SubagentExecutionSpec",
    "SubagentBudgetReservation",
    "SubagentSpec",
    "SubagentSpecCompiler",
    "ToolResult",
    "TurnEnvironment",
    "ToolFailureKind",
    "TypedIngress",
    "UnsupportedContractError",
    "VerifiedSecurityContext",
    "WorkspaceLease",
    "WorkspaceLeaseManager",
    "WorkspaceAuthority",
    "digest",
]
