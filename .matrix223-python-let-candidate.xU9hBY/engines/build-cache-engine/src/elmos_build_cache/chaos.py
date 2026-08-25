"""Deterministic fault injection and production certification.

Chaos here is not random. Every injector names an exact **kill point** and
records the seed, so a failure found once becomes a permanent regression test
that reproduces byte for byte.

The kill points are the boundaries where a naive implementation loses data:
before and after reservation, temp creation, write, fsync, seal, CAS put,
metadata commit, checkpoint attach, remote publish, and the final tree switch.

Certification compares clean, cached, resumed, remote and failure-injected
output-tree digests, proves at-most-once side effects, and binds a signed
certificate to exact artifacts, scope, expiry and revocation hooks.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import random
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, digest_of
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .db.store import new_id
from .enums import ValidationLevel
from .errors import (
    CertificateInvalid,
    ConflictError,
    ContractViolation,
    ElmosCacheError,
    QuotaExceeded,
    StaleLease,
)
from .manifests import EvidenceBundle
from .security import Provenance, ProvenanceSigner, SignedProvenance, require_asymmetric

SCHEMA_VERSION = "1.0.0"


class KillPoint(str, Enum):
    BEFORE_RESERVATION = "BEFORE_RESERVATION"
    AFTER_RESERVATION = "AFTER_RESERVATION"
    AFTER_TEMP_CREATE = "AFTER_TEMP_CREATE"
    DURING_WRITE = "DURING_WRITE"
    AFTER_WRITE_BEFORE_FSYNC = "AFTER_WRITE_BEFORE_FSYNC"
    AFTER_FSYNC_BEFORE_RENAME = "AFTER_FSYNC_BEFORE_RENAME"
    AFTER_RENAME_BEFORE_METADATA = "AFTER_RENAME_BEFORE_METADATA"
    AFTER_SEAL = "AFTER_SEAL"
    BEFORE_CAS_PUT = "BEFORE_CAS_PUT"
    AFTER_CAS_PUT = "AFTER_CAS_PUT"
    AFTER_METADATA_COMMIT = "AFTER_METADATA_COMMIT"
    BEFORE_CHECKPOINT_ATTACH = "BEFORE_CHECKPOINT_ATTACH"
    AFTER_CHECKPOINT_ATTACH = "AFTER_CHECKPOINT_ATTACH"
    BEFORE_REMOTE_PUBLISH = "BEFORE_REMOTE_PUBLISH"
    AFTER_REMOTE_PUBLISH = "AFTER_REMOTE_PUBLISH"
    BEFORE_TREE_SWITCH = "BEFORE_TREE_SWITCH"
    AFTER_TREE_SWITCH = "AFTER_TREE_SWITCH"


ALL_KILL_POINTS: tuple[KillPoint, ...] = tuple(KillPoint)


class KillMode(str, Enum):
    """How a fault manifests.

    ``RAISE`` is the cheap in-process simulation: useful for exercising error
    paths, but it still unwinds the stack and runs ``finally`` blocks, so it
    cannot prove that durability survives a process that gets no epilogue.
    ``SIGKILL`` sends the real signal.
    """

    RAISE = "RAISE"
    SIGKILL = "SIGKILL"


class FaultKind(str, Enum):
    PROCESS_KILL = "PROCESS_KILL"
    HOST_REBOOT = "HOST_REBOOT"
    DISK_FULL = "DISK_FULL"
    INODE_EXHAUSTION = "INODE_EXHAUSTION"
    FSYNC_FAILURE = "FSYNC_FAILURE"
    PARTIAL_WRITE = "PARTIAL_WRITE"
    PERMISSION_LOSS = "PERMISSION_LOSS"
    NETWORK_PARTITION = "NETWORK_PARTITION"
    DUPLICATE_DELIVERY = "DUPLICATE_DELIVERY"
    STALE_LEASE = "STALE_LEASE"
    CLOCK_SKEW = "CLOCK_SKEW"
    CORRUPT_OBJECT = "CORRUPT_OBJECT"
    REMOTE_INCONSISTENCY = "REMOTE_INCONSISTENCY"


ALL_FAULT_KINDS: tuple[FaultKind, ...] = tuple(FaultKind)


class InjectedFault(ElmosCacheError):
    """Raised by the injector. Distinguishable from a genuine defect."""

    code = "INJECTED_FAULT"


@dataclass(frozen=True)
class FaultSpec:
    kill_point: KillPoint
    kind: FaultKind
    seed: int = 0
    repeat: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "kill_point": self.kill_point.value,
            "kind": self.kind.value,
            "seed": self.seed,
            "repeat": self.repeat,
        }


@dataclass
class FaultInjector:
    """Deterministic: same seed and spec produce the same failure sequence."""

    specs: tuple[FaultSpec, ...] = ()
    seed: int = 20260819
    fired: list[dict[str, Any]] = field(default_factory=list)
    #: ``RAISE`` for in-process simulation, ``SIGKILL`` for a real process kill.
    mode: KillMode = KillMode.RAISE
    #: Where a ``SIGKILL``-mode injector records what it fired, since the
    #: process will not survive to report it.
    marker_path: str | None = None
    _remaining: dict[KillPoint, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._remaining = {spec.kill_point: spec.repeat for spec in self.specs}
        self._random = random.Random(self.seed)

    def armed_at(self, point: KillPoint) -> FaultSpec | None:
        for spec in self.specs:
            if spec.kill_point is point and self._remaining.get(point, 0) > 0:
                return spec
        return None

    def maybe_fail(self, point: KillPoint, **context: Any) -> None:
        """Call at every kill point. A no-op unless a fault is armed there.

        In :attr:`KillMode.SIGKILL` mode this does not raise: it sends the
        process an uncatchable ``SIGKILL``, so no ``finally``, no ``atexit``
        handler and no buffered write ever completes. That is the only way to
        prove the durability ordering rather than the exception handling.
        """
        spec = self.armed_at(point)
        if spec is None:
            return
        self._remaining[point] -= 1
        record = {
            "kill_point": point.value,
            "kind": spec.kind.value,
            "seed": spec.seed or self.seed,
            "mode": self.mode.value,
            "context": {key: str(value)[:80] for key, value in sorted(context.items())},
        }
        self.fired.append(record)
        if self.mode is KillMode.SIGKILL:
            self._record_kill(record)
            os.kill(os.getpid(), signal.SIGKILL)
            raise InjectedFault("SIGKILL did not take effect")  # pragma: no cover
        raise self._error(spec, point)

    def _record_kill(self, record: dict[str, Any]) -> None:
        """Persist the kill marker *before* dying; the process gets no epilogue."""
        if self.marker_path is None:
            return
        marker = Path(self.marker_path)
        marker.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(handle, canonical_json_bytes(record) + b"\n")
            os.fsync(handle)
        finally:
            os.close(handle)

    @staticmethod
    def _error(spec: FaultSpec, point: KillPoint) -> ElmosCacheError:
        if spec.kind is FaultKind.DISK_FULL:
            return QuotaExceeded("injected: no space left on device", kill_point=point.value)
        if spec.kind is FaultKind.INODE_EXHAUSTION:
            return QuotaExceeded("injected: inode exhaustion", kill_point=point.value)
        if spec.kind is FaultKind.STALE_LEASE:
            return StaleLease("injected: lease epoch advanced", kill_point=point.value)
        if spec.kind is FaultKind.CORRUPT_OBJECT:
            return ConflictError("injected: object corruption", kill_point=point.value)
        return InjectedFault(f"injected {spec.kind.value}", kill_point=point.value)

    def report(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "specs": [spec.to_dict() for spec in self.specs],
            "fired": self.fired,
            "reproduce": {"seed": self.seed, "specs": [spec.to_dict() for spec in self.specs]},
        }


def kill_point_matrix(
    kinds: Sequence[FaultKind] = ALL_FAULT_KINDS, points: Sequence[KillPoint] = ALL_KILL_POINTS
) -> list[FaultSpec]:
    """Full cross product; the chaos suite iterates this."""
    return [
        FaultSpec(kill_point=point, kind=kind, seed=index)
        for index, (point, kind) in enumerate(
            (point, kind) for point in points for kind in kinds
        )
    ]


# --------------------------------------------------------------------------
# real process kills
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ProcessKillResult:
    """Outcome of a scenario that ran in its own operating-system process."""

    returncode: int
    stdout: str
    stderr: str
    fired: dict[str, Any] | None = None

    @property
    def killed_by_signal(self) -> int | None:
        return -self.returncode if self.returncode < 0 else None

    @property
    def sigkilled(self) -> bool:
        return self.killed_by_signal == int(signal.SIGKILL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "killed_by_signal": self.killed_by_signal,
            "sigkilled": self.sigkilled,
            "fired": self.fired,
            "stderr_tail": self.stderr[-400:],
        }


def run_until_kill(
    source: str,
    workdir: Path,
    marker: Path | None = None,
    timeout: float = 120.0,
    env: Mapping[str, str] | None = None,
    python: str | None = None,
) -> ProcessKillResult:
    """Run ``source`` in a fresh interpreter and report how it died.

    The scenario must arrange its own kill (``FaultInjector`` in
    :attr:`KillMode.SIGKILL` mode does exactly that). Running it out of process
    is what makes the test honest: the parent inspects only what actually
    reached the filesystem, exactly as a restarted worker would.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / f"scenario-{os.urandom(4).hex()}.py"
    script.write_text(source, encoding="utf-8")

    environment = dict(os.environ)
    environment.update(env or {})
    completed = subprocess.run(  # noqa: S603 - the source is built by the caller
        [python or sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workdir),
        env=environment,
        check=False,
    )
    fired: dict[str, Any] | None = None
    if marker is not None and Path(marker).is_file():
        import json

        fired = json.loads(Path(marker).read_text(encoding="utf-8"))
    return ProcessKillResult(completed.returncode, completed.stdout, completed.stderr, fired)


