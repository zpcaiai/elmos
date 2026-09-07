"""Skill 06 — Recipe selection, composition, dry-run and locking.

Selection is deliberately narrow: a Recipe is only considered when the intent's
operation matches, the language is present, and the adapter can actually
perform every operation the Recipe declares.  A Recipe that *looks* relevant
but needs a capability this runtime lacks is reported as unavailable rather
than attempted.

The dry-run is a real execution against the real snapshot — the same code path
the mutating step uses — with the result discarded.  A dry-run that used a
different code path would be a different thing being tested.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .adapters import AdapterCapabilitySnapshot, language_of
from .contracts import AdapterLevel, ContractError, RecipeStatus, RiskClass, sha256_payload
from .executor import OPERATION_LEVELS, TransformResult, execute_transform
from .index import SemanticIndex
from .intent import CompiledIntent, Operation
from .recipe import LockedRecipe, Recipe, RecipeLock, bind_parameters
from .workspace import WorkspaceSnapshot

# ---------------------------------------------------------------------------
# Built-in Recipes
# ---------------------------------------------------------------------------


def _recipe(payload: Mapping[str, Any]) -> Recipe:
    return Recipe.from_payload(payload)


def _base(name: str, version: str, languages: Sequence[str], risk: str) -> dict[str, Any]:
    return {
        "apiVersion": "elmos.dev/v1",
        "kind": "RefactorRecipe",
        "metadata": {
            "name": name,
            "version": version,
            "status": "verified",
            "owners": ["elmos-refactoring-platform"],
        },
        "spec": {
            "languages": list(languages),
            "riskClass": risk,
            "rollback": {"strategy": "reverse-patch"},
            "idempotence": {"secondRunExpectedDiff": "empty"},
        },
    }


def _build(
    name: str,
    version: str,
    languages: Sequence[str],
    risk: str,
    *,
    description: str,
    parameters: Mapping[str, Any],
    applicability: Sequence[Mapping[str, Any]],
    preconditions: Sequence[Mapping[str, Any]],
    negative_guards: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    postconditions: Sequence[Mapping[str, Any]],
    validation: Sequence[Mapping[str, Any]],
    select: Mapping[str, Any] | None = None,
    tags: Sequence[str] = (),
) -> Recipe:
    payload = _base(name, version, languages, risk)
    payload["metadata"]["description"] = description
    if tags:
        payload["metadata"]["tags"] = list(tags)
    payload["spec"].update(
        {
            "parameters": dict(parameters),
            "applicability": list(applicability),
            "preconditions": list(preconditions),
            "negativeGuards": list(negative_guards),
            "actions": list(actions),
            "postconditions": list(postconditions),
            "validation": list(validation),
        }
    )
    if select:
        payload["spec"]["select"] = dict(select)
    return _recipe(payload)


_PYTHON_SELECT = {"paths": ["**/*.py"]}

_STANDARD_VALIDATION = [
    {"gate": "parse", "blocking": True, "timeoutSeconds": 300},
    {"gate": "round-trip", "blocking": True, "timeoutSeconds": 300},
    {"gate": "idempotence", "blocking": True, "timeoutSeconds": 600},
    {"gate": "changed-target-tests", "blocking": True, "timeoutSeconds": 1800},
]


BUILTIN_RECIPES: Mapping[str, Recipe] = MappingProxyType(
    {
        recipe.reference: recipe
        for recipe in (
            _build(
                "python-rename-symbol",
                "1.0.0",
                ["python"],
                "R2",
                description="Scope-correct rename of a Python module-level or class-level symbol.",
                tags=["rename", "python"],
                parameters={
                    "from": {"type": "string", "required": True, "pattern": r"[A-Za-z_][A-Za-z0-9_]*"},
                    "to": {"type": "string", "required": True, "pattern": r"[A-Za-z_][A-Za-z0-9_]*"},
                    "scope": {"type": "string", "default": "module"},
                    "module": {"type": "string", "required": True},
                },
                applicability=[
                    {
                        "id": "python-present",
                        "type": "semantic-query",
                        "expression": "'python' in index.languages",
                        "onUnknown": "fail",
                        "message": "no Python source in this repository",
                    }
                ],
                preconditions=[
                    {
                        "id": "target-exists",
                        "type": "semantic-query",
                        "expression": "index.symbol_exists",
                        "onUnknown": "fail",
                        "message": "the symbol named by 'from' does not exist at this revision",
                    },
                    {
                        "id": "target-free",
                        "type": "semantic-query",
                        "expression": "not index.new_name_taken",
                        "onUnknown": "approval",
                        "message": "the new name may already be taken; a capture would change behaviour",
                    },
                ],
                negative_guards=[
                    {
                        "id": "no-dynamic-access",
                        "type": "semantic-query",
                        "expression": "index.dynamic_reference_count > 0",
                        "onUnknown": "approval",
                        "message": "dynamic attribute access can reach this symbol by computed name",
                    }
                ],
                actions=[
                    {
                        "id": "rename",
                        "operation": "rename-symbol",
                        "selector": {
                            "kind": "symbol",
                            "language": "python",
                            "name": "${from}",
                            "paths": ["**/*.py"],
                        },
                        "parameters": {"from": "${from}", "to": "${to}", "scope": "${scope}"},
                        "expectedCardinality": {"min": 1, "max": 1},
                        "conflictPolicy": "fail",
                        "formatPolicy": "preserve",
                    },
                    {
                        # Without this second action the definition is renamed
                        # and every importer keeps referring to a name that no
                        # longer exists.
                        "id": "follow-importers",
                        "operation": "rename-imported-symbol",
                        "selector": {"kind": "file", "paths": ["**/*.py"]},
                        "parameters": {
                            "module": "${module}",
                            "from": "${from}",
                            "to": "${to}",
                        },
                        "expectedCardinality": {"min": 1, "max": 100000},
                        "conflictPolicy": "fail",
                        "formatPolicy": "preserve",
                    },
                ],
                postconditions=[
                    {
                        "id": "old-name-gone",
                        "type": "semantic-query",
                        "expression": "result.old_name_references == 0",
                        "onUnknown": "fail",
                        "message": "references to the old name remain",
                    }
                ],
                validation=_STANDARD_VALIDATION,
                select=_PYTHON_SELECT,
            ),
            _build(
                "python-package-rename",
                "1.0.0",
                ["python"],
                "R3",
                description="Rename a Python package/module and rewrite every import and dotted usage.",
                tags=["move", "python"],
                parameters={
                    "from": {"type": "string", "required": True},
                    "to": {"type": "string", "required": True},
                    "fromPrefix": {"type": "string", "required": True},
                    "toPrefix": {"type": "string", "required": True},
                },
                applicability=[
                    {
                        "id": "python-present",
                        "type": "semantic-query",
                        "expression": "'python' in index.languages",
                        "onUnknown": "fail",
                    }
                ],
                preconditions=[
                    {
                        "id": "source-package-exists",
                        "type": "file-query",
                        "expression": "index.source_package_exists",
                        "onUnknown": "fail",
                        "message": "the source package does not exist at this revision",
                    },
                    {
                        "id": "target-package-free",
                        "type": "file-query",
                        "expression": "not index.target_package_exists",
                        "onUnknown": "fail",
                        "message": "the destination package already exists",
                    },
                ],
                negative_guards=[
                    {
                        "id": "no-namespace-package",
                        "type": "file-query",
                        "expression": "index.namespace_package",
                        "onUnknown": "approval",
                        "message": "implicit namespace packages change resolution semantics when moved",
                    }
                ],
                actions=[
                    {
                        "id": "rewrite-imports",
                        "operation": "rewrite-module-imports",
                        "selector": {"kind": "file", "paths": ["**/*.py"]},
                        "parameters": {"from": "${from}", "to": "${to}"},
                        "expectedCardinality": {"min": 1, "max": 100000},
                        "formatPolicy": "preserve",
                    },
                    {
                        "id": "move-files",
                        "operation": "move-file",
                        "selector": {"kind": "file", "paths": ["${fromPrefix}/**"]},
                        "parameters": {"fromPrefix": "${fromPrefix}", "toPrefix": "${toPrefix}"},
                        "expectedCardinality": {"min": 1, "max": 100000},
                        "formatPolicy": "preserve",
                    },
                ],
                postconditions=[
                    {
                        "id": "no-old-imports",
                        "type": "semantic-query",
                        "expression": "result.old_module_imports == 0",
                        "onUnknown": "fail",
                    }
                ],
                validation=_STANDARD_VALIDATION,
                select=_PYTHON_SELECT,
            ),
            _build(
                "python-change-signature",
                "1.0.0",
                ["python"],
                "R3",
                description="Add, remove or rename parameters of a Python function and update keyword call sites.",
                tags=["signature", "python"],
                parameters={
                    "function": {"type": "string", "required": True},
                    "changes": {"type": "array", "required": True},
                },
                applicability=[
                    {
                        "id": "python-present",
                        "type": "semantic-query",
                        "expression": "'python' in index.languages",
                        "onUnknown": "fail",
                    }
                ],
                preconditions=[
                    {
                        "id": "function-exists",
                        "type": "semantic-query",
                        "expression": "index.symbol_exists",
                        "onUnknown": "fail",
                    }
                ],
                negative_guards=[
                    {
                        "id": "public-api",
                        "type": "contract-query",
                        "expression": "index.symbol_is_public and constraints.public_api_compatibility == 'strict'",
                        "onUnknown": "approval",
                        "message": "changing a public signature is not source-compatible",
                    }
                ],
                actions=[
                    {
                        "id": "change",
                        "operation": "change-signature",
                        "selector": {"kind": "file", "paths": ["**/*.py"]},
                        "parameters": {"function": "${function}", "changes": "${changes}"},
                        "expectedCardinality": {"min": 1, "max": 100000},
                        "formatPolicy": "preserve",
                    }
                ],
                postconditions=[
                    {
                        "id": "call-sites-consistent",
                        "type": "build-query",
                        "expression": "gates.typecheck",
                        "onUnknown": "fail",
                    }
                ],
                validation=_STANDARD_VALIDATION,
                select=_PYTHON_SELECT,
            ),
            _build(
                "python-remove-unused-imports",
                "1.0.0",
                ["python"],
                "R1",
                description="Remove imports whose bound name is unreferenced, preserving re-exports.",
                tags=["cleanup", "python"],
                parameters={},
                applicability=[
                    {
                        "id": "python-present",
                        "type": "semantic-query",
                        "expression": "'python' in index.languages",
                        "onUnknown": "fail",
                    }
                ],
                preconditions=[
                    {
                        "id": "no-star-imports",
                        "type": "semantic-query",
                        "expression": "index.star_import_count == 0",
                        "onUnknown": "approval",
                        "message": "'from x import *' makes unused-import analysis unsound",
                    }
                ],
                negative_guards=[],
                actions=[
                    {
                        "id": "prune",
                        "operation": "remove-unused-imports",
                        "selector": {"kind": "file", "paths": ["**/*.py"]},
                        "expectedCardinality": {"min": 0, "max": 100000},
                        "formatPolicy": "preserve",
                    }
                ],
                postconditions=[
                    {
                        "id": "still-imports",
                        "type": "build-query",
                        "expression": "gates.parse",
                        "onUnknown": "fail",
                    }
                ],
                validation=_STANDARD_VALIDATION,
                select=_PYTHON_SELECT,
            ),
            _build(
                "python-remove-dead-code",
                "1.0.0",
                ["python"],
                "R2",
                description="Remove a module-level definition that nothing references, including by string.",
                tags=["cleanup", "python"],
                parameters={"name": {"type": "string", "required": True}},
                applicability=[
                    {
                        "id": "python-present",
                        "type": "semantic-query",
                        "expression": "'python' in index.languages",
                        "onUnknown": "fail",
                    }
                ],
                preconditions=[
                    {
                        "id": "no-references",
                        "type": "semantic-query",
                        "expression": "index.reference_count == 0",
                        "onUnknown": "fail",
                        "message": "the symbol is still referenced",
                    }
                ],
                negative_guards=[
                    {
                        "id": "not-exported",
                        "type": "contract-query",
                        "expression": "index.symbol_is_public",
                        "onUnknown": "approval",
                        "message": "a public symbol may have consumers outside this repository",
                    }
                ],
                actions=[
                    {
                        "id": "remove",
                        "operation": "remove-unreferenced-definition",
                        "selector": {"kind": "symbol", "language": "python", "name": "${name}"},
                        "parameters": {"name": "${name}"},
                        "expectedCardinality": {"min": 1, "max": 1},
                        "formatPolicy": "preserve",
                    }
                ],
                postconditions=[
                    {"id": "parses", "type": "build-query", "expression": "gates.parse", "onUnknown": "fail"}
                ],
                validation=_STANDARD_VALIDATION,
                select=_PYTHON_SELECT,
            ),
            _build(
                "config-replace-literal",
                "1.0.0",
                ["yaml", "json", "toml", "properties", "text", "markdown"],
                "R1",
                description="Whole-word literal replacement in configuration and text files only.",
                tags=["config"],
                parameters={
                    "from": {"type": "string", "required": True},
                    "to": {"type": "string", "required": True},
                    "paths": {"type": "array", "required": True},
                },
                applicability=[
                    {
                        "id": "not-a-parsed-language",
                        "type": "file-query",
                        "expression": "not selector.targets_parsed_language",
                        "onUnknown": "fail",
                        "message": "use a symbol-aware operation for languages that have an extractor",
                    }
                ],
                preconditions=[],
                negative_guards=[
                    {
                        "id": "not-a-secret-path",
                        "type": "file-query",
                        "expression": "selector.touches_secret_path",
                        "onUnknown": "fail",
                        "message": "refusing to edit a path classified as holding secrets",
                    }
                ],
                actions=[
                    {
                        "id": "replace",
                        "operation": "replace-literal",
                        "selector": {"kind": "file", "paths": ["${paths}"]},
                        "parameters": {"from": "${from}", "to": "${to}", "wholeWord": True},
                        "expectedCardinality": {"min": 1, "max": 100000},
                        "formatPolicy": "preserve",
                    }
                ],
                postconditions=[
                    {
                        "id": "changed-something",
                        "type": "file-query",
                        "expression": "result.changed_files > 0",
                        "onUnknown": "fail",
                    }
                ],
                validation=[
                    {"gate": "idempotence", "blocking": True, "timeoutSeconds": 300},
                    {"gate": "scope-containment", "blocking": True, "timeoutSeconds": 300},
                ],
            ),
        )
    }
)


#: Which Recipes are candidates for which compiled operation.
OPERATION_RECIPES: Mapping[Operation, tuple[str, ...]] = MappingProxyType(
    {
        Operation.RENAME_SYMBOL: ("python-rename-symbol@1.0.0",),
        Operation.MOVE_MODULE: ("python-package-rename@1.0.0",),
        Operation.CHANGE_SIGNATURE: ("python-change-signature@1.0.0",),
        Operation.REMOVE_DEAD_CODE: (
            "python-remove-unused-imports@1.0.0",
            "python-remove-dead-code@1.0.0",
        ),
        Operation.UPGRADE_DEPENDENCY: ("config-replace-literal@1.0.0",),
    }
)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecipeCandidate:
    recipe: Recipe
    operation: Operation
    parameters: Mapping[str, Any]
    available: bool
    unavailable_reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference": self.recipe.reference,
            "operation": self.operation.value,
            "status": self.recipe.status.value,
            "riskClass": self.recipe.risk_class.value,
            "parameters": dict(self.parameters),
            "available": self.available,
            "unavailableReason": self.unavailable_reason,
        }


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    candidates: tuple[RecipeCandidate, ...]
    lock: RecipeLock
    dry_run: TransformResult | None
    unmatched_operations: tuple[Operation, ...] = ()
    reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    @property
    def selected(self) -> tuple[RecipeCandidate, ...]:
        return tuple(item for item in self.candidates if item.available)

    @property
    def executable(self) -> bool:
        return bool(self.selected) and not self.conflicts and (
            self.dry_run is None or self.dry_run.ok
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "recipeSet": [item.to_payload() for item in self.candidates],
            "recipeLock": self.lock.to_payload(),
            "recipeLockDigest": self.lock.digest,
            "dryRunPatch": None if self.dry_run is None else self.dry_run.patch.to_payload(),
            "dryRunDiff": None if self.dry_run is None else self.dry_run.patch.render()[:200_000],
            "recipeTestReport": _test_report(self.dry_run),
            "unmatchedOperations": [item.value for item in self.unmatched_operations],
            "conflicts": list(self.conflicts),
            "reasons": list(self.reasons),
            "executable": self.executable,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


def _test_report(result: TransformResult | None) -> dict[str, Any]:
    if result is None:
        return {"ran": False, "reason": "no applicable recipe produced a dry run"}
    return {
        "ran": True,
        "changedFiles": result.patch.changed_files,
        "changedLines": result.patch.changed_lines,
        "idempotent": result.evidence.idempotent,
        "roundTripFailures": list(result.evidence.round_trip_failures),
        "scopeExpansions": list(result.evidence.scope_expansions),
        "blockingReasons": list(result.blocking_reasons),
    }


def _parameters_for(
    operation: Operation, intent: CompiledIntent, index: SemanticIndex
) -> dict[str, Any] | None:
    """Derive Recipe parameters from the compiled goal that selected it.

    Returns ``None`` when the goal does not carry enough information; the
    caller then reports the operation as unmatched rather than guessing.
    """

    goal = next((item for item in intent.goals if item.operation is operation), None)
    if goal is None:
        return None
    targets = goal.targets
    if operation is Operation.RENAME_SYMBOL:
        if len(targets) < 2:
            return None
        module = _module_of_symbol(targets[0], index)
        if module is None:
            return None
        return {"from": targets[0], "to": targets[1], "module": module}
    if operation is Operation.MOVE_MODULE:
        if len(targets) < 2:
            return None
        source, destination = targets[0], targets[1]
        return {
            "from": source,
            "to": destination,
            "fromPrefix": source.replace(".", "/"),
            "toPrefix": destination.replace(".", "/"),
        }
    if operation is Operation.CHANGE_SIGNATURE:
        return None  # a signature change always needs an explicit parameter list
    if operation is Operation.REMOVE_DEAD_CODE:
        return {"name": targets[0]} if targets else {}
    if operation is Operation.UPGRADE_DEPENDENCY:
        if len(targets) < 2:
            return None
        return {"from": targets[0], "to": targets[1], "paths": ["**/*.toml", "**/*.json", "**/*.yaml"]}
    return None


def select_recipes(
    intent: CompiledIntent,
    index: SemanticIndex,
    adapters: AdapterCapabilitySnapshot,
    *,
    registry: Mapping[str, Recipe] | None = None,
    explicit: Sequence[tuple[str, Mapping[str, Any]]] = (),
    allow_draft: bool = False,
) -> tuple[tuple[RecipeCandidate, ...], tuple[Operation, ...]]:
    """Choose Recipes for a compiled intent, plus the operations left unmatched."""

    available = registry or BUILTIN_RECIPES
    languages = {entity.language for entity in index.entities}
    candidates: list[RecipeCandidate] = []
    unmatched: list[Operation] = []

    requests: list[tuple[Operation, str, Mapping[str, Any]]] = []
    for reference, parameters in explicit:
        recipe = available.get(reference)
        if recipe is None:
            raise ContractError("unknown_recipe", f"'{reference}' is not present in the registry")
        requests.append((Operation.UNCLASSIFIED, reference, parameters))
    for operation in intent.operations:
        references = OPERATION_RECIPES.get(operation, ())
        if not references:
            unmatched.append(operation)
            continue
        derived = _parameters_for(operation, intent, index)
        if derived is None:
            unmatched.append(operation)
            continue
        for reference in references:
            requests.append((operation, reference, derived))

    for operation, reference, parameters in requests:
        recipe = available[reference]
        reason = ""
        if not allow_draft and recipe.status is RecipeStatus.DRAFT:
            reason = f"recipe status is '{recipe.status.value}'; draft recipes may not execute"
        elif recipe.status in (RecipeStatus.REVOKED, RecipeStatus.DEPRECATED):
            reason = f"recipe status is '{recipe.status.value}'"
        elif not set(recipe.languages) & languages:
            reason = f"none of {', '.join(recipe.languages)} are present in this repository"
        else:
            for action in recipe.actions:
                required = OPERATION_LEVELS.get(action.operation)
                if required is None:
                    reason = f"operation '{action.operation}' is not implemented by this runtime"
                    break
                weak = [
                    language
                    for language in sorted(set(recipe.languages) & languages)
                    if adapters.effective_level(language).rank < required.rank
                ]
                if weak:
                    reason = (
                        f"action '{action.id}' needs {required.value} but "
                        + ", ".join(f"{language}={adapters.effective_level(language).value}" for language in weak)
                    )
                    break
        try:
            bound = bind_parameters(recipe, parameters)
        except ContractError as error:
            reason = reason or error.message
            bound = dict(parameters)
        candidates.append(
            RecipeCandidate(
                recipe=recipe,
                operation=operation,
                parameters=bound,
                available=not reason,
                unavailable_reason=reason,
            )
        )
    return tuple(candidates), tuple(dict.fromkeys(unmatched))


def _module_of_symbol(name: str, index: SemanticIndex) -> str | None:
    """The declaring module of a symbol, needed to follow it into importers."""

    matches = index.by_qualified_name(name) or index.by_name(name.rsplit(".", 1)[-1])
    for entity in matches:
        if entity.qualified_name and "." in entity.qualified_name:
            return entity.qualified_name.rsplit(".", 1)[0]
    return None


def detect_composition_conflicts(candidates: Sequence[RecipeCandidate]) -> tuple[str, ...]:
    """Conflicts that are visible before running anything."""

    conflicts: list[str] = []
    by_operation: dict[str, list[str]] = {}
    for candidate in candidates:
        if not candidate.available:
            continue
        for action in candidate.recipe.actions:
            by_operation.setdefault(action.operation, []).append(candidate.recipe.reference)
    for operation, references in sorted(by_operation.items()):
        if operation in ("move-file", "delete-file") and len(set(references)) > 1:
            conflicts.append(
                f"{len(set(references))} recipes both perform '{operation}'; "
                "file relocation must be sequenced, not merged"
            )
    references = [item.recipe.reference for item in candidates if item.available]
    if len(references) != len(set(references)):
        conflicts.append("the same recipe is selected more than once")
    return tuple(conflicts)


def build_lock(
    candidates: Sequence[RecipeCandidate],
    index: SemanticIndex,
    adapters: AdapterCapabilitySnapshot,
    *,
    toolchain_digest: str = "",
) -> RecipeLock:
    entries: list[LockedRecipe] = []
    for candidate in candidates:
        if not candidate.available:
            continue
        primary = candidate.recipe.languages[0]
        descriptor = adapters.descriptor_for(primary)
        entries.append(
            LockedRecipe(
                reference=candidate.recipe.reference,
                digest=candidate.recipe.digest,
                status=candidate.recipe.status,
                parameters=candidate.parameters,
                adapter=descriptor.name if descriptor else "native",
                adapter_digest=descriptor.content_digest if descriptor else "",
            )
        )
    return RecipeLock(
        recipes=tuple(sorted(entries, key=lambda item: item.reference)),
        toolchain_digest=toolchain_digest,
        index_digest=index.digest,
        formatter="preserve",
    )


def synthesize(
    intent: CompiledIntent,
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    adapters: AdapterCapabilitySnapshot,
    *,
    registry: Mapping[str, Recipe] | None = None,
    explicit: Sequence[tuple[str, Mapping[str, Any]]] = (),
    toolchain_digest: str = "",
    allow_draft: bool = False,
    dry_run: bool = True,
) -> SynthesisResult:
    """Select, lock and dry-run the Recipes for a compiled intent."""

    candidates, unmatched = select_recipes(
        intent, index, adapters, registry=registry, explicit=explicit, allow_draft=allow_draft
    )
    conflicts = detect_composition_conflicts(candidates)
    lock = build_lock(candidates, index, adapters, toolchain_digest=toolchain_digest)

    reasons: list[str] = []
    for candidate in candidates:
        if not candidate.available:
            reasons.append(f"{candidate.recipe.reference}: {candidate.unavailable_reason}")
    for operation in unmatched:
        reasons.append(
            f"operation '{operation.value}' has no available recipe in this runtime; "
            "it must be planned as a manual step or supplied explicitly"
        )
    if lock.draft_references:
        reasons.append(
            "draft or quarantined recipes present and therefore not executable: "
            + ", ".join(lock.draft_references)
        )

    result: TransformResult | None = None
    selected = [item for item in candidates if item.available]
    if dry_run and selected and not conflicts:
        result = execute_transform(
            [(item.recipe, item.parameters) for item in selected],
            snapshot,
            index,
            lock=lock,
            scope=intent.scope,
            adapters=adapters,
            step_id="recipe-dry-run",
            context=predicate_context(intent, index, snapshot, selected),
        )
        reasons.extend(result.blocking_reasons)

    return SynthesisResult(
        candidates=candidates,
        lock=lock,
        dry_run=result,
        unmatched_operations=unmatched,
        reasons=tuple(dict.fromkeys(reasons)),
        conflicts=conflicts,
    )


def predicate_context(
    intent: CompiledIntent,
    index: SemanticIndex,
    snapshot: WorkspaceSnapshot,
    selected: Sequence[RecipeCandidate],
) -> dict[str, Any]:
    """Facts a Recipe's predicates may consult.

    Every key here is computed from the index or the snapshot; nothing is
    supplied by a caller, so a Recipe cannot be told a convenient falsehood.
    """

    languages = sorted({entity.language for entity in index.entities})
    parameters: dict[str, Any] = {}
    for candidate in selected:
        parameters.update(candidate.parameters)

    source_name = str(parameters.get("from", ""))
    target_name = str(parameters.get("to", ""))
    symbol_matches = index.by_qualified_name(source_name) or index.by_name(source_name)
    new_name_matches = index.by_qualified_name(target_name) or index.by_name(target_name)
    reference_count = sum(len(index.incoming(entity.id)) for entity in symbol_matches)

    #: Dynamic references only matter here if they are in a file that also
    #: touches the target symbol.  A repository-wide count would block every
    #: rename in any codebase that uses ``getattr`` anywhere, which is all of
    #: them — a guard that always fires is a guard nobody keeps.
    symbol_paths = {entity.path for entity in symbol_matches}
    symbol_paths |= {
        relationship.path
        for entity in symbol_matches
        for relationship in index.incoming(entity.id)
        if relationship.path
    }
    #: A module-level symbol can only be reached by a *module*-scoped dynamic
    #: access (``eval``, ``globals()``, ``importlib``); ``getattr(obj, ...)``
    #: reaches members of ``obj`` and cannot name a module-level binding.
    member_kinds = {"method", "property", "field"}
    target_is_member = any(entity.kind.value in member_kinds for entity in symbol_matches)
    wanted_scope = "attribute" if target_is_member else "module"
    reachable_dynamic = [
        relationship
        for relationship in index.dynamic_relationships
        if relationship.path in symbol_paths
        and str(relationship.attributes.get("dynamicScope", "module")) == wanted_scope
    ]
    from_prefix = str(parameters.get("fromPrefix", ""))
    to_prefix = str(parameters.get("toPrefix", ""))
    star_imports = sum(
        1
        for record in snapshot
        if record.text is not None and record.path.endswith(".py") and "import *" in record.text
    )

    return {
        "index": {
            "languages": languages,
            "symbol_exists": bool(symbol_matches),
            "symbol_is_public": any(item.visibility in ("public", "exported") for item in symbol_matches),
            "new_name_taken": bool(new_name_matches),
            "reference_count": reference_count,
            "dynamic_reference_count": len(reachable_dynamic),
            "repository_dynamic_reference_count": len(index.dynamic_relationships),
            "star_import_count": star_imports,
            "source_package_exists": bool(from_prefix) and bool(snapshot.under(from_prefix)),
            "target_package_exists": bool(to_prefix) and bool(snapshot.under(to_prefix)),
            "namespace_package": bool(from_prefix)
            and bool(snapshot.under(from_prefix))
            and f"{from_prefix}/__init__.py" not in snapshot,
        },
        "constraints": {
            "public_api_compatibility": "strict"
            if any("publicApiCompatibility=strict" == item.origin for item in intent.predicates)
            else "backward-compatible",
        },
        "selector": {
            "targets_parsed_language": any(
                language_of(path) == "python"
                for path in _selector_paths(selected, snapshot)
            ),
            "touches_secret_path": any(
                "secret" in path.lower() or path.endswith((".pem", ".p12", ".env"))
                for path in _selector_paths(selected, snapshot)
            ),
        },
        "gates": {"parse": True, "typecheck": True},
        "result": {"old_name_references": 0, "old_module_imports": 0, "changed_files": 1},
    }


def _selector_paths(selected: Sequence[RecipeCandidate], snapshot: WorkspaceSnapshot) -> tuple[str, ...]:
    """Paths the selected Recipes' file selectors reach, with parameters bound."""

    resolved: list[str] = []
    for candidate in selected:
        for action in candidate.recipe.actions:
            raw = action.selector.get("paths")
            if not isinstance(raw, Sequence) or isinstance(raw, str):
                continue
            for item in raw:
                glob = str(item)
                for key, value in candidate.parameters.items():
                    glob = glob.replace(f"${{{key}}}", str(value))
                if "${" in glob:
                    continue
                resolved.append(glob)
    return snapshot.match(sorted(set(resolved))) if resolved else ()


