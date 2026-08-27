"""Recipes: the only thing allowed to produce a final patch.

A Recipe is a signed, versioned, idempotent transformation with an explicit
proof obligation attached to every stage:

``applicability``
    Is this Recipe *about* this repository at all?
``preconditions``
    Is the specific state it needs actually true right now?
``negativeGuards``
    Is there a reason this must **not** run, even though it could?
``actions``
    The transformation itself, each with an expected cardinality.
``postconditions``
    Is the result what the Recipe claimed it would be?
``rollback`` / ``idempotence``
    Can it be undone, and is a second run a no-op?

Two rules are enforced mechanically rather than left to reviewers:

* **Cardinality is a contract.**  An action declaring ``{min: 1, max: 1}`` that
  matches three symbols fails; it does not edit three symbols.
* **A selector may not widen itself.**  Paths are resolved against the
  Recipe's declared file globs, and a match outside them is a scope expansion,
  not a bonus.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    ConflictPolicy,
    ContractError,
    FormatPolicy,
    OnUnknown,
    PredicateType,
    RecipeStatus,
    RiskClass,
    RollbackStrategy,
    integer_value,
    match_path_glob,
    optional_string,
    reject_unknown_fields,
    require_bool,
    require_digest,
    require_enum,
    require_identifier,
    require_mapping,
    require_mapping_sequence,
    require_string,
    require_string_sequence,
    sha256_payload,
)
from .expressions import UNKNOWN, compile_expression
from .index import SemanticEntity, SemanticIndex

RECIPE_KIND = "RefactorRecipe"
API_VERSION = "elmos.dev/v1"

#: Maximum wall-clock a Recipe may request for one validation gate.  A Recipe
#: that wants longer has to say so through policy, not through its own file.
MAX_VALIDATION_TIMEOUT_SECONDS = 7200


@dataclass(frozen=True, slots=True)
class Predicate:
    type: PredicateType
    expression: str
    id: str = ""
    expected: Any = None
    on_unknown: OnUnknown = OnUnknown.FAIL
    message: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type.value, "expression": self.expression}
        if self.id:
            payload["id"] = self.id
        if self.expected is not None:
            payload["expected"] = self.expected
        payload["onUnknown"] = self.on_unknown.value
        if self.message:
            payload["message"] = self.message
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> Predicate:
        reject_unknown_fields(value, {"id", "type", "expression", "expected", "onUnknown", "message"}, "predicate")
        expression = require_string(value.get("expression"), "predicate.expression", max_length=4096)
        compile_expression(expression)
        return cls(
            type=require_enum(value.get("type"), PredicateType, "predicate.type"),
            expression=expression,
            id=optional_string(value.get("id"), "predicate.id", max_length=128) or "",
            expected=value.get("expected"),
            on_unknown=require_enum(value.get("onUnknown", "fail"), OnUnknown, "predicate.onUnknown"),
            message=optional_string(value.get("message"), "predicate.message", max_length=2048) or "",
        )


@dataclass(frozen=True, slots=True)
class Cardinality:
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if self.maximum < self.minimum:
            raise ContractError("invalid_cardinality", "expectedCardinality.max must be >= min")

    def contains(self, count: int) -> bool:
        return self.minimum <= count <= self.maximum

    def to_payload(self) -> dict[str, Any]:
        return {"min": self.minimum, "max": self.maximum}


@dataclass(frozen=True, slots=True)
class RecipeAction:
    id: str
    operation: str
    selector: Mapping[str, Any]
    expected_cardinality: Cardinality
    parameters: Mapping[str, Any] = field(default_factory=dict)
    conflict_policy: ConflictPolicy = ConflictPolicy.FAIL
    format_policy: FormatPolicy = FormatPolicy.TOUCHED_RANGE

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "operation": self.operation,
            "selector": dict(self.selector),
            "expectedCardinality": self.expected_cardinality.to_payload(),
            "conflictPolicy": self.conflict_policy.value,
            "formatPolicy": self.format_policy.value,
        }
        if self.parameters:
            payload["parameters"] = dict(self.parameters)
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> RecipeAction:
        reject_unknown_fields(
            value,
            {"id", "operation", "selector", "parameters", "expectedCardinality", "conflictPolicy", "formatPolicy"},
            "action",
        )
        cardinality = require_mapping(value.get("expectedCardinality"), "action.expectedCardinality")
        reject_unknown_fields(cardinality, {"min", "max"}, "action.expectedCardinality")
        format_policy = require_enum(
            value.get("formatPolicy", "touched-range"), FormatPolicy, "action.formatPolicy"
        )
        if format_policy is FormatPolicy.REPOSITORY:
            raise ContractError(
                "repository_wide_formatting_forbidden",
                "formatPolicy 'repository' would reformat untouched code and hide the real diff",
            )
        return cls(
            id=require_identifier(value.get("id"), "action.id"),
            operation=require_string(value.get("operation"), "action.operation", max_length=128),
            selector=dict(require_mapping(value.get("selector"), "action.selector")),
            expected_cardinality=Cardinality(
                minimum=integer_value(cardinality.get("min"), "action.expectedCardinality.min", minimum=0),
                maximum=integer_value(cardinality.get("max"), "action.expectedCardinality.max", minimum=0),
            ),
            parameters=dict(require_mapping(value.get("parameters", {}), "action.parameters")),
            conflict_policy=require_enum(
                value.get("conflictPolicy", "fail"), ConflictPolicy, "action.conflictPolicy"
            ),
            format_policy=format_policy,
        )


@dataclass(frozen=True, slots=True)
class ValidationGate:
    gate: str
    blocking: bool
    command: str = ""
    profile: str = ""
    timeout_seconds: int = 900

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "gate": self.gate,
            "blocking": self.blocking,
            "timeoutSeconds": self.timeout_seconds,
        }
        if self.command:
            payload["command"] = self.command
        if self.profile:
            payload["profile"] = self.profile
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> ValidationGate:
        reject_unknown_fields(value, {"gate", "command", "profile", "blocking", "timeoutSeconds"}, "validation")
        return cls(
            gate=require_string(value.get("gate"), "validation.gate", max_length=128),
            blocking=require_bool(value.get("blocking"), "validation.blocking"),
            command=optional_string(value.get("command"), "validation.command", max_length=4096) or "",
            profile=optional_string(value.get("profile"), "validation.profile") or "",
            timeout_seconds=integer_value(
                value.get("timeoutSeconds", 900),
                "validation.timeoutSeconds",
                minimum=1,
                maximum=MAX_VALIDATION_TIMEOUT_SECONDS,
            ),
        )


@dataclass(frozen=True, slots=True)
class RecipeRollback:
    strategy: RollbackStrategy
    actions: tuple[RecipeAction, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"strategy": self.strategy.value}
        if self.actions:
            payload["actions"] = [item.to_payload() for item in self.actions]
        return payload


@dataclass(frozen=True, slots=True)
class Recipe:
    name: str
    version: str
    languages: tuple[str, ...]
    risk_class: RiskClass
    applicability: tuple[Predicate, ...]
    preconditions: tuple[Predicate, ...]
    negative_guards: tuple[Predicate, ...]
    actions: tuple[RecipeAction, ...]
    postconditions: tuple[Predicate, ...]
    validation: tuple[ValidationGate, ...]
    rollback: RecipeRollback
    idempotence_key: str = ""
    status: RecipeStatus = RecipeStatus.DRAFT
    frameworks: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    description: str = ""
    tags: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    select: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    declared_digest: str | None = None

    # -- identity --------------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {"name": self.name, "version": self.version, "status": self.status.value}
        if self.owners:
            metadata["owners"] = list(self.owners)
        if self.description:
            metadata["description"] = self.description
        if self.tags:
            metadata["tags"] = list(self.tags)
        spec: dict[str, Any] = {
            "languages": list(self.languages),
            "riskClass": self.risk_class.value,
            "applicability": [item.to_payload() for item in self.applicability],
            "preconditions": [item.to_payload() for item in self.preconditions],
            "negativeGuards": [item.to_payload() for item in self.negative_guards],
            "actions": [item.to_payload() for item in self.actions],
            "postconditions": [item.to_payload() for item in self.postconditions],
            "validation": [item.to_payload() for item in self.validation],
            "rollback": self.rollback.to_payload(),
            "idempotence": {"secondRunExpectedDiff": "empty"}
            | ({"key": self.idempotence_key} if self.idempotence_key else {}),
        }
        if self.frameworks:
            spec["frameworks"] = list(self.frameworks)
        if self.parameters:
            spec["parameters"] = dict(self.parameters)
        if self.select:
            spec["select"] = dict(self.select)
        if self.evidence:
            spec["evidence"] = list(self.evidence)
        return {"apiVersion": API_VERSION, "kind": RECIPE_KIND, "metadata": metadata, "spec": spec}

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    @property
    def reference(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def file_globs(self) -> tuple[str, ...]:
        globs = self.select.get("paths") if isinstance(self.select, Mapping) else None
        if isinstance(globs, Sequence) and not isinstance(globs, str):
            return tuple(str(item) for item in globs)
        return ()

    def action(self, action_id: str) -> RecipeAction:
        for item in self.actions:
            if item.id == action_id:
                return item
        raise ContractError("unknown_action", f"recipe '{self.reference}' has no action '{action_id}'")

    def autonomous_eligible(self) -> bool:
        return self.status.autonomous_eligible

    # -- parsing ---------------------------------------------------------

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Recipe:
        value = require_mapping(payload, "recipe")
        reject_unknown_fields(value, {"apiVersion", "kind", "metadata", "spec"}, "recipe")
        if value.get("apiVersion") != API_VERSION:
            raise ContractError("invalid_api_version", f"recipe.apiVersion must be {API_VERSION}")
        if value.get("kind") != RECIPE_KIND:
            raise ContractError("invalid_kind", f"recipe.kind must be {RECIPE_KIND}")
        metadata = require_mapping(value.get("metadata"), "recipe.metadata")
        reject_unknown_fields(
            metadata, {"name", "version", "digest", "status", "owners", "description", "tags"}, "recipe.metadata"
        )
        spec = require_mapping(value.get("spec"), "recipe.spec")
        reject_unknown_fields(
            spec,
            {
                "languages",
                "frameworks",
                "riskClass",
                "parameters",
                "applicability",
                "preconditions",
                "negativeGuards",
                "select",
                "actions",
                "postconditions",
                "validation",
                "rollback",
                "idempotence",
                "evidence",
                "plugin",
            },
            "recipe.spec",
        )
        if "plugin" in spec:
            plugin = require_mapping(spec["plugin"], "recipe.spec.plugin")
            digest = plugin.get("digest")
            if digest is None:
                raise ContractError(
                    "unsigned_plugin",
                    "a Recipe plugin must carry a content digest; unsigned code is never executed",
                )
            require_digest(digest, "recipe.spec.plugin.digest")

        idempotence = require_mapping(spec.get("idempotence"), "recipe.spec.idempotence")
        reject_unknown_fields(idempotence, {"secondRunExpectedDiff", "key"}, "recipe.spec.idempotence")
        if idempotence.get("secondRunExpectedDiff") != "empty":
            raise ContractError(
                "non_idempotent_recipe",
                "every Recipe must declare secondRunExpectedDiff: empty",
            )
        rollback_raw = require_mapping(spec.get("rollback"), "recipe.spec.rollback")
        reject_unknown_fields(rollback_raw, {"strategy", "actions"}, "recipe.spec.rollback")

        actions = tuple(
            RecipeAction.from_payload(item)
            for item in require_mapping_sequence(spec.get("actions"), "recipe.spec.actions", allow_empty=False)
        )
        action_ids = [item.id for item in actions]
        if len(set(action_ids)) != len(action_ids):
            raise ContractError("duplicate_action_id", "recipe action ids must be unique")

        recipe = cls(
            name=require_string(metadata.get("name"), "recipe.metadata.name", max_length=128),
            version=require_string(metadata.get("version"), "recipe.metadata.version", max_length=64),
            languages=require_string_sequence(
                spec.get("languages"), "recipe.spec.languages", allow_empty=False, unique=True
            ),
            risk_class=require_enum(spec.get("riskClass"), RiskClass, "recipe.spec.riskClass"),
            applicability=_predicates(spec.get("applicability", ()), "recipe.spec.applicability"),
            preconditions=_predicates(spec.get("preconditions", ()), "recipe.spec.preconditions"),
            negative_guards=_predicates(spec.get("negativeGuards", ()), "recipe.spec.negativeGuards"),
            actions=actions,
            postconditions=_predicates(
                spec.get("postconditions"), "recipe.spec.postconditions", allow_empty=False
            ),
            validation=tuple(
                ValidationGate.from_payload(item)
                for item in require_mapping_sequence(
                    spec.get("validation"), "recipe.spec.validation", allow_empty=False
                )
            ),
            rollback=RecipeRollback(
                strategy=require_enum(rollback_raw.get("strategy"), RollbackStrategy, "recipe.spec.rollback.strategy"),
                actions=tuple(
                    RecipeAction.from_payload(item)
                    for item in require_mapping_sequence(
                        rollback_raw.get("actions", ()), "recipe.spec.rollback.actions"
                    )
                ),
            ),
            idempotence_key=optional_string(idempotence.get("key"), "recipe.spec.idempotence.key") or "",
            status=require_enum(metadata.get("status", "draft"), RecipeStatus, "recipe.metadata.status"),
            frameworks=require_string_sequence(spec.get("frameworks", ()), "recipe.spec.frameworks"),
            owners=require_string_sequence(metadata.get("owners", ()), "recipe.metadata.owners"),
            description=optional_string(metadata.get("description"), "recipe.metadata.description", max_length=4096)
            or "",
            tags=require_string_sequence(metadata.get("tags", ()), "recipe.metadata.tags"),
            parameters=dict(require_mapping(spec.get("parameters", {}), "recipe.spec.parameters")),
            select=dict(require_mapping(spec.get("select", {}), "recipe.spec.select")),
            evidence=require_string_sequence(spec.get("evidence", ()), "recipe.spec.evidence"),
            declared_digest=None
            if metadata.get("digest") is None
            else require_digest(metadata["digest"], "recipe.metadata.digest"),
        )
        if recipe.declared_digest is not None and recipe.declared_digest != recipe.digest:
            raise ContractError(
                "recipe_digest_mismatch",
                f"declared digest for '{recipe.reference}' does not match its content",
            )
        return recipe


def _predicates(value: Any, field_name: str, *, allow_empty: bool = True) -> tuple[Predicate, ...]:
    return tuple(
        Predicate.from_payload(item)
        for item in require_mapping_sequence(value, field_name, allow_empty=allow_empty)
    )


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PredicateOutcome:
    predicate: Predicate
    result: str  # satisfied | violated | unknown
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.predicate.id,
            "type": self.predicate.type.value,
            "expression": self.predicate.expression,
            "result": self.result,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PredicateReport:
    outcomes: tuple[PredicateOutcome, ...]
    requires_approval: tuple[str, ...] = ()

    @property
    def satisfied(self) -> bool:
        return all(item.result == "satisfied" for item in self.outcomes)

    @property
    def violations(self) -> tuple[PredicateOutcome, ...]:
        return tuple(item for item in self.outcomes if item.result == "violated")

    @property
    def unknowns(self) -> tuple[PredicateOutcome, ...]:
        return tuple(item for item in self.outcomes if item.result == "unknown")

    def to_payload(self) -> dict[str, Any]:
        return {
            "satisfied": self.satisfied,
            "outcomes": [item.to_payload() for item in self.outcomes],
            "requiresApproval": list(self.requires_approval),
        }


def evaluate_predicates(
    predicates: Sequence[Predicate],
    context: Mapping[str, Any],
    *,
    negated: bool = False,
) -> PredicateReport:
    """Evaluate predicates three-valued, honouring each one's ``onUnknown``.

    ``negated`` is used for ``negativeGuards``: a guard that evaluates *true*
    is a violation, because the guard describes a reason not to proceed.
    """

    outcomes: list[PredicateOutcome] = []
    approvals: list[str] = []
    for predicate in predicates:
        try:
            value = compile_expression(predicate.expression).evaluate(context)
        except ContractError as error:
            outcomes.append(PredicateOutcome(predicate, "violated", f"expression error: {error.message}"))
            continue
        if value is UNKNOWN:
            if predicate.on_unknown is OnUnknown.WARN:
                outcomes.append(PredicateOutcome(predicate, "satisfied", "undecidable; downgraded to a warning"))
            elif predicate.on_unknown is OnUnknown.APPROVAL:
                outcomes.append(PredicateOutcome(predicate, "unknown", "undecidable; escalated for approval"))
                approvals.append(predicate.id or predicate.expression)
            else:
                outcomes.append(PredicateOutcome(predicate, "violated", "undecidable and onUnknown=fail"))
            continue
        truth = bool(value)
        if predicate.expected is not None:
            truth = value == predicate.expected
        satisfied = (not truth) if negated else truth
        outcomes.append(
            PredicateOutcome(
                predicate,
                "satisfied" if satisfied else "violated",
                predicate.message if not satisfied else "",
            )
        )
    return PredicateReport(outcomes=tuple(outcomes), requires_approval=tuple(approvals))


# ---------------------------------------------------------------------------
# Selector resolution
# ---------------------------------------------------------------------------

SELECTOR_KINDS = ("symbol", "file", "module", "import", "database-object", "config-key", "api-contract")


@dataclass(frozen=True, slots=True)
class SelectorMatch:
    path: str
    entity_id: str = ""
    qualified_name: str = ""
    name: str = ""
    language: str = ""
    scope: str = "module"

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "entityId": self.entity_id,
            "qualifiedName": self.qualified_name,
            "name": self.name,
            "language": self.language,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class SelectorResolution:
    action_id: str
    matches: tuple[SelectorMatch, ...]
    out_of_scope: tuple[str, ...] = ()
    reason: str = ""

    @property
    def count(self) -> int:
        return len(self.matches)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(sorted({item.path for item in self.matches}))

    def to_payload(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "count": self.count,
            "matches": [item.to_payload() for item in self.matches[:500]],
            "truncated": self.count > 500,
            "outOfScope": list(self.out_of_scope),
            "reason": self.reason,
        }


def resolve_selector(
    action: RecipeAction,
    index: SemanticIndex,
    *,
    allowed_globs: Sequence[str] = (),
    parameters: Mapping[str, Any] | None = None,
) -> SelectorResolution:
    """Resolve one action's selector against the semantic index.

    Matches outside ``allowed_globs`` are *reported*, not silently dropped and
    not silently included: a Recipe whose selector reaches beyond its declared
    file set is a scope expansion the caller has to decide about.
    """

    selector = _substitute(action.selector, parameters or {})
    kind = str(selector.get("kind", "symbol"))
    if kind not in SELECTOR_KINDS:
        raise ContractError("unknown_selector_kind", f"selector kind '{kind}' is not supported")

    language = selector.get("language")
    qualified = selector.get("qualifiedName")
    name = selector.get("name")
    visibility = selector.get("visibility")
    paths = selector.get("paths")
    path_globs: tuple[str, ...] = ()
    if isinstance(paths, Sequence) and not isinstance(paths, str):
        path_globs = tuple(str(item) for item in paths)

    candidates: list[SemanticEntity] = []
    if kind == "file":
        candidates = [
            entity
            for entity in index.entities
            if entity.kind.value in ("source-file", "generated-file")
            and (not path_globs or any(match_path_glob(entity.path, glob) for glob in path_globs))
        ]
    else:
        wanted_kinds = {
            "symbol": {"type", "function", "method", "property", "field", "variable", "macro", "template"},
            "module": {"module", "package", "namespace", "source-file"},
            "import": {"module", "package"},
            "database-object": {"database-object"},
            "config-key": {"config-key"},
            "api-contract": {"api-contract", "event-contract"},
        }[kind]
        for entity in index.entities:
            if entity.kind.value not in wanted_kinds:
                continue
            if language is not None and entity.language != language:
                continue
            if qualified is not None and entity.qualified_name != qualified:
                continue
            if name is not None and entity.name != name:
                continue
            if visibility is not None and entity.visibility != visibility:
                continue
            if path_globs and not any(match_path_glob(entity.path, glob) for glob in path_globs):
                continue
            candidates.append(entity)

    matches: list[SelectorMatch] = []
    out_of_scope: list[str] = []
    for entity in candidates:
        if allowed_globs and not any(match_path_glob(entity.path, glob) for glob in allowed_globs):
            out_of_scope.append(entity.path)
            continue
        matches.append(
            SelectorMatch(
                path=entity.path,
                entity_id=entity.id,
                qualified_name=entity.qualified_name,
                name=entity.name,
                language=entity.language,
                scope=_scope_of(entity),
            )
        )
    matches.sort(key=lambda item: (item.path, item.qualified_name, item.name))
    return SelectorResolution(
        action_id=action.id,
        matches=tuple(matches),
        out_of_scope=tuple(sorted(set(out_of_scope))),
    )


def _scope_of(entity: SemanticEntity) -> str:
    """The declaring scope path a Python operation needs (``Class`` or ``module``)."""

    qualified = entity.qualified_name
    if not qualified or "." not in qualified:
        return "module"
    parts = qualified.split(".")
    if entity.kind.value in ("method", "property", "field") and len(parts) >= 2:
        return parts[-2]
    return "module"


def _substitute(value: Any, parameters: Mapping[str, Any]) -> Any:
    """Replace ``${name}`` placeholders from the Recipe's parameters."""

    if isinstance(value, str):
        result = value
        for key, item in parameters.items():
            result = result.replace(f"${{{key}}}", str(item))
        if "${" in result:
            raise ContractError("unbound_parameter", f"selector references an unbound parameter: '{result}'")
        return result
    if isinstance(value, Mapping):
        return {key: _substitute(item, parameters) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_substitute(item, parameters) for item in value]
    return value