# --------------------------------------------------------------------------
# real filesystem exhaustion
# --------------------------------------------------------------------------
class ExhaustionUnavailable(RuntimeError):
    """Raised when the platform cannot provide a real bounded filesystem."""


@contextmanager
def bounded_filesystem(
    mount_point: Path, size_bytes: int = 1 << 20, inodes: int = 64
) -> Iterator[Path]:
    """Mount a real tmpfs so ``ENOSPC`` and ``EDQUOT`` are genuine.

    Simulating a full disk by raising an exception tests the handler, not the
    filesystem: it cannot show what a short ``write`` or a failed ``rename``
    leaves behind. Callers should skip -- never silently degrade -- when this
    raises :class:`ExhaustionUnavailable`.
    """
    target = Path(mount_point)
    target.mkdir(parents=True, exist_ok=True)
    libc_name = ctypes.util.find_library("c")
    if libc_name is None or os.geteuid() != 0:  # pragma: no cover - platform dependent
        raise ExhaustionUnavailable("mounting a tmpfs requires libc and root")
    libc = ctypes.CDLL(libc_name, use_errno=True)
    options = f"size={size_bytes},nr_inodes={inodes}".encode()
    if libc.mount(b"tmpfs", str(target).encode(), b"tmpfs", 0, options) != 0:
        raise ExhaustionUnavailable(
            f"mount(2) failed: {os.strerror(ctypes.get_errno())}"
        )
    try:
        yield target
    finally:
        libc.umount(str(target).encode())


