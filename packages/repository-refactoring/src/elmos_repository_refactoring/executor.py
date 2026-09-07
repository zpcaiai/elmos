"""Skill 07 — the deterministic transform executor.

Executes locked Recipes against an isolated snapshot and produces a minimal,
reviewable, invertible patch.  Nothing here writes to disk: the snapshot is
immutable and every step produces a new one, which is what makes shard
execution, rollback and second-run comparison trivial rather than delicate.

The guarantees this module is responsible for:

* **Preconditions before edits.**  Applicability, preconditions and negative
  guards are evaluated first; a Recipe that cannot prove it applies does not
  run.
* **Cardinality is enforced.**  An action that matches a different number of
  targets than it declared fails the step.
* **Scope containment.**  A file touched outside the scope policy is a scope
  expansion — reported, and blocking.
* **Round-trip.**  Every edited file is re-parsed; an edit that produces
  something the language cannot parse is rejected before it reaches a patch.
* **Order independence.**  Shards are executed against the same base and
  merged; merging is only defined for disjoint file sets, so the resulting
  tree cannot depend on completion order.
* **Idempotence.**  Re-running against the produced snapshot must yield an
  empty patch, and that is checked rather than asserted.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .adapters import AdapterCapabilitySnapshot, language_of
from .buildgraph import BuildGraph
from .contracts import (
    AdapterLevel,
    ConflictPolicy,
    ContractError,
    RiskClass,
    match_path_glob,
    sha256_payload,
)
from .index import SemanticIndex
from .intent import ScopePolicy
from .patch import PatchSet, TextEdit, check_overlaps, patch_from_edits
from .pyops import (
    Diagnostic,
    OperationResult,
    ParameterChange,
    Severity,
    add_import,
    change_signature,
    remove_unreferenced_definition,
    remove_unused_imports,
    rename_binding,
    rename_imported_symbol,
    rewrite_module_imports,
)
from .recipe import (
    Recipe,
    RecipeAction,
    RecipeLock,
    SelectorResolution,
    bind_parameters,
    check_cardinality,
    evaluate_predicates,
    resolve_selector,
)
from .workspace import WorkspaceSnapshot

#: Operations this executor can actually perform, with the adapter level each
#: one needs.  An operation absent from this table is refused; it is never
#: attempted with a weaker mechanism.
OPERATION_LEVELS: Mapping[str, AdapterLevel] = {
    "rename-symbol": AdapterLevel.L2,
    "rename-imported-symbol": AdapterLevel.L2,
    "rewrite-module-imports": AdapterLevel.L2,
    "change-signature": AdapterLevel.L2,
    "remove-unused-imports": AdapterLevel.L1,
    "remove-unreferenced-definition": AdapterLevel.L2,
    "add-import": AdapterLevel.L1,
    "move-file": AdapterLevel.L1,
    "create-file": AdapterLevel.L1,
    "delete-file": AdapterLevel.L1,
    "replace-literal": AdapterLevel.L1,
}


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    action_id: str
    operation: str
    resolution: SelectorResolution
    edits: tuple[TextEdit, ...] = ()
    creations: Mapping[str, str] = field(default_factory=dict)
    deletions: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    cardinality_violation: str = ""

    @property
    def blocked(self) -> bool:
        return bool(self.cardinality_violation) or any(
            item.severity is Severity.BLOCKING for item in self.diagnostics
        )

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(
            sorted({*(edit.path for edit in self.edits), *self.creations, *self.deletions})
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "operation": self.operation,
            "matched": self.resolution.count,
            "editCount": len(self.edits),
            "created": sorted(self.creations),
            "deleted": list(self.deletions),
            "blocked": self.blocked,
            "cardinalityViolation": self.cardinality_violation,
            "diagnostics": [item.to_payload() for item in self.diagnostics],
            "outOfScope": list(self.resolution.out_of_scope),
        }


@dataclass(frozen=True, slots=True)
class RecipeOutcome:
    reference: str
    applicable: bool
    actions: tuple[ActionOutcome, ...] = ()
    reasons: tuple[str, ...] = ()
    predicate_reports: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return any(item.blocked for item in self.actions)

    @property
    def edits(self) -> tuple[TextEdit, ...]:
        return tuple(edit for action in self.actions for edit in action.edits)

    @property
    def creations(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for action in self.actions:
            merged.update(action.creations)
        return merged

    @property
    def deletions(self) -> tuple[str, ...]:
        return tuple(sorted({path for action in self.actions for path in action.deletions}))

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "applicable": self.applicable,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
            "actions": [item.to_payload() for item in self.actions],
            "predicates": dict(self.predicate_reports),
        }


@dataclass(frozen=True, slots=True)
class TransformEvidence:
    base_tree_digest: str
    result_tree_digest: str
    patch_digest: str
    recipe_lock_digest: str
    changed_paths: tuple[str, ...]
    scope_expansions: tuple[str, ...]
    round_trip_failures: tuple[str, ...]
    idempotent: bool | None
    second_run_paths: tuple[str, ...] = ()
    shard_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "baseTreeDigest": self.base_tree_digest,
            "resultTreeDigest": self.result_tree_digest,
            "patchDigest": self.patch_digest,
            "recipeLockDigest": self.recipe_lock_digest,
            "changedPaths": list(self.changed_paths),
            "scopeExpansions": list(self.scope_expansions),
            "roundTripFailures": list(self.round_trip_failures),
            "idempotent": self.idempotent,
            "secondRunPaths": list(self.second_run_paths),
            "shardIds": list(self.shard_ids),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class TransformResult:
    patch: PatchSet
    snapshot: WorkspaceSnapshot
    recipes: tuple[RecipeOutcome, ...]
    evidence: TransformEvidence
    blocking_reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocking_reasons

    @property
    def changed_symbols(self) -> tuple[str, ...]:
        return tuple(
            sorted({edit.symbol for outcome in self.recipes for edit in outcome.edits if edit.symbol})
        )

    def source_map(self) -> list[dict[str, Any]]:
        """hunk -> action -> symbol, the traceability spine of the evidence bundle."""

        return [
            {
                "hunkId": hunk.hunk_id,
                "path": hunk.path,
                "actionIds": list(hunk.action_ids),
                "symbols": list(hunk.symbols),
                "beforeStart": hunk.before_start,
                "afterStart": hunk.after_start,
            }
            for hunk in self.patch.hunks
        ]

    def to_payload(self) -> dict[str, Any]:
        return {
            "patchSet": self.patch.to_payload(),
            "changedSymbolSet": list(self.changed_symbols),
            "sourceMap": self.source_map(),
            "transformEvidence": self.evidence.to_payload(),
            "recipes": [item.to_payload() for item in self.recipes],
            "blockingReasons": list(self.blocking_reasons),
        }


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------


def _python_operation(
    operation: str,
    path: str,
    source: str,
    action: RecipeAction,
    match_scope: str,
    parameters: Mapping[str, Any],
) -> OperationResult:
    action_id = action.id
    if operation == "rename-symbol":
        return rename_binding(
            path,
            source,
            old_name=str(parameters["from"]),
            new_name=str(parameters["to"]),
            scope=str(parameters.get("scope", match_scope)),
            action_id=action_id,
        )
    if operation == "rename-imported-symbol":
        return rename_imported_symbol(
            path,
            source,
            module=str(parameters["module"]),
            old_name=str(parameters["from"]),
            new_name=str(parameters["to"]),
            action_id=action_id,
        )
    if operation == "rewrite-module-imports":
        return rewrite_module_imports(
            path,
            source,
            old_module=str(parameters["from"]),
            new_module=str(parameters["to"]),
            action_id=action_id,
        )
    if operation == "change-signature":
        changes = [
            ParameterChange(
                operation=str(item["operation"]),
                name=str(item["name"]),
                new_name=str(item.get("newName", "")),
                annotation=str(item.get("annotation", "")),
                default=str(item.get("default", "")),
                position=item.get("position"),
            )
            for item in parameters.get("changes", ())
        ]
        return change_signature(
            path,
            source,
            qualified_function=str(parameters["function"]),
            changes=changes,
            action_id=action_id,
        )
    if operation == "remove-unused-imports":
        return remove_unused_imports(path, source, action_id=action_id)
    if operation == "remove-unreferenced-definition":
        return remove_unreferenced_definition(path, source, name=str(parameters["name"]), action_id=action_id)
    if operation == "add-import":
        names = parameters.get("names", ())
        return add_import(
            path,
            source,
            module=str(parameters["module"]),
            names=tuple(str(item) for item in names) if isinstance(names, Sequence) else (),
            action_id=action_id,
        )
    raise ContractError("unsupported_operation", f"operation '{operation}' has no Python implementation")


def _replace_literal(
    path: str,
    source: str,
    action: RecipeAction,
    parameters: Mapping[str, Any],
) -> OperationResult:
    """Bounded literal replacement for text and configuration files.

    Deliberately crude and deliberately guarded: it only ever matches whole
    lines or whole words, refuses to run on a language that has a real
    extractor, and reports its match count so cardinality still applies.
    """

    language = language_of(path)
    if language in ("python",):
        return OperationResult(
            diagnostics=(
                Diagnostic(
                    "literal_replacement_on_parsed_language",
                    f"'{path}' has a semantic extractor; use a symbol-aware operation instead of literal replacement",
                    Severity.BLOCKING,
                    path,
                ),
            )
        )
    needle = str(parameters["from"])
    replacement = str(parameters["to"])
    whole_word = bool(parameters.get("wholeWord", True))
    edits: list[TextEdit] = []
    for number, line in enumerate(source.splitlines(), start=1):
        start = 0
        while True:
            index = line.find(needle, start)
            if index == -1:
                break
            start = index + len(needle)
            if whole_word:
                before = line[index - 1] if index > 0 else " "
                after = line[index + len(needle)] if index + len(needle) < len(line) else " "
                if (before.isalnum() or before == "_") or (after.isalnum() or after == "_"):
                    continue
            edits.append(
                TextEdit(
                    path=path,
                    start_line=number,
                    start_column=index,
                    end_line=number,
                    end_column=index + len(needle),
                    replacement=replacement,
                    action_id=action.id,
                    symbol=needle,
                    rationale="literal replacement",
                )
            )
    return OperationResult(edits=tuple(edits), matched=len(edits))


def execute_action(
    action: RecipeAction,
    recipe: Recipe,
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    *,
    parameters: Mapping[str, Any],
    scope: ScopePolicy,
    adapters: AdapterCapabilitySnapshot,
) -> ActionOutcome:
    """Resolve one action's targets and produce its edits."""

    required = OPERATION_LEVELS.get(action.operation)
    if required is None:
        return ActionOutcome(
            action_id=action.id,
            operation=action.operation,
            resolution=SelectorResolution(action.id, ()),
            diagnostics=(
                Diagnostic(
                    "unsupported_operation",
                    f"operation '{action.operation}' is not implemented by this runtime",
                    Severity.BLOCKING,
                ),
            ),
        )

    resolution = resolve_selector(action, index, allowed_globs=scope.allowed_paths, parameters=parameters)
    violation = check_cardinality(action, resolution)
    diagnostics: list[Diagnostic] = []
    if resolution.out_of_scope:
        diagnostics.append(
            Diagnostic(
                "selector_out_of_scope",
                f"action '{action.id}' matched {len(resolution.out_of_scope)} path(s) outside the allowed scope",
                Severity.BLOCKING,
            )
        )

    if action.operation in ("create-file", "delete-file", "move-file"):
        return _file_operation(action, resolution, parameters, snapshot, scope, tuple(diagnostics), violation)

    edits: list[TextEdit] = []
    seen_paths: set[str] = set()
    for match in resolution.matches:
        if match.path in seen_paths and action.operation in (
            "remove-unused-imports",
            "rewrite-module-imports",
            "rename-imported-symbol",
        ):
            continue
        seen_paths.add(match.path)
        record = snapshot.get(match.path)
        if record is None or record.text is None:
            diagnostics.append(
                Diagnostic(
                    "unreadable_target",
                    f"'{match.path}' has no readable text and cannot be transformed",
                    Severity.BLOCKING,
                    match.path,
                )
            )
            continue
        language = language_of(match.path)
        if adapters.effective_level(language).rank < required.rank:
            diagnostics.append(
                Diagnostic(
                    "adapter_capability_insufficient",
                    f"operation '{action.operation}' needs {required.value} for {language}, "
                    f"but the effective level is {adapters.effective_level(language).value}",
                    Severity.BLOCKING,
                    match.path,
                )
            )
            continue
        if action.operation == "replace-literal":
            result = _replace_literal(match.path, record.text, action, parameters)
        elif language == "python":
            result = _python_operation(
                action.operation, match.path, record.text, action, match.scope, parameters
            )
        else:
            diagnostics.append(
                Diagnostic(
                    "no_engine_for_language",
                    f"'{match.path}' is {language}; no semantic engine in this runtime implements "
                    f"'{action.operation}' for it",
                    Severity.BLOCKING,
                    match.path,
                )
            )
            continue
        edits.extend(result.edits)
        diagnostics.extend(result.diagnostics)

    return ActionOutcome(
        action_id=action.id,
        operation=action.operation,
        resolution=resolution,
        edits=tuple(edits),
        diagnostics=tuple(diagnostics),
        cardinality_violation=violation or "",
    )


