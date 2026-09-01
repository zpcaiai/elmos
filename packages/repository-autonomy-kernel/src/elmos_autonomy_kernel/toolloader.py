"""Lazy tool loader: discovery is not authorization, and deferred is not available.

Loading every tool a catalogue offers costs context, widens the attack surface
and — worst of the three — makes the model choose between near-duplicates it
should never have seen.  This module decides which tools are worth their tokens
*before* the run starts, and it does so with an ordering that can be written
down: capability match first, then usage prior, then cost, then tool id.  The
final key exists so that two kernels with the same catalogue in a different dict
order produce the same plan; ranking that ends in "whatever came first" is not a
decision, it is a coincidence.

Two refusals matter more than the ranking.  A deferred tool is not callable:
``resolve`` raises ``TOOL_NOT_LOADED`` and says how to load it, rather than
quietly loading it and blowing the budget mid-run.  And the budget is hard —
running past it raises ``BUDGET_EXHAUSTED`` instead of trimming the plan, because
a silently trimmed plan is a capability that vanished without anyone deciding it
should.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .contracts import (
    digest,
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
    Category.SEMANTIC,
    "TOOL_NOT_LOADED",
    "TOOL_DISCOVERY_FAILED",
    "SCHEMA_LOAD_FAILED",
)
register_codes(Category.AUTHORITY, "TOOL_NOT_AUTHORIZED")
register_codes(Category.PROVIDER, "REMOTE_TOOL_UNAVAILABLE")

__all__ = [
    "CatalogueEntry",
    "TaskProfile",
    "LoadDecision",
    "LoadPlan",
    "ToolLoader",
    "StaticConnector",
    "MAX_USAGE_PRIOR",
    "handle",
]

#: Usage priors are per-mille integers.  A float prior would be one more thing
#: that hashes differently on two machines, and the ordering it feeds is
#: persisted in the load plan.
MAX_USAGE_PRIOR = 1000

_MAX_CATALOGUE = 1024


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    """One discoverable tool and what it costs to have it in context.

    ``schema`` is held here but is only published through a loaded tool: that is
    the "schema on demand" property — metadata is cheap and always available,
    the full schema is paid for when the tool is actually loaded.
    """

    tool_id: str
    version: str
    capabilities: tuple[str, ...]
    token_cost: int
    usage_prior: int = 0
    remote: bool = False
    schema: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_identifier(self.tool_id, "tool_id")
        require_str(self.version, "version", max_length=64)
        require_int(self.token_cost, "token_cost", minimum=0)
        require_int(self.usage_prior, "usage_prior", minimum=0, maximum=MAX_USAGE_PRIOR)
        require_bool(self.remote, "remote")
        require_mapping(self.schema, "schema")
        object.__setattr__(self, "capabilities", tuple(sorted(set(self.capabilities))))
        for capability in self.capabilities:
            require_str(capability, "capability", max_length=128)

    def matches(self, required: frozenset[str]) -> int:
        return len(required.intersection(self.capabilities))

    def to_payload(self) -> dict[str, Any]:
        return {
            "toolId": self.tool_id,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "tokenCost": self.token_cost,
            "usagePrior": self.usage_prior,
            "remote": self.remote,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CatalogueEntry:
        payload = require_mapping(payload, "catalogue entry")
        known = {"toolId", "version", "capabilities", "tokenCost", "usagePrior",
                 "remote", "schema"}
        reject_unknown_fields(payload, known, field_name="catalogue entry")
        return cls(
            tool_id=require_identifier(payload.get("toolId"), "catalogue entry.toolId"),
            version=require_str(payload.get("version", "1.0.0"), "catalogue entry.version",
                                max_length=64),
            capabilities=require_str_seq(payload.get("capabilities", ()),
                                         "catalogue entry.capabilities"),
            token_cost=require_int(payload.get("tokenCost"), "catalogue entry.tokenCost",
                                   minimum=0),
            usage_prior=require_int(payload.get("usagePrior", 0),
                                    "catalogue entry.usagePrior", minimum=0,
                                    maximum=MAX_USAGE_PRIOR),
            remote=require_bool(payload.get("remote", False), "catalogue entry.remote"),
            schema=require_mapping(payload.get("schema", {}), "catalogue entry.schema"),
        )


@dataclass(frozen=True, slots=True)
class TaskProfile:
    """What the step needs and what it may spend."""

    required_capabilities: tuple[str, ...]
    token_budget: int
    max_tools: int | None = None

    def __post_init__(self) -> None:
        require_int(self.token_budget, "token_budget", minimum=0)
        if self.max_tools is not None:
            require_int(self.max_tools, "max_tools", minimum=1)
        object.__setattr__(self, "required_capabilities",
                           tuple(sorted(set(self.required_capabilities))))
        for capability in self.required_capabilities:
            require_str(capability, "required capability", max_length=128)

    @property
    def required(self) -> frozenset[str]:
        return frozenset(self.required_capabilities)

    def to_payload(self) -> dict[str, Any]:
        return {
            "requiredCapabilities": list(self.required_capabilities),
            "tokenBudget": self.token_budget,
            "maxTools": self.max_tools,
        }


@dataclass(frozen=True, slots=True)
class LoadDecision:
    """Why one tool is loaded, deferred or denied.

    ``score`` is carried verbatim so that a reviewer can re-sort the catalogue by
    hand and reach the same plan.  An unexplainable selection is indistinguishable
    from a biased one.
    """

    tool_id: str
    state: str  # LOADED | DEFERRED | DENIED
    reason: str
    capability_matches: int
    usage_prior: int
    token_cost: int
    rank: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "toolId": self.tool_id,
            "state": self.state,
            "reason": self.reason,
            "capabilityMatches": self.capability_matches,
            "usagePrior": self.usage_prior,
            "tokenCost": self.token_cost,
            "rank": self.rank,
            "score": [-self.capability_matches, -self.usage_prior, self.token_cost,
                      self.tool_id],
        }


@dataclass(frozen=True, slots=True)
class LoadPlan:
    """The decision record for one step's tool set."""

    loaded: tuple[str, ...]
    deferred: tuple[str, ...]
    denied: tuple[str, ...]
    decisions: tuple[LoadDecision, ...]
    tokens_loaded: int
    token_budget: int

    @property
    def tokens_remaining(self) -> int:
        return self.token_budget - self.tokens_loaded

    def to_payload(self) -> dict[str, Any]:
        return {
            "loaded": list(self.loaded),
            "deferred": list(self.deferred),
            "denied": list(self.denied),
            "decisions": [item.to_payload() for item in self.decisions],
            "tokensLoaded": self.tokens_loaded,
            "tokenBudget": self.token_budget,
            "tokensRemaining": self.tokens_remaining,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


class StaticConnector:
    """A remote-tool connector backed by an in-process map.

    A remote tool that cannot be connected is unavailable, full stop — the
    loader never falls back to a cached or assumed schema, because acting on a
    stale ABI is worse than not acting.
    """

    __slots__ = ("_schemas",)

    def __init__(self, schemas: Mapping[str, Mapping[str, Any]]) -> None:
        self._schemas = dict(schemas)

    def connect(self, tool_id: str) -> Mapping[str, Any]:
        if tool_id not in self._schemas:
            raise KernelError(
                code="REMOTE_TOOL_UNAVAILABLE",
                message=f"remote tool {tool_id!r} did not answer",
                retryable=True,
                recommended_action="retry the connection or drop the tool from the plan",
                details={"toolId": tool_id},
            )
        return self._schemas[tool_id]


def _sort_key(entry: CatalogueEntry, required: frozenset[str]) -> tuple[int, int, int, str]:
    """Capability match, then usage prior, then cost, then id.

    Every component is an integer or a string; nothing here can differ between
    two runs of the same inputs.
    """

    return (-entry.matches(required), -entry.usage_prior, entry.token_cost, entry.tool_id)


class ToolLoader:
    """Plans, loads and resolves tools against a frozen authority snapshot.

    The authority's allowed-tool set is copied at construction.  A later change
    to the authority object cannot retroactively widen a plan that has already
    been made, which is the "dynamic loading does not alter a frozen authority"
    invariant expressed as a data structure rather than as a rule.
    """

    __slots__ = ("_entries", "_profile", "_allowed", "_connector", "_loaded", "_plan",
                 "_tokens")

    def __init__(self, catalogue: Sequence[CatalogueEntry], profile: TaskProfile,
                 authority: Any, *, connector: Any = None) -> None:
        if len(catalogue) > _MAX_CATALOGUE:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"catalogue exceeds {_MAX_CATALOGUE} entries",
                recommended_action="pre-filter the catalogue by phase",
            )
        entries: dict[str, CatalogueEntry] = {}
        for entry in catalogue:
            if entry.tool_id in entries:
                raise KernelError(
                    code="TOOL_DISCOVERY_FAILED",
                    message=f"catalogue lists {entry.tool_id!r} twice",
                    recommended_action="deduplicate the catalogue before planning",
                    details={"toolId": entry.tool_id},
                )
            entries[entry.tool_id] = entry
        self._entries = dict(sorted(entries.items()))
        self._profile = profile
        self._allowed = _frozen_allowed(authority)
        self._connector = connector
        self._loaded: dict[str, Mapping[str, Any]] = {}
        self._tokens = 0
        self._plan: LoadPlan | None = None

    @property
    def allowed_tools(self) -> frozenset[str]:
        """The authority snapshot taken at construction time."""

        return self._allowed

    @property
    def tokens_loaded(self) -> int:
        return self._tokens

    @property
    def loaded_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._loaded))

    def plan(self) -> LoadPlan:
        """Decide the eager set.  Idempotent: re-planning returns the same plan."""

        if self._plan is not None:
            return self._plan

        required = self._profile.required
        ranked = sorted(self._entries.values(),
                        key=lambda entry: _sort_key(entry, required))
        ranks = {entry.tool_id: index for index, entry in enumerate(ranked)}

        decisions: dict[str, LoadDecision] = {}
        denied: list[str] = []
        candidates: list[CatalogueEntry] = []
        for entry in ranked:
            if entry.tool_id not in self._allowed:
                denied.append(entry.tool_id)
                decisions[entry.tool_id] = LoadDecision(
                    tool_id=entry.tool_id, state="DENIED",
                    reason="not granted by the execution authority",
                    capability_matches=entry.matches(required),
                    usage_prior=entry.usage_prior, token_cost=entry.token_cost,
                    rank=ranks[entry.tool_id])
                continue
            candidates.append(entry)

        selected: list[str] = []
        covered: set[str] = set()
        spent = 0

        # Phase A — mandatory coverage.  A required capability that cannot be
        # covered inside the budget is an error, never a quietly smaller plan.
        for capability in self._profile.required_capabilities:
            if capability in covered:
                continue
            providers = [entry for entry in candidates
                         if capability in entry.capabilities
                         and entry.tool_id not in selected]
            if not providers:
                if any(capability in self._entries[tool_id].capabilities
                       for tool_id in denied):
                    raise KernelError(
                        code="TOOL_NOT_AUTHORIZED",
                        message=(
                            f"capability {capability!r} is only provided by tools the "
                            "authority does not grant"
                        ),
                        retryable=False,
                        recommended_action="grant the tool in the permission profile",
                        details={"capability": capability},
                    )
                raise KernelError(
                    code="TOOL_DISCOVERY_FAILED",
                    message=f"no catalogue entry provides capability {capability!r}",
                    retryable=False,
                    recommended_action="extend the catalogue or relax the requirement",
                    details={"capability": capability},
                )
            chosen = providers[0]
            if spent + chosen.token_cost > self._profile.token_budget:
                raise KernelError(
                    code="BUDGET_EXHAUSTED",
                    message=(
                        f"covering capability {capability!r} needs {chosen.token_cost} "
                        f"tokens but only {self._profile.token_budget - spent} remain of "
                        f"{self._profile.token_budget}"
                    ),
                    retryable=False,
                    recommended_action=(
                        "raise the budget or drop the requirement; the plan is not "
                        "silently truncated"
                    ),
                    details={"capability": capability, "toolId": chosen.tool_id,
                             "tokenCost": chosen.token_cost,
                             "tokensRemaining": self._profile.token_budget - spent},
                )
            if self._profile.max_tools is not None and \
                    len(selected) >= self._profile.max_tools:
                raise KernelError(
                    code="BUDGET_EXHAUSTED",
                    message=(
                        f"covering capability {capability!r} needs more than the "
                        f"{self._profile.max_tools}-tool ceiling"
                    ),
                    retryable=False,
                    recommended_action="raise max_tools or drop the requirement",
                    details={"capability": capability},
                )
            selected.append(chosen.tool_id)
            spent += chosen.token_cost
            covered.update(chosen.capabilities)

        # Phase B — classify everything Phase A did not take.  There is no
        # "optional fill": Phase A already covers every required capability, so
        # any remaining tool is either irrelevant to the task or a second
        # provider of a capability that is already covered.  Loading it would
        # spend permanent context on zero new capability, which is precisely the
        # cost this loader exists to avoid — it stays deferred and one `resolve`
        # call away.  The reason distinguishes the two cases, because "I don't
        # need you" and "someone else already does your job" send a caller
        # looking in different places.
        for entry in candidates:
            if entry.tool_id in selected:
                continue
            overlapping = sorted(
                capability for capability in entry.capabilities
                if capability in self._profile.required_capabilities
            )
            if not overlapping:
                decisions[entry.tool_id] = LoadDecision(
                    tool_id=entry.tool_id, state="DEFERRED",
                    reason="matches no required capability",
                    capability_matches=0, usage_prior=entry.usage_prior,
                    token_cost=entry.token_cost, rank=ranks[entry.tool_id])
                continue
            covering = {
                capability: next(
                    tool_id for tool_id in selected
                    if capability in self._entries[tool_id].capabilities
                )
                for capability in overlapping
            }
            decisions[entry.tool_id] = LoadDecision(
                tool_id=entry.tool_id, state="DEFERRED",
                reason=(
                    f"capability {overlapping} already covered by "
                    f"{sorted(set(covering.values()))}; deferred to keep the "
                    "loaded set minimal"
                ),
                capability_matches=entry.matches(required),
                usage_prior=entry.usage_prior, token_cost=entry.token_cost,
                rank=ranks[entry.tool_id])

        for tool_id in selected:
            entry = self._entries[tool_id]
            decisions[tool_id] = LoadDecision(
                tool_id=tool_id, state="LOADED",
                reason="selected for a required capability",
                capability_matches=entry.matches(required),
                usage_prior=entry.usage_prior, token_cost=entry.token_cost,
                rank=ranks[tool_id])

        for tool_id in selected:
            self._materialise(self._entries[tool_id])

        plan = LoadPlan(
            loaded=tuple(sorted(selected)),
            deferred=tuple(sorted(item.tool_id for item in decisions.values()
                                  if item.state == "DEFERRED")),
            denied=tuple(sorted(denied)),
            decisions=tuple(sorted(decisions.values(), key=lambda item: item.tool_id)),
            tokens_loaded=spent,
            token_budget=self._profile.token_budget,
        )
        self._plan = plan
        return plan

    def _materialise(self, entry: CatalogueEntry) -> None:
        """Bring one tool's schema into the loaded set, connecting if it is remote."""

        if entry.tool_id in self._loaded:
            return
        if entry.remote:
            if self._connector is None:
                raise KernelError(
                    code="REMOTE_TOOL_UNAVAILABLE",
                    message=(
                        f"tool {entry.tool_id!r} is remote and no connector is configured; "
                        "an unreachable remote tool is unavailable, not assumed"
                    ),
                    retryable=False,
                    recommended_action="configure a connector or drop the tool",
                    details={"toolId": entry.tool_id},
                )
            schema = self._connector.connect(entry.tool_id)
            if not isinstance(schema, Mapping):
                raise KernelError(
                    code="SCHEMA_LOAD_FAILED",
                    message=f"remote tool {entry.tool_id!r} returned a non-object schema",
                    retryable=False,
                    recommended_action="treat the remote tool as unusable",
                    details={"toolId": entry.tool_id},
                )
            self._loaded[entry.tool_id] = dict(schema)
        else:
            self._loaded[entry.tool_id] = dict(entry.schema)
        self._tokens += entry.token_cost

    def load(self, tool_id: str) -> Mapping[str, Any]:
        """Load one tool on demand.  Idempotent; charges the budget exactly once."""

        require_identifier(tool_id, "tool_id")
        entry = self._entries.get(tool_id)
        if entry is None:
            raise KernelError(
                code="TOOL_DISCOVERY_FAILED",
                message=f"tool {tool_id!r} is not in the catalogue",
                retryable=False,
                recommended_action="the loader never invents tools; extend the catalogue",
                details={"toolId": tool_id},
            )
        if tool_id not in self._allowed:
            raise KernelError(
                code="TOOL_NOT_AUTHORIZED",
                message=(
                    f"tool {tool_id!r} is discoverable but not granted; discovery is not "
                    "authorization"
                ),
                retryable=False,
                recommended_action="grant the tool in the permission profile",
                details={"toolId": tool_id},
            )
        if tool_id in self._loaded:
            return self._loaded[tool_id]
        if self._tokens + entry.token_cost > self._profile.token_budget:
            raise KernelError(
                code="BUDGET_EXHAUSTED",
                message=(
                    f"loading {tool_id!r} costs {entry.token_cost} tokens but only "
                    f"{self._profile.token_budget - self._tokens} remain"
                ),
                retryable=False,
                recommended_action="unload another tool or raise the budget explicitly",
                details={"toolId": tool_id, "tokenCost": entry.token_cost,
                         "tokensRemaining": self._profile.token_budget - self._tokens},
            )
        self._materialise(entry)
        return self._loaded[tool_id]

    def resolve(self, tool_id: str) -> Mapping[str, Any]:
        """Return a loaded tool's schema.  A deferred tool is not callable."""

        require_identifier(tool_id, "tool_id")
        loaded = self._loaded.get(tool_id)
        if loaded is not None:
            return loaded
        entry = self._entries.get(tool_id)
        if entry is None:
            raise KernelError(
                code="TOOL_DISCOVERY_FAILED",
                message=f"tool {tool_id!r} is not in the catalogue",
                retryable=False,
                recommended_action="the loader never invents tools; extend the catalogue",
                details={"toolId": tool_id},
            )
        if tool_id not in self._allowed:
            raise KernelError(
                code="TOOL_NOT_AUTHORIZED",
                message=(
                    f"tool {tool_id!r} is discoverable but not granted; discovery is not "
                    "authorization"
                ),
                retryable=False,
                recommended_action="grant the tool in the permission profile",
                details={"toolId": tool_id},
            )
        raise KernelError(
            code="TOOL_NOT_LOADED",
            message=(
                f"tool {tool_id!r} is deferred and therefore not callable; load it "
                f"explicitly ({entry.token_cost} tokens) before use"
            ),
            retryable=False,
            recommended_action=f"call ToolLoader.load({tool_id!r}) first",
            details={"toolId": tool_id, "tokenCost": entry.token_cost,
                     "tokensRemaining": self._profile.token_budget - self._tokens,
                     "loadWith": f"load({tool_id!r})"},
        )

    def schema_bundle(self) -> Mapping[str, Any]:
        """The schemas actually paid for.  Deferred tools contribute nothing."""

        return {tool_id: dict(schema) for tool_id, schema in sorted(self._loaded.items())}

    def metrics(self) -> Mapping[str, Any]:
        """Load accounting.

        ``measured`` is explicit: a zero here means "nothing was loaded", and a
        caller must never have to guess whether it instead means "we failed to
        count".
        """

        return {
            "toolsDiscovered": len(self._entries),
            "toolsAuthorized": len(self._allowed.intersection(self._entries)),
            "toolsLoaded": len(self._loaded),
            "tokensLoaded": self._tokens,
            "tokenBudget": self._profile.token_budget,
            "tokensRemaining": self._profile.token_budget - self._tokens,
            "measured": True,
        }


