"""Prefix-stable context planning: the same bytes in the same order, every turn.

Provider prompt caches key on an exact byte prefix.  Reorder one block near the
front and every cache entry behind it is dead — the request still succeeds, the
answer still looks right, and the bill quietly multiplies.  That is the failure
this module exists to make impossible, so ordering is a *function of the block*,
never of the caller's dict: blocks sort by stability class (immutable, then
slow, then volatile) and then by a declared, deterministic key.  The invariant
that matters follows from it — appending a volatile block cannot change the
content or position of anything before it, which is what the shared-prefix test
checks digest by digest.

Two further rules keep the plan honest under pressure.  Eviction is
volatile-first and never touches a ``required`` block: if the required set alone
will not fit, the answer is ``BUDGET_EXHAUSTED``, not a truncated system prompt
that produces a confident wrong answer.  And a token cost is either measured —
supplied by the caller or produced by an injected counter — or it is *unmeasured*
and the plan refuses to make a budget decision at all.  Treating an unknown cost
as zero is how a plan reports that it fits inside a budget it has already blown.

Repository content is untrusted data.  A block whose kind is repository-derived
may never occupy the system role, because that is precisely the escalation an
instruction embedded in a README is looking for.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

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

__all__ = [
    "BlockKind",
    "BlockRole",
    "BudgetDecision",
    "CacheBreakpoint",
    "ContextBlock",
    "DEFAULT_MAX_BREAKPOINTS",
    "Eviction",
    "EvictionReason",
    "PromptPlan",
    "StabilityClass",
    "TokenCounter",
    "UNTRUSTED_KINDS",
    "handle",
    "plan",
]

register_codes(Category.RESOURCE, "CONTEXT_OVER_BUDGET")
register_codes(
    Category.SEMANTIC,
    "COMPACTION_DATA_LOSS",
    "RETRIEVAL_MISS",
    "TOKEN_COST_UNMEASURED",
    "CONTEXT_SNAPSHOT_MIXED",
    "DUPLICATE_BLOCK_ID",
)
register_codes(Category.POLICY, "PROMPT_INJECTION_RISK")

#: Most providers cap the number of cache breakpoints a request may declare.
DEFAULT_MAX_BREAKPOINTS = 4


class StabilityClass(StrEnum):
    """How often a block's bytes are expected to change.

    The class is the primary sort key and therefore the thing that decides
    cache economics.  ``IMMUTABLE`` blocks are identical for the lifetime of a
    run, ``SLOW`` blocks change when the snapshot or the spec moves, and
    ``VOLATILE`` blocks change every turn.  Ordering them in that sequence puts
    the longest reusable prefix at the front, which is the only arrangement a
    prefix cache can exploit.
    """

    IMMUTABLE = "immutable"
    SLOW = "slow"
    VOLATILE = "volatile"

    @property
    def order(self) -> int:
        return {"immutable": 0, "slow": 1, "volatile": 2}[self.value]


class BlockRole(StrEnum):
    """Conversation role the block occupies in the assembled request."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class BlockKind(StrEnum):
    """What the block contains, which decides both trust and tie-break order."""

    SYSTEM = "system"
    SPEC = "spec"
    TOOL_SCHEMA = "tool-schema"
    REPO_MAP = "repo-map"
    FILE = "file"
    HISTORY = "history"
    TASK = "task"

    @property
    def order(self) -> int:
        return {
            "system": 0, "spec": 1, "tool-schema": 2, "repo-map": 3,
            "file": 4, "history": 5, "task": 6,
        }[self.value]


#: Kinds whose bytes came out of the repository or a tool.  These are data, not
#: instructions, and the planner refuses to seat them in the system role.
UNTRUSTED_KINDS: frozenset[BlockKind] = frozenset({BlockKind.REPO_MAP, BlockKind.FILE})


class EvictionReason(StrEnum):
    """Why a block did not make it into the plan."""

    BUDGET_EXCEEDED = "budget-exceeded"