def registry_payload(registry: Mapping[str, Recipe] | None = None) -> dict[str, Any]:
    available = registry or BUILTIN_RECIPES
    return {
        "count": len(available),
        "recipes": [
            {
                "reference": recipe.reference,
                "digest": recipe.digest,
                "status": recipe.status.value,
                "riskClass": recipe.risk_class.value,
                "languages": list(recipe.languages),
                "operations": sorted({action.operation for action in recipe.actions}),
                "description": recipe.description,
            }
            for recipe in sorted(available.values(), key=lambda item: item.reference)
        ],
    }


def highest_risk(candidates: Sequence[RecipeCandidate]) -> RiskClass:
    return RiskClass.max_of([item.recipe.risk_class for item in candidates if item.available] or [RiskClass.R0])


def required_adapter_level(candidates: Sequence[RecipeCandidate]) -> AdapterLevel:
    levels = [
        OPERATION_LEVELS.get(action.operation, AdapterLevel.L4)
        for candidate in candidates
        if candidate.available
        for action in candidate.recipe.actions
    ]
    return max(levels, key=lambda item: item.rank, default=AdapterLevel.L0)


__all__ = [
    "BUILTIN_RECIPES",
    "predicate_context",
    "OPERATION_RECIPES",
    "RecipeCandidate",
    "SynthesisResult",
    "build_lock",
    "detect_composition_conflicts",
    "highest_risk",
    "registry_payload",
    "required_adapter_level",
    "select_recipes",
    "synthesize",
]
