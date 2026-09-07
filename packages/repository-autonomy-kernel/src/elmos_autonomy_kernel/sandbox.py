"""Two-phase secretless sandbox: the value never exists on this side of the wall.

The model here is that a credential is not data the kernel handles carefully —
it is data the kernel never handles at all.  Phase one (ANALYZE) resolves a
profile and a plan with no secrets in scope whatsoever; asking for a secret in
that phase is a phase violation, not a warning.  Phase two (EXECUTE) resolves
each binding into a short-lived *handle*, and what crosses into the process
runner is the handle's reference string, never the credential.  ``scrub`` exists
for the one place a value can still leak — text produced by the child process —
and it over-redacts on purpose: shredding an innocent substring is cheap, and
printing a live token is not.

Two further choices are deliberate.  Network is denied by default and an
``allow-all`` profile needs both an explicit profile flag *and* a policy
obligation, because either one alone is a single point of failure.  And a
timeout maps to ``INTERRUPTED``, never ``FAILED``: a killed process may well
have applied half its effect, and calling that a clean failure is how a caller
justifies a blind retry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .contracts import (
    digest,
    digest_bytes,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .authority import ExecutionAuthority  # noqa: F401

register_codes(
    Category.SANDBOX,
    "SANDBOX_PROVISION_FAILED",
    "SECRET_EXPOSURE",
    "NETWORK_POLICY_BYPASS",
    "CLEANUP_INCOMPLETE",
    "SANDBOX_PHASE_VIOLATION",
    "SANDBOX_PATH_DENIED",
)

__all__ = [
    "Phase",
    "NetworkMode",
    "NetworkGrant",
    "NetworkPolicy",
    "ResourceLimits",
    "SandboxProfile",
    "SecretBinding",
    "SecretHandle",
    "StaticSecretResolver",
    "Command",
    "PreparedSandbox",
    "SandboxStatus",
    "SandboxOutcome",
    "CleanupReport",
    "TwoPhaseSandbox",
    "RecordingRunner",
    "DenyAllRunner",
    "scrub",
    "REDACTION",
    "MAX_SECRET_TTL_SECONDS",
    "ALLOW_ALL_OBLIGATION",
    "handle",
]

#: A binding longer-lived than this is not "short-lived" in any useful sense.
MAX_SECRET_TTL_SECONDS = 900

#: A secret shorter than this cannot be scrubbed out of output without
#: destroying the output, so it is refused at provisioning time instead of
#: being discovered as unscrubdiscoverable during an incident.
MIN_SCRUBBABLE_SECRET = 4

#: The obligation a policy decision must carry before ``allow-all`` networking
#: is permitted.  The profile flag alone is never enough.
ALLOW_ALL_OBLIGATION = "sandbox.allow-all-network-approved"

REDACTION = "«redacted:{binding_id}»"

_MAX_ARGV = 256
_MAX_GRANTS = 64


class Phase(StrEnum):
    """Which half of the two-phase model a sandbox is provisioned for."""

    ANALYZE = "ANALYZE"
    EXECUTE = "EXECUTE"


class NetworkMode(StrEnum):
    """Network posture.  ``DENY`` is the default and the only safe default."""

    DENY = "deny"
    ALLOW_LIST = "allow-list"
    ALLOW_ALL = "allow-all"


@dataclass(frozen=True, slots=True)
class NetworkGrant:
    """One explicit destination.

    A grant is a host *and* a port.  "the host" alone would silently authorise
    every service that host happens to run, which is how an egress rule meant
    for a package registry becomes an SSH tunnel.
    """

    host: str
    port: int

    def __post_init__(self) -> None:
        require_str(self.host, "host", max_length=253)
        require_int(self.port, "port", minimum=1, maximum=65535)

    @property
    def token(self) -> str:
        return f"{self.host}:{self.port}"

    def to_payload(self) -> dict[str, Any]:
        return {"host": self.host, "port": self.port}


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """The declared network posture of a profile."""

    mode: NetworkMode = NetworkMode.DENY
    grants: tuple[NetworkGrant, ...] = ()
    allow_all_acknowledged: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, NetworkMode):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown network mode {self.mode!r}",
                recommended_action="use deny, allow-list or allow-all",
            )
        if len(self.grants) > _MAX_GRANTS:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"more than {_MAX_GRANTS} network grants",
                recommended_action="split the workload or use a proxy allow-list",
            )
        if self.mode is not NetworkMode.ALLOW_LIST and self.grants:
            raise KernelError(
                code="NETWORK_POLICY_BYPASS",
                message=f"network mode {self.mode} must not carry explicit grants",
                recommended_action="use allow-list mode to express explicit destinations",
            )
        if self.mode is NetworkMode.ALLOW_LIST and not self.grants:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="allow-list mode with no grants is a deny; declare it as deny",
                recommended_action="set mode to deny",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "mode": str(self.mode),
            "grants": [grant.to_payload() for grant in self.grants],
            "allowAllAcknowledged": self.allow_all_acknowledged,
        }

    @property
    def descriptor(self) -> str:
        """The stable string handed to the process runner."""

        if self.mode is NetworkMode.ALLOW_LIST:
            return "allow-list:" + ",".join(sorted(grant.token for grant in self.grants))
        return str(self.mode)


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Hard ceilings.  Every one is an integer; none may be absent.

    An absent limit is not "unlimited" here, it is a construction error: an
    unbounded child process is indistinguishable from a runaway one.
    """

    cpu_millicores: int
    memory_bytes: int
    wall_clock_seconds: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        require_int(self.cpu_millicores, "cpu_millicores", minimum=1)
        require_int(self.memory_bytes, "memory_bytes", minimum=1)
        require_int(self.wall_clock_seconds, "wall_clock_seconds", minimum=1)
        require_int(self.max_output_bytes, "max_output_bytes", minimum=1)

    def to_payload(self) -> dict[str, Any]:
        return {
            "cpuMillicores": self.cpu_millicores,
            "memoryBytes": self.memory_bytes,
            "wallClockSeconds": self.wall_clock_seconds,
            "maxOutputBytes": self.max_output_bytes,
        }