def _file_operation(
    action: RecipeAction,
    resolution: SelectorResolution,
    parameters: Mapping[str, Any],
    snapshot: WorkspaceSnapshot,
    scope: ScopePolicy,
    diagnostics: tuple[Diagnostic, ...],
    violation: str | None,
) -> ActionOutcome:
    creations: dict[str, str] = {}
    deletions: list[str] = []
    issues = list(diagnostics)

    def in_scope(path: str) -> bool:
        if any(match_path_glob(path, glob) for glob in scope.forbidden_paths):
            return False
        return any(match_path_glob(path, glob) for glob in scope.allowed_paths)

    if action.operation == "create-file":
        path = str(parameters["path"])
        if not in_scope(path):
            issues.append(
                Diagnostic("creation_out_of_scope", f"'{path}' is outside the allowed scope", Severity.BLOCKING, path)
            )
        elif path in snapshot:
            issues.append(
                Diagnostic("creation_conflict", f"'{path}' already exists", Severity.BLOCKING, path)
            )
        else:
            creations[path] = str(parameters.get("content", ""))
    elif action.operation == "delete-file":
        for match in resolution.matches:
            if not in_scope(match.path):
                issues.append(
                    Diagnostic(
                        "deletion_out_of_scope",
                        f"'{match.path}' is outside the allowed scope",
                        Severity.BLOCKING,
                        match.path,
                    )
                )
                continue
            deletions.append(match.path)
    elif action.operation == "move-file":
        target_root = str(parameters["toPrefix"])
        source_root = str(parameters["fromPrefix"])
        for match in resolution.matches:
            if not match.path.startswith(source_root):
                continue
            destination = target_root + match.path[len(source_root) :]
            if not in_scope(destination):
                issues.append(
                    Diagnostic(
                        "move_out_of_scope",
                        f"'{destination}' is outside the allowed scope",
                        Severity.BLOCKING,
                        destination,
                    )
                )
                continue
            record = snapshot.get(match.path)
            if record is None or record.text is None:
                issues.append(
                    Diagnostic(
                        "unreadable_move_source",
                        f"'{match.path}' has no readable text and cannot be moved textually",
                        Severity.BLOCKING,
                        match.path,
                    )
                )
                continue
            creations[destination] = record.text
            deletions.append(match.path)

    return ActionOutcome(
        action_id=action.id,
        operation=action.operation,
        resolution=resolution,
        creations=creations,
        deletions=tuple(sorted(set(deletions))),
        diagnostics=tuple(issues),
        cardinality_violation=violation or "",
    )


