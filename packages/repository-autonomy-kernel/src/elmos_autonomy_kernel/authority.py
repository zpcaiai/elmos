"""Execution Authority Kernel.

Authority in this system is a *capability token minted by the execution environment*, not a
belief held by a conversation.  That single choice is what makes prompt injection a nuisance
rather than a breach: a model can ask for anything it likes, but the only thing that can widen
what a worker may touch is code that constructs an :class:`ExecutionAuthority`, and the only
constructors are the environment (:func:`mint`) and strict narrowing (:meth:`ExecutionAuthority
.derive`).  Text cannot construct what text cannot reach.

Three decisions here are deliberate and worth defending in review:

*Every check runs, always.*  :meth:`ExecutionAuthority.authorize` does not short-circuit on the
first denial.  A decision carries one ``Reason`` per check in a fixed order, and the decision is
rejected at construction if the trace is incomplete — an allow that cannot be explained is a bug,
and a denial that hides the other seven failures wastes an incident responder's night.

*Path containment is textual and component-wise.*  ``src/a`` must not contain ``src/ab``, so the
comparison is on ``/``-split components, never ``str.startswith``.  Textual normalisation is
necessary but **not sufficient**: it cannot see a symlink, so the sandbox that finally opens the
file is still required to use ``O_NOFOLLOW``/``realpath`` inside the same scope.  This module
rejects the things it *can* see — absolute paths, drive letters, ``~``, backslashes, NUL, and
``..`` that climbs above the repository root.

*A write needs a token that something else attested.*  Holding an integer is not holding a lease.
The write-fencing check consults a token source (a :class:`~.ports.LeaseStore`) and denies when
no independent source confirms the authority's token is still current.

Deviations from the design direction, with reasons: two checks were added to the directed list —
``authority.subject-source`` (mirrors ``authority.rego``'s ``authority_source == "conversation"``
deny, so a request that *claims* conversational provenance is refused even when the authority
object itself is well-formed) and ``authority.policy-snapshot`` (a request justified by a policy
snapshot the authority was not minted under is stale authority, which SKILL.md I3/negative tests
require to be an error rather than a silent re-evaluation).  ``authority.effect`` was also added
so that an unrecognised effect denies via ``AUTHORITY_DENIED`` instead of falling through the
write-fencing check as if it were a read.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from .contracts import (
    digest,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

__all__ = [
    "ALLOWED_SUBJECTS",
    "AttestedTokenSource",
    "AuthorityDecision",
    "AuthorityRequest",
    "CHECK_ORDER",
    "ExecutionAuthority",
    "Reason",
    "TokenSource",
    "handle",
    "mint",
]

register_codes(
    Category.AUTHORITY,
    "AUTHORITY_DENIED",
    "AUTHORITY_STALE",
    "SCOPE_ESCALATION_ATTEMPT",
    "PATH_SCOPE_DENIED",
    "NETWORK_SCOPE_DENIED",
    "SECRET_BINDING_DENIED",
    "WRITE_REQUIRES_FENCING",
)

#: The only subjects an authority may be bound to.  A conversation, thread or session is
#: explicitly *not* one of them; that is invariant I1.
ALLOWED_SUBJECTS: tuple[str, ...] = ("environment", "workspace")
FORBIDDEN_SUBJECTS: tuple[str, ...] = ("conversation", "thread", "session", "prompt", "agent")

#: Effects the kernel understands.  Anything else denies (unknown permission -> deny, I2).
KNOWN_EFFECTS: tuple[str, ...] = ("read", "write")

CHECK_SUBJECT = "authority.subject-source"
CHECK_SCOPE = "authority.scope"
CHECK_POLICY = "authority.policy-snapshot"
CHECK_EFFECT = "authority.effect"
CHECK_EXPIRY = "authority.expiry"
CHECK_FENCING = "authority.fencing"
CHECK_TOOL = "authority.tool"
CHECK_PATH = "authority.path"
CHECK_NETWORK = "authority.network"
CHECK_SECRET = "authority.secret"  # noqa: S105 - a control/verdict name, not a credential
CHECK_WRITE_FENCING = "authority.write-fencing"

#: Fixed evaluation order.  A decision whose trace does not cover exactly this list, in this
#: order, is refused at construction.
CHECK_ORDER: tuple[str, ...] = (
    CHECK_SUBJECT,
    CHECK_SCOPE,
    CHECK_POLICY,
    CHECK_EFFECT,
    CHECK_EXPIRY,
    CHECK_FENCING,
    CHECK_TOOL,
    CHECK_PATH,
    CHECK_NETWORK,
    CHECK_SECRET,
    CHECK_WRITE_FENCING,
)

PASS = "pass"  # noqa: S105 - a control/verdict name, not a credential
DENY = "deny"
NOT_APPLICABLE = "not-applicable"

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


class _PathRejected(Exception):
    """A path could not be normalised into a contained repository-relative path."""


class TokenSource(Protocol):
    """The narrow slice of :class:`~.ports.LeaseStore` this kernel needs.

    Only ``current_token`` is required, so an environment that attests a token without running a
    full lease service can still satisfy the write-fencing check honestly.
    """

    def current_token(self, resource_id: str) -> int: ...


@dataclass(frozen=True, slots=True)
class AttestedTokenSource:
    """One environment-attested current token for one resource.

    Used when authority is minted from an environment descriptor that carries the token rather
    than from a live lease service.  Asking it about a different resource raises instead of
    returning ``0``: "no lease here" and "token zero" must not be the same observation.
    """

    resource_id: str
    token: int

    def __post_init__(self) -> None:
        require_identifier(self.resource_id, "resource_id")
        require_int(self.token, "token", minimum=0)

    def current_token(self, resource_id: str) -> int:
        if resource_id != self.resource_id:
            raise KernelError(
                code="FENCING_REJECTED",
                message=(
                    f"no attested fencing token for resource {resource_id!r}; "
                    f"this source only attests {self.resource_id!r}"
                ),
                recommended_action="consult the lease store that owns the resource",
            )
        return self.token


def _normalise_path(raw: str) -> tuple[str, ...]:
    """Split a repository-relative path into components, rejecting what can be seen textually."""

    if not isinstance(raw, str) or not raw:
        raise _PathRejected("path must be a non-empty string")
    if "\x00" in raw:
        raise _PathRejected("path contains NUL")
    if "\\" in raw:
        raise _PathRejected("backslash is not a path separator in a repo-relative path")
    if raw.startswith("/") or _WINDOWS_DRIVE.match(raw):
        raise _PathRejected("absolute paths lie outside every repo-relative scope")
    if raw.startswith("~"):
        raise _PathRejected("home-relative paths are not repo-relative")
    parts: list[str] = []
    for segment in raw.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not parts:
                raise _PathRejected("path escapes the repository root")
            parts.pop()
            continue
        parts.append(segment)
    return tuple(parts)


def _render_path(parts: tuple[str, ...]) -> str:
    return "/".join(parts) if parts else "."


def _within(scope: tuple[str, ...], candidate: tuple[str, ...]) -> bool:
    """Component-wise containment.  ``src/a`` contains ``src/a/b`` but never ``src/ab``."""

    return len(candidate) >= len(scope) and candidate[: len(scope)] == scope


def _normalise_endpoint(raw: Any, field_name: str) -> str:
    """Normalise an explicit ``host:port`` grant.

    Wildcards are rejected outright: a grant that is not explicit is not a grant.  IPv6 literals
    are deliberately unsupported rather than half-parsed.
    """

    text = require_str(raw, field_name, max_length=272).strip().lower()
    if "*" in text:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} uses a wildcard; network grants must be explicit",
            recommended_action="list each host:port pair you actually need",
        )
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} must be host:port",
            recommended_action="use an explicit host:port grant, e.g. registry.internal:443",
        )
    if not _HOST_RE.match(host):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} has an unusable host part",
            recommended_action="use a DNS name or IPv4 literal; IPv6 literals are unsupported",
        )
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} has an out-of-range port",
            recommended_action="use a port between 1 and 65535",
        )
    return f"{host}:{int(port)}"


@dataclass(frozen=True, slots=True)
class Reason:
    """One executed check and its verdict.

    ``code`` is the stable failure code the check would raise; it is empty exactly when the
    outcome is not a denial, which keeps "denied for no stated reason" unrepresentable.
    """

    check: str
    outcome: str
    detail: str
    code: str = ""

    def __post_init__(self) -> None:
        if self.check not in CHECK_ORDER:
            raise ValueError(f"unknown authority check {self.check!r}")
        if self.outcome not in (PASS, DENY, NOT_APPLICABLE):
            raise ValueError(f"unknown check outcome {self.outcome!r}")
        if not self.detail:
            raise ValueError(f"check {self.check!r} must state why it reached its verdict")
        if self.outcome == DENY and not self.code:
            raise ValueError(f"denial from {self.check!r} must carry a stable failure code")
        if self.outcome != DENY and self.code:
            raise ValueError(f"non-denial from {self.check!r} must not carry a failure code")

    def to_payload(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "outcome": self.outcome,
            "detail": self.detail,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    """The verdict for one request, with the whole trace that produced it.

    Construction enforces two things that reviews otherwise have to catch by eye: the trace covers
    every check in :data:`CHECK_ORDER` exactly once and in order, and ``allowed`` is exactly "no
    check denied".  Both make an unexplainable allow impossible to build.
    """

    allowed: bool
    reasons: tuple[Reason, ...]
    authority_digest: str
    request_digest: str
    decided_at: str

    def __post_init__(self) -> None:
        observed = tuple(reason.check for reason in self.reasons)
        if observed != CHECK_ORDER:
            raise KernelError(
                code="AUTHORITY_DENIED",
                message=(
                    "authority decision trace is incomplete; "
                    f"expected {list(CHECK_ORDER)}, got {list(observed)}"
                ),
                recommended_action="treat as a kernel defect and deny the request",
                details={"expected": list(CHECK_ORDER), "observed": list(observed)},
            )
        denied = any(reason.outcome == DENY for reason in self.reasons)
        if self.allowed == denied:
            raise KernelError(
                code="AUTHORITY_DENIED",
                message="authority decision disagrees with its own trace",
                recommended_action="treat as a kernel defect and deny the request",
            )

    @property
    def denials(self) -> tuple[Reason, ...]:
        return tuple(reason for reason in self.reasons if reason.outcome == DENY)

    @property
    def code(self) -> str:
        """Stable code of the earliest denial; empty when allowed."""

        denials = self.denials
        return denials[0].code if denials else ""

    def raise_for_denial(self) -> None:
        """Raise the earliest denial as a :class:`KernelError`.

        Callers that want enforcement rather than a decision call this.  ``authorize`` itself
        returns instead of raising so that the full trace survives a denial.
        """

        denials = self.denials
        if not denials:
            return
        first = denials[0]
        raise KernelError(
            code=first.code or "AUTHORITY_DENIED",
            message=f"{first.check}: {first.detail}",
            retryable=False,
            recommended_action="re-mint authority from the environment; do not widen in place",
            details={
                "decision": self.to_payload(),
            },
        )

    def to_payload(self) -> dict[str, Any]:
        core = {
            "allowed": self.allowed,
            "code": self.code,
            "reasons": [reason.to_payload() for reason in self.reasons],
            "authorityDigest": self.authority_digest,
            "requestDigest": self.request_digest,
            "decidedAt": self.decided_at,
        }
        return {**core, "digest": digest(core)}


@dataclass(frozen=True, slots=True)
class AuthorityRequest:
    """One thing a worker wants to do, stated in full before anything happens.

    ``effect`` is *not* validated here.  An unrecognised effect must produce a denied decision
    with a trace, not a construction error deep in a caller's stack, because "the kernel refused
    to understand what you asked for" is itself an audit record worth keeping.
    """

    environment_id: str
    workspace_id: str
    tool_id: str
    effect: str
    fencing_token: int
    policy_snapshot_hash: str
    paths: tuple[str, ...] = ()
    network_destinations: tuple[str, ...] = ()
    secret_bindings: tuple[str, ...] = ()
    authority_source: str = "environment"

    def __post_init__(self) -> None:
        require_identifier(self.environment_id, "environment_id")
        require_identifier(self.workspace_id, "workspace_id")
        require_identifier(self.tool_id, "tool_id")
        require_str(self.effect, "effect", max_length=64)
        require_int(self.fencing_token, "fencing_token", minimum=0)
        require_str(self.policy_snapshot_hash, "policy_snapshot_hash")
        require_str(self.authority_source, "authority_source", max_length=64)
        for index, path in enumerate(self.paths):
            require_str(path, f"paths[{index}]")
        for index, endpoint in enumerate(self.network_destinations):
            require_str(endpoint, f"network_destinations[{index}]")
        for index, binding in enumerate(self.secret_bindings):
            require_identifier(binding, f"secret_bindings[{index}]")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, default_environment_id: str,
                     default_workspace_id: str,
                     default_policy_snapshot_hash: str) -> AuthorityRequest:
        """Strictly decode a tool request; unknown fields fail closed."""

        body = require_mapping(payload, "tool_request")
        reject_unknown_fields(
            body,
            (
                "toolId", "effect", "paths", "networkDestinations", "secretBindings",
                "fencingToken", "policySnapshotHash", "authoritySource", "environmentId",
                "workspaceId",
            ),
            field_name="tool_request",
        )
        if "toolId" not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="tool_request.toolId is required",
                recommended_action="name the tool being requested",
            )
        if "fencingToken" not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="tool_request.fencingToken is required",
                recommended_action="present the fencing token the worker holds",
            )
        return cls(
            environment_id=require_identifier(
                body.get("environmentId", default_environment_id), "tool_request.environmentId"),
            workspace_id=require_identifier(
                body.get("workspaceId", default_workspace_id), "tool_request.workspaceId"),
            tool_id=require_identifier(body["toolId"], "tool_request.toolId"),
            effect=require_str(body.get("effect", "read"), "tool_request.effect", max_length=64),
            fencing_token=require_int(body["fencingToken"], "tool_request.fencingToken",
                                      minimum=0),
            policy_snapshot_hash=require_str(
                body.get("policySnapshotHash", default_policy_snapshot_hash),
                "tool_request.policySnapshotHash"),
            paths=require_str_seq(body.get("paths", ()), "tool_request.paths"),
            network_destinations=require_str_seq(
                body.get("networkDestinations", ()), "tool_request.networkDestinations"),
            secret_bindings=require_str_seq(
                body.get("secretBindings", ()), "tool_request.secretBindings"),
            authority_source=require_str(
                body.get("authoritySource", "environment"), "tool_request.authoritySource",
                max_length=64),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "environmentId": self.environment_id,
            "workspaceId": self.workspace_id,
            "toolId": self.tool_id,
            "effect": self.effect,
            "fencingToken": self.fencing_token,
            "policySnapshotHash": self.policy_snapshot_hash,
            "paths": list(self.paths),
            "networkDestinations": list(self.network_destinations),
            "secretBindings": list(self.secret_bindings),
            "authoritySource": self.authority_source,
        }


@dataclass(frozen=True, slots=True)
class ExecutionAuthority:
    """A frozen capability token bound to an environment and a workspace.

    Nothing about it is negotiable at runtime: the fields are normalised and validated once, at
    construction, and the only way to obtain a *different* authority is :meth:`derive`, which can
    only take things away.  A caller that wants more must go back to the environment.
    """

    environment_id: str
    workspace_id: str
    permission_profile_id: str
    policy_snapshot_hash: str
    fencing_token: int
    allowed_tools: frozenset[str]
    path_scopes: tuple[str, ...]
    network_scopes: tuple[str, ...]
    secret_bindings: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    subject: str = "environment"
    derived_from: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.environment_id, "environment_id")
        require_identifier(self.workspace_id, "workspace_id")
        require_identifier(self.permission_profile_id, "permission_profile_id")
        require_str(self.policy_snapshot_hash, "policy_snapshot_hash")
        require_int(self.fencing_token, "fencing_token", minimum=1)
        if self.subject not in ALLOWED_SUBJECTS:
            raise KernelError(
                code="THREAD_GLOBAL_AUTHORITY_FORBIDDEN",
                message=(
                    f"authority subject {self.subject!r} is not one of {list(ALLOWED_SUBJECTS)}; "
                    "a conversation, thread or session can never own authority"
                ),
                recommended_action="mint authority from the execution environment instead",
                details={"subject": self.subject, "allowed": list(ALLOWED_SUBJECTS)},
            )
        tools = frozenset(
            require_identifier(tool, "allowed_tools[]") for tool in self.allowed_tools
        )
        object.__setattr__(self, "allowed_tools", tools)

        scopes: list[str] = []
        for index, scope in enumerate(self.path_scopes):
            try:
                scopes.append(_render_path(_normalise_path(scope)))
            except _PathRejected as exc:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"path_scopes[{index}]={scope!r} is not a usable scope: {exc}",
                    recommended_action="use a clean repo-relative prefix such as 'src/pkg'",
                ) from exc
        object.__setattr__(self, "path_scopes", tuple(sorted(set(scopes))))

        endpoints = {
            _normalise_endpoint(endpoint, f"network_scopes[{index}]")
            for index, endpoint in enumerate(self.network_scopes)
        }
        object.__setattr__(self, "network_scopes", tuple(sorted(endpoints)))

        bindings = {
            require_identifier(binding, f"secret_bindings[{index}]")
            for index, binding in enumerate(self.secret_bindings)
        }
        object.__setattr__(self, "secret_bindings", tuple(sorted(bindings)))

        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"{name} must be a timezone-aware datetime",
                    recommended_action="pass an aware UTC datetime",
                )
        if self.expires_at <= self.issued_at:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="authority expires_at must be strictly after issued_at",
                recommended_action="grant a positive lifetime or refuse to mint",
            )

    # --- introspection -------------------------------------------------------

    @property
    def scope_parts(self) -> tuple[tuple[str, ...], ...]:
        return tuple(_normalise_path(scope) if scope != "." else () for scope in self.path_scopes)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def to_payload(self) -> dict[str, Any]:
        core = {
            "environmentId": self.environment_id,
            "workspaceId": self.workspace_id,
            "permissionProfileId": self.permission_profile_id,
            "policySnapshotHash": self.policy_snapshot_hash,
            "fencingToken": self.fencing_token,
            "allowedTools": sorted(self.allowed_tools),
            "pathScopes": list(self.path_scopes),
            "networkScopes": list(self.network_scopes),
            "secretBindings": list(self.secret_bindings),
            "issuedAt": format_timestamp(self.issued_at),
            "expiresAt": format_timestamp(self.expires_at),
            "subject": self.subject,
            "derivedFrom": self.derived_from,
        }
        return core

    @property
    def digest(self) -> str:
        return digest(self.to_payload())

    def snapshot(self) -> dict[str, Any]:
        """Freeze the authority for this request: payload plus its own content address."""

        payload = self.to_payload()
        return {"authority": payload, "digest": digest(payload)}

    # --- narrowing -----------------------------------------------------------

    def derive(self, *, allowed_tools: frozenset[str] | tuple[str, ...] | None = None,
               path_scopes: tuple[str, ...] | None = None,
               network_scopes: tuple[str, ...] | None = None,
               secret_bindings: tuple[str, ...] | None = None,
               expires_at: datetime | None = None) -> ExecutionAuthority:
        """Produce a strictly narrower child authority.

        Only removal is expressible: tools and network and secret grants must be subsets, every
        child path scope must sit inside a parent scope, and the expiry may only move earlier.
        Anything else raises ``AUTHORITY_SCOPE_MISMATCH``.  This is the anti-escalation primitive
        the rest of the kernel leans on — a sub-agent, a tool adapter or an injected instruction
        can call ``derive`` all day and never end up with more than the parent held.
        """

        child_tools = frozenset(self.allowed_tools if allowed_tools is None else allowed_tools)
        extra_tools = sorted(child_tools - self.allowed_tools)
        if extra_tools:
            raise _escalation("allowed_tools", extra_tools)

        child_scopes = tuple(self.path_scopes if path_scopes is None else path_scopes)
        parent_parts = self.scope_parts
        widened: list[str] = []
        for scope in child_scopes:
            try:
                parts = _normalise_path(scope)
            except _PathRejected as exc:
                raise KernelError(
                    code="AUTHORITY_SCOPE_MISMATCH",
                    message=f"derived path scope {scope!r} is not usable: {exc}",
                    recommended_action="derive with a clean repo-relative prefix",
                ) from exc
            if not any(_within(parent, parts) for parent in parent_parts):
                widened.append(_render_path(parts))
        if widened:
            raise _escalation("path_scopes", widened)

        child_network = tuple(self.network_scopes if network_scopes is None else network_scopes)
        normalised_network = tuple(
            _normalise_endpoint(endpoint, f"network_scopes[{index}]")
            for index, endpoint in enumerate(child_network)
        )
        extra_network = sorted(set(normalised_network) - set(self.network_scopes))
        if extra_network:
            raise _escalation("network_scopes", extra_network)

        child_secrets = tuple(self.secret_bindings if secret_bindings is None
                              else secret_bindings)
        extra_secrets = sorted(set(child_secrets) - set(self.secret_bindings))
        if extra_secrets:
            raise _escalation("secret_bindings", extra_secrets)

        child_expiry = self.expires_at if expires_at is None else expires_at
        if child_expiry > self.expires_at:
            raise _escalation(
                "expires_at", [format_timestamp(child_expiry)],
                detail=f"parent expires at {format_timestamp(self.expires_at)}",
            )

        return replace(
            self,
            allowed_tools=child_tools,
            path_scopes=child_scopes,
            network_scopes=normalised_network,
            secret_bindings=child_secrets,
            expires_at=child_expiry,
            derived_from=self.digest,
        )

    # --- the decision --------------------------------------------------------

    def authorize(self, request: AuthorityRequest, *, clock: Any,
                  token_source: TokenSource | None = None) -> AuthorityDecision:
        """Decide one request and explain every check that ran.

        Checks are never short-circuited: the returned trace always contains one ``Reason`` per
        entry of :data:`CHECK_ORDER`, in that order, so a denial shows *all* the ways the request
        was wrong rather than only the first.  The decision is returned, not raised, because a
        denial is a record worth keeping; call :meth:`AuthorityDecision.raise_for_denial` to
        enforce it.
        """

        now = clock.now()
        reasons: list[Reason] = [
            self._check_subject(request),
            self._check_scope(request),
            self._check_policy_snapshot(request),
            self._check_effect(request),
            self._check_expiry(now),
            self._check_fencing(request, token_source),
            self._check_tool(request),
            self._check_paths(request),
            self._check_network(request),
            self._check_secrets(request),
            self._check_write_fencing(request, token_source),
        ]
        allowed = not any(reason.outcome == DENY for reason in reasons)
        return AuthorityDecision(
            allowed=allowed,
            reasons=tuple(reasons),
            authority_digest=self.digest,
            request_digest=digest(request.to_payload()),
            decided_at=format_timestamp(now),
        )

    def _check_subject(self, request: AuthorityRequest) -> Reason:
        if request.authority_source in FORBIDDEN_SUBJECTS:
            return Reason(
                check=CHECK_SUBJECT, outcome=DENY,
                code="THREAD_GLOBAL_AUTHORITY_FORBIDDEN",
                detail=(
                    f"request claims authority sourced from {request.authority_source!r}; "
                    "authority is owned by the execution environment"
                ),
            )
        if request.authority_source not in ALLOWED_SUBJECTS:
            return Reason(
                check=CHECK_SUBJECT, outcome=DENY,
                code="THREAD_GLOBAL_AUTHORITY_FORBIDDEN",
                detail=f"unknown authority source {request.authority_source!r}; unknown denies",
            )
        return Reason(
            check=CHECK_SUBJECT, outcome=PASS,
            detail=f"authority source {request.authority_source!r} is environment-owned",
        )

    def _check_scope(self, request: AuthorityRequest) -> Reason:
        if request.environment_id != self.environment_id:
            return Reason(
                check=CHECK_SCOPE, outcome=DENY, code="AUTHORITY_SCOPE_MISMATCH",
                detail=(
                    f"request environment {request.environment_id!r} != authority environment "
                    f"{self.environment_id!r}"
                ),
            )
        if request.workspace_id != self.workspace_id:
            return Reason(
                check=CHECK_SCOPE, outcome=DENY, code="AUTHORITY_SCOPE_MISMATCH",
                detail=(
                    f"request workspace {request.workspace_id!r} != authority workspace "
                    f"{self.workspace_id!r}"
                ),
            )
        return Reason(
            check=CHECK_SCOPE, outcome=PASS,
            detail=f"environment {self.environment_id!r} / workspace {self.workspace_id!r} match",
        )

    def _check_policy_snapshot(self, request: AuthorityRequest) -> Reason:
        if request.policy_snapshot_hash != self.policy_snapshot_hash:
            return Reason(
                check=CHECK_POLICY, outcome=DENY, code="AUTHORITY_STALE",
                detail=(
                    "request is justified by policy snapshot "
                    f"{request.policy_snapshot_hash} but authority was minted under "
                    f"{self.policy_snapshot_hash}"
                ),
            )
        return Reason(
            check=CHECK_POLICY, outcome=PASS,
            detail=f"policy snapshot {self.policy_snapshot_hash} matches the minted authority",
        )

    def _check_effect(self, request: AuthorityRequest) -> Reason:
        if request.effect not in KNOWN_EFFECTS:
            return Reason(
                check=CHECK_EFFECT, outcome=DENY, code="AUTHORITY_DENIED",
                detail=(
                    f"unknown effect {request.effect!r}; known effects are "
                    f"{list(KNOWN_EFFECTS)} and an unknown permission denies"
                ),
            )
        return Reason(
            check=CHECK_EFFECT, outcome=PASS, detail=f"effect {request.effect!r} is understood",
        )

    def _check_expiry(self, now: datetime) -> Reason:
        if self.is_expired(now):
            return Reason(
                check=CHECK_EXPIRY, outcome=DENY, code="AUTHORITY_EXPIRED",
                detail=(
                    f"authority expired at {format_timestamp(self.expires_at)}; "
                    f"now is {format_timestamp(now)}"
                ),
            )
        return Reason(
            check=CHECK_EXPIRY, outcome=PASS,
            detail=f"authority is valid until {format_timestamp(self.expires_at)}",
        )

    def _check_fencing(self, request: AuthorityRequest,
                       token_source: TokenSource | None) -> Reason:
        if request.fencing_token != self.fencing_token:
            return Reason(
                check=CHECK_FENCING, outcome=DENY, code="FENCING_REJECTED",
                detail=(
                    f"request presents fencing token {request.fencing_token}, "
                    f"authority was minted at {self.fencing_token}"
                ),
            )
        if token_source is None:
            return Reason(
                check=CHECK_FENCING, outcome=PASS,
                detail=(
                    f"token {self.fencing_token} matches the authority; no token source was "
                    "supplied, so currency is unverified (reads only)"
                ),
            )
        current = token_source.current_token(self.workspace_id)
        if current > self.fencing_token:
            return Reason(
                check=CHECK_FENCING, outcome=DENY, code="FENCING_REJECTED",
                detail=(
                    f"authority token {self.fencing_token} was superseded; "
                    f"{self.workspace_id!r} is now at {current}"
                ),
            )
        return Reason(
            check=CHECK_FENCING, outcome=PASS,
            detail=f"token {self.fencing_token} is current for {self.workspace_id!r}",
        )

    def _check_tool(self, request: AuthorityRequest) -> Reason:
        if request.tool_id not in self.allowed_tools:
            return Reason(
                check=CHECK_TOOL, outcome=DENY, code="TOOL_DENIED",
                detail=(
                    f"tool {request.tool_id!r} is not in the allow-list "
                    f"{sorted(self.allowed_tools)}"
                ),
            )
        return Reason(
            check=CHECK_TOOL, outcome=PASS, detail=f"tool {request.tool_id!r} is allow-listed",
        )

    def _check_paths(self, request: AuthorityRequest) -> Reason:
        if not request.paths:
            return Reason(
                check=CHECK_PATH, outcome=NOT_APPLICABLE, detail="request touches no path",
            )
        if not self.path_scopes:
            return Reason(
                check=CHECK_PATH, outcome=DENY, code="PATH_SCOPE_DENIED",
                detail="authority grants no path scope; every path is out of scope",
            )
        scopes = self.scope_parts
        for raw in request.paths:
            try:
                parts = _normalise_path(raw)
            except _PathRejected as exc:
                return Reason(
                    check=CHECK_PATH, outcome=DENY, code="PATH_SCOPE_DENIED",
                    detail=f"path {raw!r} rejected: {exc}",
                )
            if not any(_within(scope, parts) for scope in scopes):
                return Reason(
                    check=CHECK_PATH, outcome=DENY, code="PATH_SCOPE_DENIED",
                    detail=(
                        f"path {raw!r} normalises to {_render_path(parts)!r}, which is outside "
                        f"{list(self.path_scopes)}"
                    ),
                )
        return Reason(
            check=CHECK_PATH, outcome=PASS,
            detail=f"{len(request.paths)} path(s) contained in {list(self.path_scopes)}",
        )

    def _check_network(self, request: AuthorityRequest) -> Reason:
        if not request.network_destinations:
            return Reason(
                check=CHECK_NETWORK, outcome=NOT_APPLICABLE, detail="request needs no network",
            )
        if not self.network_scopes:
            return Reason(
                check=CHECK_NETWORK, outcome=DENY, code="NETWORK_SCOPE_DENIED",
                detail="authority grants no network scope; network is denied by default",
            )
        for raw in request.network_destinations:
            try:
                endpoint = _normalise_endpoint(raw, "networkDestinations[]")
            except KernelError as exc:
                return Reason(
                    check=CHECK_NETWORK, outcome=DENY, code="NETWORK_SCOPE_DENIED",
                    detail=f"destination {raw!r} rejected: {exc.message}",
                )
            if endpoint not in self.network_scopes:
                return Reason(
                    check=CHECK_NETWORK, outcome=DENY, code="NETWORK_SCOPE_DENIED",
                    detail=(
                        f"destination {endpoint!r} is not in the explicit grants "
                        f"{list(self.network_scopes)}"
                    ),
                )
        return Reason(
            check=CHECK_NETWORK, outcome=PASS,
            detail=f"all destinations are explicitly granted: {list(self.network_scopes)}",
        )

    def _check_secrets(self, request: AuthorityRequest) -> Reason:
        if not request.secret_bindings:
            return Reason(
                check=CHECK_SECRET, outcome=NOT_APPLICABLE, detail="request needs no secret",
            )
        missing = sorted(set(request.secret_bindings) - set(self.secret_bindings))
        if missing:
            return Reason(
                check=CHECK_SECRET, outcome=DENY, code="SECRET_BINDING_DENIED",
                detail=f"secret binding ids {missing} are not bound to this authority",
            )
        return Reason(
            check=CHECK_SECRET, outcome=PASS,
            detail=f"secret binding ids {list(request.secret_bindings)} are bound",
        )

    def _check_write_fencing(self, request: AuthorityRequest,
                             token_source: TokenSource | None) -> Reason:
        if request.effect != "write":
            return Reason(
                check=CHECK_WRITE_FENCING, outcome=NOT_APPLICABLE,
                detail=f"effect {request.effect!r} performs no write",
            )
        if token_source is None:
            return Reason(
                check=CHECK_WRITE_FENCING, outcome=DENY, code="WRITE_REQUIRES_FENCING",
                detail=(
                    "no token source was supplied; an unverified fencing token is not a lease "
                    "and cannot authorise a write"
                ),
            )
        current = token_source.current_token(self.workspace_id)
        if current != self.fencing_token:
            return Reason(
                check=CHECK_WRITE_FENCING, outcome=DENY, code="WRITE_REQUIRES_FENCING",
                detail=(
                    f"write needs the current token for {self.workspace_id!r}: authority holds "
                    f"{self.fencing_token}, the lease store reports {current}"
                ),
            )
        return Reason(
            check=CHECK_WRITE_FENCING, outcome=PASS,
            detail=f"write carries current fencing token {self.fencing_token}",
        )


def _escalation(dimension: str, offending: list[str], *, detail: str = "") -> KernelError:
    suffix = f"; {detail}" if detail else ""
    return KernelError(
        code="AUTHORITY_SCOPE_MISMATCH",
        message=(
            f"derive() may only narrow: {dimension} would gain {offending}{suffix}"
        ),
        retryable=False,
        recommended_action="request a wider authority from the environment, never derive one",
        details={"dimension": dimension, "widened": offending,
                 "escalation": "SCOPE_ESCALATION_ATTEMPT"},
    )


def mint(environment: Mapping[str, Any], permission_profile: Mapping[str, Any], *,
         now: datetime, fencing_token: int) -> ExecutionAuthority:
    """Mint an authority from an environment descriptor narrowed by a permission profile.

    The environment states the ceiling; the profile may only stay under it.  A profile asking for
    a tool, path, endpoint or secret binding the environment does not grant raises
    ``SCOPE_ESCALATION_ATTEMPT`` — this is the boundary at which an injected "please also allow
    ``shell``" dies, because the profile is data and the ceiling is not.
    """

    env = require_mapping(environment, "environment")
    reject_unknown_fields(
        env,
        ("environmentId", "workspaceId", "policySnapshotHash", "subject", "ttlSeconds",
         "grantedTools", "pathScopes", "networkScopes", "secretBindings"),
        field_name="environment",
    )
    profile = require_mapping(permission_profile, "permission_profile")
    reject_unknown_fields(
        profile,
        ("permissionProfileId", "tools", "pathScopes", "networkScopes", "secretBindings",
         "ttlSeconds"),
        field_name="permission_profile",
    )

    environment_id = require_identifier(env.get("environmentId"), "environment.environmentId")
    workspace_id = require_identifier(env.get("workspaceId"), "environment.workspaceId")
    policy_hash = require_str(env.get("policySnapshotHash"), "environment.policySnapshotHash")
    subject = require_str(env.get("subject", "environment"), "environment.subject", max_length=64)
    env_ttl = require_int(env.get("ttlSeconds"), "environment.ttlSeconds", minimum=1,
                          maximum=86_400)

    granted_tools = frozenset(require_str_seq(env.get("grantedTools", ()),
                                              "environment.grantedTools"))
    granted_paths = require_str_seq(env.get("pathScopes", ()), "environment.pathScopes")
    granted_network = require_str_seq(env.get("networkScopes", ()), "environment.networkScopes")
    granted_secrets = require_str_seq(env.get("secretBindings", ()),
                                      "environment.secretBindings")

    profile_id = require_identifier(profile.get("permissionProfileId"),
                                    "permission_profile.permissionProfileId")
    profile_tools = frozenset(require_str_seq(profile.get("tools", ()),
                                              "permission_profile.tools"))
    profile_paths = require_str_seq(profile.get("pathScopes", ()),
                                    "permission_profile.pathScopes")
    profile_network = require_str_seq(profile.get("networkScopes", ()),
                                      "permission_profile.networkScopes")
    profile_secrets = require_str_seq(profile.get("secretBindings", ()),
                                      "permission_profile.secretBindings")
    profile_ttl = require_int(profile.get("ttlSeconds", env_ttl), "permission_profile.ttlSeconds",
                              minimum=1, maximum=86_400)

    ceiling = ExecutionAuthority(
        environment_id=environment_id,
        workspace_id=workspace_id,
        permission_profile_id=profile_id,
        policy_snapshot_hash=policy_hash,
        fencing_token=require_int(fencing_token, "fencing_token", minimum=1),
        allowed_tools=granted_tools,
        path_scopes=granted_paths,
        network_scopes=granted_network,
        secret_bindings=granted_secrets,
        issued_at=now,
        expires_at=now + timedelta(seconds=env_ttl),
        subject=subject,
    )

    extra_tools = sorted(profile_tools - ceiling.allowed_tools)
    if extra_tools:
        raise _profile_escalation(profile_id, "tools", extra_tools)
    ceiling_scopes = ceiling.scope_parts
    outside: list[str] = []
    for scope in profile_paths:
        try:
            parts = _normalise_path(scope)
        except _PathRejected as exc:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"permission_profile.pathScopes contains {scope!r}: {exc}",
                recommended_action="use a clean repo-relative prefix",
            ) from exc
        if not any(_within(granted, parts) for granted in ceiling_scopes):
            outside.append(_render_path(parts))
    if outside:
        raise _profile_escalation(profile_id, "pathScopes", outside)
    normalised_profile_network = tuple(
        _normalise_endpoint(endpoint, f"permission_profile.networkScopes[{index}]")
        for index, endpoint in enumerate(profile_network)
    )
    extra_network = sorted(set(normalised_profile_network) - set(ceiling.network_scopes))
    if extra_network:
        raise _profile_escalation(profile_id, "networkScopes", extra_network)
    extra_secrets = sorted(set(profile_secrets) - set(ceiling.secret_bindings))
    if extra_secrets:
        raise _profile_escalation(profile_id, "secretBindings", extra_secrets)

    return ExecutionAuthority(
        environment_id=environment_id,
        workspace_id=workspace_id,
        permission_profile_id=profile_id,
        policy_snapshot_hash=policy_hash,
        fencing_token=ceiling.fencing_token,
        allowed_tools=profile_tools,
        path_scopes=profile_paths,
        network_scopes=normalised_profile_network,
        secret_bindings=profile_secrets,
        issued_at=now,
        expires_at=now + timedelta(seconds=min(env_ttl, profile_ttl)),
        subject=subject,
    )


def _profile_escalation(profile_id: str, dimension: str, offending: list[str]) -> KernelError:
    return KernelError(
        code="SCOPE_ESCALATION_ATTEMPT",
        message=(
            f"permission profile {profile_id!r} requests {dimension} {offending} "
            "that the environment does not grant"
        ),
        retryable=False,
        recommended_action="change the environment grant, not the profile, and re-mint",
        details={"permissionProfileId": profile_id, "dimension": dimension,
                 "requested": offending},
    )


class _FrozenClock:
    """A clock pinned to one instant, so ``handle`` is a pure function of its inputs."""

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return 0


@register("execution-authority-kernel")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point: mint an authority and, if asked, decide one tool request.

    A denied tool request is a *successful* decision, not a failed skill: the outputs carry the
    denial and its trace.  Raising would throw away the reason, and the reason is the product.
    Enforcement belongs to the caller (``AuthorityDecision.raise_for_denial``).
    """

    body = require_mapping(request, "request")
    reject_unknown_fields(
        body,
        ("environment", "workspace", "permission_profile", "tool_request", "fencing_token",
         "issued_at"),
        field_name="request",
    )
    for required in ("environment", "permission_profile", "fencing_token", "issued_at"):
        if required not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{required} is required",
                recommended_action=f"supply {required}",
            )

    now = parse_timestamp(body["issued_at"], "issued_at")
    attested = require_int(body["fencing_token"], "fencing_token", minimum=1)
    authority = mint(body["environment"], body["permission_profile"], now=now,
                     fencing_token=attested)

    workspace = body.get("workspace")
    if workspace is not None:
        ws = require_mapping(workspace, "workspace")
        reject_unknown_fields(ws, ("workspaceId",), field_name="workspace")
        declared = require_identifier(ws.get("workspaceId"), "workspace.workspaceId")
        if declared != authority.workspace_id:
            raise KernelError(
                code="AUTHORITY_SCOPE_MISMATCH",
                message=(
                    f"workspace {declared!r} does not match the environment's workspace "
                    f"{authority.workspace_id!r}"
                ),
                recommended_action="mint authority in the workspace you intend to act in",
            )

    token_source = AttestedTokenSource(resource_id=authority.workspace_id, token=attested)
    decision_payload: dict[str, Any] = {"evaluated": False, "decision": None}
    if body.get("tool_request") is not None:
        tool_request = AuthorityRequest.from_mapping(
            body["tool_request"],
            default_environment_id=authority.environment_id,
            default_workspace_id=authority.workspace_id,
            default_policy_snapshot_hash=authority.policy_snapshot_hash,
        )
        decision = authority.authorize(tool_request, clock=_FrozenClock(now),
                                       token_source=token_source)
        decision_payload = {"evaluated": True, "decision": decision.to_payload()}

    snapshot = authority.snapshot()
    audit_core = {
        "type": "authority.minted",
        "environmentId": authority.environment_id,
        "workspaceId": authority.workspace_id,
        "permissionProfileId": authority.permission_profile_id,
        "policySnapshotHash": authority.policy_snapshot_hash,
        "fencingToken": authority.fencing_token,
        "subject": authority.subject,
        "authorityDigest": snapshot["digest"],
        "recordedAt": format_timestamp(now),
        "authorizationDecision": decision_payload,
    }
    audit_event = {
        **audit_core,
        "idempotencyKey": digest(audit_core),
        "digest": digest(audit_core),
    }

    return {
        "execution_authority": authority.to_payload(),
        "authority_snapshot": snapshot,
        "authorization_decision": decision_payload,
        "audit_event": audit_event,
    }