def _frozen_allowed(authority: Any) -> frozenset[str]:
    if not hasattr(authority, "allowed_tools"):
        raise KernelError(
            code="TOOL_NOT_AUTHORIZED",
            message="execution authority does not declare 'allowed_tools'",
            recommended_action="supply a complete ExecutionAuthority; absence is a deny",
            details={"missingAttribute": "allowed_tools"},
        )
    value = authority.allowed_tools
    if isinstance(value, Mapping):
        return frozenset(str(key) for key in value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(item) for item in value)
    raise KernelError(
        code="TOOL_NOT_AUTHORIZED",
        message="execution authority 'allowed_tools' is not a collection",
        recommended_action="declare the allowed tools as a sequence",
    )


class _AuthorityView:
    """Read-only adapter over a wire-form execution authority."""

    __slots__ = ("allowed_tools", "policy_snapshot_hash")

    def __init__(self, payload: Mapping[str, Any]) -> None:
        payload = require_mapping(payload, "execution_authority")
        reject_unknown_fields(
            payload,
            {"environmentId", "workspaceId", "fencingToken", "allowedTools",
             "pathScopes", "networkScopes", "secretBindings", "policySnapshotHash"},
            field_name="execution_authority",
        )
        self.allowed_tools = require_str_seq(payload.get("allowedTools", ()),
                                             "execution_authority.allowedTools")
        raw_hash = payload.get("policySnapshotHash")
        self.policy_snapshot_hash = (
            None if raw_hash is None
            else require_str(raw_hash, "execution_authority.policySnapshotHash")
        )