# ---------------------------------------------------------------------------
# Recipe execution
# ---------------------------------------------------------------------------


def execute_recipe(
    recipe: Recipe,
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    *,
    supplied_parameters: Mapping[str, Any],
    scope: ScopePolicy,
    adapters: AdapterCapabilitySnapshot,
    context: Mapping[str, Any] | None = None,
) -> RecipeOutcome:
    """Evaluate a Recipe's guards, then run its actions."""

    parameters = bind_parameters(recipe, supplied_parameters)
    evaluation_context = dict(context or {})
    evaluation_context.setdefault("recipe", {"name": recipe.name, "version": recipe.version})
    evaluation_context.setdefault("parameters", parameters)

    applicability = evaluate_predicates(recipe.applicability, evaluation_context)
    if not applicability.satisfied:
        return RecipeOutcome(
            reference=recipe.reference,
            applicable=False,
            reasons=tuple(
                f"applicability not met: {item.predicate.expression}" for item in applicability.violations
            ),
            predicate_reports={"applicability": applicability.to_payload()},
        )

    preconditions = evaluate_predicates(recipe.preconditions, evaluation_context)
    guards = evaluate_predicates(recipe.negative_guards, evaluation_context, negated=True)
    reasons: list[str] = []
    for item in preconditions.violations:
        reasons.append(f"precondition failed: {item.predicate.message or item.predicate.expression}")
    for item in guards.violations:
        reasons.append(f"negative guard tripped: {item.predicate.message or item.predicate.expression}")
    for identity in (*preconditions.requires_approval, *guards.requires_approval):
        reasons.append(f"undecidable predicate escalated for approval: {identity}")

    reports = {
        "applicability": applicability.to_payload(),
        "preconditions": preconditions.to_payload(),
        "negativeGuards": guards.to_payload(),
    }
    if reasons:
        return RecipeOutcome(
            reference=recipe.reference,
            applicable=True,
            reasons=tuple(reasons),
            predicate_reports=reports,
        )

    outcomes = tuple(
        execute_action(
            action,
            recipe,
            snapshot,
            index,
            parameters=parameters,
            scope=scope,
            adapters=adapters,
        )
        for action in recipe.actions
    )
    return RecipeOutcome(
        reference=recipe.reference,
        applicable=True,
        actions=outcomes,
        predicate_reports=reports,
    )