def _normalise_path(path: str) -> str:
    """Lexically normalise without touching the filesystem.

    Resolution is deliberately lexical: asking the filesystem would follow
    symlinks, and a symlink planted by an untrusted repository is exactly the
    escape this check exists to stop.  Any ``..`` segment is refused outright
    rather than collapsed, because a collapsed traversal still tells the caller
    their path was accepted.
    """

    text = require_str(path, "path", max_length=1024)
    if "\x00" in text:
        raise KernelError(
            code="SANDBOX_PATH_DENIED",
            message="path contains a NUL byte",
            recommended_action="supply a plain POSIX path",
        )
    if not text.startswith("/"):
        raise KernelError(
            code="SANDBOX_PATH_DENIED",
            message=f"path {text!r} is not absolute",
            recommended_action="supply an absolute path rooted in the workspace",
        )
    segments = [segment for segment in text.split("/") if segment not in ("", ".")]
    if any(segment == ".." for segment in segments):
        raise KernelError(
            code="SANDBOX_PATH_DENIED",
            message=f"path {text!r} contains a parent-directory segment",
            recommended_action="reference the target directly; traversal is never resolved",
            details={"path": text},
        )
    return "/" + "/".join(segments)


def _within(path: str, root: str) -> bool:
    if path == root:
        return True
    prefix = root if root.endswith("/") else root + "/"
    return path.startswith(prefix)


