"""Multi-agent worktree coordination: two writers never share a path in one wave.

Parallel agents are cheap to start and expensive to reconcile.  The entire value of this module is
that it decides *before* dispatch which tasks may run at the same time, and it decides it on path
claims rather than on optimism.

The one hard problem here is deciding whether two claims overlap, and there is exactly one wrong
way to do it that looks right: comparing the glob's fixed prefix as a *string*.  ``"src/ab/c.py"``
starts with ``"src/a"``, so a string-prefix check reports that ``src/a/**`` and ``src/ab/c.py``
collide and serialises two tasks that were always independent — and, worse, the same class of bug
run the other way (comparing only the first component, or only the literal head) reports that two
genuinely colliding claims are safe.  Claims are therefore normalised into *path components* and
intersected component by component, with ``**`` matching zero or more whole components and ``*``
/ ``?`` confined inside one.  ``src/a/**`` overlaps ``src/a/b.py``; it does not overlap
``src/ab/c.py``; and :func:`tests.test_worktree` proves both.

Three further refusals are deliberate:

*Overlap is decided conservatively.*  Where two wildcard segments cannot be intersected exactly
(character classes), the input is rejected rather than guessed at.  A claim language that silently
under-approximates overlap is a corrupted worktree waiting to happen.

*A wave is all-or-nothing.*  :func:`assign` acquires one lease per worktree, and if any
acquisition fails it releases everything it already took before raising.  A half-held wave leaves
leases owned by a coordinator that has already given up, and they only come back on TTL expiry.

*A task that cannot be dispatched is reported, not dropped.*  Every wave member ends up either in
``assignments`` or in ``unassigned`` with a stable code, and a wave with any unassigned member is
``PARTIAL`` — never a success with a shorter list.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from .contracts import (
    Status,
    digest,
    format_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .leasing import Lease, LeaseManager
from .registry import register

__all__ = [
    "Agent",
    "AgentContract",
    "AgentRun",
    "ArtifactContract",
    "ArtifactHandoff",
    "Assignment",
    "AssignmentResult",
    "ConflictPair",
    "MergePlan",
    "MergeVerification",
    "PathClaim",
    "Unassigned",
    "Wave",
    "WavePlan",
    "WorktreeTask",
    "CLAIM_MODES",
    "RUN_STATES",
    "assign",
    "build_merge_plan",
    "handle",
    "plan_waves",
    "validate_agent_contract",
    "verify_handoffs",
    "verify_merge",
]

register_codes(Category.CONCURRENCY, "AGENT_CONFLICT", "WORKTREE_UNAVAILABLE")
register_codes(Category.ORCHESTRATION, "AGENT_PARTIAL", "DEPENDENCY_CYCLE")
register_codes(Category.SEMANTIC, "HANDOFF_MISMATCH", "AGENT_CONTRACT_INVALID")
register_codes(Category.VERIFICATION, "MERGE_VERIFICATION_FAILED")

#: A claim is a read or a write.  Two readers never conflict; anything involving a writer does.
CLAIM_MODES = ("read", "write")

#: A run is either still in flight or settled, and the four settled states stay apart.  A
#: ``partial`` run is not a success and must not be merged.
RUN_STATES = ("running", "succeeded", "partial", "failed", "interrupted")

_SETTLED_OK = "succeeded"
_MAX_TASKS = 2048
_MAX_CLAIMS_PER_TASK = 256


# --- glob normalisation ------------------------------------------------------


def _normalise_glob(path_glob: str, field_name: str = "path_glob") -> tuple[str, ...]:
    """Split a repo-relative path glob into normalised components.

    Rejects what it cannot compare exactly: absolute paths, ``..`` traversal, backslash
    separators, character classes, and ``**`` fused into a larger segment.  Every rejection here
    is a case where guessing the intended meaning would produce an overlap answer nobody could
    audit.
    """

    text = require_str(path_glob, field_name, max_length=1024)
    if "\\" in text:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} must use '/' separators",
            recommended_action="write the claim with forward slashes",
        )
    if "[" in text or "]" in text:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"{field_name}={text!r} uses a character class; the coordinator cannot "
                "intersect character classes exactly and will not approximate an overlap check"
            ),
            recommended_action="expand the class into explicit claims",
        )
    if text.startswith("/"):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} must be repository-relative",
            recommended_action="drop the leading '/'",
        )
    components: list[str] = []
    for raw in text.split("/"):
        if raw in ("", "."):
            continue
        if raw == "..":
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{field_name}={text!r} escapes the repository root",
                recommended_action="claim paths inside the worktree only",
            )
        if "**" in raw and raw != "**":
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    f"{field_name}={text!r} fuses '**' into the segment {raw!r}; '**' matches "
                    "whole components and must stand alone"
                ),
                recommended_action="write 'a/**' rather than 'a**'",
            )
        components.append(raw)
    if not components:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message=f"{field_name} must name at least one path component",
            recommended_action="claim a concrete path or glob",
        )
    return tuple(components)


def _has_wildcard(segment: str) -> bool:
    return "*" in segment or "?" in segment


@lru_cache(maxsize=8192)
def _segments_intersect(left: str, right: str) -> bool:
    """Do two single-component globs admit at least one common concrete component?

    A dynamic program over the two patterns, where ``*`` matches any run of characters inside the
    component and ``?`` matches exactly one.  It is an *intersection* test, not a match test:
    ``*.py`` and ``*.md`` both match plenty of names and share none of them.
    """

    n, m = len(left), len(right)
    table = [[False] * (m + 1) for _ in range(n + 1)]
    table[n][m] = True
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                continue
            result = False
            if i < n and left[i] == "*":
                result = table[i + 1][j] or (j < m and table[i][j + 1])
            if not result and j < m and right[j] == "*":
                result = table[i][j + 1] or (i < n and table[i + 1][j])
            if not result and i < n and j < m:
                a, b = left[i], right[j]
                if a == "?" or b == "?" or a == b:
                    result = table[i + 1][j + 1]
            table[i][j] = result
    return table[0][0]


def _components_intersect(left: Sequence[str], right: Sequence[str]) -> bool:
    """Do two component globs admit at least one common concrete path?

    ``**`` matches zero or more whole components; everything else is matched one component at a
    time by :func:`_segments_intersect`.  Because the comparison never concatenates components,
    ``src/a`` cannot bleed into ``src/ab``.
    """

    n, m = len(left), len(right)
    table = [[False] * (m + 1) for _ in range(n + 1)]
    table[n][m] = True
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                continue
            result = False
            if i < n and left[i] == "**":
                result = table[i + 1][j] or (j < m and table[i][j + 1])
            if not result and j < m and right[j] == "**":
                result = table[i][j + 1] or (i < n and table[i + 1][j])
            if (not result and i < n and j < m
                    and left[i] != "**" and right[j] != "**"):
                result = _segments_intersect(left[i], right[j]) and table[i + 1][j + 1]
            table[i][j] = result
    return table[0][0]


def _segment_covers(scope: str, claim: str) -> bool:
    if scope == "*":
        return True
    if _has_wildcard(claim):
        # A wildcard claim is only covered by a scope that covers the whole component space.
        # Anything narrower would require proving containment of one pattern in another, and a
        # wrong answer here silently widens an agent's authority.
        return False
    if _has_wildcard(scope):
        return fnmatch.fnmatchcase(claim, scope)
    return scope == claim


def _components_cover(scope: Sequence[str], claim: Sequence[str]) -> bool:
    """Is every concrete path matched by ``claim`` also matched by ``scope``?

    Deliberately conservative: where containment cannot be decided exactly the answer is "no", so
    an under-specified agent contract denies rather than grants.
    """

    n, m = len(scope), len(claim)
    table = [[False] * (m + 1) for _ in range(n + 1)]
    table[n][m] = True
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                continue
            result = False
            if i < n and scope[i] == "**":
                result = table[i + 1][j] or (j < m and table[i][j + 1])
            if not result and i < n and j < m and scope[i] != "**":
                result = _segment_covers(scope[i], claim[j]) and table[i + 1][j + 1]
            table[i][j] = result
    return table[0][0]


# --- claims and tasks --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PathClaim:
    """One agent's declared interest in a set of paths.

    ``components`` is derived, not supplied: the normalised form is what every comparison runs
    against, so two spellings of the same claim (``./src/a/`` and ``src/a``) are one value.
    """

    path_glob: str
    mode: str = "write"
    components: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in CLAIM_MODES:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"claim mode {self.mode!r} is not one of {list(CLAIM_MODES)}",
                recommended_action="declare the claim as 'read' or 'write'",
            )
        components = _normalise_glob(self.path_glob)
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "path_glob", "/".join(components))

    @property
    def is_write(self) -> bool:
        return self.mode == "write"

    @property
    def fixed_prefix(self) -> tuple[str, ...]:
        """The leading components that contain no wildcard.

        Exposed for indexing and for tests; it is *not* what overlap is decided on, because a
        fixed prefix compared as a string is exactly the bug this module refuses to have.
        """

        prefix: list[str] = []
        for component in self.components:
            if component == "**" or _has_wildcard(component):
                break
            prefix.append(component)
        return tuple(prefix)

    def overlaps(self, other: PathClaim) -> bool:
        """True when some concrete path is matched by both claims, regardless of mode."""

        return _components_intersect(self.components, other.components)

    def conflicts_with(self, other: PathClaim) -> bool:
        """True when the two claims overlap *and* at least one of them writes.

        Two readers of one file are fine.  A reader concurrent with a writer is not: it sees a
        torn tree, which is harder to diagnose than a refusal.
        """

        return (self.is_write or other.is_write) and self.overlaps(other)

    def covered_by(self, scope: PathClaim) -> bool:
        return _components_cover(scope.components, self.components)

    def to_payload(self) -> dict[str, Any]:
        return {"pathGlob": self.path_glob, "mode": self.mode}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], field_name: str = "claim") -> PathClaim:
        body = require_mapping(payload, field_name)
        reject_unknown_fields(body, ("pathGlob", "mode"), field_name=field_name)
        return cls(
            path_glob=require_str(body.get("pathGlob"), f"{field_name}.pathGlob", max_length=1024),
            mode=require_str(body.get("mode", "write"), f"{field_name}.mode", max_length=16),
        )


@dataclass(frozen=True, slots=True)
class WorktreeTask:
    """One unit of parallel work, its write set, and what it must follow.

    ``worktree_id`` is the leased resource.  Two tasks sharing a worktree id share a lease and
    therefore cannot run concurrently even if their claims are disjoint — which is the honest
    model of a single checkout.
    """

    task_id: str
    role: str
    claims: tuple[PathClaim, ...] = ()
    depends_on: tuple[str, ...] = ()
    worktree_id: str = ""
    required_tools: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.task_id, "task_id")
        require_str(self.role, "role", max_length=64)
        if not self.claims:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"task {self.task_id!r} declares no path claims",
                recommended_action=(
                    "declare the write set; an undeclared write set cannot be checked for overlap"
                ),
            )
        if len(self.claims) > _MAX_CLAIMS_PER_TASK:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"task {self.task_id!r} declares more than {_MAX_CLAIMS_PER_TASK} claims",
                recommended_action="coarsen the claim set with a directory glob",
            )
        object.__setattr__(self, "claims",
                           tuple(sorted(set(self.claims), key=lambda c: (c.path_glob, c.mode))))
        object.__setattr__(self, "depends_on", tuple(sorted(set(self.depends_on))))
        for dependency in self.depends_on:
            require_identifier(dependency, "depends_on entry")
            if dependency == self.task_id:
                raise KernelError(
                    code="DEPENDENCY_CYCLE",
                    message=f"task {self.task_id!r} depends on itself",
                    recommended_action="remove the self-dependency",
                    details={"taskId": self.task_id},
                )
        object.__setattr__(self, "required_tools", tuple(sorted(set(self.required_tools))))
        object.__setattr__(self, "produces", tuple(sorted(set(self.produces))))
        object.__setattr__(self, "consumes", tuple(sorted(set(self.consumes))))
        object.__setattr__(self, "worktree_id",
                           require_identifier(self.worktree_id or f"wt-{self.task_id}",
                                              "worktree_id"))

    @property
    def write_claims(self) -> tuple[PathClaim, ...]:
        return tuple(claim for claim in self.claims if claim.is_write)

    def conflicting_claims(self, other: WorktreeTask) -> tuple[PathClaim, PathClaim] | None:
        """Return the first conflicting claim pair, or ``None``.

        The *pair* is returned rather than a boolean because a conflict report that cannot name
        the two globs it objected to is not reviewable.
        """

        if self.worktree_id == other.worktree_id and self.task_id != other.task_id:
            return self.claims[0], other.claims[0]
        for mine in self.claims:
            for theirs in other.claims:
                if mine.conflicts_with(theirs):
                    return mine, theirs
        return None

    def conflicts_with(self, other: WorktreeTask) -> bool:
        return self.conflicting_claims(other) is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "role": self.role,
            "worktreeId": self.worktree_id,
            "claims": [claim.to_payload() for claim in self.claims],
            "dependsOn": list(self.depends_on),
            "requiredTools": list(self.required_tools),
            "produces": list(self.produces),
            "consumes": list(self.consumes),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], index: int = 0) -> WorktreeTask:
        field_name = f"task_dag.tasks[{index}]"
        body = require_mapping(payload, field_name)
        reject_unknown_fields(
            body,
            ("taskId", "role", "worktreeId", "claims", "dependsOn", "requiredTools",
             "produces", "consumes"),
            field_name=field_name,
        )
        raw_claims = body.get("claims")
        if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes)):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{field_name}.claims must be an array",
                recommended_action="supply the write set as a JSON array of claims",
            )
        return cls(
            task_id=require_identifier(body.get("taskId"), f"{field_name}.taskId"),
            role=require_str(body.get("role"), f"{field_name}.role", max_length=64),
            claims=tuple(PathClaim.from_payload(item, f"{field_name}.claims[{n}]")
                         for n, item in enumerate(raw_claims)),
            depends_on=require_str_seq(body.get("dependsOn", ()), f"{field_name}.dependsOn"),
            worktree_id=require_str(body.get("worktreeId", "") or f"wt-{body.get('taskId')}",
                                    f"{field_name}.worktreeId", max_length=128),
            required_tools=require_str_seq(body.get("requiredTools", ()),
                                           f"{field_name}.requiredTools"),
            produces=require_str_seq(body.get("produces", ()), f"{field_name}.produces"),
            consumes=require_str_seq(body.get("consumes", ()), f"{field_name}.consumes"),
        )


@dataclass(frozen=True, slots=True)
class AgentContract:
    """The bounded authority of one sub-agent: roles, paths, tools, network, budget.

    Every field is a ceiling, and an empty collection is a *deny*, not a wildcard.  An agent with
    no declared role takes no task; an agent with no declared path scope may write nothing.  This
    is what stops a prompt from talking an agent into a wider write set than the plan gave it.
    """

    agent_id: str
    roles: tuple[str, ...] = ()
    path_scopes: tuple[PathClaim, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    network: str = "deny"
    max_turns: int = 1
    token_budget: int = 0

    def __post_init__(self) -> None:
        require_identifier(self.agent_id, "agent_id")
        require_int(self.max_turns, "max_turns", minimum=1)
        require_int(self.token_budget, "token_budget", minimum=0)
        if self.network not in ("deny", "explicit-allowlist"):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"agent {self.agent_id!r} declares network={self.network!r}",
                recommended_action="network is 'deny' or 'explicit-allowlist'",
            )
        object.__setattr__(self, "roles", tuple(sorted(set(self.roles))))
        object.__setattr__(self, "allowed_tools", tuple(sorted(set(self.allowed_tools))))
        object.__setattr__(self, "path_scopes",
                           tuple(sorted(set(self.path_scopes),
                                        key=lambda c: (c.path_glob, c.mode))))

    def covers(self, task: WorktreeTask) -> str | None:
        """Return the reason this contract does not cover ``task``, or ``None`` when it does."""

        if task.role not in self.roles:
            return f"role {task.role!r} is not in the agent's declared roles {list(self.roles)}"
        for tool in task.required_tools:
            if tool not in self.allowed_tools:
                return f"tool {tool!r} is not granted by the agent contract"
        for claim in task.claims:
            # A write claim needs a write scope; a read claim is satisfied by either.  A read
            # scope silently authorising a write is the one direction that must not be possible.
            scopes = [scope for scope in self.path_scopes
                      if scope.is_write or not claim.is_write]
            if not any(claim.covered_by(scope) for scope in scopes):
                return f"claim {claim.path_glob!r} lies outside the agent's path scopes"
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "agentId": self.agent_id,
            "roles": list(self.roles),
            "pathScopes": [scope.to_payload() for scope in self.path_scopes],
            "allowedTools": list(self.allowed_tools),
            "network": self.network,
            "maxTurns": self.max_turns,
            "tokenBudget": self.token_budget,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], index: int = 0) -> AgentContract:
        field_name = f"agent_contracts[{index}]"
        body = require_mapping(payload, field_name)
        reject_unknown_fields(
            body,
            ("agentId", "roles", "pathScopes", "allowedTools", "network", "maxTurns",
             "tokenBudget"),
            field_name=field_name,
        )
        raw_scopes = body.get("pathScopes", ())
        if not isinstance(raw_scopes, Sequence) or isinstance(raw_scopes, (str, bytes)):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{field_name}.pathScopes must be an array",
                recommended_action="supply the path scopes as a JSON array",
            )
        return cls(
            agent_id=require_identifier(body.get("agentId"), f"{field_name}.agentId"),
            roles=require_str_seq(body.get("roles", ()), f"{field_name}.roles"),
            path_scopes=tuple(PathClaim.from_payload(item, f"{field_name}.pathScopes[{n}]")
                              for n, item in enumerate(raw_scopes)),
            allowed_tools=require_str_seq(body.get("allowedTools", ()),
                                          f"{field_name}.allowedTools"),
            network=require_str(body.get("network", "deny"), f"{field_name}.network",
                                max_length=32),
            max_turns=require_int(body.get("maxTurns", 1), f"{field_name}.maxTurns", minimum=1),
            token_budget=require_int(body.get("tokenBudget", 0), f"{field_name}.tokenBudget",
                                     minimum=0),
        )


def validate_agent_contract(contract: AgentContract, task: WorktreeTask) -> None:
    """Raise ``AGENT_CONTRACT_INVALID`` unless ``contract`` authorises ``task``.

    Used by the ``agent-contract-valid`` gate.  :func:`assign` uses the softer
    :meth:`AgentContract.covers` so that a mismatched agent is skipped in favour of another,
    rather than failing the whole wave.
    """

    reason = contract.covers(task)
    if reason is not None:
        raise KernelError(
            code="AGENT_CONTRACT_INVALID",
            message=f"agent {contract.agent_id!r} may not run task {task.task_id!r}: {reason}",
            retryable=False,
            recommended_action="widen the agent contract deliberately, or re-plan the task",
            details={"agentId": contract.agent_id, "taskId": task.task_id, "reason": reason},
        )


@dataclass(frozen=True, slots=True)
class Agent:
    """A dispatchable worker slot.

    ``roles`` is required and an empty tuple means the agent takes nothing.  "No declared
    capability" resolving to "any capability" is the default-allow bug in miniature.
    """

    agent_id: str
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.agent_id, "agent_id")
        object.__setattr__(self, "roles", tuple(sorted(set(self.roles))))

    def can_take(self, role: str) -> bool:
        return role in self.roles


# --- wave planning -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConflictPair:
    """Two tasks that may not run together, and the exact claims that decided it."""

    left_task: str
    right_task: str
    left_glob: str
    right_glob: str
    reason: str
    separated: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "leftTask": self.left_task,
            "rightTask": self.right_task,
            "leftGlob": self.left_glob,
            "rightGlob": self.right_glob,
            "reason": self.reason,
            "separated": self.separated,
        }


@dataclass(frozen=True, slots=True)
class Wave:
    """A set of tasks that provably may run at the same time."""

    index: int
    tasks: tuple[WorktreeTask, ...]

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(task.task_id for task in self.tasks)

    @property
    def write_set(self) -> tuple[str, ...]:
        globs = {claim.path_glob for task in self.tasks for claim in task.write_claims}
        return tuple(sorted(globs))

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "taskIds": list(self.task_ids),
            "writeSet": list(self.write_set),
        }


@dataclass(frozen=True, slots=True)
class WavePlan:
    """The full schedule plus the conflict evidence that produced it."""

    waves: tuple[Wave, ...]
    conflicts: tuple[ConflictPair, ...]

    @property
    def task_count(self) -> int:
        return sum(len(wave.tasks) for wave in self.waves)

    def wave_of(self, task_id: str) -> int:
        for wave in self.waves:
            if task_id in wave.task_ids:
                return wave.index
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message=f"task {task_id!r} is not in this plan",
            recommended_action="plan the task before asking for its wave",
        )

    def to_payload(self) -> dict[str, Any]:
        core = {
            "waves": [wave.to_payload() for wave in self.waves],
            "conflicts": [pair.to_payload() for pair in self.conflicts],
            "taskCount": self.task_count,
            "waveCount": len(self.waves),
        }
        return {**core, "digest": digest(core)}


def plan_waves(tasks: Sequence[WorktreeTask]) -> WavePlan:
    """Group tasks into waves with no intra-wave conflict and dependencies strictly earlier.

    Ordering is by ``task_id``, never by input order: two callers holding the same task set in a
    different order must get byte-identical waves, or the plan cannot be cached, compared or
    replayed.  Packing is greedy in that order, which is not optimal and is not trying to be —
    an optimal packing that changes when an unrelated task is renamed is worse than a slightly
    wider schedule that never does.
    """

    if len(tasks) > _MAX_TASKS:
        raise KernelError(
            code="INPUT_TOO_LARGE",
            message=f"task DAG exceeds {_MAX_TASKS} tasks",
            recommended_action="split the DAG across runs",
        )
    by_id: dict[str, WorktreeTask] = {}
    for task in tasks:
        if task.task_id in by_id:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"task {task.task_id!r} is declared twice",
                recommended_action="deduplicate the task DAG",
                details={"taskId": task.task_id},
            )
        by_id[task.task_id] = task
    for task in by_id.values():
        for dependency in task.depends_on:
            if dependency not in by_id:
                raise KernelError(
                    code="MISSING_REQUIRED_INPUT",
                    message=(
                        f"task {task.task_id!r} depends on {dependency!r}, which is not in "
                        "the DAG"
                    ),
                    recommended_action="include the dependency or drop the edge",
                    details={"taskId": task.task_id, "dependsOn": dependency},
                )

    placed: dict[str, int] = {}
    remaining = sorted(by_id)
    waves: list[Wave] = []
    index = 0
    while remaining:
        wave_members: list[WorktreeTask] = []
        for task_id in remaining:
            task = by_id[task_id]
            if any(dependency not in placed for dependency in task.depends_on):
                continue
            if any(task.conflicts_with(member) for member in wave_members):
                continue
            wave_members.append(task)
        if not wave_members:
            stuck = sorted(remaining)
            raise KernelError(
                code="DEPENDENCY_CYCLE",
                message=f"tasks {stuck} form a dependency cycle and can never be scheduled",
                retryable=False,
                recommended_action="break the cycle in the task DAG",
                details={"tasks": stuck},
            )
        for member in wave_members:
            placed[member.task_id] = index
        waves.append(Wave(index=index, tasks=tuple(wave_members)))
        chosen = {member.task_id for member in wave_members}
        remaining = [task_id for task_id in remaining if task_id not in chosen]
        index += 1

    conflicts: list[ConflictPair] = []
    ordered = sorted(by_id)
    for position, left_id in enumerate(ordered):
        for right_id in ordered[position + 1:]:
            pair = by_id[left_id].conflicting_claims(by_id[right_id])
            if pair is None:
                continue
            left_claim, right_claim = pair
            conflicts.append(ConflictPair(
                left_task=left_id,
                right_task=right_id,
                left_glob=left_claim.path_glob,
                right_glob=right_claim.path_glob,
                reason=(
                    "shared worktree"
                    if by_id[left_id].worktree_id == by_id[right_id].worktree_id
                    else "overlapping write claim"
                ),
                separated=placed[left_id] != placed[right_id],
            ))
    return WavePlan(waves=tuple(waves), conflicts=tuple(conflicts))


# --- assignment --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentRun:
    """The state of one dispatched task, carried forward between waves.

    The claims travel with the run because an earlier wave's *still running* task keeps its paths
    reserved.  Waves bound what may start together; they say nothing about what has finished.
    """

    task_id: str
    agent_id: str
    worktree_id: str
    wave_index: int
    state: str
    fencing_token: int
    claims: tuple[PathClaim, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.task_id, "task_id")
        require_identifier(self.agent_id, "agent_id")
        require_identifier(self.worktree_id, "worktree_id")
        require_int(self.wave_index, "wave_index", minimum=0)
        require_int(self.fencing_token, "fencing_token", minimum=1)
        if self.state not in RUN_STATES:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"run state {self.state!r} is not one of {list(RUN_STATES)}",
                recommended_action="report a state from the declared vocabulary",
            )

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def succeeded(self) -> bool:
        """True only for ``succeeded``; ``partial`` and ``interrupted`` are not successes."""

        return self.state == _SETTLED_OK

    def to_payload(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "agentId": self.agent_id,
            "worktreeId": self.worktree_id,
            "waveIndex": self.wave_index,
            "state": self.state,
            "fencingToken": self.fencing_token,
            "claims": [claim.to_payload() for claim in self.claims],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], index: int = 0) -> AgentRun:
        field_name = f"agent_runs[{index}]"
        body = require_mapping(payload, field_name)
        reject_unknown_fields(
            body,
            ("taskId", "agentId", "worktreeId", "waveIndex", "state", "fencingToken", "claims"),
            field_name=field_name,
        )
        raw_claims = body.get("claims", ())
        if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes)):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{field_name}.claims must be an array",
                recommended_action="supply the run's claims as a JSON array",
            )
        return cls(
            task_id=require_identifier(body.get("taskId"), f"{field_name}.taskId"),
            agent_id=require_identifier(body.get("agentId"), f"{field_name}.agentId"),
            worktree_id=require_identifier(body.get("worktreeId"), f"{field_name}.worktreeId"),
            wave_index=require_int(body.get("waveIndex"), f"{field_name}.waveIndex", minimum=0),
            state=require_str(body.get("state"), f"{field_name}.state", max_length=32),
            fencing_token=require_int(body.get("fencingToken"), f"{field_name}.fencingToken",
                                      minimum=1),
            claims=tuple(PathClaim.from_payload(item, f"{field_name}.claims[{n}]")
                         for n, item in enumerate(raw_claims)),
        )


@dataclass(frozen=True, slots=True)
class Assignment:
    """One task bound to one agent, one worktree and one fencing token."""

    task_id: str
    agent_id: str
    worktree_id: str
    wave_index: int
    fencing_token: int
    lease_expires_at: datetime
    claims: tuple[PathClaim, ...]

    def to_payload(self) -> dict[str, Any]:
        core = {
            "taskId": self.task_id,
            "agentId": self.agent_id,
            "worktreeId": self.worktree_id,
            "waveIndex": self.wave_index,
            "fencingToken": self.fencing_token,
            "leaseExpiresAt": format_timestamp(self.lease_expires_at),
            "claims": [claim.to_payload() for claim in self.claims],
        }
        return {**core, "digest": digest(core)}

    def to_run(self, state: str = "running") -> AgentRun:
        return AgentRun(
            task_id=self.task_id, agent_id=self.agent_id, worktree_id=self.worktree_id,
            wave_index=self.wave_index, state=state, fencing_token=self.fencing_token,
            claims=self.claims,
        )


@dataclass(frozen=True, slots=True)
class Unassigned:
    """A wave member that was not dispatched, and why.

    This type exists so that "we ran four of five tasks" can never be rendered as "we ran the
    wave".  Every member of the wave appears in exactly one of the two output lists.
    """

    task_id: str
    code: str
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {"taskId": self.task_id, "code": self.code, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class AssignmentResult:
    """The outcome of dispatching one wave."""

    wave_index: int
    assignments: tuple[Assignment, ...]
    unassigned: tuple[Unassigned, ...]

    @property
    def status(self) -> Status:
        """``PARTIAL`` whenever any wave member was not dispatched."""

        return Status.PARTIAL if self.unassigned else Status.SUCCEEDED

    def to_payload(self) -> dict[str, Any]:
        core = {
            "waveIndex": self.wave_index,
            "assignments": [item.to_payload() for item in self.assignments],
            "unassigned": [item.to_payload() for item in self.unassigned],
            "status": str(self.status),
            "assignedCount": len(self.assignments),
            "unassignedCount": len(self.unassigned),
            "measured": True,
        }
        return {**core, "digest": digest(core)}


def assign(wave: Wave, agents: Sequence[Agent], lease_manager: LeaseManager, *,
           running: Sequence[AgentRun] = (), ttl_seconds: int = 900,
           contracts: Mapping[str, AgentContract] | None = None,
           max_parallel: int | None = None) -> AssignmentResult:
    """Bind a wave's tasks to agents, taking exactly one lease per worktree.

    Three refusals, in the order they are checked:

    * A task whose claims collide with a task from an earlier wave that is *still running* is not
      dispatched.  Wave membership only says the tasks could start together; it says nothing
      about what has actually finished, and dispatching on the plan alone is how two writers meet.
    * A task no available agent's contract authorises is not dispatched.
    * If any lease acquisition fails, every lease already taken for this wave is released before
      the error propagates.  A half-held wave strands leases on a coordinator that has given up.

    Everything not dispatched is reported in ``unassigned`` with a stable code, and the result is
    then ``PARTIAL``.
    """

    require_int(ttl_seconds, "ttl_seconds", minimum=1)
    if max_parallel is not None:
        require_int(max_parallel, "max_parallel", minimum=1)
    blocking = tuple(run for run in running if run.is_running)
    pool = sorted(agents, key=lambda agent: agent.agent_id)
    taken: set[str] = set()
    assignments: list[Assignment] = []
    unassigned: list[Unassigned] = []
    acquired: list[Lease] = []

    try:
        for task in wave.tasks:
            blocker = _blocked_by(task, blocking)
            if blocker is not None:
                run, mine, theirs = blocker
                unassigned.append(Unassigned(
                    task_id=task.task_id,
                    code="AGENT_CONFLICT",
                    reason=(
                        f"claim {mine.path_glob!r} overlaps {theirs.path_glob!r}, still held by "
                        f"running task {run.task_id!r} from wave {run.wave_index}"
                    ),
                ))
                continue
            if max_parallel is not None and len(assignments) >= max_parallel:
                unassigned.append(Unassigned(
                    task_id=task.task_id,
                    code="BUDGET_EXHAUSTED",
                    reason=f"the wave is capped at {max_parallel} concurrent agents",
                ))
                continue
            agent, refusal = _pick_agent(task, pool, taken, contracts)
            if agent is None:
                unassigned.append(Unassigned(
                    task_id=task.task_id,
                    code="WORKTREE_UNAVAILABLE" if refusal.startswith("no free") else
                         "AGENT_CONTRACT_INVALID",
                    reason=refusal,
                ))
                continue
            lease = lease_manager.acquire(task.worktree_id, agent.agent_id,
                                          ttl_seconds=ttl_seconds)
            acquired.append(lease)
            taken.add(agent.agent_id)
            assignments.append(Assignment(
                task_id=task.task_id,
                agent_id=agent.agent_id,
                worktree_id=task.worktree_id,
                wave_index=wave.index,
                fencing_token=lease.fencing_token,
                lease_expires_at=lease.expires_at,
                claims=task.claims,
            ))
    except KernelError as exc:
        for lease in reversed(acquired):
            try:
                lease_manager.release(lease)
            except KernelError:  # noqa: PERF203 - rollback must not mask the first failure
                continue
        raise KernelError(
            code="AGENT_CONFLICT",
            message=(
                f"wave {wave.index} could not be fully leased ({exc.code}: {exc.message}); "
                f"{len(acquired)} lease(s) taken for it were released"
            ),
            retryable=True,
            recommended_action="re-plan the wave once the conflicting worktree is free",
            details={"waveIndex": wave.index, "releasedLeases": len(acquired),
                     "cause": exc.code},
        ) from exc

    return AssignmentResult(wave_index=wave.index, assignments=tuple(assignments),
                            unassigned=tuple(unassigned))


def _blocked_by(task: WorktreeTask,
                blocking: Sequence[AgentRun]) -> tuple[AgentRun, PathClaim, PathClaim] | None:
    for run in blocking:
        if run.task_id == task.task_id:
            continue
        if run.worktree_id == task.worktree_id:
            return run, task.claims[0], (run.claims[0] if run.claims else task.claims[0])
        for mine in task.claims:
            for theirs in run.claims:
                if mine.conflicts_with(theirs):
                    return run, mine, theirs
    return None


def _pick_agent(task: WorktreeTask, pool: Sequence[Agent], taken: set[str],
                contracts: Mapping[str, AgentContract] | None) -> tuple[Agent | None, str]:
    free = [agent for agent in pool if agent.agent_id not in taken]
    by_role = [agent for agent in free if agent.can_take(task.role)]
    if not by_role:
        return None, f"no free agent declares the role {task.role!r}"
    if contracts is None:
        return by_role[0], ""
    refusals: list[str] = []
    for agent in by_role:
        contract = contracts.get(agent.agent_id)
        if contract is None:
            refusals.append(f"{agent.agent_id}: no agent contract on file")
            continue
        reason = contract.covers(task)
        if reason is None:
            return agent, ""
        refusals.append(f"{agent.agent_id}: {reason}")
    return None, "; ".join(refusals)


# --- handoffs and merge ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArtifactContract:
    """The declared shape of one handoff artifact."""

    artifact_id: str
    schema_id: str

    def __post_init__(self) -> None:
        require_identifier(self.artifact_id, "artifact_id")
        require_identifier(self.schema_id, "schema_id")

    def to_payload(self) -> dict[str, Any]:
        return {"artifactId": self.artifact_id, "schemaId": self.schema_id}


@dataclass(frozen=True, slots=True)
class ArtifactHandoff:
    """One producer-to-consumer artifact transfer with its claimed content digest."""

    artifact_id: str
    producer_task_id: str
    consumer_task_id: str
    schema_id: str
    content_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.artifact_id, "artifact_id")
        require_identifier(self.producer_task_id, "producer_task_id")
        require_identifier(self.consumer_task_id, "consumer_task_id")
        require_identifier(self.schema_id, "schema_id")
        require_str(self.content_digest, "content_digest", max_length=256)

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "producerTaskId": self.producer_task_id,
            "consumerTaskId": self.consumer_task_id,
            "schemaId": self.schema_id,
            "contentDigest": self.content_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], index: int = 0) -> ArtifactHandoff:
        field_name = f"artifact_handoffs[{index}]"
        body = require_mapping(payload, field_name)
        reject_unknown_fields(
            body,
            ("artifactId", "producerTaskId", "consumerTaskId", "schemaId", "contentDigest"),
            field_name=field_name,
        )
        return cls(
            artifact_id=require_identifier(body.get("artifactId"), f"{field_name}.artifactId"),
            producer_task_id=require_identifier(body.get("producerTaskId"),
                                                f"{field_name}.producerTaskId"),
            consumer_task_id=require_identifier(body.get("consumerTaskId"),
                                                f"{field_name}.consumerTaskId"),
            schema_id=require_identifier(body.get("schemaId"), f"{field_name}.schemaId"),
            content_digest=require_str(body.get("contentDigest"), f"{field_name}.contentDigest",
                                       max_length=256),
        )


def verify_handoffs(handoffs: Sequence[ArtifactHandoff],
                    contracts: Mapping[str, ArtifactContract],
                    produced: Mapping[str, str]) -> tuple[Mapping[str, Any], ...]:
    """Check every handoff against its contract and the digest actually produced.

    An artifact with no contract is a mismatch, not a pass: accepting an undeclared handoff is
    how a sub-agent's free-text output becomes an input to a merge.  A digest that does not match
    what the producer actually wrote is a mismatch even when the schema is right — that is the
    case where the consumer reads a *different, plausible* artifact.
    """

    verified: list[Mapping[str, Any]] = []
    for handoff in handoffs:
        contract = contracts.get(handoff.artifact_id)
        if contract is None:
            raise KernelError(
                code="HANDOFF_MISMATCH",
                message=f"artifact {handoff.artifact_id!r} has no declared artifact contract",
                retryable=False,
                recommended_action="declare the artifact contract or drop the handoff",
                details={"artifactId": handoff.artifact_id},
            )
        if contract.schema_id != handoff.schema_id:
            raise KernelError(
                code="HANDOFF_MISMATCH",
                message=(
                    f"artifact {handoff.artifact_id!r} was handed off as schema "
                    f"{handoff.schema_id!r} but is contracted as {contract.schema_id!r}"
                ),
                retryable=False,
                recommended_action="re-produce the artifact against the contracted schema",
                details={"artifactId": handoff.artifact_id,
                         "declared": handoff.schema_id, "contracted": contract.schema_id},
            )
        actual = produced.get(handoff.artifact_id)
        if actual is None:
            raise KernelError(
                code="HANDOFF_MISMATCH",
                message=(
                    f"artifact {handoff.artifact_id!r} is consumed by "
                    f"{handoff.consumer_task_id!r} but was never produced"
                ),
                retryable=False,
                recommended_action="run the producer before the consumer",
                details={"artifactId": handoff.artifact_id},
            )
        if actual != handoff.content_digest:
            raise KernelError(
                code="HANDOFF_MISMATCH",
                message=(
                    f"artifact {handoff.artifact_id!r} hands off {handoff.content_digest} but "
                    f"the producer wrote {actual}"
                ),
                retryable=False,
                recommended_action="do not consume the artifact; re-run the producer",
                details={"artifactId": handoff.artifact_id, "declared": handoff.content_digest,
                         "actual": actual},
            )
        verified.append({**handoff.to_payload(), "verified": True})
    return tuple(verified)


@dataclass(frozen=True, slots=True)
class MergePlan:
    """The order in which finished worktrees fold back into the integration branch."""

    order: tuple[str, ...]
    wave_of: Mapping[str, int]
    write_sets: Mapping[str, tuple[str, ...]]

    def to_payload(self) -> dict[str, Any]:
        core = {
            "order": list(self.order),
            "waveOf": {task_id: self.wave_of[task_id] for task_id in sorted(self.wave_of)},
            "writeSets": {task_id: list(self.write_sets[task_id])
                          for task_id in sorted(self.write_sets)},
        }
        return {**core, "digest": digest(core)}


def build_merge_plan(plan: WavePlan) -> MergePlan:
    """Merge order follows wave order, and within a wave, task id order."""

    order: list[str] = []
    wave_of: dict[str, int] = {}
    write_sets: dict[str, tuple[str, ...]] = {}
    for wave in plan.waves:
        for task in wave.tasks:
            order.append(task.task_id)
            wave_of[task.task_id] = wave.index
            write_sets[task.task_id] = tuple(claim.path_glob for claim in task.write_claims)
    return MergePlan(order=tuple(order), wave_of=wave_of, write_sets=write_sets)


@dataclass(frozen=True, slots=True)
class MergeVerification:
    """Whether the integration merge may proceed, and what blocks it."""

    merged: tuple[str, ...]
    blocked: tuple[Mapping[str, Any], ...]

    @property
    def passed(self) -> bool:
        return not self.blocked

    def to_payload(self) -> dict[str, Any]:
        core = {
            "merged": list(self.merged),
            "blocked": [dict(item) for item in self.blocked],
            "passed": self.passed,
        }
        return {**core, "digest": digest(core)}


def verify_merge(plan: MergePlan, runs: Sequence[AgentRun], *,
                 handoffs_verified: bool = True) -> MergeVerification:
    """Admit to the merge only tasks whose runs actually succeeded.

    ``partial``, ``interrupted`` and ``failed`` all block, separately and by name.  A partial
    sub-agent result folded into an integration branch is the quietest way this system can ship
    half a change: the tree builds, the tests pass, and a third of the intended edit is missing.
    """

    by_task = {run.task_id: run for run in runs}
    merged: list[str] = []
    blocked: list[Mapping[str, Any]] = []
    for task_id in plan.order:
        run = by_task.get(task_id)
        if run is None:
            blocked.append({"taskId": task_id, "code": "AGENT_PARTIAL",
                            "reason": "no run was recorded for this task"})
            continue
        if run.succeeded:
            merged.append(task_id)
            continue
        blocked.append({
            "taskId": task_id,
            "code": "AGENT_PARTIAL" if run.state in ("partial", "interrupted")
                    else "MERGE_VERIFICATION_FAILED",
            "reason": f"run state is {run.state!r}, which is not 'succeeded'",
        })
    if not handoffs_verified:
        blocked.append({"taskId": "*", "code": "HANDOFF_MISMATCH",
                        "reason": "artifact handoffs were not verified before the merge"})
    return MergeVerification(merged=tuple(merged), blocked=tuple(blocked))


def assert_merge_passed(verification: MergeVerification) -> None:
    """Raise ``MERGE_VERIFICATION_FAILED`` unless every planned task may merge."""

    if not verification.passed:
        raise KernelError(
            code="MERGE_VERIFICATION_FAILED",
            message=(
                f"{len(verification.blocked)} task(s) may not merge: "
                f"{[item['taskId'] for item in verification.blocked]}"
            ),
            retryable=False,
            partial=bool(verification.merged),
            recommended_action="repair or re-run the blocked tasks before integrating",
            details={"blocked": [dict(item) for item in verification.blocked]},
        )


# --- registry entry point ----------------------------------------------------


def _require_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be an array",
            recommended_action=f"supply {field_name} as a JSON array",
        )
    return value


@register("multi-agent-worktree-coordinator")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Like :mod:`.leasing`, this handler takes live ports: a coordinator that invents its own
    in-memory lease store would hand out worktrees it does not actually own.  It plans every wave
    but dispatches only the first — a single step assigns a single wave, and the caller records
    the resulting runs before asking for the next one.
    """

    body = require_mapping(request, "request")
    reject_unknown_fields(
        body,
        ("task_dag", "agent_contracts", "workspace_topology", "budget", "artifact_contracts",
         "agent_runs", "artifact_handoffs", "produced_artifacts", "ports"),
        field_name="request",
    )
    for required in ("task_dag", "agent_contracts", "workspace_topology", "ports"):
        if required not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{required} is required",
                recommended_action=f"supply {required}",
            )

    ports = require_mapping(body["ports"], "ports")
    reject_unknown_fields(ports, ("lease_store", "clock", "event_store"), field_name="ports")
    lease_store = ports.get("lease_store")
    clock = ports.get("clock")
    if lease_store is None or clock is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="ports.lease_store and ports.clock are required to lease a worktree",
            recommended_action="inject a LeaseStore and a Clock adapter",
        )

    dag = require_mapping(body["task_dag"], "task_dag")
    reject_unknown_fields(dag, ("tasks", "snapshotSha"), field_name="task_dag")
    tasks = tuple(WorktreeTask.from_payload(item, index)
                  for index, item in enumerate(_require_sequence(dag.get("tasks"),
                                                                 "task_dag.tasks")))
    if not tasks:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="task_dag.tasks must not be empty",
            recommended_action="supply at least one task",
        )

    topology = require_mapping(body["workspace_topology"], "workspace_topology")
    reject_unknown_fields(topology, ("leaseTtlSeconds", "agents", "snapshotSha"),
                          field_name="workspace_topology")
    declared_snapshot = topology.get("snapshotSha")
    dag_snapshot = dag.get("snapshotSha")
    if declared_snapshot is not None and dag_snapshot is not None \
            and declared_snapshot != dag_snapshot:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"the task DAG was compiled against {dag_snapshot!r} but the workspace is at "
                f"{declared_snapshot!r}"
            ),
            retryable=False,
            recommended_action="re-plan the DAG against the current snapshot",
            details={"dagSnapshot": dag_snapshot, "workspaceSnapshot": declared_snapshot},
        )
    ttl_seconds = require_int(topology.get("leaseTtlSeconds", 900),
                              "workspace_topology.leaseTtlSeconds", minimum=1, maximum=86_400)
    agents = tuple(
        Agent(agent_id=require_identifier(require_mapping(item, "agent").get("agentId"),
                                          "agent.agentId"),
              roles=require_str_seq(require_mapping(item, "agent").get("roles", ()),
                                    "agent.roles"))
        for item in _require_sequence(topology.get("agents", ()), "workspace_topology.agents")
    )

    contracts = {
        contract.agent_id: contract
        for contract in (AgentContract.from_payload(item, index) for index, item
                         in enumerate(_require_sequence(body["agent_contracts"],
                                                        "agent_contracts")))
    }

    budget = require_mapping(body.get("budget") or {}, "budget")
    reject_unknown_fields(budget, ("maxParallelAgents",), field_name="budget")
    raw_parallel = budget.get("maxParallelAgents")
    max_parallel = (None if raw_parallel is None
                    else require_int(raw_parallel, "budget.maxParallelAgents", minimum=1))

    artifact_contracts = {
        contract.artifact_id: contract
        for contract in (
            ArtifactContract(
                artifact_id=require_identifier(require_mapping(item, "artifact_contract")
                                               .get("artifactId"), "artifact_contract.artifactId"),
                schema_id=require_identifier(require_mapping(item, "artifact_contract")
                                             .get("schemaId"), "artifact_contract.schemaId"),
            )
            for item in _require_sequence(body.get("artifact_contracts") or (),
                                          "artifact_contracts")
        )
    }
    handoffs = tuple(
        ArtifactHandoff.from_payload(item, index)
        for index, item in enumerate(_require_sequence(body.get("artifact_handoffs") or (),
                                                       "artifact_handoffs"))
    )
    produced = {
        require_identifier(key, "produced_artifacts key"): require_str(value,
                                                                       "produced_artifacts value",
                                                                       max_length=256)
        for key, value in require_mapping(body.get("produced_artifacts") or {},
                                          "produced_artifacts").items()
    }
    prior_runs = tuple(
        AgentRun.from_payload(item, index)
        for index, item in enumerate(_require_sequence(body.get("agent_runs") or (),
                                                       "agent_runs"))
    )

    plan = plan_waves(tasks)
    manager = LeaseManager(lease_store, clock, events=ports.get("event_store"))
    result = assign(plan.waves[0], agents, manager, running=prior_runs,
                    ttl_seconds=ttl_seconds, contracts=contracts, max_parallel=max_parallel)
    verified = verify_handoffs(handoffs, artifact_contracts, produced)
    merge_plan = build_merge_plan(plan)
    runs = prior_runs + tuple(item.to_run() for item in result.assignments)
    merge = verify_merge(merge_plan, runs, handoffs_verified=True)

    return {
        "status": result.status,
        "wave_plan": plan.to_payload(),
        "agent_assignments": result.to_payload(),
        "agent_runs": [run.to_payload() for run in runs],
        "artifact_handoffs": [dict(item) for item in verified],
        "conflict_report": [pair.to_payload() for pair in plan.conflicts],
        "merge_plan": {**merge_plan.to_payload(), "verification": merge.to_payload()},
    }