class BudgetDecision(StrEnum):
    """Whether the plan is allowed to claim anything about the budget.

    ``REFUSED_UNMEASURED`` is the important member.  A plan holding a block of
    unknown size has not been shown to fit, and saying "within budget" there
    would be a guess dressed as a measurement.
    """

    HONOURED = "HONOURED"
    NO_BUDGET = "NO_BUDGET"
    REFUSED_UNMEASURED = "REFUSED_UNMEASURED"


@runtime_checkable
class TokenCounter(Protocol):
    """Injected tokeniser.

    Counting is a provider-specific measurement, so it enters through a port
    like every other contact with the world.  ``count`` returns an ``int``; a
    counter that cannot answer must raise rather than return a placeholder.
    """

    def count(self, block: ContextBlock) -> int: ...


@dataclass(frozen=True, slots=True)
class ContextBlock:
    """One addressable unit of prompt content.

    The block carries a ``digest`` of its bytes rather than the bytes: the
    planner decides order, budget and cache boundaries, and none of those
    decisions needs the content.  Keeping content out also keeps secrets and
    untrusted repository text out of every plan, ledger and trace this module
    emits.  ``token_cost`` is ``None`` when nobody has measured it — never 0.
    """

    block_id: str
    role: BlockRole
    kind: BlockKind
    stability_class: StabilityClass
    digest: str
    token_cost: int | None = None
    required: bool = False
    snapshot_sha: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.block_id, "block.block_id")
        for name, enum_type in (("role", BlockRole), ("kind", BlockKind),
                                ("stability_class", StabilityClass)):
            value = getattr(self, name)
            if not isinstance(value, enum_type):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"block.{name} {value!r} is not a {enum_type.__name__}",
                    recommended_action=(
                        f"use one of {sorted(item.value for item in enum_type)}"
                    ),
                )
        require_str(self.digest, "block.digest", max_length=128)
        if self.token_cost is not None:
            require_int(self.token_cost, "block.token_cost", minimum=0)
        require_bool(self.required, "block.required")
        if self.snapshot_sha:
            require_str(self.snapshot_sha, "block.snapshot_sha", max_length=128)
        if self.kind in UNTRUSTED_KINDS and self.role is BlockRole.SYSTEM:
            raise KernelError(
                code="PROMPT_INJECTION_RISK",
                message=(
                    f"block {self.block_id!r} carries repository-derived content of kind "
                    f"{str(self.kind)!r} and cannot occupy the system role"
                ),
                retryable=False,
                recommended_action="place repository content in a user or tool role block",
                details={"blockId": self.block_id, "kind": str(self.kind)},
            )

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """The declared, deterministic ordering key.

        Stability first, then kind, then id.  Nothing here reads insertion
        order, which is the whole point: two callers that build the same set of
        blocks in different orders must produce the same prompt.
        """

        return (self.stability_class.order, self.kind.order, self.block_id)

    def to_payload(self) -> dict[str, Any]:
        return {
            "blockId": self.block_id,
            "role": str(self.role),
            "kind": str(self.kind),
            "stabilityClass": str(self.stability_class),
            "digest": self.digest,
            "tokenCost": self.token_cost,
            "tokenCostMeasured": self.token_cost is not None,
            "required": self.required,
            "snapshotSha": self.snapshot_sha,
        }


@dataclass(frozen=True, slots=True)
class CacheBreakpoint:
    """A boundary a provider may be asked to cache up to.

    ``prefix_digest`` covers every block before the boundary, so two turns can
    be compared for cache eligibility without holding either prompt.
    """

    index: int
    before_class: StabilityClass
    after_class: StabilityClass
    prefix_block_count: int
    prefix_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "beforeClass": str(self.before_class),
            "afterClass": str(self.after_class),
            "prefixBlockCount": self.prefix_block_count,
            "prefixDigest": self.prefix_digest,
        }