@dataclass(frozen=True, slots=True)
class SandboxProfile:
    """The complete, environment-owned description of a sandbox.

    A profile is looked up by id from a catalogue the environment supplies.  It
    is never assembled from anything the agent said, which is the mechanical
    form of "an agent cannot modify its own sandbox policy".
    """

    profile_id: str
    filesystem_allow: tuple[str, ...]
    network: NetworkPolicy
    env_allow: tuple[str, ...]
    limits: ResourceLimits

    def __post_init__(self) -> None:
        require_identifier(self.profile_id, "profile_id")
        if not self.filesystem_allow:
            raise KernelError(
                code="SANDBOX_PROVISION_FAILED",
                message=f"profile {self.profile_id!r} allows no filesystem root",
                recommended_action="declare at least the workspace root",
            )
        object.__setattr__(
            self, "filesystem_allow",
            tuple(sorted({_normalise_path(item) for item in self.filesystem_allow})),
        )
        object.__setattr__(self, "env_allow", tuple(sorted(set(self.env_allow))))
        for name in self.env_allow:
            require_str(name, "env_allow entry", max_length=128)

    def to_payload(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "filesystemAllow": list(self.filesystem_allow),
            "network": self.network.to_payload(),
            "envAllow": list(self.env_allow),
            "limits": self.limits.to_payload(),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SandboxProfile:
        payload = require_mapping(payload, "sandbox_profile")
        known = {"profileId", "filesystemAllow", "network", "envAllow", "limits"}
        reject_unknown_fields(payload, known, field_name="sandbox_profile")
        network_raw = require_mapping(payload.get("network", {}), "sandbox_profile.network")
        reject_unknown_fields(network_raw, {"mode", "grants", "allowAllAcknowledged"},
                              field_name="sandbox_profile.network")
        mode = NetworkMode(require_str(network_raw.get("mode", "deny"),
                                       "sandbox_profile.network.mode"))
        grants = tuple(
            NetworkGrant(
                host=require_str(item.get("host"), "network.grants[].host"),
                port=require_int(item.get("port"), "network.grants[].port",
                                 minimum=1, maximum=65535),
            )
            for item in network_raw.get("grants", ())
        )
        limits_raw = require_mapping(payload.get("limits", {}), "sandbox_profile.limits")
        reject_unknown_fields(
            limits_raw,
            {"cpuMillicores", "memoryBytes", "wallClockSeconds", "maxOutputBytes"},
            field_name="sandbox_profile.limits",
        )
        return cls(
            profile_id=require_identifier(payload.get("profileId"),
                                          "sandbox_profile.profileId"),
            filesystem_allow=require_str_seq(payload.get("filesystemAllow", ()),
                                             "sandbox_profile.filesystemAllow"),
            network=NetworkPolicy(
                mode=mode,
                grants=grants,
                allow_all_acknowledged=require_bool(
                    network_raw.get("allowAllAcknowledged", False),
                    "sandbox_profile.network.allowAllAcknowledged",
                ),
            ),
            env_allow=require_str_seq(payload.get("envAllow", ()),
                                      "sandbox_profile.envAllow"),
            limits=ResourceLimits(
                cpu_millicores=require_int(limits_raw.get("cpuMillicores"),
                                           "limits.cpuMillicores", minimum=1),
                memory_bytes=require_int(limits_raw.get("memoryBytes"),
                                         "limits.memoryBytes", minimum=1),
                wall_clock_seconds=require_int(limits_raw.get("wallClockSeconds"),
                                               "limits.wallClockSeconds", minimum=1),
                max_output_bytes=require_int(limits_raw.get("maxOutputBytes"),
                                             "limits.maxOutputBytes", minimum=1),
            ),
        )


@dataclass(frozen=True, slots=True)
class SecretBinding:
    """A *request* for a credential: which one, for what, for how long.

    There is no value field and there never will be one.  This object is safe to
    log, digest and persist, which is precisely why the plan is expressed in
    these terms rather than in resolved credentials.
    """

    binding_id: str
    scope: str
    ttl_seconds: int

    def __post_init__(self) -> None:
        require_identifier(self.binding_id, "binding_id")
        require_str(self.scope, "scope", max_length=256)
        require_int(self.ttl_seconds, "ttl_seconds", minimum=1)
        if self.ttl_seconds > MAX_SECRET_TTL_SECONDS:
            raise KernelError(
                code="SECRET_EXPOSURE",
                message=(
                    f"binding {self.binding_id!r} requests {self.ttl_seconds}s, above the "
                    f"{MAX_SECRET_TTL_SECONDS}s ceiling for a short-lived credential"
                ),
                recommended_action="shorten the TTL or use a durable credential deliberately",
                details={"bindingId": self.binding_id},
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "bindingId": self.binding_id,
            "scope": self.scope,
            "ttlSeconds": self.ttl_seconds,
        }

    @property
    def reference(self) -> str:
        """The opaque string the runner exchanges for a value at the real boundary."""

        return "secret-ref:" + digest(self.to_payload()).split(":", 1)[1][:24]


class SecretHandle:
    """A resolved binding.

    This is intentionally *not* a dataclass: a dataclass would give it a
    generated ``__repr__`` that prints every field, and one such repr in a log
    line is a credential disclosure.  The value is reachable only through
    :meth:`reveal`, which the process-runner boundary and :func:`scrub` call and
    nothing else does.  ``to_payload`` is value-free by construction.
    """

    __slots__ = ("binding_id", "scope", "ttl_seconds", "reference", "_value", "_revoked")

    def __init__(self, binding: SecretBinding, value: str) -> None:
        if not isinstance(value, str) or len(value) < MIN_SCRUBBABLE_SECRET:
            raise KernelError(
                code="SECRET_EXPOSURE",
                message=(
                    f"binding {binding.binding_id!r} resolved to a value shorter than "
                    f"{MIN_SCRUBBABLE_SECRET} characters, which cannot be scrubbed out of "
                    "output without destroying it"
                ),
                recommended_action="rotate the credential to a scrubbable length",
                details={"bindingId": binding.binding_id},
            )
        self.binding_id = binding.binding_id
        self.scope = binding.scope
        self.ttl_seconds = binding.ttl_seconds
        self.reference = binding.reference
        self._value = value
        self._revoked = False

    @property
    def revoked(self) -> bool:
        return self._revoked

    @property
    def redaction(self) -> str:
        return REDACTION.format(binding_id=self.binding_id)

    def reveal(self) -> str:
        """Return the credential.  Only the runner boundary and ``scrub`` may call this."""

        if self._revoked:
            raise KernelError(
                code="SECRET_EXPOSURE",
                message=f"binding {self.binding_id!r} has been revoked",
                recommended_action="re-prepare the sandbox; a revoked handle is not reusable",
                details={"bindingId": self.binding_id},
            )
        return self._value

    def revoke(self) -> None:
        """Wipe the value.  Idempotent, and irreversible for this handle."""

        self._value = ""
        self._revoked = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "bindingId": self.binding_id,
            "scope": self.scope,
            "ttlSeconds": self.ttl_seconds,
            "reference": self.reference,
            "revoked": self._revoked,
        }

    def __repr__(self) -> str:
        return f"SecretHandle(binding_id={self.binding_id!r}, reference={self.reference!r})"

    __str__ = __repr__


