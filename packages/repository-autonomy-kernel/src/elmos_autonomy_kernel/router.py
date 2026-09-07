"""Phase-aware model routing: every route, and every non-route, is explainable.

Routing is a policy decision that happens hundreds of times a run, and the failure mode that
matters is not "picked a slightly worse model" — it is "picked a model nobody can account for".
So the decision this module returns carries a reason for *every* candidate it considered,
including the ones it threw away and why.  A route you cannot explain after the fact is
indistinguishable from a route that was never made.

Four rules are enforced rather than advertised:

*An unknown model id is denied, never resolved.*  There is no fuzzy match, no prefix match, no
"closest registered model".  ``claude-opus`` does not become ``claude-opus-5``.  A typo in a
routing table must surface as a configuration error at the first call, not as silent traffic to
a model nobody chose.

*A missing token estimate is not zero.*  Cost is projected from declared estimates; when an
estimate is absent the decision reports ``projected: false`` and carries no number.  A policy
that states a cost ceiling therefore *cannot* be satisfied without an estimate, and the route is
refused — you cannot bound a cost you refused to measure.

*Tiers ratchet upward inside a run.*  A verify or repair phase past its attempt threshold raises
the minimum tier, and once a run has used a tier, dropping below it needs the policy to say so
out loud.  Silent de-escalation after a failure is how a repair loop ends up cheaper and dumber
on exactly the attempt that needed to be smarter.

*An empty policy is a deny.*  No rule for a (phase, risk) pair means ``ROUTING_DENIED``, not
"anything goes".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .contracts import (
    digest,
    reject_unknown_fields,
    require_bool,
    require_decimal,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

__all__ = [
    "Budget",
    "Exclusion",
    "ModelProfile",
    "ModelRegistry",
    "PHASES",
    "RISK_CLASSES",
    "RouteDecision",
    "RouteRequest",
    "RoutingPolicy",
    "RoutingRule",
    "TIERS",
    "handle",
    "project_cost",
    "route",
    "tier_rank",
]

register_codes(Category.SEMANTIC, "NO_ELIGIBLE_MODEL", "MODEL_CAPABILITY_MISMATCH",
               "MODEL_NOT_REGISTERED", "COST_ESTIMATE_MISSING")
register_codes(Category.POLICY, "ROUTING_DENIED", "TIER_DE_ESCALATION_FORBIDDEN")
register_codes(Category.PROVIDER, "PROVIDER_UNAVAILABLE")

#: Workflow phases, in the order a run walks them.  The phase is an input to routing, not a
#: label on it: a plan-phase call and a verify-phase call with identical prompts are allowed to
#: land on different models, and that is the whole point of the capability.
PHASES = ("discover", "specify", "plan", "execute", "verify", "repair", "release")

#: Risk classes, ascending.  Risk raises the floor; it never lowers it.
RISK_CLASSES = ("low", "medium", "high", "critical")

#: Capability tiers, ascending.  Tier is a measured property of the model in *this* repository,
#: not a brand: a vendor's flagship that fails the repo evals is not frontier here.
TIERS = ("small", "standard", "frontier")

_COST_EXPONENT = Decimal("0.00000001")
_TOKENS_PER_MTOK = Decimal(1_000_000)
_MAX_CANDIDATES = 256


def tier_rank(tier: str) -> int:
    """Ordinal position of ``tier`` in :data:`TIERS`; unknown tiers raise."""

    try:
        return TIERS.index(tier)
    except ValueError as exc:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"tier {tier!r} is not one of {list(TIERS)}",
            recommended_action="declare a known tier; an unknown tier is not routable",
        ) from exc


def _require_phase(value: Any, field_name: str) -> str:
    phase = require_str(value, field_name, max_length=32)
    if phase not in PHASES:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={phase!r} is not one of {list(PHASES)}",
            recommended_action="use a declared workflow phase",
        )
    return phase


def _require_risk(value: Any, field_name: str) -> str:
    risk = require_str(value, field_name, max_length=32)
    if risk not in RISK_CLASSES:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={risk!r} is not one of {list(RISK_CLASSES)}",
            recommended_action="use a declared risk class",
        )
    return risk


# --- model registry ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """What one model actually is, in units this kernel can compare.

    Prices are ``Decimal`` per million tokens and ``reliability_prior`` is a ``Decimal`` in
    ``[0, 1]``: both are hashed into the routing decision, and a float would make two kernels
    disagree about the same model.  ``deprecated`` is a first-class field rather than a naming
    convention, because "we thought that one was retired" is not a control.
    """

    model_id: str
    tier: str
    context_window: int
    max_output: int
    price_input_per_mtok: Decimal
    price_output_per_mtok: Decimal
    capabilities: frozenset[str]
    reliability_prior: Decimal
    provider: str
    deprecated: bool = False

    def __post_init__(self) -> None:
        require_str(self.model_id, "model_id", max_length=128)
        tier_rank(self.tier)
        require_int(self.context_window, "context_window", minimum=1)
        require_int(self.max_output, "max_output", minimum=1)
        require_decimal(self.price_input_per_mtok, "price_input_per_mtok", minimum=Decimal(0))
        require_decimal(self.price_output_per_mtok, "price_output_per_mtok", minimum=Decimal(0))
        require_bool(self.deprecated, "deprecated")
        require_str(self.provider, "provider", max_length=64)
        prior = require_decimal(self.reliability_prior, "reliability_prior", minimum=Decimal(0))
        if prior > 1:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"reliability_prior={prior} must be in [0, 1]",
                recommended_action="express the prior as a fraction, not a percentage",
            )
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        for capability in self.capabilities:
            require_str(capability, "capability", max_length=64)

    @property
    def rank(self) -> int:
        return tier_rank(self.tier)

    def to_payload(self) -> dict[str, Any]:
        return {
            "modelId": self.model_id,
            "tier": self.tier,
            "provider": self.provider,
            "contextWindow": self.context_window,
            "maxOutput": self.max_output,
            "priceInputPerMtok": self.price_input_per_mtok,
            "priceOutputPerMtok": self.price_output_per_mtok,
            "capabilities": sorted(self.capabilities),
            "reliabilityPrior": self.reliability_prior,
            "deprecated": self.deprecated,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], index: int = 0) -> ModelProfile:
        field_name = f"model_registry[{index}]"
        body = require_mapping(payload, field_name)
        reject_unknown_fields(
            body,
            ("modelId", "tier", "provider", "contextWindow", "maxOutput", "priceInputPerMtok",
             "priceOutputPerMtok", "capabilities", "reliabilityPrior", "deprecated"),
            field_name=field_name,
        )
        return cls(
            model_id=require_str(body.get("modelId"), f"{field_name}.modelId", max_length=128),
            tier=require_str(body.get("tier"), f"{field_name}.tier", max_length=32),
            context_window=require_int(body.get("contextWindow"), f"{field_name}.contextWindow",
                                       minimum=1),
            max_output=require_int(body.get("maxOutput"), f"{field_name}.maxOutput", minimum=1),
            price_input_per_mtok=require_decimal(body.get("priceInputPerMtok"),
                                                 f"{field_name}.priceInputPerMtok",
                                                 minimum=Decimal(0)),
            price_output_per_mtok=require_decimal(body.get("priceOutputPerMtok"),
                                                  f"{field_name}.priceOutputPerMtok",
                                                  minimum=Decimal(0)),
            capabilities=frozenset(require_str_seq(body.get("capabilities", ()),
                                                   f"{field_name}.capabilities")),
            reliability_prior=require_decimal(body.get("reliabilityPrior"),
                                              f"{field_name}.reliabilityPrior",
                                              minimum=Decimal(0)),
            provider=require_str(body.get("provider"), f"{field_name}.provider", max_length=64),
            deprecated=require_bool(body.get("deprecated", False), f"{field_name}.deprecated"),
        )


class ModelRegistry:
    """The set of models this kernel will admit to a route.

    :meth:`resolve` is exact.  It does not normalise case, strip whitespace, match a prefix or
    suggest a near neighbour, because every one of those behaviours turns a typo into traffic.
    The error names the registered ids so a human can fix the table; the kernel does not fix it
    for them.
    """

    __slots__ = ("_profiles",)

    def __init__(self, profiles: Sequence[ModelProfile]) -> None:
        registered: dict[str, ModelProfile] = {}
        for profile in profiles:
            if profile.model_id in registered:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"model {profile.model_id!r} is registered twice",
                    recommended_action="deduplicate the model registry",
                    details={"modelId": profile.model_id},
                )
            registered[profile.model_id] = profile
        self._profiles = dict(sorted(registered.items()))

    def __len__(self) -> int:
        return len(self._profiles)

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def resolve(self, model_id: str) -> ModelProfile:
        """Return the profile for ``model_id`` or raise ``MODEL_NOT_REGISTERED``."""

        profile = self._profiles.get(model_id)
        if profile is None:
            raise KernelError(
                code="MODEL_NOT_REGISTERED",
                message=(
                    f"model {model_id!r} is not in the registry; the router does not guess at "
                    "near matches"
                ),
                retryable=False,
                recommended_action="register the model or correct the id in the routing table",
                details={"modelId": model_id, "registered": list(self._profiles)},
            )
        return profile


# --- policy ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """The floor for one ``(phase, risk_class)`` pair.

    ``cost_ceiling`` is ``Decimal | None`` where ``None`` means *explicitly unbounded*.  The
    distinction is load-bearing: an absent ceiling and a ceiling of zero are opposite
    instructions, and only a policy author may choose between them.

    ``allowed_providers`` is a required set and an empty set denies every provider.  "The policy
    said nothing about providers" resolving to "all providers" is the fail-open bug this whole
    kernel is built against.
    """

    phase: str
    risk_class: str
    min_tier: str
    required_capabilities: frozenset[str]
    cost_ceiling: Decimal | None
    allowed_providers: frozenset[str]
    min_context_window: int = 0
    min_reliability: Decimal = Decimal(0)
    allow_deprecated: bool = False
    allow_de_escalation: bool = False
    escalate_after_attempts: int | None = None
    escalated_min_tier: str | None = None

    def __post_init__(self) -> None:
        _require_phase(self.phase, "rule.phase")
        _require_risk(self.risk_class, "rule.risk_class")
        tier_rank(self.min_tier)
        require_int(self.min_context_window, "min_context_window", minimum=0)
        require_decimal(self.min_reliability, "min_reliability", minimum=Decimal(0))
        require_bool(self.allow_deprecated, "allow_deprecated")
        require_bool(self.allow_de_escalation, "allow_de_escalation")
        if self.cost_ceiling is not None:
            require_decimal(self.cost_ceiling, "cost_ceiling", minimum=Decimal(0))
        object.__setattr__(self, "required_capabilities", frozenset(self.required_capabilities))
        object.__setattr__(self, "allowed_providers", frozenset(self.allowed_providers))
        if self.escalate_after_attempts is not None:
            require_int(self.escalate_after_attempts, "escalate_after_attempts", minimum=1)
            if self.escalated_min_tier is None:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message="escalate_after_attempts requires an escalated_min_tier",
                    recommended_action="state the tier the rule escalates to",
                )
            if tier_rank(self.escalated_min_tier) < tier_rank(self.min_tier):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=(
                        f"escalated_min_tier={self.escalated_min_tier!r} is below "
                        f"min_tier={self.min_tier!r}; escalation never lowers the floor"
                    ),
                    recommended_action="escalate to a tier at least as high as the base floor",
                )
        elif self.escalated_min_tier is not None:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="escalated_min_tier requires escalate_after_attempts",
                recommended_action="state when the escalation applies",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "riskClass": self.risk_class,
            "minTier": self.min_tier,
            "requiredCapabilities": sorted(self.required_capabilities),
            "costCeiling": self.cost_ceiling,
            "allowedProviders": sorted(self.allowed_providers),
            "minContextWindow": self.min_context_window,
            "minReliability": self.min_reliability,
            "allowDeprecated": self.allow_deprecated,
            "allowDeEscalation": self.allow_de_escalation,
            "escalateAfterAttempts": self.escalate_after_attempts,
            "escalatedMinTier": self.escalated_min_tier,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], index: int = 0) -> RoutingRule:
        field_name = f"routing_policy.rules[{index}]"
        body = require_mapping(payload, field_name)
        reject_unknown_fields(
            body,
            ("phase", "riskClass", "minTier", "requiredCapabilities", "costCeiling",
             "allowedProviders", "minContextWindow", "minReliability", "allowDeprecated",
             "allowDeEscalation", "escalateAfterAttempts", "escalatedMinTier"),
            field_name=field_name,
        )
        if "costCeiling" not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=(f"{field_name}.costCeiling is required; "
                         "use null for 'explicitly unbounded'"),
                recommended_action="state the ceiling, or null to declare it unbounded",
            )
        ceiling = body.get("costCeiling")
        attempts = body.get("escalateAfterAttempts")
        return cls(
            phase=_require_phase(body.get("phase"), f"{field_name}.phase"),
            risk_class=_require_risk(body.get("riskClass"), f"{field_name}.riskClass"),
            min_tier=require_str(body.get("minTier"), f"{field_name}.minTier", max_length=32),
            required_capabilities=frozenset(
                require_str_seq(body.get("requiredCapabilities", ()),
                                f"{field_name}.requiredCapabilities")),
            cost_ceiling=(None if ceiling is None
                          else require_decimal(ceiling, f"{field_name}.costCeiling",
                                               minimum=Decimal(0))),
            allowed_providers=frozenset(require_str_seq(body.get("allowedProviders", ()),
                                                        f"{field_name}.allowedProviders")),
            min_context_window=require_int(body.get("minContextWindow", 0),
                                           f"{field_name}.minContextWindow", minimum=0),
            min_reliability=require_decimal(body.get("minReliability", 0),
                                            f"{field_name}.minReliability", minimum=Decimal(0)),
            allow_deprecated=require_bool(body.get("allowDeprecated", False),
                                          f"{field_name}.allowDeprecated"),
            allow_de_escalation=require_bool(body.get("allowDeEscalation", False),
                                             f"{field_name}.allowDeEscalation"),
            escalate_after_attempts=(None if attempts is None
                                     else require_int(attempts,
                                                      f"{field_name}.escalateAfterAttempts",
                                                      minimum=1)),
            escalated_min_tier=(None if body.get("escalatedMinTier") is None
                                else require_str(body["escalatedMinTier"],
                                                 f"{field_name}.escalatedMinTier",
                                                 max_length=32)),
        )


class RoutingPolicy:
    """A lookup from ``(phase, risk_class)`` to the rule that governs it.

    A missing pair is a deny.  There is deliberately no default rule and no inheritance from a
    neighbouring risk class: a routing policy that quietly covers a phase nobody wrote a rule for
    is a policy nobody has actually read.
    """

    __slots__ = ("_rules",)

    def __init__(self, rules: Sequence[RoutingRule]) -> None:
        table: dict[tuple[str, str], RoutingRule] = {}
        for rule in rules:
            key = (rule.phase, rule.risk_class)
            if key in table:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"routing policy declares {key} twice",
                    recommended_action="deduplicate the routing policy",
                    details={"phase": rule.phase, "riskClass": rule.risk_class},
                )
            table[key] = rule
        self._rules = table

    def __len__(self) -> int:
        return len(self._rules)

    def rule_for(self, phase: str, risk_class: str) -> RoutingRule:
        rule = self._rules.get((phase, risk_class))
        if rule is None:
            raise KernelError(
                code="ROUTING_DENIED",
                message=(
                    f"no routing rule covers phase {phase!r} at risk {risk_class!r}; an "
                    "uncovered pair is a deny, not a default"
                ),
                retryable=False,
                recommended_action="add an explicit rule for this phase and risk class",
                details={"phase": phase, "riskClass": risk_class,
                         "covered": sorted(f"{p}/{r}" for p, r in self._rules)},
            )
        return rule


# --- request, budget, cost ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Budget:
    """What is left to spend, in one stated currency.

    ``remaining`` may legitimately be zero — that is "the budget is spent", a real business
    value.  It is never used to stand in for "we could not read the budget"; an unreadable budget
    is an absent :class:`Budget`, which the router refuses to route against when a ceiling
    applies.
    """

    remaining: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        require_decimal(self.remaining, "remaining", minimum=Decimal(0))
        require_str(self.currency, "currency", max_length=8)

    def to_payload(self) -> dict[str, Any]:
        return {"remaining": self.remaining, "currency": self.currency}


@dataclass(frozen=True, slots=True)
class RouteRequest:
    """One routing question: which phase, at what risk, over which candidates.

    ``estimated_input_tokens`` / ``estimated_output_tokens`` are ``int | None`` and ``None``
    means *not estimated*.  ``prior_tier`` is the tier this run has already used; it is what
    makes de-escalation detectable at all.
    """

    phase: str
    risk_class: str
    candidate_model_ids: tuple[str, ...]
    required_capabilities: frozenset[str] = frozenset()
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    attempt_no: int = 1
    prior_tier: str | None = None
    allow_deprecated: bool = False

    def __post_init__(self) -> None:
        _require_phase(self.phase, "phase")
        _require_risk(self.risk_class, "risk_class")
        require_int(self.attempt_no, "attempt_no", minimum=1)
        require_bool(self.allow_deprecated, "allow_deprecated")
        if not self.candidate_model_ids:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="a route request must name at least one candidate model",
                recommended_action="supply the candidate model ids",
            )
        if len(self.candidate_model_ids) > _MAX_CANDIDATES:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"more than {_MAX_CANDIDATES} candidate models",
                recommended_action="pre-filter the candidate set",
            )
        for tokens, name in ((self.estimated_input_tokens, "estimated_input_tokens"),
                             (self.estimated_output_tokens, "estimated_output_tokens")):
            if tokens is not None:
                require_int(tokens, name, minimum=0)
        if self.prior_tier is not None:
            tier_rank(self.prior_tier)
        object.__setattr__(self, "candidate_model_ids",
                           tuple(dict.fromkeys(self.candidate_model_ids)))
        object.__setattr__(self, "required_capabilities",
                           frozenset(self.required_capabilities))

    @property
    def is_estimated(self) -> bool:
        """True only when *both* token estimates are present."""

        return (self.estimated_input_tokens is not None
                and self.estimated_output_tokens is not None)

    def to_payload(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "riskClass": self.risk_class,
            "candidateModelIds": list(self.candidate_model_ids),
            "requiredCapabilities": sorted(self.required_capabilities),
            "estimatedInputTokens": self.estimated_input_tokens,
            "estimatedOutputTokens": self.estimated_output_tokens,
            "attemptNo": self.attempt_no,
            "priorTier": self.prior_tier,
            "allowDeprecated": self.allow_deprecated,
        }


def project_cost(profile: ModelProfile, input_tokens: int, output_tokens: int) -> Decimal:
    """Projected call cost as an exact ``Decimal``.

    Quantised to eight decimal places so that two kernels projecting the same call produce the
    same string and therefore the same digest.  This is a *projection*, never a measurement; the
    decision labels it as such so that nothing downstream bills against it.
    """

    require_int(input_tokens, "input_tokens", minimum=0)
    require_int(output_tokens, "output_tokens", minimum=0)
    total = ((Decimal(input_tokens) * profile.price_input_per_mtok)
             + (Decimal(output_tokens) * profile.price_output_per_mtok)) / _TOKENS_PER_MTOK
    return total.quantize(_COST_EXPONENT, rounding=ROUND_HALF_UP)


# --- decision ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Exclusion:
    """Why one candidate did not win — or did not qualify at all."""

    model_id: str
    decision: str  # SELECTED | FALLBACK | EXCLUDED
    code: str
    detail: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "modelId": self.model_id,
            "decision": self.decision,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """The chosen model, the ordered fallbacks, the projected cost, and the whole reasoning.

    ``projected`` is separate from ``projected_cost`` on purpose.  ``projected_cost is None`` with
    ``projected is False`` says "not estimated"; a ``Decimal("0")`` with ``projected is True``
    says "estimated, and free".  Collapsing those two into a bare zero is the defect this
    repository has shipped three times.
    """

    model_id: str
    tier: str
    provider: str
    fallback_chain: tuple[str, ...]
    projected_cost: Decimal | None
    projected: bool
    effective_min_tier: str
    escalated: bool
    reasons: tuple[Exclusion, ...]
    phase: str
    risk_class: str
    attempt_no: int
    currency: str = "USD"

    def to_payload(self) -> dict[str, Any]:
        core = {
            "modelId": self.model_id,
            "tier": self.tier,
            "provider": self.provider,
            "fallbackChain": list(self.fallback_chain),
            "projectedCost": self.projected_cost,
            "projected": self.projected,
            "currency": self.currency,
            "effectiveMinTier": self.effective_min_tier,
            "escalated": self.escalated,
            "phase": self.phase,
            "riskClass": self.risk_class,
            "attemptNo": self.attempt_no,
            "reasons": [reason.to_payload() for reason in self.reasons],
        }
        return {**core, "digest": digest(core)}

    def usage_record(self) -> dict[str, Any]:
        """The projected (never measured) usage this route implies."""

        return {
            "modelId": self.model_id,
            "provider": self.provider,
            "phase": self.phase,
            "attemptNo": self.attempt_no,
            "projectedCost": self.projected_cost,
            "currency": self.currency,
            "measured": False,
            "projected": self.projected,
        }


def _effective_floor(request: RouteRequest, rule: RoutingRule) -> tuple[str, bool, list[str]]:
    """Compute the tier floor for this attempt, and say what raised it."""

    notes: list[str] = []
    floor = rule.min_tier
    escalated = False
    if (rule.escalate_after_attempts is not None
            and request.phase in ("verify", "repair")
            and request.attempt_no > rule.escalate_after_attempts):
        assert rule.escalated_min_tier is not None  # noqa: S101 - guarded in RoutingRule
        if tier_rank(rule.escalated_min_tier) > tier_rank(floor):
            floor = rule.escalated_min_tier
            notes.append(
                f"attempt {request.attempt_no} exceeds the {rule.escalate_after_attempts}-attempt "
                f"threshold for phase {request.phase!r}; floor raised to {floor!r}"
            )
        escalated = True
    if request.prior_tier is not None and not rule.allow_de_escalation:
        if tier_rank(request.prior_tier) > tier_rank(floor):
            floor = request.prior_tier
            notes.append(
                f"the run already used tier {request.prior_tier!r} and the policy forbids "
                "de-escalation; floor raised to match"
            )
    return floor, escalated, notes


def route(request: RouteRequest, registry: ModelRegistry, policy: RoutingPolicy,
          budget: Budget | None = None) -> RouteDecision:
    """Choose a model, an ordered fallback chain, and record why every other candidate lost.

    Ordering among eligible models is cheapest first, then most reliable, then by id — every
    component an exact integer, ``Decimal`` or string, so the same inputs always produce the same
    chain.  The fallback chain then prefers a *different provider* first: a fallback that shares
    the failed model's provider is not a fallback for the failure mode that actually happens,
    which is the provider being down.
    """

    rule = policy.rule_for(request.phase, request.risk_class)
    floor, escalated, notes = _effective_floor(request, rule)
    floor_rank = tier_rank(floor)
    required = frozenset(rule.required_capabilities | request.required_capabilities)

    reasons: list[Exclusion] = []
    eligible: list[tuple[ModelProfile, Decimal | None]] = []

    # Resolution happens before any filtering: an unregistered id is a configuration error, and
    # dropping it silently would let a typo masquerade as a policy exclusion.
    profiles = [registry.resolve(model_id) for model_id in request.candidate_model_ids]

    for profile in profiles:
        if profile.deprecated and not (rule.allow_deprecated and request.allow_deprecated):
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "MODEL_DEPRECATED",
                "the model is deprecated and both the policy and the request must opt in",
            ))
            continue
        if profile.provider not in rule.allowed_providers:
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "PROVIDER_NOT_ALLOWED",
                f"provider {profile.provider!r} is not in the rule's allow-list "
                f"{sorted(rule.allowed_providers)}",
            ))
            continue
        if profile.rank < floor_rank:
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "TIER_BELOW_MINIMUM",
                f"tier {profile.tier!r} is below the effective floor {floor!r}",
            ))
            continue
        missing = sorted(required - profile.capabilities)
        if missing:
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "MODEL_CAPABILITY_MISMATCH",
                f"missing required capabilities {missing}",
            ))
            continue
        if profile.context_window < rule.min_context_window:
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "CONTEXT_WINDOW_TOO_SMALL",
                f"context window {profile.context_window} is below the required "
                f"{rule.min_context_window}",
            ))
            continue
        if profile.reliability_prior < rule.min_reliability:
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "RELIABILITY_BELOW_FLOOR",
                f"reliability prior {profile.reliability_prior} is below the required "
                f"{rule.min_reliability}",
            ))
            continue
        if (request.estimated_output_tokens is not None
                and profile.max_output < request.estimated_output_tokens):
            reasons.append(Exclusion(
                profile.model_id, "EXCLUDED", "MAX_OUTPUT_TOO_SMALL",
                f"max output {profile.max_output} cannot cover the estimated "
                f"{request.estimated_output_tokens} tokens",
            ))
            continue

        cost: Decimal | None = None
        if request.is_estimated:
            cost = project_cost(profile, request.estimated_input_tokens or 0,
                                request.estimated_output_tokens or 0)
            if rule.cost_ceiling is not None and cost > rule.cost_ceiling:
                reasons.append(Exclusion(
                    profile.model_id, "EXCLUDED", "COST_CEILING_EXCEEDED",
                    f"projected {cost} exceeds the ceiling {rule.cost_ceiling}",
                ))
                continue
            if budget is not None and cost > budget.remaining:
                reasons.append(Exclusion(
                    profile.model_id, "EXCLUDED", "BUDGET_EXHAUSTED",
                    f"projected {cost} exceeds the remaining budget {budget.remaining}",
                ))
                continue
        elif rule.cost_ceiling is not None or budget is not None:
            # No estimate and a bound to honour: refusing is the only honest answer.  Treating
            # the missing estimate as zero would satisfy every ceiling ever written.
            raise KernelError(
                code="COST_ESTIMATE_MISSING",
                message=(
                    "the routing rule states a cost bound but the request carries no token "
                    "estimate; the router will not assume zero"
                ),
                retryable=False,
                recommended_action=(
                    "supply estimatedInputTokens and estimatedOutputTokens, or declare the "
                    "ceiling explicitly unbounded"
                ),
                details={"phase": request.phase, "riskClass": request.risk_class,
                         "costCeiling": str(rule.cost_ceiling)
                         if rule.cost_ceiling is not None else None},
            )
        eligible.append((profile, cost))

    if not eligible:
        raise KernelError(
            code="NO_ELIGIBLE_MODEL",
            message=(
                f"no candidate survived the rule for phase {request.phase!r} at risk "
                f"{request.risk_class!r} (effective floor {floor!r})"
            ),
            retryable=False,
            recommended_action="widen the candidate set or revise the routing rule",
            details={"phase": request.phase, "riskClass": request.risk_class,
                     "effectiveMinTier": floor,
                     "reasons": [reason.to_payload() for reason in reasons]},
        )

    ordered = sorted(
        eligible,
        key=lambda item: (
            item[1] if item[1] is not None else Decimal(0),
            -item[0].reliability_prior,
            item[0].rank,
            item[0].model_id,
        ),
    )
    chosen, chosen_cost = ordered[0]
    rest = [profile for profile, _ in ordered[1:]]
    fallbacks = sorted(
        enumerate(rest),
        key=lambda pair: (pair[1].provider == chosen.provider, pair[0]),
    )
    chain = tuple(profile.model_id for _, profile in fallbacks)

    reasons.append(Exclusion(chosen.model_id, "SELECTED", "ELIGIBLE",
                             "; ".join(notes) if notes else
                             f"cheapest eligible candidate at or above tier {floor!r}"))
    for position, model_id in enumerate(chain):
        reasons.append(Exclusion(
            model_id, "FALLBACK", "ELIGIBLE",
            f"fallback position {position}"
            + ("" if _provider_of(rest, model_id) != chosen.provider
               else " (same provider as the primary)"),
        ))

    return RouteDecision(
        model_id=chosen.model_id,
        tier=chosen.tier,
        provider=chosen.provider,
        fallback_chain=chain,
        projected_cost=chosen_cost,
        projected=chosen_cost is not None,
        effective_min_tier=floor,
        escalated=escalated,
        reasons=tuple(sorted(reasons, key=lambda item: (item.decision, item.model_id))),
        phase=request.phase,
        risk_class=request.risk_class,
        attempt_no=request.attempt_no,
        currency=budget.currency if budget is not None else "USD",
    )


def _provider_of(profiles: Sequence[ModelProfile], model_id: str) -> str:
    for profile in profiles:
        if profile.model_id == model_id:
            return profile.provider
    return ""


def escalation_plan(request: RouteRequest, rule: RoutingRule) -> dict[str, Any]:
    """What would raise the floor on a later attempt, stated up front."""

    return {
        "phase": request.phase,
        "attemptNo": request.attempt_no,
        "escalateAfterAttempts": rule.escalate_after_attempts,
        "escalatedMinTier": rule.escalated_min_tier,
        "deEscalationAllowed": rule.allow_de_escalation,
        "baseMinTier": rule.min_tier,
    }


# --- registry entry point ----------------------------------------------------


@register("phase-aware-model-router")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``phase-aware-model-router``."""

    body = require_mapping(request, "request")
    reject_unknown_fields(
        body,
        ("step_profile", "model_registry", "routing_policy", "budget"),
        field_name="request",
    )
    for required in ("step_profile", "model_registry", "routing_policy"):
        if required not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{required} is required",
                recommended_action=f"supply {required}",
            )

    raw_registry = body["model_registry"]
    if not isinstance(raw_registry, Sequence) or isinstance(raw_registry, (str, bytes)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="model_registry must be an array of model profiles",
            recommended_action="supply model_registry as a JSON array",
        )
    registry = ModelRegistry([ModelProfile.from_payload(item, index)
                              for index, item in enumerate(raw_registry)])

    policy_body = require_mapping(body["routing_policy"], "routing_policy")
    reject_unknown_fields(policy_body, ("rules",), field_name="routing_policy")
    raw_rules = policy_body.get("rules")
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="routing_policy.rules must be an array",
            recommended_action="supply routing_policy.rules as a JSON array",
        )
    policy = RoutingPolicy([RoutingRule.from_payload(item, index)
                            for index, item in enumerate(raw_rules)])

    step = require_mapping(body["step_profile"], "step_profile")
    reject_unknown_fields(
        step,
        ("phase", "riskClass", "candidateModelIds", "requiredCapabilities",
         "estimatedInputTokens", "estimatedOutputTokens", "attemptNo", "priorTier",
         "allowDeprecated"),
        field_name="step_profile",
    )
    route_request = RouteRequest(
        phase=_require_phase(step.get("phase"), "step_profile.phase"),
        risk_class=_require_risk(step.get("riskClass"), "step_profile.riskClass"),
        candidate_model_ids=require_str_seq(step.get("candidateModelIds", ()),
                                            "step_profile.candidateModelIds",
                                            allow_empty=False),
        required_capabilities=frozenset(
            require_str_seq(step.get("requiredCapabilities", ()),
                            "step_profile.requiredCapabilities")),
        estimated_input_tokens=(None if step.get("estimatedInputTokens") is None
                                else require_int(step["estimatedInputTokens"],
                                                 "step_profile.estimatedInputTokens", minimum=0)),
        estimated_output_tokens=(None if step.get("estimatedOutputTokens") is None
                                 else require_int(step["estimatedOutputTokens"],
                                                  "step_profile.estimatedOutputTokens",
                                                  minimum=0)),
        attempt_no=require_int(step.get("attemptNo", 1), "step_profile.attemptNo", minimum=1),
        prior_tier=(None if step.get("priorTier") is None
                    else require_str(step["priorTier"], "step_profile.priorTier", max_length=32)),
        allow_deprecated=require_bool(step.get("allowDeprecated", False),
                                      "step_profile.allowDeprecated"),
    )

    budget: Budget | None = None
    if body.get("budget") is not None:
        budget_body = require_mapping(body["budget"], "budget")
        reject_unknown_fields(budget_body, ("remaining", "currency"), field_name="budget")
        budget = Budget(
            remaining=require_decimal(budget_body.get("remaining"), "budget.remaining",
                                      minimum=Decimal(0)),
            currency=require_str(budget_body.get("currency", "USD"), "budget.currency",
                                 max_length=8),
        )

    decision = route(route_request, registry, policy, budget)
    rule = policy.rule_for(route_request.phase, route_request.risk_class)
    return {
        "routing_decision": decision.to_payload(),
        "fallback_chain": list(decision.fallback_chain),
        "escalation_plan": escalation_plan(route_request, rule),
        "estimated_cost": {
            "amount": decision.projected_cost,
            "currency": decision.currency,
            "projected": decision.projected,
            "measured": False,
        },
        "usage_record": decision.usage_record(),
    }