def check_cardinality(action: RecipeAction, resolution: SelectorResolution) -> str | None:
    """Return a violation message, or ``None`` when the count is as declared."""

    if action.expected_cardinality.contains(resolution.count):
        return None
    return (
        f"action '{action.id}' matched {resolution.count} target(s) but declared "
        f"[{action.expected_cardinality.minimum}, {action.expected_cardinality.maximum}]"
    )


def bind_parameters(recipe: Recipe, supplied: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and default a Recipe's parameters."""

    declared = recipe.parameters
    unknown = sorted(set(supplied) - set(declared))
    if unknown:
        raise ContractError(
            "unknown_recipe_parameter",
            f"recipe '{recipe.reference}' has no parameter(s): " + ", ".join(unknown),
        )
    bound: dict[str, Any] = {}
    for name, definition in declared.items():
        spec = require_mapping(definition, f"recipe.parameters.{name}")
        if name in supplied:
            bound[name] = supplied[name]
        elif "default" in spec:
            bound[name] = spec["default"]
        elif spec.get("required", False):
            raise ContractError("missing_recipe_parameter", f"parameter '{name}' is required")
        else:
            continue
        expected = spec.get("type")
        value = bound[name]
        checks: Mapping[str, type | tuple[type, ...]] = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": (list, tuple),
            "object": dict,
        }
        python_type = checks.get(str(expected))
        if python_type is not None and not isinstance(value, python_type):
            raise ContractError(
                "invalid_recipe_parameter",
                f"parameter '{name}' must be of type {expected}",
            )
        pattern = spec.get("pattern")
        if pattern is not None and isinstance(value, str):
            import re

            if not re.fullmatch(str(pattern), value):
                raise ContractError(
                    "invalid_recipe_parameter", f"parameter '{name}' does not match {pattern}"
                )
        allowed = spec.get("enum")
        if isinstance(allowed, Sequence) and not isinstance(allowed, str) and value not in allowed:
            raise ContractError("invalid_recipe_parameter", f"parameter '{name}' is not an allowed value")
    return bound