def _assert_policy_snapshot_agrees(snapshot: Any, authority: _AuthorityView) -> None:
    """Refuse to plan against a policy snapshot the authority was not frozen under.

    ``handle`` accepts ``policy_snapshot`` and the authority carries
    ``policySnapshotHash``.  Taking both and comparing neither is worse than
    taking neither: the caller believes a constraint was applied when it was
    silently dropped, and a grant list frozen under an older policy keeps
    working after that policy has been tightened.  Either the pair agrees or the
    plan does not happen.
    """

    if snapshot is None:
        return
    body = require_mapping(snapshot, "policy_snapshot")
    reject_unknown_fields(body, {"policySnapshotHash"}, field_name="policy_snapshot")
    declared = body.get("policySnapshotHash")
    if declared is None:
        return
    declared = require_str(declared, "policy_snapshot.policySnapshotHash")
    if authority.policy_snapshot_hash is None:
        raise KernelError(
            code="STALE_POLICY_SNAPSHOT",
            message=(
                "a policy snapshot was supplied but the execution authority declares "
                "no policySnapshotHash to check it against"
            ),
            retryable=False,
            recommended_action="mint the authority under the policy snapshot, or omit it",
            details={"policySnapshotHash": declared},
        )
    if declared != authority.policy_snapshot_hash:
        raise KernelError(
            code="STALE_POLICY_SNAPSHOT",
            message=(
                f"policy snapshot {declared} does not match the authority's "
                f"{authority.policy_snapshot_hash}"
            ),
            retryable=False,
            recommended_action="re-mint the execution authority under the current policy",
            details={"supplied": declared, "authority": authority.policy_snapshot_hash},
        )