# ---------------------------------------------------------------------------
# Whole-step execution
# ---------------------------------------------------------------------------


def _round_trip_failures(snapshot: WorkspaceSnapshot, paths: Sequence[str]) -> tuple[str, ...]:
    """Re-parse every changed file whose language has a real parser."""

    failures: list[str] = []
    for path in paths:
        record = snapshot.get(path)
        if record is None or record.text is None:
            continue
        if language_of(path) != "python":
            continue
        try:
            ast.parse(record.text, filename=path)
        except SyntaxError as error:
            failures.append(f"{path}:{error.lineno}: {error.msg}")
    return tuple(failures)


def _scope_expansions(paths: Sequence[str], scope: ScopePolicy) -> tuple[str, ...]:
    expansions: list[str] = []
    for path in paths:
        if any(match_path_glob(path, glob) for glob in scope.forbidden_paths):
            expansions.append(f"{path} (forbidden by scope policy)")
        elif scope.allowed_paths and not any(match_path_glob(path, glob) for glob in scope.allowed_paths):
            expansions.append(f"{path} (outside allowed paths)")
    return tuple(expansions)


def execute_transform(
    recipes: Sequence[tuple[Recipe, Mapping[str, Any]]],
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    *,
    lock: RecipeLock,
    scope: ScopePolicy,
    adapters: AdapterCapabilitySnapshot,
    step_id: str = "transform",
    context: Mapping[str, Any] | None = None,
    check_idempotence: bool = True,
    shard_ids: Sequence[str] = (),
) -> TransformResult:
    """Run every Recipe, merge the result and prove the required properties."""

    outcomes: list[RecipeOutcome] = []
    blocking: list[str] = []
    all_edits: list[TextEdit] = []
    creations: dict[str, str] = {}
    deletions: list[str] = []
    applicable_count = 0

    for recipe, parameters in recipes:
        locked = lock.entry(recipe.reference)
        if locked.digest != recipe.digest:
            raise ContractError(
                "recipe_digest_mismatch",
                f"'{recipe.reference}' does not match the digest recorded in the recipe lock",
            )
        outcome = execute_recipe(
            recipe,
            snapshot,
            index,
            supplied_parameters=parameters,
            scope=scope,
            adapters=adapters,
            context=context,
        )
        outcomes.append(outcome)
        if not outcome.applicable:
            continue
        applicable_count += 1
        if outcome.reasons:
            blocking.extend(outcome.reasons)
            continue
        for action in outcome.actions:
            if action.cardinality_violation:
                blocking.append(action.cardinality_violation)
            for diagnostic in action.diagnostics:
                if diagnostic.severity is Severity.BLOCKING:
                    blocking.append(f"{diagnostic.code}: {diagnostic.message}")
        all_edits.extend(outcome.edits)
        for path, content in outcome.creations.items():
            if path in creations and creations[path] != content:
                blocking.append(f"two recipes create '{path}' with different content")
            creations[path] = content
        deletions.extend(outcome.deletions)

    if recipes and applicable_count == 0:
        # Producing an empty patch because nothing applied is not a success.
        # Without this, a step whose every Recipe was inapplicable would report
        # "no changes needed" — the exact unearned success this package refuses.
        blocking.append(
            "no recipe was applicable to this snapshot: "
            + "; ".join(
                f"{item.reference}: {', '.join(item.reasons) or 'applicability predicates not satisfied'}"
                for item in outcomes
                if not item.applicable
            )
        )

    overlaps = check_overlaps(all_edits)
    for left, right in overlaps:
        policy = ConflictPolicy.FAIL
        blocking.append(
            f"overlapping edits in '{left.path}' from actions "
            f"'{left.action_id}' and '{right.action_id}' (conflictPolicy={policy.value})"
        )

    if blocking:
        empty = PatchSet(base_revision=snapshot.revision, base_tree_digest=snapshot.tree_digest, changes=())
        return TransformResult(
            patch=empty,
            snapshot=snapshot,
            recipes=tuple(outcomes),
            evidence=TransformEvidence(
                base_tree_digest=snapshot.tree_digest,
                result_tree_digest=snapshot.tree_digest,
                patch_digest=empty.digest,
                recipe_lock_digest=lock.digest,
                changed_paths=(),
                scope_expansions=(),
                round_trip_failures=(),
                idempotent=None,
                shard_ids=tuple(shard_ids),
            ),
            blocking_reasons=tuple(dict.fromkeys(blocking)),
        )

    patch, updated = patch_from_edits(
        snapshot,
        all_edits,
        step_id=step_id,
        recipe_lock_digest=lock.digest,
        creations=creations,
        deletions=tuple(sorted(set(deletions))),
    )
    changed_paths = patch.paths
    expansions = _scope_expansions(changed_paths, scope)
    failures = _round_trip_failures(updated, changed_paths)
    if expansions:
        blocking.extend(f"scope expansion: {item}" for item in expansions)
    if failures:
        blocking.extend(f"round-trip parse failure: {item}" for item in failures)

    idempotent: bool | None = None
    second_run_paths: tuple[str, ...] = ()
    if check_idempotence and not blocking:
        # The real check: run the same Recipes again against the produced
        # snapshot.  Diffing the result against itself would be trivially
        # empty and would prove nothing.
        second = execute_transform(
            recipes,
            updated,
            index,
            lock=lock,
            scope=scope,
            adapters=adapters,
            step_id=f"{step_id}:second-run",
            context=context,
            check_idempotence=False,
            shard_ids=shard_ids,
        )
        idempotent = second.patch.empty and not second.blocking_reasons
        second_run_paths = second.patch.paths
        if not idempotent:
            blocking.append(
                "second run is not a no-op: "
                + (", ".join(second_run_paths) if second_run_paths else "; ".join(second.blocking_reasons))
            )

    evidence = TransformEvidence(
        base_tree_digest=snapshot.tree_digest,
        result_tree_digest=updated.tree_digest,
        patch_digest=patch.digest,
        recipe_lock_digest=lock.digest,
        changed_paths=changed_paths,
        scope_expansions=expansions,
        round_trip_failures=failures,
        idempotent=idempotent,
        second_run_paths=second_run_paths,
        shard_ids=tuple(shard_ids),
    )
    if blocking:
        # A patch that failed a structural property is not offered as a result;
        # the caller gets the reasons and an unchanged snapshot.
        return TransformResult(
            patch=patch,
            snapshot=snapshot,
            recipes=tuple(outcomes),
            evidence=evidence,
            blocking_reasons=tuple(dict.fromkeys(blocking)),
        )
    return TransformResult(
        patch=patch,
        snapshot=updated,
        recipes=tuple(outcomes),
        evidence=evidence,
        blocking_reasons=(),
    )