def fill_filesystem(root: Path, chunk: int = 64 * 1024) -> int:
    """Consume free space until the next write fails. Returns bytes written."""
    ballast = Path(root) / ".elmos-ballast"
    written = 0
    try:
        with ballast.open("wb") as handle:
            while True:
                handle.write(b"\0" * chunk)
                handle.flush()
                os.fsync(handle.fileno())
                written += chunk
    except OSError as exc:
        if exc.errno not in (errno.ENOSPC, errno.EDQUOT, errno.EFBIG):
            raise
    return written


def exhaust_inodes(root: Path, limit: int = 1000) -> int:
    """Create empty files until the filesystem runs out of inodes."""
    created = 0
    for index in range(limit):
        try:
            (Path(root) / f".inode-{index}").touch()
        except OSError as exc:
            if exc.errno not in (errno.ENOSPC, errno.EDQUOT, errno.EMFILE):
                raise
            break
        created += 1
    return created


def release_ballast(root: Path) -> None:
    """Free the space taken by :func:`fill_filesystem` so recovery can run."""
    ballast = Path(root) / ".elmos-ballast"
    ballast.unlink(missing_ok=True)


def temporary_mount_point(prefix: str = "elmos-bounded-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


# --------------------------------------------------------------------------
# invariant checks after a fault
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class InvariantReport:
    name: str
    held: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"invariant": self.name, "held": self.held, "detail": self.detail}