@dataclass(frozen=True, slots=True)
class Eviction:
    """One block that was dropped, with what it bought.

    ``prefix_disturbed`` records the expensive case: dropping a non-volatile
    block reclaims tokens *and* invalidates the provider cache behind it, so a
    reader can see that the saving was not free.
    """

    block_id: str
    stability_class: StabilityClass
    reason: EvictionReason
    reclaimed_tokens: int
    prefix_disturbed: bool
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "blockId": self.block_id,
            "stabilityClass": str(self.stability_class),
            "reason": str(self.reason),
            "reclaimedTokens": self.reclaimed_tokens,
            "prefixDisturbed": self.prefix_disturbed,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PromptPlan:
    """An ordered, budgeted, cache-annotated prompt.

    ``prefix_digests[i]`` addresses blocks ``0..i`` inclusive.  It exists so the
    prefix-stability invariant can be tested directly rather than inferred:
    plan twice, append a volatile block the second time, and the first plan's
    digests must be a prefix of the second's.
    """

    blocks: tuple[ContextBlock, ...]
    cache_breakpoints: tuple[CacheBreakpoint, ...]
    evictions: tuple[Eviction, ...]
    token_cost_measured: bool
    total_token_cost: int | None
    budget_tokens: int | None
    budget_decision: BudgetDecision
    prefix_digests: tuple[str, ...]
    dropped_breakpoints: int = 0

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(item.block_id for item in self.blocks)

    @property
    def prefix_digest(self) -> str:
        """Address of the whole ordered plan; empty for an empty plan."""

        return self.prefix_digests[-1] if self.prefix_digests else digest([])

    @property
    def stable_prefix_length(self) -> int:
        """How many leading blocks are not volatile."""

        return sum(1 for item in self.blocks
                   if item.stability_class is not StabilityClass.VOLATILE)

    @property
    def ordering_is_stability_first(self) -> bool:
        """True when the emitted order never moves backwards in stability class."""

        orders = [item.stability_class.order for item in self.blocks]
        return all(left <= right for left, right in zip(orders, orders[1:], strict=False))

    @property
    def within_budget(self) -> bool | None:
        """``None`` when unmeasured or unbudgeted — never an optimistic ``True``."""

        if self.budget_tokens is None or self.total_token_cost is None:
            return None
        return self.total_token_cost <= self.budget_tokens

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "blocks": [item.to_payload() for item in self.blocks],
            "cacheBreakpoints": [item.to_payload() for item in self.cache_breakpoints],
            "droppedBreakpoints": self.dropped_breakpoints,
            "evictions": [item.to_payload() for item in self.evictions],
            "tokenCostMeasured": self.token_cost_measured,
            "totalTokenCost": self.total_token_cost,
            "budgetTokens": self.budget_tokens,
            "budgetDecision": str(self.budget_decision),
            "withinBudget": self.within_budget,
            "prefixDigests": list(self.prefix_digests),
            "prefixDigest": self.prefix_digest,
            "stablePrefixLength": self.stable_prefix_length,
        }
        payload["planDigest"] = digest(payload)
        return payload

    @property
    def plan_digest(self) -> str:
        return self.to_payload()["planDigest"]


def _prefix_digests(blocks: Sequence[ContextBlock]) -> tuple[str, ...]:
    running: list[str] = []
    digests: list[str] = []
    for block in blocks:
        running.append(digest(block.to_payload()))
        digests.append(digest(running))
    return tuple(digests)


def _breakpoints(blocks: Sequence[ContextBlock], prefixes: Sequence[str],
                 limit: int) -> tuple[tuple[CacheBreakpoint, ...], int]:
    boundaries: list[CacheBreakpoint] = []
    for index in range(1, len(blocks)):
        previous = blocks[index - 1].stability_class
        current = blocks[index].stability_class
        if previous is not current:
            boundaries.append(CacheBreakpoint(
                index=index,
                before_class=previous,
                after_class=current,
                prefix_block_count=index,
                prefix_digest=prefixes[index - 1],
            ))
    if len(boundaries) <= limit:
        return tuple(boundaries), 0
    # Keep the boundaries covering the longest prefixes: those are the ones a
    # provider cache can actually reuse.  Dropping is counted, not hidden.
    kept = boundaries[len(boundaries) - limit:] if limit else []
    return tuple(kept), len(boundaries) - len(kept)


