"""Edits, patches, hunks and inversion.

Everything a Recipe produces lands here as a :class:`TextEdit` — an explicit
replacement over a source range, carrying the action and symbol it came from.
Edits are then:

* **checked for overlap** before anything is applied, so two Recipes editing
  the same range is an error rather than a race;
* **applied right-to-left** within a file, so earlier offsets stay valid;
* **rendered as a minimal unified diff**, computed with ``difflib`` over lines
  rather than by dumping whole files, because a diff that rewrites untouched
  lines destroys reviewability and hides the real change;
* **invertible**, so a rollback is a patch application rather than a restore
  from a snapshot that may no longer exist.

Every hunk carries a stable ``hunk_id`` derived from its content and position.
That id is what the evidence bundle uses to map a changed line back to the plan
step, Recipe action and symbol that produced it.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    ContractError,
    canonical_json,
    detect_newline,
    normalize_newlines,
    normalize_relative_path,
    sha256_payload,
    sha256_text,
)
from .workspace import WorkspaceSnapshot

#: Lines of unchanged context kept around each hunk in a rendered diff.
CONTEXT_LINES = 3


@dataclass(frozen=True, slots=True)
class TextEdit:
    """A replacement over ``[start_line, end_line]`` (1-based, inclusive lines).

    Columns are 0-based character offsets within their line.  ``end_column`` is
    exclusive, so a zero-width edit (an insertion) has
    ``start == end``.
    """

    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    replacement: str
    action_id: str = ""
    symbol: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ContractError("invalid_edit_range", f"edit on '{self.path}' has an inverted or zero-based range")
        if self.start_line == self.end_line and self.end_column < self.start_column:
            raise ContractError("invalid_edit_range", f"edit on '{self.path}' has an inverted column range")
        if self.start_column < 0 or self.end_column < 0:
            raise ContractError("invalid_edit_range", f"edit on '{self.path}' has a negative column")

    @property
    def key(self) -> tuple[str, int, int, int, int]:
        return (self.path, self.start_line, self.start_column, self.end_line, self.end_column)

    @property
    def insertion(self) -> bool:
        return self.start_line == self.end_line and self.start_column == self.end_column

    def overlaps(self, other: TextEdit) -> bool:
        """True when two edits on the same file touch the same characters.

        Two insertions at the identical point also count as overlapping: their
        relative order would decide the result, and an order that depends on
        iteration is not deterministic.
        """

        if self.path != other.path:
            return False
        left = (self.start_line, self.start_column)
        left_end = (self.end_line, self.end_column)
        right = (other.start_line, other.start_column)
        right_end = (other.end_line, other.end_column)
        if self.insertion and other.insertion:
            return left == right
        return left < right_end and right < left_end

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "startLine": self.start_line,
            "startColumn": self.start_column,
            "endLine": self.end_line,
            "endColumn": self.end_column,
            "replacementDigest": sha256_text(self.replacement),
            "replacementLength": len(self.replacement),
        }
        if self.action_id:
            payload["actionId"] = self.action_id
        if self.symbol:
            payload["symbol"] = self.symbol
        if self.rationale:
            payload["rationale"] = self.rationale
        return payload


def check_overlaps(edits: Sequence[TextEdit]) -> tuple[tuple[TextEdit, TextEdit], ...]:
    """All overlapping pairs, grouped per file for O(n log n) behaviour."""

    by_path: dict[str, list[TextEdit]] = {}
    for edit in edits:
        by_path.setdefault(edit.path, []).append(edit)
    found: list[tuple[TextEdit, TextEdit]] = []
    for items in by_path.values():
        ordered = sorted(items, key=lambda item: (item.start_line, item.start_column, item.end_line, item.end_column))
        for index, edit in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if (other.start_line, other.start_column) >= (edit.end_line, edit.end_column) and not (
                    edit.insertion and other.insertion
                ):
                    break
                if edit.overlaps(other):
                    found.append((edit, other))
    return tuple(found)


def apply_edits(text: str, edits: Sequence[TextEdit]) -> str:
    """Apply ``edits`` to ``text``, preserving its original newline style.

    Applying right-to-left keeps every not-yet-applied offset valid, which is
    why no offset recalculation is needed and why the result cannot depend on
    the order edits were discovered in.
    """

    if not edits:
        return text
    overlapping = check_overlaps(edits)
    if overlapping:
        first, second = overlapping[0]
        raise ContractError(
            "overlapping_edits",
            f"edits overlap in '{first.path}' at lines {first.start_line} and {second.start_line}",
            {"actions": sorted({first.action_id, second.action_id})},
        )
    newline = detect_newline(text)
    body = normalize_newlines(text)
    lines = body.split("\n")
    ordered = sorted(
        edits,
        key=lambda item: (item.start_line, item.start_column, item.end_line, item.end_column),
        reverse=True,
    )
    for edit in ordered:
        if edit.end_line > len(lines):
            raise ContractError(
                "edit_out_of_range",
                f"edit on '{edit.path}' ends at line {edit.end_line} but the file has {len(lines)} line(s)",
            )
        start_index = edit.start_line - 1
        end_index = edit.end_line - 1
        prefix = lines[start_index][: edit.start_column]
        suffix = lines[end_index][edit.end_column :]
        merged = (prefix + normalize_newlines(edit.replacement) + suffix).split("\n")
        lines[start_index : end_index + 1] = merged
    result = "\n".join(lines)
    return result.replace("\n", newline) if newline != "\n" else result


@dataclass(frozen=True, slots=True)
class Hunk:
    """One contiguous changed region of one file."""

    hunk_id: str
    path: str
    before_start: int
    before_length: int
    after_start: int
    after_length: int
    before_lines: tuple[str, ...]
    after_lines: tuple[str, ...]
    context_before: tuple[str, ...] = ()
    context_after: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()

    @property
    def added(self) -> int:
        return len(self.after_lines)

    @property
    def removed(self) -> int:
        return len(self.before_lines)

    def render(self) -> str:
        header = (
            f"@@ -{self.before_start},{self.before_length + len(self.context_before) + len(self.context_after)} "
            f"+{self.after_start},{self.after_length + len(self.context_before) + len(self.context_after)} @@"
        )
        body = [header]
        body.extend(f" {line}" for line in self.context_before)
        body.extend(f"-{line}" for line in self.before_lines)
        body.extend(f"+{line}" for line in self.after_lines)
        body.extend(f" {line}" for line in self.context_after)
        return "\n".join(body)

    def to_payload(self) -> dict[str, Any]:
        return {
            "hunkId": self.hunk_id,
            "path": self.path,
            "beforeStart": self.before_start,
            "beforeLength": self.before_length,
            "afterStart": self.after_start,
            "afterLength": self.after_length,
            "added": self.added,
            "removed": self.removed,
            "actionIds": list(self.action_ids),
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    before_digest: str | None
    after_digest: str | None
    hunks: tuple[Hunk, ...]
    before_text: str | None = field(default=None, repr=False, compare=False)
    after_text: str | None = field(default=None, repr=False, compare=False)

    @property
    def created(self) -> bool:
        return self.before_digest is None

    @property
    def deleted(self) -> bool:
        return self.after_digest is None

    @property
    def added_lines(self) -> int:
        return sum(hunk.added for hunk in self.hunks)

    @property
    def removed_lines(self) -> int:
        return sum(hunk.removed for hunk in self.hunks)

    def render(self) -> str:
        before_label = "/dev/null" if self.created else f"a/{self.path}"
        after_label = "/dev/null" if self.deleted else f"b/{self.path}"
        lines = [f"--- {before_label}", f"+++ {after_label}"]
        lines.extend(hunk.render() for hunk in self.hunks)
        return "\n".join(lines)

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "beforeDigest": self.before_digest,
            "afterDigest": self.after_digest,
            "created": self.created,
            "deleted": self.deleted,
            "addedLines": self.added_lines,
            "removedLines": self.removed_lines,
            "hunks": [hunk.to_payload() for hunk in self.hunks],
        }


@dataclass(frozen=True, slots=True)
class PatchSet:
    """A complete, applicable, invertible change over one snapshot."""

    base_revision: str
    base_tree_digest: str
    changes: tuple[FileChange, ...]
    recipe_lock_digest: str = ""
    step_id: str = ""

    # -- shape -----------------------------------------------------------

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(change.path for change in self.changes)

    @property
    def changed_files(self) -> int:
        return len(self.changes)

    @property
    def changed_lines(self) -> int:
        return sum(change.added_lines + change.removed_lines for change in self.changes)

    @property
    def hunks(self) -> tuple[Hunk, ...]:
        return tuple(hunk for change in self.changes for hunk in change.hunks)

    @property
    def empty(self) -> bool:
        return not self.changes

    def change_for(self, path: str) -> FileChange | None:
        for change in self.changes:
            if change.path == path:
                return change
        return None

    # -- rendering and identity ------------------------------------------

    def render(self) -> str:
        return "\n".join(change.render() for change in self.changes)

    def to_payload(self) -> dict[str, Any]:
        return {
            "baseRevision": self.base_revision,
            "baseTreeDigest": self.base_tree_digest,
            "recipeLockDigest": self.recipe_lock_digest,
            "stepId": self.step_id,
            "changedFiles": self.changed_files,
            "changedLines": self.changed_lines,
            "changes": [change.to_payload() for change in self.changes],
        }

    @property
    def digest(self) -> str:
        """Content identity: the same logical change always hashes the same.

        Deliberately excludes ``step_id`` so that the *same* transformation
        produced by two different steps is recognisable as the same patch —
        which is what makes second-run-zero-diff checkable.
        """

        return sha256_payload(
            {
                "baseTreeDigest": self.base_tree_digest,
                "changes": [
                    {
                        "path": change.path,
                        "before": change.before_digest,
                        "after": change.after_digest,
                    }
                    for change in self.changes
                ],
            }
        )

    # -- application -----------------------------------------------------

    def apply(self, snapshot: WorkspaceSnapshot, *, verify_base: bool = True) -> WorkspaceSnapshot:
        """Apply this patch to ``snapshot``, refusing a drifted base."""

        if verify_base and snapshot.tree_digest != self.base_tree_digest:
            raise ContractError(
                "patch_base_mismatch",
                "the patch was produced against a different tree; re-plan rather than force-apply",
                {"expected": self.base_tree_digest, "found": snapshot.tree_digest},
            )
        replacements: dict[str, str | None] = {}
        for change in self.changes:
            if change.deleted:
                replacements[change.path] = None
                continue
            if change.after_text is None:
                raise ContractError(
                    "patch_not_materialised",
                    f"change for '{change.path}' has no materialised content to apply",
                )
            if not change.created:
                record = snapshot.get(change.path)
                if record is None:
                    raise ContractError("patch_target_missing", f"'{change.path}' is not present in the snapshot")
                if record.content_digest != change.before_digest:
                    raise ContractError(
                        "patch_target_drifted",
                        f"'{change.path}' changed since the patch was computed",
                    )
            replacements[change.path] = change.after_text
        return snapshot.with_files(replacements)

    def invert(self) -> PatchSet:
        """The patch that undoes this one, computed rather than remembered."""

        inverted: list[FileChange] = []
        for change in self.changes:
            inverted.append(
                _diff_file(
                    change.path,
                    change.after_text,
                    change.before_text,
                    action_ids=tuple(sorted({item for hunk in change.hunks for item in hunk.action_ids})),
                    symbols=tuple(sorted({item for hunk in change.hunks for item in hunk.symbols})),
                )
            )
        return PatchSet(
            base_revision=self.base_revision,
            base_tree_digest="",
            changes=tuple(item for item in inverted if item.hunks or item.created or item.deleted),
            recipe_lock_digest=self.recipe_lock_digest,
            step_id=self.step_id,
        )

    def merge(self, other: PatchSet) -> PatchSet:
        """Merge two disjoint patches; overlapping files are a hard error.

        Shard results are merged with this, which is why "merge-if-disjoint"
        is the only supported semantic: silently picking a winner would make
        the final tree depend on shard completion order.
        """

        if self.base_tree_digest and other.base_tree_digest and self.base_tree_digest != other.base_tree_digest:
            raise ContractError("patch_base_mismatch", "cannot merge patches computed against different trees")
        overlap = sorted(set(self.paths) & set(other.paths))
        if overlap:
            raise ContractError(
                "patch_merge_conflict",
                "patches touch the same file(s): " + ", ".join(overlap),
                {"paths": overlap},
            )
        return PatchSet(
            base_revision=self.base_revision or other.base_revision,
            base_tree_digest=self.base_tree_digest or other.base_tree_digest,
            changes=tuple(sorted((*self.changes, *other.changes), key=lambda item: item.path)),
            recipe_lock_digest=self.recipe_lock_digest or other.recipe_lock_digest,
            step_id=self.step_id or other.step_id,
        )


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _split(text: str | None) -> list[str]:
    if text is None:
        return []
    body = normalize_newlines(text)
    lines = body.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _hunk_id(path: str, before_start: int, before: Sequence[str], after: Sequence[str]) -> str:
    return sha256_payload(
        {"path": path, "start": before_start, "before": list(before), "after": list(after)}
    )[:24]


def _diff_file(
    path: str,
    before_text: str | None,
    after_text: str | None,
    *,
    action_ids: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    context: int = CONTEXT_LINES,
) -> FileChange:
    before_lines = _split(before_text)
    after_lines = _split(after_text)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    hunks: list[Hunk] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            Hunk(
                hunk_id=_hunk_id(path, i1 + 1, before_lines[i1:i2], after_lines[j1:j2]),
                path=path,
                before_start=i1 + 1,
                before_length=i2 - i1,
                after_start=j1 + 1,
                after_length=j2 - j1,
                before_lines=tuple(before_lines[i1:i2]),
                after_lines=tuple(after_lines[j1:j2]),
                context_before=tuple(before_lines[max(0, i1 - context) : i1]),
                context_after=tuple(before_lines[i2 : i2 + context]),
                action_ids=action_ids,
                symbols=symbols,
            )
        )
    return FileChange(
        path=path,
        before_digest=None if before_text is None else sha256_text(before_text),
        after_digest=None if after_text is None else sha256_text(after_text),
        hunks=tuple(hunks),
        before_text=before_text,
        after_text=after_text,
    )


def diff_snapshots(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    *,
    step_id: str = "",
    recipe_lock_digest: str = "",
    edits: Sequence[TextEdit] = (),
) -> PatchSet:
    """Compute the minimal patch between two snapshots.

    Attribution comes from ``edits``: each hunk is labelled with the action ids
    and symbols of the edits that fall inside its line range, which is what
    makes "which Recipe produced this line?" answerable from the patch alone.
    """

    by_path: dict[str, list[TextEdit]] = {}
    for edit in edits:
        by_path.setdefault(edit.path, []).append(edit)

    changes: list[FileChange] = []
    for path in sorted(set(before.paths) | set(after.paths)):
        before_record = before.get(path)
        after_record = after.get(path)
        before_digest = before_record.content_digest if before_record else None
        after_digest = after_record.content_digest if after_record else None
        if before_digest == after_digest:
            continue
        before_text = before_record.text if before_record else None
        after_text = after_record.text if after_record else None
        if before_record is not None and before_text is None:
            raise ContractError(
                "unreadable_patch_source",
                f"'{path}' changed but its previous content is not readable; refusing to synthesise a diff",
            )
        change = _diff_file(path, before_text, after_text)
        change = _attribute(change, by_path.get(path, ()))
        changes.append(change)
    return PatchSet(
        base_revision=before.revision,
        base_tree_digest=before.tree_digest,
        changes=tuple(changes),
        recipe_lock_digest=recipe_lock_digest,
        step_id=step_id,
    )


def _attribute(change: FileChange, edits: Sequence[TextEdit]) -> FileChange:
    if not edits:
        return change
    attributed: list[Hunk] = []
    for hunk in change.hunks:
        start = hunk.before_start
        end = start + max(hunk.before_length, 1) - 1
        touching = [
            edit
            for edit in edits
            if not (edit.end_line < start - 1 or edit.start_line > end + 1)
        ]
        attributed.append(
            Hunk(
                hunk_id=hunk.hunk_id,
                path=hunk.path,
                before_start=hunk.before_start,
                before_length=hunk.before_length,
                after_start=hunk.after_start,
                after_length=hunk.after_length,
                before_lines=hunk.before_lines,
                after_lines=hunk.after_lines,
                context_before=hunk.context_before,
                context_after=hunk.context_after,
                action_ids=tuple(sorted({edit.action_id for edit in touching if edit.action_id})),
                symbols=tuple(sorted({edit.symbol for edit in touching if edit.symbol})),
            )
        )
    return FileChange(
        path=change.path,
        before_digest=change.before_digest,
        after_digest=change.after_digest,
        hunks=tuple(attributed),
        before_text=change.before_text,
        after_text=change.after_text,
    )


def patch_from_edits(
    snapshot: WorkspaceSnapshot,
    edits: Sequence[TextEdit],
    *,
    step_id: str = "",
    recipe_lock_digest: str = "",
    creations: Mapping[str, str] | None = None,
    deletions: Iterable[str] = (),
) -> tuple[PatchSet, WorkspaceSnapshot]:
    """Apply ``edits`` (plus creations/deletions) and return the patch and result."""

    by_path: dict[str, list[TextEdit]] = {}
    for edit in edits:
        normalized = normalize_relative_path(edit.path, "edit.path")
        by_path.setdefault(normalized, []).append(edit)

    replacements: dict[str, str | None] = {}
    for path, items in by_path.items():
        record = snapshot.get(path)
        if record is None:
            raise ContractError("edit_target_missing", f"'{path}' is not present in the snapshot")
        if record.text is None:
            raise ContractError(
                "edit_target_unreadable",
                f"'{path}' has no readable text; a binary or oversized file cannot be edited textually",
            )
        replacements[path] = apply_edits(record.text, items)
    for path, content in (creations or {}).items():
        normalized = normalize_relative_path(path, "creation.path")
        if normalized in snapshot:
            raise ContractError("creation_conflict", f"'{normalized}' already exists")
        replacements[normalized] = content
    for path in deletions:
        normalized = normalize_relative_path(path, "deletion.path")
        if normalized not in snapshot:
            raise ContractError("deletion_target_missing", f"'{normalized}' is not present in the snapshot")
        replacements[normalized] = None

    updated = snapshot.with_files(replacements)
    patch = diff_snapshots(
        snapshot,
        updated,
        step_id=step_id,
        recipe_lock_digest=recipe_lock_digest,
        edits=edits,
    )
    return patch, updated


def unified_diff_text(patch: PatchSet) -> str:
    return patch.render()


def patch_summary(patch: PatchSet) -> dict[str, Any]:
    return {
        "digest": patch.digest,
        "changedFiles": patch.changed_files,
        "changedLines": patch.changed_lines,
        "hunks": len(patch.hunks),
        "created": sorted(change.path for change in patch.changes if change.created),
        "deleted": sorted(change.path for change in patch.changes if change.deleted),
        "modified": sorted(
            change.path for change in patch.changes if not change.created and not change.deleted
        ),
        "renderedDigest": sha256_text(patch.render()),
        "canonical": sha256_text(canonical_json(patch.to_payload())),
    }


__all__ = [
    "CONTEXT_LINES",
    "FileChange",
    "Hunk",
    "PatchSet",
    "TextEdit",
    "apply_edits",
    "check_overlaps",
    "diff_snapshots",
    "patch_from_edits",
    "patch_summary",
    "unified_diff_text",
]