def check_no_partial_publication(publisher: Any) -> InvariantReport:
    """Either the previous complete tree or the new one; never a mixture."""
    current = publisher.current_tree_digest()
    if current is None:
        return InvariantReport("no-partial-publication", True, "nothing published")
    directory = publisher.publish_root / current.split(":", 1)[1]
    if not directory.is_dir():
        return InvariantReport("no-partial-publication", False, "pointer targets a missing tree")
    manifest_path = directory / ".elmos-tree-manifest.json"
    if not manifest_path.is_file():
        return InvariantReport("no-partial-publication", False, "published tree has no manifest")
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [
        entry["logical_path"]
        for entry in manifest["entries"]
        if not (directory / entry["logical_path"]).is_file()
    ]
    return InvariantReport(
        "no-partial-publication",
        not missing,
        f"{len(missing)} declared files are absent" if missing else "complete tree",
    )


def check_recovery_converges(
    recover: Callable[[], Mapping[str, Any]], max_rounds: int = 5
) -> InvariantReport:
    """Recovery must reach a fixed point in bounded rounds, or fail explicitly."""
    previous: str | None = None
    for round_index in range(max_rounds):
        summary = recover()
        fingerprint = digest_of({k: sorted(v) if isinstance(v, list) else v for k, v in summary.items()})
        if fingerprint == previous:
            return InvariantReport("recovery-converges", True, f"fixed point after {round_index} rounds")
        previous = fingerprint
    return InvariantReport("recovery-converges", False, f"no fixed point within {max_rounds} rounds")


def check_at_most_once_side_effects(store: MetadataStore, run_id: str) -> InvariantReport:
    receipts = store.list_side_effects(run_id)
    keys = [receipt["idempotency_key"] for receipt in receipts]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    uncompensated = [
        receipt["idempotency_key"] for receipt in receipts if receipt["status"] == "PENDING"
    ]
    return InvariantReport(
        "at-most-once-side-effects",
        not duplicates,
        f"duplicates={duplicates} pending={uncompensated}" if (duplicates or uncompensated) else "clean",
    )


def check_no_orphan_metadata(store: MetadataStore, cas: Any, tenant_id: str) -> InvariantReport:
    known = {artifact.digest for artifact in store.list_artifacts(tenant_id)}
    present = set(cas.iter_digests())
    orphans = sorted(known - present)
    return InvariantReport(
        "no-orphan-metadata",
        not orphans,
        f"{len(orphans)} metadata rows without bytes" if orphans else "consistent",
    )


# --------------------------------------------------------------------------
# certification
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DigestComparison:
    """Clean vs cached vs resumed vs remote vs fault-injected tree digests."""

    clean: str
    cached: str | None = None
    resumed: str | None = None
    remote: str | None = None
    fault_injected: str | None = None

    def divergences(self) -> list[str]:
        rows: list[str] = []
        for name in ("cached", "resumed", "remote", "fault_injected"):
            value = getattr(self, name)
            if value is not None and value != self.clean:
                rows.append(f"{name}={value} differs from clean={self.clean}")
        return rows

    @property
    def all_match(self) -> bool:
        return not self.divergences()

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean": self.clean,
            "cached": self.cached,
            "resumed": self.resumed,
            "remote": self.remote,
            "fault_injected": self.fault_injected,
            "all_match": self.all_match,
            "divergences": self.divergences(),
        }


@dataclass(frozen=True)
class CertificationScope:
    stage_ids: tuple[str, ...]
    schema_version: str
    toolchain_digest: str
    rule_pack_digest: str
    storage_profile: str
    platform: str
    trust_namespace: str

    def digest(self) -> str:
        return digest_of(
            {
                "stage_ids": sorted(self.stage_ids),
                "schema_version": self.schema_version,
                "toolchain_digest": self.toolchain_digest,
                "rule_pack_digest": self.rule_pack_digest,
                "storage_profile": self.storage_profile,
                "platform": self.platform,
                "trust_namespace": self.trust_namespace,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_ids": sorted(self.stage_ids),
            "schema_version": self.schema_version,
            "toolchain_digest": self.toolchain_digest,
            "rule_pack_digest": self.rule_pack_digest,
            "storage_profile": self.storage_profile,
            "platform": self.platform,
            "trust_namespace": self.trust_namespace,
            "scope_digest": self.digest(),
        }


@dataclass(frozen=True)
class Certificate:
    certificate_id: str
    scope: CertificationScope
    tree_digest: str
    evidence_digest: str
    validation_level: ValidationLevel
    issued_at: float
    expires_at: float
    signed_provenance: SignedProvenance
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "certificate_id": self.certificate_id,
            "scope": self.scope.to_dict(),
            "tree_digest": self.tree_digest,
            "evidence_digest": self.evidence_digest,
            "validation_level": str(self.validation_level),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "limitations": list(self.limitations),
            "provenance": self.signed_provenance.to_dict(),
        }