def _resolve_costs(blocks: Sequence[ContextBlock],
                   counter: TokenCounter | None) -> tuple[tuple[ContextBlock, ...], bool]:
    """Fill in token costs, or report that they could not be measured."""

    resolved: list[ContextBlock] = []
    measured = True
    for block in blocks:
        if block.token_cost is not None:
            resolved.append(block)
            continue
        if counter is None:
            measured = False
            resolved.append(block)
            continue
        count = counter.count(block)
        if isinstance(count, bool) or not isinstance(count, int):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    f"token counter returned {type(count).__name__} for block "
                    f"{block.block_id!r}; token costs are integers"
                ),
                recommended_action="return an integer token count, or raise",
            )
        require_int(count, f"counter.count({block.block_id})", minimum=0)
        resolved.append(ContextBlock(
            block_id=block.block_id, role=block.role, kind=block.kind,
            stability_class=block.stability_class, digest=block.digest,
            token_cost=count, required=block.required, snapshot_sha=block.snapshot_sha,
        ))
    return tuple(resolved), measured


def _check_snapshot_agreement(blocks: Sequence[ContextBlock]) -> None:
    seen = sorted({block.snapshot_sha for block in blocks if block.snapshot_sha})
    if len(seen) > 1:
        raise KernelError(
            code="CONTEXT_SNAPSHOT_MIXED",
            message=(
                f"context blocks are bound to {len(seen)} different repository snapshots; "
                "a prompt describing two repository states describes neither"
            ),
            retryable=False,
            recommended_action="rebuild the context against one snapshot",
            details={"snapshotShas": seen},
        )


def plan(blocks: Sequence[ContextBlock], budget_tokens: int | None = None,
         breakpoints: int = DEFAULT_MAX_BREAKPOINTS, *,
         counter: TokenCounter | None = None,
         must_include: Sequence[str] = ()) -> PromptPlan:
    """Order, budget and annotate a set of context blocks.

    Order is decided before anything else and never revisited, so eviction can
    only remove blocks — it can never move one.  That is what makes the prefix
    stable across turns even as the volatile tail churns.

    ``budget_tokens`` of ``0`` is a legal budget and means exactly what it says.
    A budget of ``None`` means no budget was stated, which is a different thing
    again, and the plan reports which of the two it saw.
    """

    ordered_input = tuple(blocks)
    seen: set[str] = set()
    for block in ordered_input:
        if not isinstance(block, ContextBlock):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"blocks must be ContextBlock, got {type(block).__name__}",
                recommended_action="construct ContextBlock instances",
            )
        if block.block_id in seen:
            raise KernelError(
                code="DUPLICATE_BLOCK_ID",
                message=f"block id {block.block_id!r} appears more than once",
                retryable=False,
                recommended_action="give every context block a unique id",
            )
        seen.add(block.block_id)
    missing = sorted(set(must_include) - seen)
    if missing:
        raise KernelError(
            code="RETRIEVAL_MISS",
            message=f"required context blocks were not retrieved: {missing}",
            retryable=True,
            recommended_action="retrieve the missing blocks before planning",
            details={"missingBlockIds": missing},
        )
    _check_snapshot_agreement(ordered_input)
    limit = require_int(breakpoints, "breakpoints", minimum=0, maximum=64)
    if budget_tokens is not None:
        require_int(budget_tokens, "budget_tokens", minimum=0)

    resolved, measured = _resolve_costs(ordered_input, counter)
    ordered = tuple(sorted(resolved, key=lambda item: item.sort_key))

    evictions: tuple[Eviction, ...] = ()
    if not measured:
        decision = BudgetDecision.REFUSED_UNMEASURED
        total: int | None = None
        kept = ordered
    elif budget_tokens is None:
        decision = BudgetDecision.NO_BUDGET
        total = sum(item.token_cost or 0 for item in ordered)
        kept = ordered
    else:
        kept, evictions = _evict_to_budget(ordered, budget_tokens)
        decision = BudgetDecision.HONOURED
        total = sum(item.token_cost or 0 for item in kept)

    prefixes = _prefix_digests(kept)
    emitted, dropped = _breakpoints(kept, prefixes, limit)
    return PromptPlan(
        blocks=kept,
        cache_breakpoints=emitted,
        evictions=evictions,
        token_cost_measured=measured,
        total_token_cost=total,
        budget_tokens=budget_tokens,
        budget_decision=decision,
        prefix_digests=prefixes,
        dropped_breakpoints=dropped,
    )


