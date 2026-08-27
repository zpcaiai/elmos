"""Skill 12 — bounded, explainable, reversible auto-repair.

Repair is the most dangerous stage in the package, because its whole purpose is
to make a red build green.  Every constraint here exists to stop it doing that
the easy way:

* **One observed failure at a time.**  A candidate must be derived from a
  specific failure signature; "while I was in there" changes are refused.
* **A closed candidate vocabulary.**  Repairs are generated from a fixed set of
  transformations with known semantics — add a missing import, drop an import
  that is now unused, fix a keyword argument at a call site.  There is no
  free-form edit path.
* **Forbidden repairs are structurally impossible.**  Deleting a test, adding a
  skip, widening an ignore, swallowing an exception and lowering a rule
  severity are not in the vocabulary, and any candidate that would produce one
  is rejected by the same anti-cheat analysis the verifier runs.
* **Loop detection.**  The same failure signature twice means the strategy is
  wrong, not that it needs another attempt.
* **Every attempt is reversible.**  A candidate is applied to a copy; a failed
  candidate is discarded whole, never partially kept.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .anticheat import analyse as analyse_cheating
from .contracts import ContractError, sha256_payload
from .index import SemanticIndex
from .patch import PatchSet, TextEdit, diff_snapshots, patch_from_edits
from .pyops import OperationResult, add_import, remove_unused_imports
from .workspace import WorkspaceSnapshot

#: Failure kinds this module can produce a candidate for.  Anything else is
#: reported as unresolved rather than guessed at.
REPAIRABLE_KINDS = (
    "missing-import",
    "unresolved-name",
    "unused-import",
    "unexpected-keyword-argument",
)

_PATTERNS: tuple[tuple[str, str], ...] = (
    ("missing-import", r"ModuleNotFoundError: No module named ['\"](?P<module>[\w.]+)['\"]"),
    ("missing-import", r"ImportError: cannot import name ['\"](?P<name>\w+)['\"] from ['\"](?P<module>[\w.]+)['\"]"),
    ("unresolved-name", r"NameError: name ['\"](?P<name>\w+)['\"] is not defined"),
    ("unresolved-name", r"(?P<path>[\w./-]+):(?P<line>\d+):\d+: F821 Undefined name `(?P<name>\w+)`"),
    ("unused-import", r"(?P<path>[\w./-]+):(?P<line>\d+):\d+: F401 .*?`(?P<name>[\w.]+)` imported but unused"),
    (
        "unexpected-keyword-argument",
        r"TypeError: (?P<function>\w+)\(\) got an unexpected keyword argument ['\"](?P<name>\w+)['\"]",
    ),
    (
        "missing-required-argument",
        r"TypeError: (?P<function>\w+)\(\) missing \d+ required positional argument",
    ),
    ("syntax-error", r"SyntaxError: (?P<message>.+)"),
)


@dataclass(frozen=True, slots=True)
class FailureSignature:
    """A normalised, comparable identity for one failure."""

    kind: str
    identity: str
    detail: str
    path: str = ""
    line: int = 0
    fields: Mapping[str, str] = field(default_factory=dict)

    @property
    def repairable(self) -> bool:
        return self.kind in REPAIRABLE_KINDS

    @property
    def digest(self) -> str:
        return sha256_payload({"kind": self.kind, "identity": self.identity})[:24]

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "identity": self.identity,
            "detail": self.detail,
            "path": self.path,
            "line": self.line,
            "repairable": self.repairable,
            "digest": self.digest,
        }


def normalise_failures(text: str, *, limit: int = 200) -> tuple[FailureSignature, ...]:
    """Turn raw tool output into comparable signatures.

    Normalisation strips paths, line numbers and object addresses out of the
    *identity* while keeping them in the detail, so "the same failure again"
    is a decidable question rather than a string comparison on a traceback.
    """

    found: list[FailureSignature] = []
    for kind, pattern in _PATTERNS:
        for match in re.finditer(pattern, text):
            if len(found) >= limit:
                return tuple(found)
            groups = {key: value for key, value in match.groupdict().items() if value}
            identity_parts = [kind, *(f"{key}={value}" for key, value in sorted(groups.items()) if key != "line")]
            found.append(
                FailureSignature(
                    kind=kind,
                    identity="|".join(identity_parts),
                    detail=match.group(0)[:400],
                    path=groups.get("path", ""),
                    line=int(groups["line"]) if groups.get("line", "").isdigit() else 0,
                    fields=groups,
                )
            )
    #: Deduplicate by identity: the same failure reported by two tools is one
    #: failure, and repairing it twice would look like progress.
    unique: dict[str, FailureSignature] = {}
    for item in found:
        unique.setdefault(item.identity, item)
    return tuple(unique.values())


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    signature: FailureSignature
    strategy: str
    rationale: str
    edits: tuple[TextEdit, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def actionable(self) -> bool:
        return bool(self.edits)

    def to_payload(self) -> dict[str, Any]:
        return {
            "signature": self.signature.to_payload(),
            "strategy": self.strategy,
            "rationale": self.rationale,
            "editCount": len(self.edits),
            "paths": sorted({edit.path for edit in self.edits}),
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    attempt: int
    candidate: RepairCandidate
    applied: bool
    accepted: bool
    reason: str
    patch_digest: str = ""
    cost_usd: Decimal = Decimal("0")

    def to_payload(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "candidate": self.candidate.to_payload(),
            "applied": self.applied,
            "accepted": self.accepted,
            "reason": self.reason,
            "patchDigest": self.patch_digest,
            "costUsd": str(self.cost_usd),
        }


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    attempts: tuple[RepairAttempt, ...]
    snapshot: WorkspaceSnapshot
    patch: PatchSet
    unresolved: tuple[FailureSignature, ...]
    stopped_because: str = ""

    @property
    def repaired(self) -> int:
        return sum(1 for item in self.attempts if item.accepted)

    @property
    def changed(self) -> bool:
        return not self.patch.empty

    def to_payload(self) -> dict[str, Any]:
        return {
            "repairAttemptRecords": [item.to_payload() for item in self.attempts],
            "updatedPatchSet": self.patch.to_payload(),
            "unresolvedFailureReport": {
                "count": len(self.unresolved),
                "failures": [item.to_payload() for item in self.unresolved],
                "stoppedBecause": self.stopped_because,
            },
            "repairedCount": self.repaired,
        }


@dataclass(frozen=True, slots=True)
class RepairBudgetState:
    max_attempts: int
    max_changed_files: int
    max_cost_usd: Decimal
    attempts_used: int = 0
    files_touched: int = 0
    cost_spent: Decimal = Decimal("0")

    def exhausted(self) -> str | None:
        if self.attempts_used >= self.max_attempts:
            return f"repair budget exhausted after {self.attempts_used} attempt(s)"
        if self.max_changed_files and self.files_touched >= self.max_changed_files:
            return f"repair budget exhausted after touching {self.files_touched} file(s)"
        if self.max_cost_usd and self.cost_spent >= self.max_cost_usd:
            return f"repair budget exhausted after spending {self.cost_spent} USD"
        return None


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


def _module_exporting(name: str, index: SemanticIndex) -> str | None:
    """A module that exports ``name``, if exactly one does.

    Ambiguity is not resolved by picking the first: importing the wrong
    ``Config`` compiles and then behaves differently, which is worse than
    leaving the failure visible.
    """

    candidates = {
        entity.qualified_name.rsplit(".", 1)[0]
        for entity in index.by_name(name)
        if entity.qualified_name and "." in entity.qualified_name and entity.visibility in ("public", "exported")
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def generate_candidate(
    signature: FailureSignature,
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    *,
    failing_path: str = "",
) -> RepairCandidate:
    """Derive one minimal candidate for one failure, or explain why not."""

    path = signature.path or failing_path
    record = snapshot.get(path) if path else None

    if signature.kind == "syntax-error":
        return RepairCandidate(
            signature,
            "none",
            "a syntax error means the transformation itself is wrong; repairing the symptom would hide it",
            diagnostics=("syntax errors are never auto-repaired",),
        )
    if signature.kind == "missing-required-argument":
        return RepairCandidate(
            signature,
            "none",
            "supplying a value for a newly required argument is a semantic decision, not a repair",
            diagnostics=("a value cannot be invented for a required parameter",),
        )
    if record is None or record.text is None:
        return RepairCandidate(
            signature,
            "none",
            f"no readable source for '{path or 'unknown path'}'",
            diagnostics=("the failing file is not present or not readable in this snapshot",),
        )

    if signature.kind == "unused-import":
        result: OperationResult = remove_unused_imports(path, record.text, action_id="repair")
        return RepairCandidate(
            signature,
            "remove-unused-import",
            f"'{signature.fields.get('name', '')}' is no longer referenced after the transformation",
            edits=result.edits,
            diagnostics=tuple(item.message for item in result.diagnostics),
        )

    if signature.kind in ("unresolved-name", "missing-import"):
        name = signature.fields.get("name", "")
        module = signature.fields.get("module") or (_module_exporting(name, index) if name else None)
        if not module:
            return RepairCandidate(
                signature,
                "none",
                f"no single module in the index exports '{name}'; the correct import is ambiguous",
                diagnostics=("ambiguous or unknown import source",),
            )
        result = add_import(path, record.text, module=module, names=(name,) if name else (), action_id="repair")
        return RepairCandidate(
            signature,
            "add-import",
            f"'{name}' resolves to '{module}' in the semantic index for this revision",
            edits=result.edits,
            diagnostics=tuple(item.message for item in result.diagnostics),
        )

    if signature.kind == "unexpected-keyword-argument":
        return RepairCandidate(
            signature,
            "none",
            (
                f"call site passes '{signature.fields.get('name', '')}' which "
                f"'{signature.fields.get('function', '')}' no longer accepts; the correct fix belongs to the "
                "signature recipe, not to repair"
            ),
            diagnostics=("keyword mismatches are fixed by re-running the signature recipe",),
        )

    return RepairCandidate(
        signature,
        "none",
        f"no candidate strategy exists for failure kind '{signature.kind}'",
        diagnostics=("unrecognised failure kind",),
    )


# ---------------------------------------------------------------------------
# Repair loop
# ---------------------------------------------------------------------------


def repair(
    failures: Sequence[FailureSignature],
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    *,
    budget: RepairBudgetState,
    test_paths: Sequence[str] = (),
    cost_per_attempt: Decimal = Decimal("0"),
) -> RepairOutcome:
    """Attempt bounded repairs, stopping at the first structural reason to stop."""

    attempts: list[RepairAttempt] = []
    current = snapshot
    seen_signatures: dict[str, int] = {}
    unresolved: list[FailureSignature] = []
    stopped = ""
    state = budget

    for signature in failures:
        reason = state.exhausted()
        if reason:
            stopped = reason
            unresolved.append(signature)
            continue

        seen = seen_signatures.get(signature.digest, 0)
        if seen >= 1:
            stopped = (
                f"the same failure signature ({signature.identity}) reappeared after a repair; "
                "the strategy is wrong, not under-applied"
            )
            unresolved.append(signature)
            continue
        seen_signatures[signature.digest] = seen + 1

        if not signature.repairable:
            unresolved.append(signature)
            attempts.append(
                RepairAttempt(
                    attempt=len(attempts) + 1,
                    candidate=RepairCandidate(signature, "none", "failure kind is not in the repair vocabulary"),
                    applied=False,
                    accepted=False,
                    reason="not repairable by construction",
                )
            )
            continue

        candidate = generate_candidate(signature, current, index)
        if not candidate.actionable:
            unresolved.append(signature)
            attempts.append(
                RepairAttempt(
                    attempt=len(attempts) + 1,
                    candidate=candidate,
                    applied=False,
                    accepted=False,
                    reason=candidate.rationale,
                )
            )
            continue

        try:
            attempt_patch, attempted = patch_from_edits(current, candidate.edits, step_id="repair")
        except ContractError as error:
            unresolved.append(signature)
            attempts.append(
                RepairAttempt(
                    attempt=len(attempts) + 1,
                    candidate=candidate,
                    applied=False,
                    accepted=False,
                    reason=f"candidate could not be applied: {error.message}",
                )
            )
            continue

        cheating = analyse_cheating(attempt_patch, current, attempted, test_paths=test_paths)
        if not cheating.clean:
            #: A repair that trips anti-cheat is discarded whole.  This is the
            #: structural guarantee that repair cannot make a build green by
            #: removing what was checking it.
            unresolved.append(signature)
            attempts.append(
                RepairAttempt(
                    attempt=len(attempts) + 1,
                    candidate=candidate,
                    applied=False,
                    accepted=False,
                    reason="candidate rejected by anti-cheat: "
                    + "; ".join(f"{item.code} at {item.path}:{item.line}" for item in cheating.blocking),
                )
            )
            continue

        touched = attempt_patch.changed_files
        if state.max_changed_files and state.files_touched + touched > state.max_changed_files:
            stopped = (
                f"applying this candidate would touch {state.files_touched + touched} file(s), "
                f"over the repair budget of {state.max_changed_files}"
            )
            unresolved.append(signature)
            continue

        current = attempted
        state = RepairBudgetState(
            max_attempts=state.max_attempts,
            max_changed_files=state.max_changed_files,
            max_cost_usd=state.max_cost_usd,
            attempts_used=state.attempts_used + 1,
            files_touched=state.files_touched + touched,
            cost_spent=state.cost_spent + cost_per_attempt,
        )
        attempts.append(
            RepairAttempt(
                attempt=len(attempts) + 1,
                candidate=candidate,
                applied=True,
                accepted=True,
                reason=candidate.rationale,
                patch_digest=attempt_patch.digest,
                cost_usd=cost_per_attempt,
            )
        )

    combined = diff_snapshots(snapshot, current, step_id="repair")
    return RepairOutcome(
        attempts=tuple(attempts),
        snapshot=current,
        patch=combined,
        unresolved=tuple(unresolved),
        stopped_because=stopped,
    )


def attribute_to_actions(
    failures: Sequence[FailureSignature],
    source_map: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Map each failure to the recipe actions that touched its file.

    Attribution is what makes a repair explainable: "this failure came from
    action X" is reviewable, "something in the patch broke it" is not.
    """

    by_path: dict[str, set[str]] = {}
    for entry in source_map:
        path = str(entry.get("path", ""))
        for action in entry.get("actionIds", ()):
            by_path.setdefault(path, set()).add(str(action))
    attribution: dict[str, list[str]] = {}
    for signature in failures:
        attribution[signature.identity] = sorted(by_path.get(signature.path, set()))
    return attribution


def budget_from_request(max_attempts: int, max_changed_files: int, max_cost_usd: Decimal) -> RepairBudgetState:
    return RepairBudgetState(
        max_attempts=max_attempts,
        max_changed_files=max_changed_files,
        max_cost_usd=max_cost_usd,
    )


__all__ = [
    "REPAIRABLE_KINDS",
    "FailureSignature",
    "RepairAttempt",
    "RepairBudgetState",
    "RepairCandidate",
    "RepairOutcome",
    "attribute_to_actions",
    "budget_from_request",
    "generate_candidate",
    "normalise_failures",
    "repair",
]
