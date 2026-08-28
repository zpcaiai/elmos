"""Immutable, fail-closed evidence ledger for PI Harness external gates.

The ledger records facts produced by separately authorized external runs.  It
does not execute infrastructure and it can never emit a certification.  Every
state transition is bound to one frozen release candidate, content-addressed
raw evidence, an exact target, and (where applicable) a cryptographically
verified actor from a distinct trust domain.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Iterator

from .canonical import (
    canonical_bytes,
    digest,
    digest_bytes,
    require_nonempty,
    require_uuid,
    utc_now,
)
from .independent_verifier import (
    Ed25519Backend,
    EvidenceStatement,
    SignedVerification,
    TrustedVerifier,
    VerifierTrustStore,
)
from .models import ConflictError, PolicyDeniedError
from .production import ExactTarget, ExternalEvidenceState


GATE_IDS: tuple[str, ...] = (
    "P0-G01",
    "P0-G02",
    "P0-G03",
    "P0-G04",
    "P0-G05",
    "P0-G06",
    "P1-G07",
    "P0-G08",
)

GATE_NAMES: Mapping[str, str] = MappingProxyType({
    "P0-G01": "postgresql",
    "P0-G02": "temporal",
    "P0-G03": "cloud_provider",
    "P0-G04": "idp_mtls",
    "P0-G05": "independent_verifier",
    "P0-G06": "disaster_recovery",
    "P1-G07": "customer_acceptance",
    "P0-G08": "production_deployment",
})

RELEASE_SCHEMA_VERSION = "elmos.pi-harness.release-candidate/v1"
EXECUTION_SCHEMA_VERSION = "elmos.pi-harness.external-gate-result/v1"
TRUST_STORE_SCHEMA_VERSION = "elmos.pi-harness.verifier-trust-store/v1"
RECEIPT_SCHEMA_VERSION = "elmos.pi-harness.signed-verification/v1"
EVENT_SCHEMA_VERSION = "elmos.pi-harness.external-gate-event/v1"

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_EVENT_FILE = re.compile(
    r"^(?P<sequence>[0-9]{8})-(?P<event>[0-9a-f]{8}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.json$"
)
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024 * 1024
_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "event_id",
        "event_type",
        "gap_id",
        "release_digest",
        "previous_event_digest",
        "recorded_at",
        "payload",
        "payload_digest",
        "certified",
        "event_digest",
    }
)


def _exact_fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{field} fields mismatch: missing={missing}, extra={extra}")


def _require_digest(value: Any, field: str) -> str:
    text = require_nonempty(value, field, 71)
    if not _DIGEST.fullmatch(text):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _time(value: Any, field: str) -> datetime:
    text = require_nonempty(value, field, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _strings(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(
            f"{field} must be a {'possibly empty ' if allow_empty else 'non-empty '}array"
        )
    result = tuple(require_nonempty(item, f"{field}[]", 4096) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} contains duplicate values")
    return result


def _json_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    canonical_bytes(value)
    return dict(value)


def _read_json(path: Path, *, field: str) -> dict[str, Any]:
    if not path.is_absolute():
        raise ValueError(f"{field} path must be absolute")
    if path.is_symlink():
        raise PolicyDeniedError(f"{field} must not be a symbolic link")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PolicyDeniedError(f"{field} must be a regular file")
        if metadata.st_size > _MAX_JSON_BYTES:
            raise ValueError(f"{field} exceeds {_MAX_JSON_BYTES} bytes")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(_MAX_JSON_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > _MAX_JSON_BYTES:
        raise ValueError(f"{field} exceeds {_MAX_JSON_BYTES} bytes")
    try:
        return _json_object(json.loads(raw), field)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} is not valid UTF-8 JSON") from exc


def _target_from_dict(value: Any) -> ExactTarget:
    target = _json_object(value, "target")
    fields = {"provider", "service", "version", "region", "account_id", "environment"}
    _exact_fields(target, fields, "target")
    return ExactTarget(**{name: target[name] for name in fields})


@dataclass(frozen=True)
class ReleaseCandidate:
    release_id: str
    source_git_sha: str
    package_version: str
    source_archive_digest: str
    artifact_digests: Mapping[str, str]
    implementation_trust_domain: str
    created_at: str
    frozen_by: str
    limitations: tuple[str, ...] = ()
    schema_version: str = RELEASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_SCHEMA_VERSION:
            raise ValueError("unsupported release-candidate schema version")
        require_uuid(self.release_id, "release_id")
        if not _GIT_SHA.fullmatch(
            require_nonempty(self.source_git_sha, "source_git_sha", 40)
        ):
            raise ValueError(
                "source_git_sha must be an exact lowercase 40-character Git SHA"
            )
        require_nonempty(self.package_version, "package_version", 128)
        _require_digest(self.source_archive_digest, "source_archive_digest")
        require_nonempty(
            self.implementation_trust_domain, "implementation_trust_domain", 512
        )
        require_nonempty(self.frozen_by, "frozen_by", 512)
        _time(self.created_at, "created_at")
        if not isinstance(self.artifact_digests, Mapping) or not self.artifact_digests:
            raise ValueError("artifact_digests must be a non-empty object")
        artifacts = dict(self.artifact_digests)
        for name, value in artifacts.items():
            require_nonempty(name, "artifact_digests key", 512)
            _require_digest(value, f"artifact_digests[{name}]")
        if isinstance(self.limitations, str):
            raise ValueError("limitations must be an array")
        limitations = tuple(self.limitations)
        for limitation in limitations:
            require_nonempty(limitation, "limitations[]", 4096)
        object.__setattr__(self, "artifact_digests", MappingProxyType(artifacts))
        object.__setattr__(self, "limitations", limitations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "release_id": self.release_id,
            "source_git_sha": self.source_git_sha,
            "package_version": self.package_version,
            "source_archive_digest": self.source_archive_digest,
            "artifact_digests": dict(sorted(self.artifact_digests.items())),
            "implementation_trust_domain": self.implementation_trust_domain,
            "created_at": self.created_at,
            "frozen_by": self.frozen_by,
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReleaseCandidate":
        fields = {
            "schema_version",
            "release_id",
            "source_git_sha",
            "package_version",
            "source_archive_digest",
            "artifact_digests",
            "implementation_trust_domain",
            "created_at",
            "frozen_by",
            "limitations",
        }
        _exact_fields(value, fields, "release_candidate")
        limitations = _strings(value["limitations"], "limitations", allow_empty=True)
        return cls(
            release_id=value["release_id"],
            source_git_sha=value["source_git_sha"],
            package_version=value["package_version"],
            source_archive_digest=value["source_archive_digest"],
            artifact_digests=_json_object(
                value["artifact_digests"], "artifact_digests"
            ),
            implementation_trust_domain=value["implementation_trust_domain"],
            created_at=value["created_at"],
            frozen_by=value["frozen_by"],
            limitations=limitations,
            schema_version=value["schema_version"],
        )

    @property
    def release_digest(self) -> str:
        return digest(self.to_dict())


@dataclass(frozen=True)
class GateExecution:
    result_id: str
    gap_id: str
    release_digest: str
    target: ExactTarget
    authorization_id: str
    executor_id: str
    producer_trust_domain: str
    environment_digest: str
    started_at: str
    completed_at: str
    raw_evidence_digests: tuple[str, ...]
    replay_reference: str
    status: str
    certified: bool = False
    limitations: tuple[str, ...] = ()
    schema_version: str = EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_SCHEMA_VERSION:
            raise ValueError("unsupported external-gate result schema version")
        require_uuid(self.result_id, "result_id")
        if self.gap_id not in GATE_IDS:
            raise ValueError("unknown external gate")
        if not isinstance(self.target, ExactTarget):
            raise ValueError("target must be an ExactTarget")
        _require_digest(self.release_digest, "release_digest")
        for name in (
            "authorization_id",
            "executor_id",
            "producer_trust_domain",
            "replay_reference",
        ):
            require_nonempty(getattr(self, name), name, 4096)
        _require_digest(self.environment_digest, "environment_digest")
        evidence_digests = tuple(self.raw_evidence_digests)
        if not evidence_digests:
            raise ValueError("raw_evidence_digests cannot be empty")
        for value in evidence_digests:
            _require_digest(value, "raw_evidence_digests[]")
        if len(set(evidence_digests)) != len(evidence_digests):
            raise ValueError("raw_evidence_digests contains duplicates")
        if self.status not in {"EXECUTED", "FAILED", "UNKNOWN"}:
            raise ValueError("execution status must be EXECUTED, FAILED, or UNKNOWN")
        if self.certified is not False:
            raise PolicyDeniedError("an execution result cannot certify the release")
        if _time(self.completed_at, "completed_at") < _time(
            self.started_at, "started_at"
        ):
            raise ValueError("execution completion precedes start")
        if isinstance(self.limitations, str):
            raise ValueError("limitations must be an array")
        limitations = tuple(self.limitations)
        for limitation in limitations:
            require_nonempty(limitation, "limitations[]", 4096)
        object.__setattr__(self, "raw_evidence_digests", evidence_digests)
        object.__setattr__(self, "limitations", limitations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "gap_id": self.gap_id,
            "release_digest": self.release_digest,
            "target": self.target.to_dict(),
            "authorization_id": self.authorization_id,
            "executor_id": self.executor_id,
            "producer_trust_domain": self.producer_trust_domain,
            "environment_digest": self.environment_digest,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "raw_evidence_digests": list(self.raw_evidence_digests),
            "replay_reference": self.replay_reference,
            "status": self.status,
            "certified": False,
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GateExecution":
        fields = {
            "schema_version",
            "result_id",
            "gap_id",
            "release_digest",
            "target",
            "authorization_id",
            "executor_id",
            "producer_trust_domain",
            "environment_digest",
            "started_at",
            "completed_at",
            "raw_evidence_digests",
            "replay_reference",
            "status",
            "certified",
            "limitations",
        }
        _exact_fields(value, fields, "external_gate_result")
        return cls(
            result_id=value["result_id"],
            gap_id=value["gap_id"],
            release_digest=value["release_digest"],
            target=_target_from_dict(value["target"]),
            authorization_id=value["authorization_id"],
            executor_id=value["executor_id"],
            producer_trust_domain=value["producer_trust_domain"],
            environment_digest=value["environment_digest"],
            started_at=value["started_at"],
            completed_at=value["completed_at"],
            raw_evidence_digests=_strings(
                value["raw_evidence_digests"], "raw_evidence_digests"
            ),
            replay_reference=value["replay_reference"],
            status=value["status"],
            certified=value["certified"],
            limitations=_strings(value["limitations"], "limitations", allow_empty=True),
            schema_version=value["schema_version"],
        )

    @property
    def result_digest(self) -> str:
        return digest(self.to_dict())


@dataclass(frozen=True)
class QualificationTrustStore:
    verifiers: tuple[TrustedVerifier, ...]
    roles: Mapping[tuple[str, str], frozenset[str]]
    backend: Ed25519Backend | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        verifiers = tuple(self.verifiers)
        normalized_roles = {
            identity: frozenset(values) for identity, values in self.roles.items()
        }
        object.__setattr__(self, "verifiers", verifiers)
        object.__setattr__(self, "roles", MappingProxyType(normalized_roles))
        identities = {(item.verifier_id, item.key_id) for item in verifiers}
        if len(identities) != len(verifiers):
            raise ValueError("duplicate verifier/key identity")
        if set(self.roles) != identities:
            raise ValueError("every trusted verifier must have an exact role binding")
        allowed = {
            "independent_verifier",
            "acceptance_authority",
            "customer_authority",
            "release_authority",
        }
        allowed_scopes = {
            *(f"external_gate:{gate}" for gate in GATE_IDS),
            *(f"external_gate_acceptance:{gate}" for gate in GATE_IDS),
        }
        domain_roles: dict[str, set[str]] = {}
        for identity, values in self.roles.items():
            if len(values) != 1 or not values <= allowed:
                raise ValueError(f"invalid verifier roles for {identity}")
            verifier = next(
                item
                for item in self.verifiers
                if (item.verifier_id, item.key_id) == identity
            )
            scopes = set(verifier.allowed_scopes)
            if not scopes or not scopes <= allowed_scopes:
                raise ValueError(f"invalid or unbounded scopes for {identity}")
            role = next(iter(values))
            if role == "independent_verifier" and not all(
                scope.startswith("external_gate:") for scope in scopes
            ):
                raise ValueError(
                    "independent verifier may hold only execution verification scopes"
                )
            if role == "customer_authority" and scopes != {
                "external_gate_acceptance:P1-G07"
            }:
                raise ValueError("customer authority must be scoped only to P1-G07")
            if role == "release_authority" and scopes != {
                "external_gate_acceptance:P0-G08"
            }:
                raise ValueError("release authority must be scoped only to P0-G08")
            if role == "acceptance_authority" and not all(
                scope.startswith("external_gate_acceptance:")
                and scope
                not in {
                    "external_gate_acceptance:P1-G07",
                    "external_gate_acceptance:P0-G08",
                }
                for scope in scopes
            ):
                raise ValueError(
                    "generic acceptance authority cannot accept customer or release gates"
                )
            domain_roles.setdefault(verifier.trust_domain, set()).add(role)
        if any(len(values) > 1 for values in domain_roles.values()):
            raise ValueError(
                "one trust domain cannot hold multiple qualification roles"
            )

    def verify(
        self,
        receipt: SignedVerification,
        *,
        expected_subject_digest: str,
        required_role: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        roles = self.roles.get((receipt.verifier_id, receipt.key_id), frozenset())
        if required_role not in roles:
            raise PolicyDeniedError(
                f"receipt signer is not trusted for role {required_role}"
            )
        result = VerifierTrustStore(self.verifiers, backend=self.backend).verify(
            receipt, expected_subject_digest=expected_subject_digest, now=now
        )
        return result | {"roles": sorted(roles)}


def release_candidate_from_file(path: str | Path) -> ReleaseCandidate:
    return ReleaseCandidate.from_dict(_read_json(Path(path), field="release_candidate"))


def gate_execution_from_file(path: str | Path) -> GateExecution:
    return GateExecution.from_dict(_read_json(Path(path), field="external_gate_result"))


def signed_verification_from_dict(value: Mapping[str, Any]) -> SignedVerification:
    fields = {
        "schema_version",
        "receipt_id",
        "verifier_id",
        "verifier_trust_domain",
        "key_id",
        "statement",
        "verdict",
        "issued_at",
        "expires_at",
        "signature_algorithm",
        "signature",
        "receipt_digest",
    }
    _exact_fields(value, fields, "signed_verification")
    if value["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise ValueError("unsupported signed-verification schema version")
    statement_value = _json_object(value["statement"], "statement")
    statement_fields = {
        "statement_id",
        "scope",
        "producer_id",
        "producer_trust_domain",
        "subject_digest",
        "environment_digest",
        "raw_evidence_digests",
        "authorization_id",
        "executor_id",
        "started_at",
        "completed_at",
        "result",
        "limitations",
    }
    _exact_fields(statement_value, statement_fields, "statement")
    statement = EvidenceStatement(
        statement_id=statement_value["statement_id"],
        scope=statement_value["scope"],
        producer_id=statement_value["producer_id"],
        producer_trust_domain=statement_value["producer_trust_domain"],
        subject_digest=statement_value["subject_digest"],
        environment_digest=statement_value["environment_digest"],
        raw_evidence_digests=_strings(
            statement_value["raw_evidence_digests"], "raw_evidence_digests"
        ),
        authorization_id=statement_value["authorization_id"],
        executor_id=statement_value["executor_id"],
        started_at=statement_value["started_at"],
        completed_at=statement_value["completed_at"],
        result=statement_value["result"],
        limitations=_strings(
            statement_value["limitations"], "limitations", allow_empty=True
        ),
    )
    receipt = SignedVerification(
        receipt_id=value["receipt_id"],
        verifier_id=value["verifier_id"],
        verifier_trust_domain=value["verifier_trust_domain"],
        key_id=value["key_id"],
        statement=statement,
        verdict=value["verdict"],
        issued_at=value["issued_at"],
        expires_at=value["expires_at"],
        signature=value["signature"],
        signature_algorithm=value["signature_algorithm"],
    )
    if value["receipt_digest"] != digest(receipt.unsigned_dict()):
        raise PolicyDeniedError("signed verification receipt digest mismatch")
    return receipt


def signed_verification_from_file(path: str | Path) -> SignedVerification:
    return signed_verification_from_dict(
        _read_json(Path(path), field="signed_verification")
    )


def trust_store_from_file(path: str | Path) -> QualificationTrustStore:
    value = _read_json(Path(path), field="verifier_trust_store")
    _exact_fields(value, {"schema_version", "verifiers"}, "verifier_trust_store")
    if value["schema_version"] != TRUST_STORE_SCHEMA_VERSION:
        raise ValueError("unsupported verifier trust-store schema version")
    rows = value["verifiers"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("verifiers must be a non-empty array")
    verifiers: list[TrustedVerifier] = []
    roles: dict[tuple[str, str], frozenset[str]] = {}
    fields = {
        "verifier_id",
        "trust_domain",
        "key_id",
        "public_key_base64",
        "not_before",
        "not_after",
        "revoked",
        "allowed_scopes",
        "roles",
    }
    for index, raw in enumerate(rows):
        item = _json_object(raw, f"verifiers[{index}]")
        _exact_fields(item, fields, f"verifiers[{index}]")
        try:
            public_key = base64.b64decode(item["public_key_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("public_key_base64 is invalid") from exc
        if not isinstance(item["revoked"], bool):
            raise ValueError("revoked must be boolean")
        verifier = TrustedVerifier(
            verifier_id=item["verifier_id"],
            trust_domain=item["trust_domain"],
            key_id=item["key_id"],
            public_key=public_key,
            not_before=item["not_before"],
            not_after=item["not_after"],
            revoked=item["revoked"],
            allowed_scopes=frozenset(
                _strings(item["allowed_scopes"], "allowed_scopes")
            ),
        )
        identity = (verifier.verifier_id, verifier.key_id)
        if identity in roles:
            raise ValueError("duplicate verifier/key identity")
        roles[identity] = frozenset(_strings(item["roles"], "roles"))
        verifiers.append(verifier)
    return QualificationTrustStore(tuple(verifiers), roles)


def _safe_root(path: str | Path, *, create: bool) -> Path:
    root = Path(path)
    if not root.is_absolute():
        raise ValueError("external gate ledger root must be absolute")
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise PolicyDeniedError("ledger path must not contain symbolic links")
            if current != root and not current.is_dir():
                raise PolicyDeniedError("ledger parent path is not a directory")
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise PolicyDeniedError("ledger root must be a non-symlink directory")
    return root


def _write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while persisting immutable ledger object")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _assert_restricted_mode(path: Path, field: str) -> None:
    if path.stat(follow_symlinks=False).st_mode & 0o022:
        raise PolicyDeniedError(f"{field} must not be group/world writable")


class ExternalGateLedger:
    """Append-only release and external-gate evidence ledger."""

    def __init__(self, root: str | Path) -> None:
        self.root = _safe_root(root, create=False)
        _assert_restricted_mode(self.root, "ledger root")
        unexpected = {
            path.name
            for path in self.root.iterdir()
            if path.name not in {"release.json", "events", "objects", ".append.lock"}
        }
        if unexpected:
            raise PolicyDeniedError(
                f"ledger root contains unexpected entries: {sorted(unexpected)}"
            )
        self.release_path = self.root / "release.json"
        self.events_path = self.root / "events"
        self.objects_path = self.root / "objects" / "sha256"
        for path in (self.events_path, self.root / "objects", self.objects_path):
            if not path.is_dir() or path.is_symlink():
                raise PolicyDeniedError(
                    f"ledger directory is missing or unsafe: {path.name}"
                )
            _assert_restricted_mode(path, f"ledger directory {path.name}")
        _assert_restricted_mode(self.release_path, "ledger release")
        self.release = self._load_release()

    @classmethod
    def initialize(
        cls, root: str | Path, release: ReleaseCandidate
    ) -> "ExternalGateLedger":
        target = _safe_root(root, create=True)
        release_path = target / "release.json"
        if not release_path.exists() and any(target.iterdir()):
            raise ConflictError("new ledger root must be empty")
        events = target / "events"
        objects = target / "objects" / "sha256"
        events.mkdir(mode=0o700, parents=True, exist_ok=True)
        objects.mkdir(mode=0o700, parents=True, exist_ok=True)
        for path in (events, target / "objects", objects):
            if path.is_symlink() or not path.is_dir():
                raise PolicyDeniedError("ledger directory hierarchy is unsafe")
        record = {
            "release": release.to_dict(),
            "release_digest": release.release_digest,
            "certification": "NOT_CERTIFIED",
            "certified": False,
        }
        raw = canonical_bytes(record)
        try:
            _write_exclusive(release_path, raw)
            _fsync_directory(target)
        except FileExistsError:
            existing = _read_json(release_path, field="ledger_release")
            if canonical_bytes(existing) != raw:
                raise ConflictError("ledger is already bound to a different release")
        return cls(target)

    def _load_release(self) -> ReleaseCandidate:
        value = _read_json(self.release_path, field="ledger_release")
        _exact_fields(
            value,
            {"release", "release_digest", "certification", "certified"},
            "ledger_release",
        )
        if value["certification"] != "NOT_CERTIFIED" or value["certified"] is not False:
            raise PolicyDeniedError(
                "ledger release contains an unauthorized certification"
            )
        release = ReleaseCandidate.from_dict(
            _json_object(value["release"], "ledger_release.release")
        )
        if value["release_digest"] != release.release_digest:
            raise PolicyDeniedError("ledger release digest mismatch")
        return release

    @contextmanager
    def _append_lock(self) -> Iterator[None]:
        path = self.root / ".append.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PolicyDeniedError("ledger lock is not a regular file")
            if metadata.st_mode & 0o022:
                raise PolicyDeniedError("ledger lock must not be group/world writable")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _load_events(self) -> list[dict[str, Any]]:
        entries = sorted(self.events_path.iterdir(), key=lambda path: path.name)
        events: list[dict[str, Any]] = []
        previous: str | None = None
        identities: set[str] = set()
        for expected_sequence, path in enumerate(entries, start=1):
            if path.is_symlink() or not path.is_file():
                raise PolicyDeniedError(
                    "ledger events directory contains an unsafe entry"
                )
            match = _EVENT_FILE.fullmatch(path.name)
            if match is None or int(match.group("sequence")) != expected_sequence:
                raise PolicyDeniedError(
                    "ledger event sequence is incomplete or malformed"
                )
            value = _read_json(
                path.resolve(), field=f"ledger_event[{expected_sequence}]"
            )
            if set(value) != _EVENT_FIELDS:
                raise PolicyDeniedError("ledger event fields are not canonical")
            if value["schema_version"] != EVENT_SCHEMA_VERSION:
                raise PolicyDeniedError("ledger event schema version mismatch")
            if value["sequence"] != expected_sequence:
                raise PolicyDeniedError("ledger event sequence mismatch")
            event_id = require_uuid(value["event_id"], "event_id")
            if event_id != match.group("event") or event_id in identities:
                raise PolicyDeniedError("ledger event identity mismatch or replay")
            identities.add(event_id)
            if value["event_type"] not in {"EXECUTION", "VERIFICATION", "ACCEPTANCE"}:
                raise PolicyDeniedError("unknown ledger event type")
            if value["gap_id"] not in GATE_IDS:
                raise PolicyDeniedError("unknown ledger gate")
            if value["release_digest"] != self.release.release_digest:
                raise PolicyDeniedError("ledger event is bound to another release")
            if value["previous_event_digest"] != previous:
                raise PolicyDeniedError("ledger event hash chain is broken")
            _time(value["recorded_at"], "recorded_at")
            if value["certified"] is not False:
                raise PolicyDeniedError(
                    "ledger event contains an unauthorized certification"
                )
            payload = _json_object(value["payload"], "payload")
            if value["payload_digest"] != digest(payload):
                raise PolicyDeniedError("ledger event payload digest mismatch")
            unsigned = dict(value)
            event_digest = unsigned.pop("event_digest")
            if event_digest != digest(unsigned):
                raise PolicyDeniedError("ledger event digest mismatch")
            previous = event_digest
            events.append(value)
        self._validate_transitions(events)
        return events

    def _validate_transitions(self, events: Sequence[Mapping[str, Any]]) -> None:
        states: dict[str, str] = {
            gate: ExternalEvidenceState.NOT_RUN.value for gate in GATE_IDS
        }
        executions: dict[str, GateExecution] = {}
        verifier_domains: dict[str, str] = {}
        verifier_ids: dict[str, str] = {}
        gate_heads: dict[str, str] = {}
        for event in events:
            gap_id = str(event["gap_id"])
            event_type = event["event_type"]
            payload = _json_object(event["payload"], "payload")
            current = states[gap_id]
            if event_type == "EXECUTION":
                execution = GateExecution.from_dict(payload)
                if (
                    execution.gap_id != gap_id
                    or execution.release_digest != self.release.release_digest
                ):
                    raise PolicyDeniedError(
                        "execution event scope does not match its envelope"
                    )
                if current not in {
                    ExternalEvidenceState.NOT_RUN.value,
                    ExternalEvidenceState.FAILED.value,
                    ExternalEvidenceState.UNKNOWN.value,
                }:
                    raise PolicyDeniedError(
                        "a completed gate cannot be silently re-executed"
                    )
                states[gap_id] = execution.status
                executions[gap_id] = execution
                verifier_domains.pop(gap_id, None)
                verifier_ids.pop(gap_id, None)
                gate_heads[gap_id] = str(event["event_digest"])
                continue
            current_execution = executions.get(gap_id)
            if current_execution is None:
                raise PolicyDeniedError("verification or acceptance precedes execution")
            if event_type == "VERIFICATION":
                if current != ExternalEvidenceState.EXECUTED.value:
                    raise PolicyDeniedError(
                        "verification does not follow a successful execution"
                    )
                self._validate_verification_payload(payload, current_execution)
                states[gap_id] = payload["resulting_status"]
                verifier_domains[gap_id] = payload["receipt"]["verifier_trust_domain"]
                verifier_ids[gap_id] = payload["receipt"]["verifier_id"]
                gate_heads[gap_id] = str(event["event_digest"])
                continue
            if current != ExternalEvidenceState.INDEPENDENTLY_VERIFIED.value:
                raise PolicyDeniedError(
                    "acceptance does not follow independent verification"
                )
            self._validate_acceptance_payload(
                payload,
                current_execution,
                verifier_domains.get(gap_id),
                verifier_ids.get(gap_id),
                gate_heads[gap_id],
            )
            states[gap_id] = payload["resulting_status"]
            gate_heads[gap_id] = str(event["event_digest"])

    def _validate_verification_payload(
        self, payload: Mapping[str, Any], execution: GateExecution
    ) -> SignedVerification:
        _exact_fields(
            payload,
            {"receipt", "verification", "execution_digest", "resulting_status"},
            "verification_event_payload",
        )
        receipt = signed_verification_from_dict(
            _json_object(payload["receipt"], "receipt")
        )
        if payload["execution_digest"] != execution.result_digest:
            raise PolicyDeniedError("verification event execution digest mismatch")
        expected_status = {
            "VERIFIED": ExternalEvidenceState.INDEPENDENTLY_VERIFIED.value,
            "REJECTED": ExternalEvidenceState.FAILED.value,
            "INCONCLUSIVE": ExternalEvidenceState.UNKNOWN.value,
        }[receipt.verdict]
        if payload["resulting_status"] != expected_status:
            raise PolicyDeniedError("verification event result is inconsistent")
        verification = _json_object(payload["verification"], "verification")
        if (
            verification.get("receipt_id") != receipt.receipt_id
            or verification.get("independent") is not True
        ):
            raise PolicyDeniedError(
                "verification event lacks a valid verification decision"
            )
        self._assert_execution_statement(receipt.statement, execution)
        return receipt

    def _validate_acceptance_payload(
        self,
        payload: Mapping[str, Any],
        execution: GateExecution,
        verifier_domain: str | None,
        verifier_id: str | None,
        verified_event_digest: str,
    ) -> SignedVerification:
        _exact_fields(
            payload,
            {"receipt", "verification", "accepted_subject_digest", "resulting_status"},
            "acceptance_event_payload",
        )
        receipt = signed_verification_from_dict(
            _json_object(payload["receipt"], "receipt")
        )
        if payload["accepted_subject_digest"] != verified_event_digest:
            raise PolicyDeniedError(
                "acceptance does not bind the preceding verified event"
            )
        if receipt.statement.scope != f"external_gate_acceptance:{execution.gap_id}":
            raise PolicyDeniedError("acceptance receipt scope mismatch")
        if receipt.statement.subject_digest != verified_event_digest:
            raise PolicyDeniedError("acceptance receipt subject digest mismatch")
        if tuple(receipt.statement.raw_evidence_digests) != (verified_event_digest,):
            raise PolicyDeniedError(
                "acceptance receipt does not bind the verified evidence chain"
            )
        if receipt.statement.environment_digest != execution.environment_digest:
            raise PolicyDeniedError("acceptance receipt environment mismatch")
        if (
            verifier_domain is None
            or receipt.statement.producer_trust_domain != verifier_domain
        ):
            raise PolicyDeniedError(
                "acceptance producer is not the independent verifier"
            )
        if verifier_id is None or receipt.statement.producer_id != verifier_id:
            raise PolicyDeniedError(
                "acceptance producer identity is not the independent verifier"
            )
        if receipt.statement.executor_id != verifier_id:
            raise PolicyDeniedError(
                "acceptance statement executor is not the independent verifier"
            )
        if receipt.statement.result != "PASS":
            raise PolicyDeniedError("only a passing verified chain may be accepted")
        if receipt.verifier_trust_domain in {
            execution.producer_trust_domain,
            verifier_domain,
        }:
            raise PolicyDeniedError("acceptance authority is not independent")
        expected_status = {
            "VERIFIED": ExternalEvidenceState.ACCEPTED.value,
            "REJECTED": ExternalEvidenceState.FAILED.value,
            "INCONCLUSIVE": ExternalEvidenceState.UNKNOWN.value,
        }[receipt.verdict]
        if payload["resulting_status"] != expected_status:
            raise PolicyDeniedError("acceptance event result is inconsistent")
        verification = _json_object(payload["verification"], "verification")
        if (
            verification.get("receipt_id") != receipt.receipt_id
            or verification.get("independent") is not True
        ):
            raise PolicyDeniedError("acceptance event lacks a valid signature decision")
        return receipt

    @staticmethod
    def _assert_execution_statement(
        statement: EvidenceStatement, execution: GateExecution
    ) -> None:
        if statement.scope != f"external_gate:{execution.gap_id}":
            raise PolicyDeniedError("verification receipt scope mismatch")
        if statement.subject_digest != execution.result_digest:
            raise PolicyDeniedError("verification receipt result digest mismatch")
        if statement.producer_id != execution.executor_id:
            raise PolicyDeniedError("verification receipt producer mismatch")
        if statement.producer_trust_domain != execution.producer_trust_domain:
            raise PolicyDeniedError(
                "verification receipt producer trust-domain mismatch"
            )
        if statement.environment_digest != execution.environment_digest:
            raise PolicyDeniedError("verification receipt environment mismatch")
        if tuple(statement.raw_evidence_digests) != execution.raw_evidence_digests:
            raise PolicyDeniedError("verification receipt raw evidence mismatch")
        if statement.authorization_id != execution.authorization_id:
            raise PolicyDeniedError("verification receipt authorization mismatch")
        if statement.executor_id != execution.executor_id:
            raise PolicyDeniedError("verification receipt executor mismatch")
        if (
            statement.started_at != execution.started_at
            or statement.completed_at != execution.completed_at
        ):
            raise PolicyDeniedError("verification receipt execution window mismatch")
        if statement.result != "PASS":
            raise PolicyDeniedError(
                "only a passing execution statement may be verified"
            )

    def _append_event(
        self,
        *,
        event_id: str,
        event_type: str,
        gap_id: str,
        payload: Mapping[str, Any],
        expected_head: str | None = None,
    ) -> dict[str, Any]:
        event_id = require_uuid(event_id, "event_id")
        with self._append_lock():
            events = self._load_events()
            payload_value = _json_object(payload, "payload")
            payload_digest = digest(payload_value)
            for existing in events:
                if existing["event_id"] == event_id:
                    if (
                        existing["event_type"] == event_type
                        and existing["gap_id"] == gap_id
                        and existing["payload_digest"] == payload_digest
                    ):
                        return dict(existing) | {"replayed": True}
                    raise ConflictError("event id was reused with different content")
            actual_head = events[-1]["event_digest"] if events else None
            if expected_head is not None and actual_head != expected_head:
                raise ConflictError(
                    "ledger advanced while the external receipt was verified"
                )
            sequence = len(events) + 1
            unsigned = {
                "schema_version": EVENT_SCHEMA_VERSION,
                "sequence": sequence,
                "event_id": event_id,
                "event_type": event_type,
                "gap_id": gap_id,
                "release_digest": self.release.release_digest,
                "previous_event_digest": events[-1]["event_digest"] if events else None,
                "recorded_at": utc_now(),
                "payload": payload_value,
                "payload_digest": payload_digest,
                "certified": False,
            }
            value = unsigned | {"event_digest": digest(unsigned)}
            self._validate_transitions([*events, value])
            path = self.events_path / f"{sequence:08d}-{event_id}.json"
            _write_exclusive(path, canonical_bytes(value))
            _fsync_directory(self.events_path)
            # Re-read the entire chain before returning success.
            persisted = self._load_events()[-1]
            return dict(persisted) | {"replayed": False}

    @staticmethod
    def _copy_and_hash(source: BinaryIO, destination: BinaryIO) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_EVIDENCE_BYTES:
                raise ValueError("raw evidence exceeds the 16 GiB ingestion limit")
            hasher.update(chunk)
            destination.write(chunk)
        return "sha256:" + hasher.hexdigest(), size

    def import_evidence(
        self, source: str | Path, *, expected_digest: str | None = None
    ) -> dict[str, Any]:
        path = Path(source)
        if not path.is_absolute():
            raise ValueError("raw evidence path must be absolute")
        if path.is_symlink():
            raise PolicyDeniedError("raw evidence must not be a symbolic link")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        temporary: str | None = None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PolicyDeniedError("raw evidence must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as source_handle:
                temporary_descriptor, temporary = tempfile.mkstemp(
                    prefix=".incoming-", dir=self.objects_path
                )
                os.fchmod(temporary_descriptor, 0o600)
                with os.fdopen(temporary_descriptor, "wb") as destination:
                    evidence_digest, size = self._copy_and_hash(
                        source_handle, destination
                    )
                    destination.flush()
                    os.fsync(destination.fileno())
            if expected_digest is not None and evidence_digest != _require_digest(
                expected_digest, "expected_digest"
            ):
                raise PolicyDeniedError(
                    "raw evidence content does not match the declared digest"
                )
            target = self.objects_path / evidence_digest.removeprefix("sha256:")
            try:
                os.link(temporary, target)
                replayed = False
                _fsync_directory(self.objects_path)
            except FileExistsError:
                replayed = True
                self._verify_object(evidence_digest)
            return {
                "digest": evidence_digest,
                "size": size,
                "object": str(target),
                "replayed": replayed,
            }
        finally:
            os.close(descriptor)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def _verify_object(self, expected_digest: str) -> int:
        expected_digest = _require_digest(expected_digest, "evidence_digest")
        path = self.objects_path / expected_digest.removeprefix("sha256:")
        if path.is_symlink():
            raise PolicyDeniedError("evidence object is a symbolic link")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PolicyDeniedError("evidence object is not a regular file")
            hasher = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                while chunk := handle.read(1024 * 1024):
                    hasher.update(chunk)
            actual = "sha256:" + hasher.hexdigest()
            if actual != expected_digest:
                raise PolicyDeniedError(
                    "content-addressed evidence object was tampered"
                )
            return metadata.st_size
        finally:
            os.close(descriptor)

    def _audit_object_store(self, referenced: set[str]) -> tuple[set[str], list[str]]:
        present: set[str] = set()
        for path in sorted(self.objects_path.iterdir(), key=lambda item: item.name):
            if (
                path.is_symlink()
                or not path.is_file()
                or re.fullmatch(r"[0-9a-f]{64}", path.name) is None
            ):
                raise PolicyDeniedError(
                    "evidence object store contains an unsafe or malformed entry"
                )
            _assert_restricted_mode(path, "evidence object")
            value = "sha256:" + path.name
            self._verify_object(value)
            present.add(value)
        missing = referenced - present
        if missing:
            raise PolicyDeniedError(
                f"referenced evidence objects are missing: {sorted(missing)}"
            )
        return present, sorted(present - referenced)

    def record_execution(
        self,
        execution: GateExecution,
        raw_evidence: Iterable[str | Path],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if execution.release_digest != self.release.release_digest:
            raise PolicyDeniedError(
                "execution is bound to a different release candidate"
            )
        if execution.producer_trust_domain != self.release.implementation_trust_domain:
            raise PolicyDeniedError(
                "execution producer is outside the implementation trust domain"
            )
        current_time = now or datetime.now(timezone.utc)
        if _time(execution.started_at, "started_at") < _time(
            self.release.created_at, "release.created_at"
        ):
            raise PolicyDeniedError(
                "external gate execution predates the frozen release candidate"
            )
        if _time(execution.completed_at, "completed_at") > current_time + timedelta(
            minutes=5
        ):
            raise PolicyDeniedError(
                "external gate execution completion is implausibly in the future"
            )
        evidence_paths = list(raw_evidence)
        if len(evidence_paths) != len(execution.raw_evidence_digests):
            raise PolicyDeniedError(
                "raw evidence file count does not match the execution result"
            )
        imported = [
            self.import_evidence(path, expected_digest=expected)
            for path, expected in zip(
                evidence_paths, execution.raw_evidence_digests, strict=True
            )
        ]
        observed = tuple(item["digest"] for item in imported)
        if observed != execution.raw_evidence_digests:
            raise PolicyDeniedError(
                "raw evidence order/digests do not match the signed execution result"
            )
        event = self._append_event(
            event_id=execution.result_id,
            event_type="EXECUTION",
            gap_id=execution.gap_id,
            payload=execution.to_dict(),
        )
        return {
            "status": execution.status,
            "certified": False,
            "result_digest": execution.result_digest,
            "event_digest": event["event_digest"],
            "objects": imported,
            "replayed": event["replayed"],
        }

    def verify_execution(
        self,
        receipt: SignedVerification,
        trust_store: QualificationTrustStore,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        events = self._load_events()
        for event in events:
            if event["event_id"] != receipt.receipt_id:
                continue
            if event["event_type"] != "VERIFICATION":
                raise ConflictError("receipt id collides with another ledger event")
            stored = signed_verification_from_dict(event["payload"]["receipt"])
            if canonical_bytes(receipt_document(stored)) != canonical_bytes(
                receipt_document(receipt)
            ):
                raise ConflictError("receipt id was reused with different content")
            gap_id, execution = self._execution_for_subject(
                events, receipt.statement.subject_digest
            )
            verified = trust_store.verify(
                receipt,
                expected_subject_digest=execution.result_digest,
                required_role="independent_verifier",
                now=now,
            )
            return {
                "gap_id": gap_id,
                "status": event["payload"]["resulting_status"],
                "certified": False,
                "event_digest": event["event_digest"],
                "verification": verified,
                "replayed": True,
            }
        gap_id, execution = self._execution_for_subject(
            events, receipt.statement.subject_digest
        )
        state = self._states(events)[gap_id]["status"]
        if state != ExternalEvidenceState.EXECUTED.value:
            raise ConflictError("gate is not awaiting independent verification")
        self._assert_execution_statement(receipt.statement, execution)
        verified = trust_store.verify(
            receipt,
            expected_subject_digest=execution.result_digest,
            required_role="independent_verifier",
            now=now,
        )
        resulting_status = {
            "VERIFIED": ExternalEvidenceState.INDEPENDENTLY_VERIFIED.value,
            "REJECTED": ExternalEvidenceState.FAILED.value,
            "INCONCLUSIVE": ExternalEvidenceState.UNKNOWN.value,
        }[receipt.verdict]
        expected_head = events[-1]["event_digest"] if events else None
        payload = {
            "receipt": {"schema_version": RECEIPT_SCHEMA_VERSION} | receipt.to_dict(),
            "verification": verified,
            "execution_digest": execution.result_digest,
            "resulting_status": resulting_status,
        }
        event = self._append_event(
            event_id=receipt.receipt_id,
            event_type="VERIFICATION",
            gap_id=gap_id,
            payload=payload,
            expected_head=expected_head,
        )
        return {
            "gap_id": gap_id,
            "status": resulting_status,
            "certified": False,
            "event_digest": event["event_digest"],
            "verification": verified,
            "replayed": event["replayed"],
        }

    def accept_gate(
        self,
        receipt: SignedVerification,
        trust_store: QualificationTrustStore,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        events = self._load_events()
        for event in events:
            if event["event_id"] != receipt.receipt_id:
                continue
            if event["event_type"] != "ACCEPTANCE":
                raise ConflictError("receipt id collides with another ledger event")
            stored = signed_verification_from_dict(event["payload"]["receipt"])
            if canonical_bytes(receipt_document(stored)) != canonical_bytes(
                receipt_document(receipt)
            ):
                raise ConflictError("receipt id was reused with different content")
            gap_id = str(event["gap_id"])
            required_role = {
                "P1-G07": "customer_authority",
                "P0-G08": "release_authority",
            }.get(gap_id, "acceptance_authority")
            verified = trust_store.verify(
                receipt,
                expected_subject_digest=receipt.statement.subject_digest,
                required_role=required_role,
                now=now,
            )
            return {
                "gap_id": gap_id,
                "status": event["payload"]["resulting_status"],
                "certified": False,
                "event_digest": event["event_digest"],
                "verification": verified,
                "replayed": True,
            }
        if not events:
            raise ConflictError("acceptance cannot precede execution")
        matches = [
            event
            for event in events
            if event["event_type"] == "VERIFICATION"
            and event["event_digest"] == receipt.statement.subject_digest
        ]
        if len(matches) != 1:
            raise PolicyDeniedError(
                "acceptance receipt does not identify one verified gate"
            )
        verified_event = matches[0]
        gap_id = str(verified_event["gap_id"])
        states = self._states(events)
        state = states[gap_id]
        if state["status"] != ExternalEvidenceState.INDEPENDENTLY_VERIFIED.value:
            raise ConflictError("latest gate is not awaiting acceptance")
        execution = GateExecution.from_dict(state["execution_event"]["payload"])
        verifier_domain = state["verifier_trust_domain"]
        expected_scope = f"external_gate_acceptance:{gap_id}"
        if receipt.statement.scope != expected_scope:
            raise PolicyDeniedError("acceptance receipt scope mismatch")
        if state["latest_event"]["event_digest"] != verified_event["event_digest"]:
            raise ConflictError("acceptance receipt is stale for this gate")
        if receipt.statement.subject_digest != verified_event["event_digest"]:
            raise PolicyDeniedError(
                "acceptance receipt does not bind the latest verified event"
            )
        if tuple(receipt.statement.raw_evidence_digests) != (
            verified_event["event_digest"],
        ):
            raise PolicyDeniedError("acceptance receipt raw evidence binding mismatch")
        if receipt.statement.environment_digest != execution.environment_digest:
            raise PolicyDeniedError("acceptance environment mismatch")
        if receipt.statement.producer_trust_domain != verifier_domain:
            raise PolicyDeniedError(
                "acceptance statement was not produced by the verifier"
            )
        if receipt.statement.producer_id != state["independent_verifier"]:
            raise PolicyDeniedError("acceptance producer identity is not the verifier")
        if receipt.statement.executor_id != state["independent_verifier"]:
            raise PolicyDeniedError("acceptance statement executor is not the verifier")
        if receipt.statement.result != "PASS":
            raise PolicyDeniedError("only a passing verified chain may be accepted")
        required_role = {
            "P1-G07": "customer_authority",
            "P0-G08": "release_authority",
        }.get(gap_id, "acceptance_authority")
        verified = trust_store.verify(
            receipt,
            expected_subject_digest=verified_event["event_digest"],
            required_role=required_role,
            now=now,
        )
        if receipt.verifier_trust_domain in {
            execution.producer_trust_domain,
            verifier_domain,
        }:
            raise PolicyDeniedError("acceptance authority is not independent")
        resulting_status = {
            "VERIFIED": ExternalEvidenceState.ACCEPTED.value,
            "REJECTED": ExternalEvidenceState.FAILED.value,
            "INCONCLUSIVE": ExternalEvidenceState.UNKNOWN.value,
        }[receipt.verdict]
        payload = {
            "receipt": {"schema_version": RECEIPT_SCHEMA_VERSION} | receipt.to_dict(),
            "verification": verified,
            "accepted_subject_digest": verified_event["event_digest"],
            "resulting_status": resulting_status,
        }
        event = self._append_event(
            event_id=receipt.receipt_id,
            event_type="ACCEPTANCE",
            gap_id=gap_id,
            payload=payload,
            expected_head=events[-1]["event_digest"],
        )
        return {
            "gap_id": gap_id,
            "status": resulting_status,
            "certified": False,
            "event_digest": event["event_digest"],
            "verification": verified,
            "replayed": event["replayed"],
        }

    @staticmethod
    def _execution_for_subject(
        events: Sequence[Mapping[str, Any]], subject_digest: str
    ) -> tuple[str, GateExecution]:
        matches: list[tuple[str, GateExecution]] = []
        for event in events:
            if event["event_type"] != "EXECUTION":
                continue
            execution = GateExecution.from_dict(event["payload"])
            if execution.result_digest == subject_digest:
                matches.append((execution.gap_id, execution))
        if len(matches) != 1:
            raise PolicyDeniedError("receipt subject does not identify one execution")
        return matches[0]

    def _states(self, events: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {
            gate: {
                "status": ExternalEvidenceState.NOT_RUN.value,
                "execution_event": None,
                "latest_event": None,
                "independent_verifier": None,
                "verifier_trust_domain": None,
            }
            for gate in GATE_IDS
        }
        for event in events:
            state = result[str(event["gap_id"])]
            payload = event["payload"]
            if event["event_type"] == "EXECUTION":
                state.update(
                    status=payload["status"],
                    execution_event=event,
                    latest_event=event,
                    independent_verifier=None,
                    verifier_trust_domain=None,
                )
            else:
                receipt = payload["receipt"]
                state.update(
                    status=payload["resulting_status"],
                    latest_event=event,
                )
                if event["event_type"] == "VERIFICATION":
                    state["independent_verifier"] = receipt["verifier_id"]
                    state["verifier_trust_domain"] = receipt["verifier_trust_domain"]
        return result

    def _revalidate_receipts(
        self,
        events: Sequence[Mapping[str, Any]],
        trust_store: QualificationTrustStore,
        *,
        now: datetime | None,
    ) -> list[str]:
        blockers: list[str] = []
        states = self._states(events)
        for event in events:
            if event["event_type"] == "EXECUTION":
                continue
            gap_id = str(event["gap_id"])
            receipt = signed_verification_from_dict(event["payload"]["receipt"])
            try:
                if event["event_type"] == "VERIFICATION":
                    execution = GateExecution.from_dict(
                        self._execution_for_subject(
                            events, receipt.statement.subject_digest
                        )[1].to_dict()
                    )
                    self._assert_execution_statement(receipt.statement, execution)
                    trust_store.verify(
                        receipt,
                        expected_subject_digest=execution.result_digest,
                        required_role="independent_verifier",
                        now=now,
                    )
                else:
                    required_role = {
                        "P1-G07": "customer_authority",
                        "P0-G08": "release_authority",
                    }.get(gap_id, "acceptance_authority")
                    trust_store.verify(
                        receipt,
                        expected_subject_digest=receipt.statement.subject_digest,
                        required_role=required_role,
                        now=now,
                    )
                    execution_event = states[gap_id]["execution_event"]
                    execution = GateExecution.from_dict(execution_event["payload"])
                    if receipt.verifier_trust_domain in {
                        execution.producer_trust_domain,
                        states[gap_id]["verifier_trust_domain"],
                    }:
                        raise PolicyDeniedError(
                            "acceptance authority is not independent"
                        )
            except (PolicyDeniedError, ValueError) as exc:
                blockers.append(
                    f"receipt_revalidation_failed:{event['event_id']}:{type(exc).__name__}"
                )
        return blockers

    def status(
        self,
        *,
        trust_store: QualificationTrustStore | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        events = self._load_events()
        states = self._states(events)
        object_digests: set[str] = set()
        rows: list[dict[str, Any]] = []
        for gate in GATE_IDS:
            state = states[gate]
            execution_event = state["execution_event"]
            execution = (
                GateExecution.from_dict(execution_event["payload"])
                if execution_event is not None
                else None
            )
            if execution is not None:
                for evidence_digest in execution.raw_evidence_digests:
                    self._verify_object(evidence_digest)
                    object_digests.add(evidence_digest)
            latest = state["latest_event"]
            rows.append(
                {
                    "gap_id": gate,
                    "name": GATE_NAMES[gate],
                    "external_evidence": state["status"],
                    "evidence_digest": latest["event_digest"] if latest else None,
                    "execution_digest": execution.result_digest if execution else None,
                    "target": execution.target.to_dict() if execution else None,
                    "independent_verifier": state["independent_verifier"],
                    "limitations": list(execution.limitations) if execution else [],
                }
            )
        present_objects, orphan_objects = self._audit_object_store(object_digests)
        statuses = {row["gap_id"]: row["external_evidence"] for row in rows}
        required_verified = set(GATE_IDS) - {"P1-G07", "P0-G08"}
        blockers: list[str] = []
        for gate in sorted(required_verified):
            if statuses[gate] not in {
                ExternalEvidenceState.INDEPENDENTLY_VERIFIED.value,
                ExternalEvidenceState.ACCEPTED.value,
            }:
                blockers.append(f"{gate}:{statuses[gate]}")
        for gate in ("P1-G07", "P0-G08"):
            if statuses[gate] != ExternalEvidenceState.ACCEPTED.value:
                blockers.append(f"{gate}:{statuses[gate]}")
        signed_events = [
            event for event in events if event["event_type"] != "EXECUTION"
        ]
        receipt_revalidation = "NOT_RUN"
        revalidation_blockers: list[str] = []
        if signed_events and trust_store is not None:
            revalidation_blockers = self._revalidate_receipts(
                events, trust_store, now=now
            )
            receipt_revalidation = "FAILED" if revalidation_blockers else "PASS"
        elif signed_events:
            revalidation_blockers = ["live_trust_store_revalidation_required"]
        blockers.extend(revalidation_blockers)
        if orphan_objects:
            blockers.append(f"unreferenced_evidence_objects:{len(orphan_objects)}")
        if (
            revalidation_blockers
            or orphan_objects
            or any(value in {"FAILED", "UNKNOWN"} for value in statuses.values())
        ):
            decision = "BLOCKED"
        elif blockers:
            decision = "NOT_RUN" if not events else "IN_PROGRESS"
        else:
            decision = "READY_FOR_HUMAN_DECISION"
            blockers = ["external_production_certification_authority_required"]
        return {
            "release": self.release.to_dict(),
            "release_digest": self.release.release_digest,
            "ledger_head_digest": events[-1]["event_digest"] if events else None,
            "event_count": len(events),
            "object_count": len(present_objects),
            "orphan_object_count": len(orphan_objects),
            "receipt_revalidation": receipt_revalidation,
            "external_evidence": "NOT_RUN" if not events else decision,
            "qualification_decision": decision,
            "certification": "NOT_CERTIFIED",
            "certified": False,
            "blockers": blockers,
            "gaps": rows,
            "limitations": [
                "ledger integrity is application-enforced; production retention requires independently administered immutable storage",
                "READY_FOR_HUMAN_DECISION is not certification or deployment authorization",
            ],
        }

    def archive(
        self,
        backend: Any,
        *,
        authorization_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Archive one immutable ledger snapshot to an external WORM backend.

        The returned receipt is engineering/external-operation evidence only.
        It does not advance any gate and cannot certify the release.
        """

        authorization_id = require_nonempty(authorization_id, "authorization_id", 512)
        actor_id = require_nonempty(actor_id, "actor_id", 512)
        with self._append_lock():
            events = self._load_events()
            referenced: set[str] = set()
            for event in events:
                if event["event_type"] == "EXECUTION":
                    execution = GateExecution.from_dict(event["payload"])
                    referenced.update(execution.raw_evidence_digests)
            for evidence_digest in referenced:
                self._verify_object(evidence_digest)
            release_raw = self.release_path.read_bytes()
            event_files: list[tuple[str, dict[str, Any], bytes]] = []
            for event in events:
                name = f"{event['sequence']:08d}-{event['event_id']}.json"
                raw = (self.events_path / name).read_bytes()
                if raw != canonical_bytes(event):
                    raise PolicyDeniedError(
                        "ledger event changed while preparing its archive"
                    )
                event_files.append((name, event, raw))
            snapshot_head = events[-1]["event_digest"] if events else None

        base = self.release.release_digest.removeprefix("sha256:")
        archived: list[dict[str, Any]] = []
        release_receipt = backend.put_bytes(
            f"{base}/release/release.json",
            release_raw,
            digest_bytes(release_raw),
            authorization_id=authorization_id,
            actor_id=actor_id,
        )
        archived.append(
            {
                "kind": "release",
                "content_digest": digest_bytes(release_raw),
                "archive_receipt_digest": release_receipt["archive_receipt_digest"],
                "archive": release_receipt["archive"],
            }
        )
        for name, event, raw in event_files:
            content_digest = digest_bytes(raw)
            receipt = backend.put_bytes(
                f"{base}/events/{name}",
                raw,
                content_digest,
                authorization_id=authorization_id,
                actor_id=actor_id,
            )
            archived.append(
                {
                    "kind": "event",
                    "event_digest": event["event_digest"],
                    "content_digest": content_digest,
                    "archive_receipt_digest": receipt["archive_receipt_digest"],
                    "archive": receipt["archive"],
                }
            )
        for evidence_digest in sorted(referenced):
            path = self.objects_path / evidence_digest.removeprefix("sha256:")
            receipt = backend.put_file(
                f"{base}/objects/sha256/{path.name}",
                path,
                evidence_digest,
                authorization_id=authorization_id,
                actor_id=actor_id,
            )
            archived.append(
                {
                    "kind": "raw_evidence",
                    "content_digest": evidence_digest,
                    "archive_receipt_digest": receipt["archive_receipt_digest"],
                    "archive": receipt["archive"],
                }
            )
        manifest = {
            "schema_version": "elmos.pi-harness.immutable-ledger-archive/v1",
            "release_digest": self.release.release_digest,
            "ledger_head_digest": snapshot_head,
            "event_count": len(events),
            "raw_object_count": len(referenced),
            "authorization_id": authorization_id,
            "actor_id": actor_id,
            "archived_at": utc_now(),
            "records": archived,
            "certification": "NOT_CERTIFIED",
            "certified": False,
        }
        manifest_raw = canonical_bytes(manifest)
        manifest_digest = digest_bytes(manifest_raw)
        manifest_receipt = backend.put_bytes(
            f"{base}/manifests/{manifest_digest.removeprefix('sha256:')}.json",
            manifest_raw,
            manifest_digest,
            authorization_id=authorization_id,
            actor_id=actor_id,
        )
        return {
            "status": "ARCHIVED",
            "release_digest": self.release.release_digest,
            "ledger_head_digest": snapshot_head,
            "archive_manifest_digest": manifest_digest,
            "archive_manifest_receipt": manifest_receipt,
            "record_count": len(archived),
            "certification": "NOT_CERTIFIED",
            "certified": False,
        }


def receipt_document(receipt: SignedVerification) -> dict[str, Any]:
    """Return the canonical JSON document shape accepted by the operator CLI."""

    return {"schema_version": RECEIPT_SCHEMA_VERSION} | receipt.to_dict()