def _evict_to_budget(ordered: Sequence[ContextBlock],
                     budget_tokens: int) -> tuple[tuple[ContextBlock, ...], tuple[Eviction, ...]]:
    """Drop optional blocks, volatile-first, until the plan fits.

    The required floor is computed first and checked against the budget before
    anything is dropped.  A required block that does not fit is not a smaller
    required block — truncating a system prompt or a task spec produces an agent
    that is confidently working on the wrong problem — so the answer is
    ``BUDGET_EXHAUSTED`` and the caller has to raise the budget or reduce what
    it declared essential.
    """

    required_total = sum(item.token_cost or 0 for item in ordered if item.required)
    if required_total > budget_tokens:
        raise KernelError(
            code="BUDGET_EXHAUSTED",
            message=(
                f"the required context alone costs {required_total} tokens against a budget "
                f"of {budget_tokens}; no eviction can close that gap"
            ),
            retryable=False,
            recommended_action="raise the budget or move blocks out of the required set",
            details={
                "requiredTokens": required_total,
                "budgetTokens": budget_tokens,
                "requiredBlockIds": [item.block_id for item in ordered if item.required],
            },
        )
    total = sum(item.token_cost or 0 for item in ordered)
    if total <= budget_tokens:
        return tuple(ordered), ()

    # Volatile first, and within a class the tail first, so the cacheable head
    # survives as long as possible.
    candidates = sorted(
        (index for index, item in enumerate(ordered) if not item.required),
        key=lambda index: (-ordered[index].stability_class.order, -index),
    )
    dropped: set[int] = set()
    evictions: list[Eviction] = []
    for index in candidates:
        if total <= budget_tokens:
            break
        block = ordered[index]
        reclaimed = block.token_cost or 0
        dropped.add(index)
        total -= reclaimed
        evictions.append(Eviction(
            block_id=block.block_id,
            stability_class=block.stability_class,
            reason=EvictionReason.BUDGET_EXCEEDED,
            reclaimed_tokens=reclaimed,
            prefix_disturbed=block.stability_class is not StabilityClass.VOLATILE,
            detail=(
                f"dropped to fit {budget_tokens} tokens; "
                f"{total} tokens remain in the plan"
            ),
        ))
    if total > budget_tokens:  # pragma: no cover - the required floor already bounds this
        raise KernelError(
            code="CONTEXT_OVER_BUDGET",
            message=(
                f"plan still costs {total} tokens after evicting every optional block "
                f"against a budget of {budget_tokens}"
            ),
            retryable=False,
            recommended_action="raise the budget or move blocks out of the required set",
        )
    kept = tuple(item for index, item in enumerate(ordered) if index not in dropped)
    return kept, tuple(evictions)


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = {
    "task_spec", "repository_index", "current_step", "skill_metadata", "token_budget",
    "previous_ledger", "blocks", "max_breakpoints", "must_include",
}
_BLOCK_FIELDS = {
    "blockId", "role", "kind", "stabilityClass", "digest", "tokenCost", "required",
    "snapshotSha",
}


def _enum(value: Any, enum_type: type[StrEnum], field_name: str) -> Any:
    text = require_str(value, field_name, max_length=64)
    if text not in {item.value for item in enum_type}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} is not a known {enum_type.__name__}",
            recommended_action=f"use one of {sorted(item.value for item in enum_type)}",
        )
    return enum_type(text)