def verify_idempotence(
    recipes: Sequence[tuple[Recipe, Mapping[str, Any]]],
    result: TransformResult,
    index: SemanticIndex,
    *,
    lock: RecipeLock,
    scope: ScopePolicy,
    adapters: AdapterCapabilitySnapshot,
    context: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Run the same Recipes against the produced snapshot; expect no change.

    This is the strong form of the idempotence check: not "the diff of the
    result against itself is empty" (trivially true) but "running the same
    transformation again changes nothing".
    """

    second = execute_transform(
        recipes,
        result.snapshot,
        index,
        lock=lock,
        scope=scope,
        adapters=adapters,
        step_id=f"{result.patch.step_id}:second-run",
        context=context,
        check_idempotence=False,
    )
    if second.blocking_reasons:
        return False, tuple(f"second run blocked: {item}" for item in second.blocking_reasons)
    if not second.patch.empty:
        return False, tuple(f"second run still changed: {path}" for path in second.patch.paths)
    return True, ()


def merge_shard_results(results: Sequence[TransformResult]) -> PatchSet:
    """Merge disjoint shard patches; overlap is an error, never a winner."""

    if not results:
        raise ContractError("no_shard_results", "cannot merge an empty set of shard results")
    merged = results[0].patch
    for item in results[1:]:
        merged = merged.merge(item.patch)
    return merged


def required_level_for(operations: Sequence[str]) -> AdapterLevel:
    levels = [OPERATION_LEVELS.get(operation, AdapterLevel.L4) for operation in operations]
    return max(levels, key=lambda item: item.rank, default=AdapterLevel.L0)


def transform_risk(recipes: Sequence[Recipe]) -> RiskClass:
    return RiskClass.max_of([recipe.risk_class for recipe in recipes] or [RiskClass.R0])


def build_targets_touched(patch: PatchSet, graph: BuildGraph) -> tuple[str, ...]:
    found: set[str] = set()
    for path in patch.paths:
        found.update(graph.targets_for(path))
    return tuple(sorted(found))


__all__ = [
    "OPERATION_LEVELS",
    "ActionOutcome",
    "RecipeOutcome",
    "TransformEvidence",
    "TransformResult",
    "build_targets_touched",
    "execute_action",
    "execute_recipe",
    "execute_transform",
    "merge_shard_results",
    "required_level_for",
    "transform_risk",
    "verify_idempotence",
]