class StaticSecretResolver:
    """A resolver backed by an in-process map, for tests and offline replay."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    def reveal(self, binding_id: str, scope: str) -> str:
        if binding_id not in self._values:
            raise KernelError(
                code="SANDBOX_PROVISION_FAILED",
                message=f"no credential is bound to {binding_id!r}",
                recommended_action="provision the binding before the execute phase",
                details={"bindingId": binding_id},
            )
        return self._values[binding_id]


def scrub(text: str, handles: Sequence[SecretHandle]) -> str:
    """Remove every handle's value from ``text``.

    Replacement runs longest value first so that a credential which contains
    another credential cannot leave a fragment behind.  Over-redaction is
    accepted: if a secret happens to be a substring of innocent output, that
    output loses the substring.  The alternative — matching on word boundaries
    so the innocent text survives — leaves the credential printed whenever it is
    embedded in a URL or a JSON blob, which is where credentials actually leak.
    """

    if not isinstance(text, str):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="scrub operates on text",
            recommended_action="decode the bytes before scrubbing",
        )
    live: list[SecretHandle] = []
    for candidate in handles:
        if candidate.revoked:
            raise KernelError(
                code="SECRET_EXPOSURE",
                message=(
                    f"cannot prove text is free of {candidate.binding_id!r}: the handle was "
                    "revoked before the text was scrubbed"
                ),
                recommended_action="scrub captured output before revoking handles",
                details={"bindingId": candidate.binding_id},
            )
        live.append(candidate)
    ordered = sorted(live, key=lambda item: (-len(item.reveal()), item.binding_id))
    for candidate in ordered:
        text = text.replace(candidate.reveal(), candidate.redaction)
    return text


@dataclass(frozen=True, slots=True)
class Command:
    """What to run.

    A command carries no policy: no network flag, no path grant, no secret. Any
    such string inside ``argv`` is inert data, which is what makes an injected
    ``--network=allow-all`` in a repository script harmless here.
    """

    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.argv:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="argv must not be empty",
                recommended_action="supply the executable and its arguments",
            )
        if len(self.argv) > _MAX_ARGV:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"argv exceeds {_MAX_ARGV} entries",
                recommended_action="write the arguments to a file in the workspace",
            )
        for index, item in enumerate(self.argv):
            require_str(item, f"argv[{index}]")
        require_str(self.cwd, "cwd", max_length=1024)
        require_mapping(self.env, "env")
        for name, value in self.env.items():
            require_str(name, "env key", max_length=128)
            require_str(value, f"env[{name}]", max_length=4096)

    def to_payload(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "envKeys": sorted(self.env),
        }

    @property
    def digest(self) -> str:
        return digest({"argv": list(self.argv), "cwd": self.cwd,
                       "env": dict(sorted(self.env.items()))})


@dataclass(frozen=True, slots=True)
class PreparedSandbox:
    """The output of phase one: everything decided, nothing executed."""

    profile: SandboxProfile
    phase: Phase
    handles: tuple[SecretHandle, ...]
    env: Mapping[str, str]
    network_descriptor: str
    obligations: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_payload(),
            "phase": str(self.phase),
            "secretLease": [item.to_payload() for item in self.handles],
            "env": dict(sorted(self.env.items())),
            "networkDescriptor": self.network_descriptor,
            "obligations": list(self.obligations),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


class SandboxStatus(StrEnum):
    """Outcome of an execution.

    ``INTERRUPTED`` covers timeout and signal death.  It is not a synonym for
    ``FAILED``: no verdict was reached, and the caller must reconcile rather
    than assume nothing happened.
    """

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class SandboxOutcome:
    """A bounded, scrubbed execution result.

    ``exit_code`` is ``None`` with ``exit_code_measured=False`` when the process
    was killed: reporting a killed process as exit 0 — or as exit 1 — invents a
    verdict the kernel does not have.  ``truncated`` is likewise explicit; output
    that was cut is never presented as complete.
    """

    status: SandboxStatus
    exit_code: int | None
    exit_code_measured: bool
    stdout: str
    stderr: str
    truncated: bool
    captured_bytes: int
    produced_bytes: int
    wall_clock_ms: int | None
    wall_clock_measured: bool
    evidence: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "exitCode": self.exit_code,
            "exitCodeMeasured": self.exit_code_measured,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
            "capturedBytes": self.captured_bytes,
            "producedBytes": self.produced_bytes,
            "wallClockMs": self.wall_clock_ms,
            "wallClockMeasured": self.wall_clock_measured,
            "evidence": dict(self.evidence),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class CleanupReport:
    """Proof that every handle was revoked.

    ``attested`` is only true when the revoked count equals the issued count.
    A partial cleanup is ``CLEANUP_INCOMPLETE``, never a report with a hopeful
    boolean.
    """

    profile_id: str
    issued: int
    revoked: int
    attested: bool
    binding_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "issued": self.issued,
            "revoked": self.revoked,
            "attested": self.attested,
            "bindingIds": list(self.binding_ids),
        }


class RecordingRunner:
    """A ``ProcessRunner`` that records what it was asked to do and replays results.

    Tests assert against ``calls`` — in particular that the env it received
    contains references and not credentials.  Nothing is ever spawned.
    """

    __slots__ = ("_results", "calls")

    def __init__(self, results: Sequence[Mapping[str, Any]]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: Sequence[str], *, cwd: str, env: Mapping[str, str],
            timeout_seconds: int, network: str) -> Mapping[str, Any]:
        self.calls.append({
            "argv": list(argv),
            "cwd": cwd,
            "env": dict(env),
            "timeoutSeconds": timeout_seconds,
            "network": network,
        })
        if not self._results:
            raise KernelError(
                code="SANDBOX_PROVISION_FAILED",
                message="RecordingRunner has no queued result for this call",
                recommended_action="queue one result per expected run",
            )
        return self._results.pop(0)


class DenyAllRunner:
    """A ``ProcessRunner`` that refuses everything.

    Used to prove that a denial happens *before* execution: if a test that
    expects a deny still reaches this runner, the failure is loud instead of
    being a silently successful run.
    """

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: Sequence[str], *, cwd: str, env: Mapping[str, str],
            timeout_seconds: int, network: str) -> Mapping[str, Any]:
        self.calls.append({"argv": list(argv), "cwd": cwd})
        raise KernelError(
            code="SANDBOX_PROVISION_FAILED",
            message="DenyAllRunner refuses every execution",
            recommended_action="this runner exists to prove nothing reached execution",
        )


def _authority_collection(authority: Any, attribute: str) -> Mapping[str, str]:
    """Read a scope collection off a duck-typed authority, failing closed."""

    if not hasattr(authority, attribute):
        raise KernelError(
            code="AUTHORITY_SCOPE_MISMATCH",
            message=f"execution authority does not declare {attribute!r}",
            recommended_action="supply a complete ExecutionAuthority; absence is a deny",
            details={"missingAttribute": attribute},
        )
    value = getattr(authority, attribute)
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(item): "" for item in value}
    raise KernelError(
        code="AUTHORITY_SCOPE_MISMATCH",
        message=f"execution authority {attribute!r} is not a collection",
        recommended_action="declare the scope set as a sequence or mapping",
    )


def _optional_text(value: Any, field_name: str) -> str:
    """Decode a possibly-absent text field.

    Empty output is a real observation ("the process printed nothing"), so it
    must not be rejected the way an absent required string is; a non-string,
    on the other hand, means the runner is broken.
    """

    if value is None:
        return ""
    if not isinstance(value, str):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be text, got {type(value).__name__}",
            recommended_action="decode the stream before reporting it",
        )
    if len(value) > (1 << 22):
        raise KernelError(
            code="INPUT_TOO_LARGE",
            message=f"{field_name} exceeds 4 MiB before truncation",
            recommended_action="have the runner bound its capture buffer",
        )
    return value


def _truncate(text: str, max_bytes: int) -> tuple[str, bool, int, int]:
    """Return ``(text, truncated, captured_bytes, produced_bytes)``.

    Truncation happens on a character boundary but is measured in bytes, so the
    reported figure is the one that matters for storage and for the caller's
    budget.
    """

    encoded = text.encode("utf-8")
    produced = len(encoded)
    if produced <= max_bytes:
        return text, False, produced, produced
    clipped = encoded[:max_bytes]
    while clipped:
        try:
            decoded = clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]
            continue
        return decoded, True, len(clipped), produced
    return "", True, 0, produced


class TwoPhaseSandbox:
    """Phase one resolves; phase two runs; phase three proves the cleanup.

    The class holds no credential state of its own — handles live in the
    ``PreparedSandbox`` the caller holds — so an instance can be reused without
    one workload's binding leaking into another's.
    """

    __slots__ = ("_catalogue",)

    def __init__(self, catalogue: Mapping[str, SandboxProfile]) -> None:
        self._catalogue = dict(catalogue)

    def prepare(self, *, profile_id: str, phase: Phase, authority: Any,
                bindings: Sequence[SecretBinding] = (),
                resolver: Any = None,
                obligations: Sequence[str] = ()) -> PreparedSandbox:
        """Resolve the profile, check every scope, and mint short-lived handles."""

        require_identifier(profile_id, "profile_id")
        if not isinstance(phase, Phase):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown sandbox phase {phase!r}",
                recommended_action="use Phase.ANALYZE or Phase.EXECUTE",
            )
        profile = self._catalogue.get(profile_id)
        if profile is None:
            raise KernelError(
                code="SANDBOX_PROVISION_FAILED",
                message=f"sandbox profile {profile_id!r} is not in the environment catalogue",
                retryable=False,
                recommended_action=(
                    "publish the profile in the environment; a profile is never assembled "
                    "from request content"
                ),
                details={"profileId": profile_id},
            )

        obligation_set = tuple(sorted(set(obligations)))

        # --- filesystem -----------------------------------------------------
        granted_paths = sorted(_authority_collection(authority, "path_scopes"))
        normalised_grants = [_normalise_path(item) for item in granted_paths]
        for root in profile.filesystem_allow:
            if not any(_within(root, granted) for granted in normalised_grants):
                raise KernelError(
                    code="AUTHORITY_SCOPE_MISMATCH",
                    message=(
                        f"profile {profile_id!r} allows {root!r}, which lies outside every "
                        "path the authority granted"
                    ),
                    retryable=False,
                    recommended_action="narrow the profile or widen the authority explicitly",
                    details={"path": root, "granted": granted_paths},
                )

        # --- network --------------------------------------------------------
        network = profile.network
        granted_net = set(_authority_collection(authority, "network_scopes"))
        if network.mode is NetworkMode.ALLOW_LIST:
            for grant in network.grants:
                if grant.token not in granted_net:
                    raise KernelError(
                        code="NETWORK_POLICY_BYPASS",
                        message=(
                            f"profile {profile_id!r} grants {grant.token}, which the "
                            "authority does not permit"
                        ),
                        retryable=False,
                        recommended_action="add the host:port to the permission profile",
                        details={"destination": grant.token},
                    )
        elif network.mode is NetworkMode.ALLOW_ALL:
            if not network.allow_all_acknowledged:
                raise KernelError(
                    code="NETWORK_POLICY_BYPASS",
                    message=(
                        f"profile {profile_id!r} requests allow-all networking without the "
                        "explicit acknowledgement flag"
                    ),
                    retryable=False,
                    recommended_action="set allowAllAcknowledged on the profile deliberately",
                )
            if ALLOW_ALL_OBLIGATION not in obligation_set:
                raise KernelError(
                    code="NETWORK_POLICY_BYPASS",
                    message=(
                        "allow-all networking additionally requires the policy obligation "
                        f"{ALLOW_ALL_OBLIGATION!r}; the profile flag alone is not sufficient"
                    ),
                    retryable=False,
                    recommended_action="obtain the policy obligation before running",
                    details={"requiredObligation": ALLOW_ALL_OBLIGATION},
                )

        # --- secrets --------------------------------------------------------
        bindings = tuple(bindings)
        if phase is Phase.ANALYZE and bindings:
            raise KernelError(
                code="SANDBOX_PHASE_VIOLATION",
                message=(
                    "a secret was requested during the secretless analysis phase; "
                    f"{len(bindings)} binding(s) were in scope"
                ),
                retryable=False,
                recommended_action="move the credentialed work into the execute phase",
                details={"phase": str(phase),
                         "bindingIds": sorted(item.binding_id for item in bindings)},
            )

        granted_secrets = _authority_collection(authority, "secret_bindings")
        handles: list[SecretHandle] = []
        env: dict[str, str] = {}
        seen: set[str] = set()
        for binding in sorted(bindings, key=lambda item: item.binding_id):
            if binding.binding_id in seen:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"binding {binding.binding_id!r} appears twice",
                    recommended_action="declare each binding once",
                )
            seen.add(binding.binding_id)
            if binding.binding_id not in granted_secrets:
                raise KernelError(
                    code="AUTHORITY_SCOPE_MISMATCH",
                    message=(
                        f"binding {binding.binding_id!r} is not granted by the execution "
                        "authority"
                    ),
                    retryable=False,
                    recommended_action="grant the binding in the permission profile",
                    details={"bindingId": binding.binding_id},
                )
            declared = granted_secrets[binding.binding_id]
            if declared and declared != binding.scope:
                raise KernelError(
                    code="AUTHORITY_SCOPE_MISMATCH",
                    message=(
                        f"binding {binding.binding_id!r} requests scope {binding.scope!r} "
                        f"but the authority grants {declared!r}"
                    ),
                    retryable=False,
                    recommended_action="request exactly the granted scope",
                    details={"bindingId": binding.binding_id},
                )
            env_name = _env_name(binding.binding_id)
            if env_name not in profile.env_allow:
                raise KernelError(
                    code="SANDBOX_PROVISION_FAILED",
                    message=(
                        f"binding {binding.binding_id!r} would populate {env_name}, which "
                        f"profile {profile_id!r} does not allow"
                    ),
                    recommended_action="add the variable to the profile's env allow-list",
                    details={"envVar": env_name},
                )
            if resolver is None:
                raise KernelError(
                    code="SANDBOX_PROVISION_FAILED",
                    message="secret bindings were requested without a resolver",
                    recommended_action="supply a SecretResolver for the execute phase",
                )
            value = resolver.reveal(binding.binding_id, binding.scope)
            handle = SecretHandle(binding, value)
            handles.append(handle)
            # The reference, not the value.  This is the whole design.
            env[env_name] = handle.reference

        return PreparedSandbox(
            profile=profile,
            phase=phase,
            handles=tuple(handles),
            env=env,
            network_descriptor=network.descriptor,
            obligations=obligation_set,
        )

    def execute(self, prepared: PreparedSandbox, command: Command,
                runner: Any) -> SandboxOutcome:
        """Run ``command`` through ``runner`` under the prepared profile."""

        profile = prepared.profile
        cwd = _normalise_path(command.cwd)
        if not any(_within(cwd, root) for root in profile.filesystem_allow):
            raise KernelError(
                code="SANDBOX_PATH_DENIED",
                message=f"working directory {cwd!r} is outside the profile's allowed roots",
                retryable=False,
                recommended_action="run inside the workspace",
                details={"cwd": cwd, "allowed": list(profile.filesystem_allow)},
            )

        env: dict[str, str] = {}
        for name in sorted(command.env):
            if name not in profile.env_allow:
                raise KernelError(
                    code="SANDBOX_PROVISION_FAILED",
                    message=(
                        f"environment variable {name!r} is not on profile "
                        f"{profile.profile_id!r}'s allow-list"
                    ),
                    retryable=False,
                    recommended_action="add the variable to the profile, not to the command",
                    details={"envVar": name},
                )
            env[name] = command.env[name]
        # Prepared secret references win over anything the command supplied: a
        # command must never be able to shadow a binding with its own value.
        env.update(prepared.env)

        try:
            raw = runner.run(list(command.argv), cwd=cwd, env=dict(sorted(env.items())),
                             timeout_seconds=profile.limits.wall_clock_seconds,
                             network=prepared.network_descriptor)
        except KernelError as exc:
            raise _scrubbed_error(exc, prepared.handles) from None

        return self._interpret(prepared, command, raw, cwd=cwd)

    def _interpret(self, prepared: PreparedSandbox, command: Command,
                   raw: Any, *, cwd: str) -> SandboxOutcome:
        raw = require_mapping(raw, "runner result")
        reject_unknown_fields(
            raw,
            {"exitCode", "stdout", "stderr", "timedOut", "signal", "wallClockMs",
             "interrupted"},
            field_name="runner result",
        )
        timed_out = require_bool(raw.get("timedOut", False), "runner result.timedOut")
        interrupted = require_bool(raw.get("interrupted", False),
                                   "runner result.interrupted")
        signal = raw.get("signal")
        if signal is not None:
            require_int(signal, "runner result.signal", minimum=1)
        exit_code = raw.get("exitCode")
        if exit_code is not None:
            require_int(exit_code, "runner result.exitCode", minimum=-256, maximum=255)

        limits = prepared.profile.limits
        stdout_raw = _optional_text(raw.get("stdout"), "runner result.stdout")
        stderr_raw = _optional_text(raw.get("stderr"), "runner result.stderr")

        stdout_clean = scrub(stdout_raw, prepared.handles)
        stderr_clean = scrub(stderr_raw, prepared.handles)
        stdout, out_trunc, out_captured, out_produced = _truncate(
            stdout_clean, limits.max_output_bytes)
        stderr, err_trunc, err_captured, err_produced = _truncate(
            stderr_clean, limits.max_output_bytes)

        killed = timed_out or interrupted or signal is not None
        if killed:
            status = SandboxStatus.INTERRUPTED
            exit_code = None
            measured = False
        elif exit_code is None:
            raise KernelError(
                code="SANDBOX_PROVISION_FAILED",
                message=(
                    "the runner reported neither an exit code nor a termination reason; "
                    "the outcome is unknown and will not be guessed"
                ),
                retryable=False,
                recommended_action="fix the runner to report exitCode or timedOut/signal",
            )
        else:
            measured = True
            status = (SandboxStatus.SUCCEEDED if exit_code == 0
                      else SandboxStatus.FAILED)

        wall_clock = raw.get("wallClockMs")
        if wall_clock is not None:
            require_int(wall_clock, "runner result.wallClockMs", minimum=0)

        evidence = {
            "profileDigest": prepared.profile.digest,
            "preparedDigest": prepared.digest,
            "commandDigest": command.digest,
            "cwd": cwd,
            "networkDescriptor": prepared.network_descriptor,
            "phase": str(prepared.phase),
            "secretReferences": sorted(item.reference for item in prepared.handles),
            "stdoutDigest": digest_bytes(stdout.encode("utf-8")),
            "stderrDigest": digest_bytes(stderr.encode("utf-8")),
            "timedOut": timed_out,
            "signal": signal,
        }

        return SandboxOutcome(
            status=status,
            exit_code=exit_code,
            exit_code_measured=measured,
            stdout=stdout,
            stderr=stderr,
            truncated=out_trunc or err_trunc,
            captured_bytes=out_captured + err_captured,
            produced_bytes=out_produced + err_produced,
            wall_clock_ms=wall_clock,
            wall_clock_measured=wall_clock is not None,
            evidence=evidence,
        )

    def finalize(self, prepared: PreparedSandbox) -> CleanupReport:
        """Revoke every handle and attest that none survived."""

        for item in prepared.handles:
            item.revoke()
        revoked = sum(1 for item in prepared.handles if item.revoked)
        issued = len(prepared.handles)
        if revoked != issued:  # pragma: no cover - defensive; revoke cannot fail
            raise KernelError(
                code="CLEANUP_INCOMPLETE",
                message=f"revoked {revoked} of {issued} secret handles",
                retryable=True,
                recommended_action="revoke the remaining bindings out of band",
            )
        return CleanupReport(
            profile_id=prepared.profile.profile_id,
            issued=issued,
            revoked=revoked,
            attested=True,
            binding_ids=tuple(sorted(item.binding_id for item in prepared.handles)),
        )


def _env_name(binding_id: str) -> str:
    """Deterministic env variable name for a binding."""

    return binding_id.upper().replace("-", "_").replace(".", "_").replace(":", "_")


def _scrubbed_error(exc: KernelError, handles: Sequence[SecretHandle]) -> KernelError:
    """Re-raise a runner error with every credential removed from its text.

    An error message is the single most-copied string in an incident, and a
    subprocess error frequently echoes its own command line.
    """

    details = {
        key: scrub(value, handles) if isinstance(value, str) else value
        for key, value in exc.details.items()
    }
    return KernelError(
        code=exc.code,
        message=scrub(exc.message, handles),
        retryable=exc.retryable,
        partial=exc.partial,
        interrupted=exc.interrupted,
        evidence_ids=exc.evidence_ids,
        recommended_action=scrub(exc.recommended_action, handles),
        details=details,
    )


# --- registry entry point ----------------------------------------------------


class _AuthorityView:
    """Read-only adapter over a wire-form execution authority."""

    __slots__ = ("environment_id", "workspace_id", "fencing_token", "allowed_tools",
                 "path_scopes", "network_scopes", "secret_bindings")

    def __init__(self, payload: Mapping[str, Any]) -> None:
        payload = require_mapping(payload, "execution_authority")
        known = {"environmentId", "workspaceId", "fencingToken", "allowedTools",
                 "pathScopes", "networkScopes", "secretBindings"}
        reject_unknown_fields(payload, known, field_name="execution_authority")
        self.environment_id = require_identifier(payload.get("environmentId", "env-unknown"),
                                                 "execution_authority.environmentId")
        self.workspace_id = require_identifier(payload.get("workspaceId", "ws-unknown"),
                                               "execution_authority.workspaceId")
        token = payload.get("fencingToken")
        self.fencing_token = (
            None if token is None
            else require_int(token, "execution_authority.fencingToken", minimum=1)
        )
        self.allowed_tools = require_str_seq(payload.get("allowedTools", ()),
                                             "execution_authority.allowedTools")
        self.path_scopes = require_str_seq(payload.get("pathScopes", ()),
                                           "execution_authority.pathScopes")
        self.network_scopes = require_str_seq(payload.get("networkScopes", ()),
                                              "execution_authority.networkScopes")
        bindings = payload.get("secretBindings", {})
        if isinstance(bindings, Mapping):
            self.secret_bindings: Mapping[str, str] | tuple[str, ...] = {
                require_identifier(key, "secretBindings key"):
                    require_str(value, f"secretBindings[{key}]")
                for key, value in bindings.items()
            }
        else:
            self.secret_bindings = require_str_seq(bindings,
                                                   "execution_authority.secretBindings")


@register("two-phase-secretless-sandbox")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``two-phase-secretless-sandbox``.

    ``runner_result`` is supplied by the transport that actually executed the
    command: this entry point decides and attests, it never spawns.
    """

    request = require_mapping(request, "request")
    known = {"sandbox_profile_catalogue", "sandbox_profile_id", "phase", "command",
             "execution_authority", "secret_bindings", "policy_obligations",
             "runner_result", "repository_snapshot"}
    reject_unknown_fields(request, known, field_name="request")
    for name in ("sandbox_profile_catalogue", "sandbox_profile_id", "command",
                 "execution_authority", "runner_result"):
        if name not in request:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{name} is required",
                recommended_action=f"supply request.{name}",
            )

    catalogue_raw = require_mapping(request["sandbox_profile_catalogue"],
                                    "sandbox_profile_catalogue")
    catalogue = {
        require_identifier(key, "sandbox_profile_catalogue key"):
            SandboxProfile.from_payload(value)
        for key, value in catalogue_raw.items()
    }
    phase = Phase(require_str(request.get("phase", "EXECUTE"), "phase"))
    authority = _AuthorityView(request["execution_authority"])
    bindings = tuple(
        SecretBinding(
            binding_id=require_identifier(item.get("bindingId"), "secret_bindings[].bindingId"),
            scope=require_str(item.get("scope"), "secret_bindings[].scope"),
            ttl_seconds=require_int(item.get("ttlSeconds"), "secret_bindings[].ttlSeconds",
                                    minimum=1),
        )
        for item in request.get("secret_bindings", ())
    )
    if bindings:
        raise KernelError(
            code="SECRET_EXPOSURE",
            message=(
                "the registry entry point does not resolve credentials; run the execute "
                "phase through TwoPhaseSandbox with an out-of-band resolver"
            ),
            retryable=False,
            recommended_action="call TwoPhaseSandbox.prepare directly for credentialed work",
            details={"bindingIds": sorted(item.binding_id for item in bindings)},
        )

    command_raw = require_mapping(request["command"], "command")
    reject_unknown_fields(command_raw, {"argv", "cwd", "env"}, field_name="command")
    command = Command(
        argv=require_str_seq(command_raw.get("argv", ()), "command.argv", allow_empty=False),
        cwd=require_str(command_raw.get("cwd"), "command.cwd", max_length=1024),
        env={
            require_str(key, "command.env key"): require_str(value, f"command.env[{key}]")
            for key, value in require_mapping(command_raw.get("env", {}),
                                              "command.env").items()
        },
    )

    sandbox = TwoPhaseSandbox(catalogue)
    prepared = sandbox.prepare(
        profile_id=require_identifier(request["sandbox_profile_id"], "sandbox_profile_id"),
        phase=phase,
        authority=authority,
        bindings=(),
        obligations=require_str_seq(request.get("policy_obligations", ()),
                                    "policy_obligations"),
    )
    outcome = sandbox.execute(prepared, command, _ReplayRunner(request["runner_result"]))
    cleanup = sandbox.finalize(prepared)
    return {
        "sandbox_environment": prepared.to_payload(),
        "secret_lease": [item.to_payload() for item in prepared.handles],
        "execution_result": outcome.to_payload(),
        "sandbox_attestation": {
            "preparedDigest": prepared.digest,
            "outcomeDigest": outcome.digest,
            "networkDescriptor": prepared.network_descriptor,
            "phase": str(prepared.phase),
        },
        "cleanup_report": cleanup.to_payload(),
        "digest": digest({"prepared": prepared.to_payload(),
                          "outcome": outcome.to_payload(),
                          "cleanup": cleanup.to_payload()}),
    }


class _ReplayRunner:
    """Replays a recorded runner result inside the registry entry point."""

    __slots__ = ("_result",)

    def __init__(self, result: Any) -> None:
        self._result = result

    def run(self, argv: Sequence[str], *, cwd: str, env: Mapping[str, str],
            timeout_seconds: int, network: str) -> Any:
        return self._result