REQUIRED_EVIDENCE_KINDS: tuple[str, ...] = (
    "determinism",
    "recovery",
    "security",
    "behavior",
    "performance",
)


class CertificationService:
    def __init__(
        self,
        store: MetadataStore,
        signer: ProvenanceSigner,
        clock: Clock = SYSTEM_CLOCK,
        validity_seconds: float = 30 * 86400.0,
        security: Any | None = None,
    ) -> None:
        self.store = store
        # A production certificate signed with a shared secret is worthless:
        # every verifier could have minted it. Enforce the policy here, at
        # wiring time, rather than at issue time.
        self.signer = require_asymmetric(signer, security)
        self.clock = clock
        self.validity_seconds = validity_seconds

    def issue(
        self,
        tenant_id: str,
        scope: CertificationScope,
        tree_digest: str,
        evidence: EvidenceBundle,
        comparison: DigestComparison,
        invariants: Sequence[InvariantReport],
        action_key: str,
        producer_identity: str,
        verifier_identities: Sequence[str],
        limitations: Sequence[str] = (),
    ) -> Certificate:
        """Issue only against fresh, complete, matching evidence."""
        if not comparison.all_match:
            raise CertificateInvalid(
                "output tree digests diverge across execution modes",
                divergences=comparison.divergences(),
            )
        failed = [report.name for report in invariants if not report.held]
        if failed:
            raise CertificateInvalid("invariants did not hold", invariants=failed)
        if evidence.tree_digest != tree_digest:
            raise CertificateInvalid(
                "evidence is bound to a different tree", evidence_tree=evidence.tree_digest
            )
        kinds = {str(record.get("kind")) for record in evidence.records}
        missing = sorted(set(REQUIRED_EVIDENCE_KINDS) - kinds)
        if missing:
            raise CertificateInvalid("evidence bundle is incomplete", missing=missing)
        if not verifier_identities or set(verifier_identities) == {producer_identity}:
            raise CertificateInvalid(
                "production certification requires an independent verifier",
                producer=producer_identity,
            )

        now = self.clock.now()
        expires = now + self.validity_seconds
        evidence_digest = evidence.digest()
        provenance = Provenance(
            subject_digest=tree_digest,
            action_key=action_key,
            producer_identity=producer_identity,
            validation_level=ValidationLevel.PRODUCTION_CERTIFIED,
            trust_namespace=_namespace(scope.trust_namespace),
            scope=scope.digest(),
            issued_at=now,
            expires_at=expires,
            verifier_identities=tuple(sorted(verifier_identities)),
            materials=(evidence_digest,),
        )
        signed = self.signer.sign(provenance)
        certificate = Certificate(
            certificate_id=new_id("cert"),
            scope=scope,
            tree_digest=tree_digest,
            evidence_digest=evidence_digest,
            validation_level=ValidationLevel.PRODUCTION_CERTIFIED,
            issued_at=now,
            expires_at=expires,
            signed_provenance=signed,
            limitations=tuple(limitations),
        )
        self.store.add_certificate(
            {
                "certificate_id": certificate.certificate_id,
                "tenant_id": tenant_id,
                "scope_digest": scope.digest(),
                "tree_digest": tree_digest,
                "evidence_digest": evidence_digest,
                "validation_level": ValidationLevel.PRODUCTION_CERTIFIED,
                "signature": signed.signature,
                "issuer": f"{self.signer.algorithm}:{self.signer.active_key_id}",
                "status": "VALID",
                "issued_at": now,
                "expires_at": expires,
                "limitations": list(limitations),
            }
        )
        return certificate

    def verify(
        self, certificate_id: str, expected_scope: CertificationScope, tree_digest: str
    ) -> dict[str, Any]:
        """Expired, revoked, forged or scope-mismatched certificates are rejected."""
        record = self.store.get_certificate(certificate_id)
        if record is None:
            raise CertificateInvalid("certificate is unknown", certificate_id=certificate_id)
        now = self.clock.now()
        if record["status"] != "VALID":
            raise CertificateInvalid("certificate is not valid", status=record["status"])
        if record["expires_at"] <= now:
            self.store.set_certificate_status(certificate_id, "EXPIRED")
            raise CertificateInvalid("certificate has expired", expires_at=record["expires_at"])
        if record["tree_digest"] != tree_digest:
            raise CertificateInvalid(
                "certificate is bound to a different output tree", bound=record["tree_digest"]
            )
        if record["scope_digest"] != expected_scope.digest():
            raise CertificateInvalid(
                "certificate scope does not match the requested scope",
                bound=record["scope_digest"],
            )
        if self.store.is_revoked(record["tenant_id"], "tree", tree_digest):
            raise CertificateInvalid("the certified tree has been revoked", tree_digest=tree_digest)
        return {"certificate_id": certificate_id, "valid": True, "expires_at": record["expires_at"]}

    def revoke(self, certificate_id: str, reason: str) -> None:
        record = self.store.get_certificate(certificate_id)
        if record is None:
            raise CertificateInvalid("certificate is unknown", certificate_id=certificate_id)
        self.store.set_certificate_status(certificate_id, "REVOKED")
        self.store.add_revocation(record["tenant_id"], "certificate", certificate_id, reason)