# ---------------------------------------------------------------------------
# Recipe lock
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LockedRecipe:
    reference: str
    digest: str
    status: RecipeStatus
    parameters: Mapping[str, Any]
    adapter: str
    adapter_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "digest": self.digest,
            "status": self.status.value,
            "parameters": dict(sorted(self.parameters.items())),
            "adapter": self.adapter,
            "adapterDigest": self.adapter_digest,
        }


@dataclass(frozen=True, slots=True)
class RecipeLock:
    """The frozen, digest-bound set of Recipes one run may execute."""

    recipes: tuple[LockedRecipe, ...]
    toolchain_digest: str = ""
    index_digest: str = ""
    formatter: str = "preserve"

    def to_payload(self) -> dict[str, Any]:
        return {
            "recipes": [item.to_payload() for item in self.recipes],
            "toolchainDigest": self.toolchain_digest,
            "indexDigest": self.index_digest,
            "formatter": self.formatter,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    def entry(self, reference: str) -> LockedRecipe:
        for item in self.recipes:
            if item.reference == reference:
                return item
        raise ContractError("recipe_not_locked", f"'{reference}' is not present in the recipe lock")

    @property
    def draft_references(self) -> tuple[str, ...]:
        return tuple(item.reference for item in self.recipes if not item.status.autonomous_eligible)


__all__ = [
    "API_VERSION",
    "MAX_VALIDATION_TIMEOUT_SECONDS",
    "RECIPE_KIND",
    "SELECTOR_KINDS",
    "Cardinality",
    "LockedRecipe",
    "Predicate",
    "PredicateOutcome",
    "PredicateReport",
    "Recipe",
    "RecipeAction",
    "RecipeLock",
    "RecipeRollback",
    "SelectorMatch",
    "SelectorResolution",
    "ValidationGate",
    "bind_parameters",
    "check_cardinality",
    "evaluate_predicates",
    "resolve_selector",
]