def _decode_block(payload: Mapping[str, Any], *, field_name: str) -> ContextBlock:
    reject_unknown_fields(payload, _BLOCK_FIELDS, field_name=field_name)
    token_cost = payload.get("tokenCost")
    if token_cost is not None:
        token_cost = require_int(token_cost, f"{field_name}.tokenCost", minimum=0)
    snapshot_sha = payload.get("snapshotSha", "")
    return ContextBlock(
        block_id=require_identifier(payload.get("blockId"), f"{field_name}.blockId"),
        role=_enum(payload.get("role"), BlockRole, f"{field_name}.role"),
        kind=_enum(payload.get("kind"), BlockKind, f"{field_name}.kind"),
        stability_class=_enum(payload.get("stabilityClass"), StabilityClass,
                              f"{field_name}.stabilityClass"),
        digest=require_str(payload.get("digest"), f"{field_name}.digest", max_length=128),
        token_cost=token_cost,
        required=require_bool(payload.get("required", False), f"{field_name}.required"),
        snapshot_sha=require_str(snapshot_sha, f"{field_name}.snapshotSha",
                                 max_length=128) if snapshot_sha else "",
    )


def _synthetic(payload: Mapping[str, Any] | None, *, field_name: str, block_id_prefix: str,
               id_field: str, role: BlockRole, kind: BlockKind,
               stability_class: StabilityClass, required: bool) -> ContextBlock | None:
    """Build one of the standard blocks the skill contract names as an input."""

    if payload is None:
        return None
    body = require_mapping(payload, field_name)
    reject_unknown_fields(body, {id_field, "digest", "tokenCost", "snapshotSha"},
                          field_name=field_name)
    token_cost = body.get("tokenCost")
    if token_cost is not None:
        token_cost = require_int(token_cost, f"{field_name}.tokenCost", minimum=0)
    snapshot_sha = body.get("snapshotSha", "")
    identifier = require_identifier(body.get(id_field), f"{field_name}.{id_field}")
    return ContextBlock(
        block_id=f"{block_id_prefix}:{identifier}",
        role=role,
        kind=kind,
        stability_class=stability_class,
        digest=require_str(body.get("digest"), f"{field_name}.digest", max_length=128),
        token_cost=token_cost,
        required=required,
        snapshot_sha=require_str(snapshot_sha, f"{field_name}.snapshotSha",
                                 max_length=128) if snapshot_sha else "",
    )