def _namespace(value: str) -> Any:
    from .enums import TrustNamespace

    try:
        return TrustNamespace(value)
    except ValueError:
        return TrustNamespace.EXPERIMENTAL


# --------------------------------------------------------------------------
# regression corpus
# --------------------------------------------------------------------------
@dataclass
class RegressionCorpus:
    """Every discovered failure becomes a permanent, replayable test case."""

    cases: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self, name: str, injector: FaultInjector, invariants: Sequence[InvariantReport], notes: str = ""
    ) -> dict[str, Any]:
        case = {
            "name": name,
            "reproduce": injector.report()["reproduce"],
            "invariants": [report.to_dict() for report in invariants],
            "notes": notes,
        }
        self.cases.append(case)
        return case

    def replay_specs(self) -> list[tuple[str, FaultInjector]]:
        replays: list[tuple[str, FaultInjector]] = []
        for case in self.cases:
            specs = tuple(
                FaultSpec(
                    kill_point=KillPoint(item["kill_point"]),
                    kind=FaultKind(item["kind"]),
                    seed=int(item["seed"]),
                    repeat=int(item["repeat"]),
                )
                for item in case["reproduce"]["specs"]
            )
            replays.append((case["name"], FaultInjector(specs, seed=int(case["reproduce"]["seed"]))))
        return replays

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "cases": self.cases}


def run_fault_campaign(
    scenario: Callable[[FaultInjector], Mapping[str, Any]],
    specs: Iterable[FaultSpec],
    seed: int = 20260819,
) -> list[dict[str, Any]]:
    """Run one scenario per kill point, recording what each fault produced."""
    results: list[dict[str, Any]] = []
    for spec in specs:
        injector = FaultInjector((spec,), seed=seed)
        try:
            outcome = dict(scenario(injector))
            status = "SURVIVED"
            error = None
        except ElmosCacheError as exc:
            outcome = {}
            status = "RAISED"
            error = exc.code
        except Exception as exc:  # noqa: BLE001 - unexpected failures are the finding
            outcome = {}
            status = "UNEXPECTED"
            error = type(exc).__name__
        results.append(
            {
                "kill_point": spec.kill_point.value,
                "kind": spec.kind.value,
                "status": status,
                "error": error,
                "fired": injector.fired,
                "outcome": outcome,
            }
        )
    return results


def require_all_invariants(reports: Sequence[InvariantReport]) -> None:
    failed = [report for report in reports if not report.held]
    if failed:
        raise ContractViolation(
            "invariants violated after fault injection",
            invariants=[report.to_dict() for report in failed],
        )