@register("lazy-tool-loader")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``lazy-tool-loader``."""

    request = require_mapping(request, "request")
    known = {"tool_catalogue", "task_profile", "execution_authority", "policy_snapshot"}
    reject_unknown_fields(request, known, field_name="request")
    for name in ("tool_catalogue", "task_profile", "execution_authority"):
        if name not in request:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{name} is required",
                recommended_action=f"supply request.{name}",
            )

    raw_catalogue = request["tool_catalogue"]
    if not isinstance(raw_catalogue, Sequence) or isinstance(raw_catalogue, (str, bytes)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="tool_catalogue must be an array of catalogue entries",
            recommended_action="supply tool_catalogue as a JSON array",
        )
    catalogue = [CatalogueEntry.from_payload(item) for item in raw_catalogue]

    profile_raw = require_mapping(request["task_profile"], "task_profile")
    reject_unknown_fields(profile_raw, {"requiredCapabilities", "tokenBudget", "maxTools"},
                          field_name="task_profile")
    max_tools = profile_raw.get("maxTools")
    profile = TaskProfile(
        required_capabilities=require_str_seq(profile_raw.get("requiredCapabilities", ()),
                                              "task_profile.requiredCapabilities"),
        token_budget=require_int(profile_raw.get("tokenBudget"), "task_profile.tokenBudget",
                                 minimum=0),
        max_tools=None if max_tools is None else require_int(max_tools,
                                                             "task_profile.maxTools",
                                                             minimum=1),
    )

    authority = _AuthorityView(request["execution_authority"])
    _assert_policy_snapshot_agrees(request.get("policy_snapshot"), authority)

    loader = ToolLoader(catalogue, profile, authority)
    plan = loader.plan()
    return {
        "tool_load_plan": plan.to_payload(),
        "loaded_tools": list(plan.loaded),
        "deferred_tools": list(plan.deferred),
        "denied_tools": list(plan.denied),
        "tool_schema_bundle": dict(loader.schema_bundle()),
        "load_metrics": dict(loader.metrics()),
        "digest": plan.digest,
    }