@register("prefix-stable-context-planner")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``prefix-stable-context-planner``.

    The contract's named inputs (task spec, skill metadata, repository index,
    current step, previous ledger) are compiled into standard blocks with fixed
    stability classes, and ``blocks`` carries anything else the caller retrieved.
    The retrieval trace accounts for every block that went in — included or
    evicted — because a block that silently vanished between retrieval and
    prompt is the hardest kind of context bug to see from the outside.
    """

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _REQUEST_FIELDS,
                          field_name="prefix-stable-context-planner request")

    if payload.get("task_spec") is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="prefix-stable-context-planner requires 'task_spec'",
            recommended_action="supply the task spec block descriptor",
        )

    synthesised = [
        _synthetic(payload.get("skill_metadata"), field_name="skill_metadata",
                   block_id_prefix="skill", id_field="skillId", role=BlockRole.SYSTEM,
                   kind=BlockKind.SYSTEM, stability_class=StabilityClass.IMMUTABLE,
                   required=True),
        _synthetic(payload.get("task_spec"), field_name="task_spec",
                   block_id_prefix="spec", id_field="taskSpecId", role=BlockRole.SYSTEM,
                   kind=BlockKind.SPEC, stability_class=StabilityClass.IMMUTABLE,
                   required=True),
        _synthetic(payload.get("repository_index"), field_name="repository_index",
                   block_id_prefix="repo", id_field="indexId", role=BlockRole.USER,
                   kind=BlockKind.REPO_MAP, stability_class=StabilityClass.SLOW,
                   required=False),
        _synthetic(payload.get("previous_ledger"), field_name="previous_ledger",
                   block_id_prefix="ledger", id_field="ledgerId", role=BlockRole.USER,
                   kind=BlockKind.HISTORY, stability_class=StabilityClass.VOLATILE,
                   required=False),
        _synthetic(payload.get("current_step"), field_name="current_step",
                   block_id_prefix="step", id_field="stepId", role=BlockRole.USER,
                   kind=BlockKind.TASK, stability_class=StabilityClass.VOLATILE,
                   required=True),
    ]
    extra = [
        _decode_block(require_mapping(item, "blocks[]"), field_name="blocks[]")
        for item in payload.get("blocks", ()) or ()
    ]
    incoming = tuple([item for item in synthesised if item is not None] + extra)

    budget_tokens: int | None = None
    budget_payload = payload.get("token_budget")
    if budget_payload is not None:
        body = require_mapping(budget_payload, "token_budget")
        reject_unknown_fields(body, {"totalTokens"}, field_name="token_budget")
        budget_tokens = require_int(body.get("totalTokens"), "token_budget.totalTokens",
                                    minimum=0)

    prompt_plan = plan(
        incoming,
        budget_tokens,
        require_int(payload.get("max_breakpoints", DEFAULT_MAX_BREAKPOINTS),
                    "max_breakpoints", minimum=0, maximum=64),
        must_include=require_str_seq(payload.get("must_include", ()), "must_include"),
    )

    kept_ids = set(prompt_plan.block_ids)
    evicted = {item.block_id: item for item in prompt_plan.evictions}
    retrieval_trace = [
        {
            "blockId": block.block_id,
            "kind": str(block.kind),
            "stabilityClass": str(block.stability_class),
            "digest": block.digest,
            "tokenCost": block.token_cost,
            "tokenCostMeasured": block.token_cost is not None,
            "disposition": "included" if block.block_id in kept_ids else "evicted",
            "reason": (str(evicted[block.block_id].reason)
                       if block.block_id in evicted else "retained"),
        }
        for block in sorted(incoming, key=lambda item: item.block_id)
    ]
    context_ledger = {
        "entries": [
            {
                "blockId": block.block_id,
                "kind": str(block.kind),
                "stabilityClass": str(block.stability_class),
                "digest": block.digest,
                "tokenCost": block.token_cost,
            }
            for block in prompt_plan.blocks
        ],
        "blockCount": len(prompt_plan.blocks),
        "contentFree": True,
    }
    context_ledger["digest"] = digest(context_ledger)
    compaction_snapshot = {
        "retainedBlockIds": sorted(item.block_id for item in prompt_plan.blocks if item.required),
        "droppedBlockIds": sorted(evicted),
        "requiredBlockEvicted": any(
            block.required for block in incoming if block.block_id in evicted),
        "reclaimedTokens": sum(item.reclaimed_tokens for item in prompt_plan.evictions),
        "reclaimedTokensMeasured": prompt_plan.token_cost_measured,
    }
    gates = {
        "within-token-budget": prompt_plan.within_budget,
        "prefix-hash-stable": prompt_plan.ordering_is_stability_first,
        "critical-state-preserved": not compaction_snapshot["requiredBlockEvicted"],
        "retrieval-trace-complete": len(retrieval_trace) == len(incoming),
    }
    return {
        "context_plan": prompt_plan.to_payload(),
        "context_bundle": {
            "blockIds": list(prompt_plan.block_ids),
            "prefixDigest": prompt_plan.prefix_digest,
            "stablePrefixLength": prompt_plan.stable_prefix_length,
            "cacheBreakpoints": [item.to_payload() for item in prompt_plan.cache_breakpoints],
        },
        "context_ledger": context_ledger,
        "retrieval_trace": retrieval_trace,
        "compaction_snapshot": compaction_snapshot,
        "eviction_report": [item.to_payload() for item in prompt_plan.evictions],
        "gates": gates,
    }
