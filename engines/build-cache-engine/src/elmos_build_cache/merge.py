"""Generated/user ownership, conflict detection and three-way merge.

User-owned content is never overwritten silently. Ownership is explicit per
path, and for shared files it is explicit per *protected region* -- the marked
blocks a human edited inside an otherwise generated file.

Every unresolved conflict is preserved in CAS with all three sides (base, ours,
theirs) so a later run, or a human, can resolve it without re-deriving anything.
Binary and unsupported-schema conflicts fail closed.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .canonical import canonical_json_bytes, digest_of, normalize_logical_path, sha256_bytes
from .cas import ContentAddressableStore
from .enums import Ownership
from .errors import ConflictError

SCHEMA_VERSION = "1.0.0"

#: ``ELMOS:BEGIN PROTECTED <name>`` ... ``ELMOS:END PROTECTED <name>``
PROTECTED_BEGIN = re.compile(r"^\s*\S*\s*ELMOS:BEGIN\s+PROTECTED\s+(?P<name>[\w.\-]+)\s*\S*\s*$")
PROTECTED_END = re.compile(r"^\s*\S*\s*ELMOS:END\s+PROTECTED\s+(?P<name>[\w.\-]+)\s*\S*\s*$")

TEXT_MERGEABLE_SUFFIXES = frozenset(
    {
        ".java", ".kt", ".py", ".cs", ".go", ".rs", ".cpp", ".hpp", ".h", ".php", ".ts", ".tsx",
        ".js", ".jsx", ".m", ".mm", ".swift", ".dart", ".md", ".txt", ".yaml", ".yml", ".toml",
        ".json", ".xml", ".gradle", ".properties", ".cfg", ".ini", ".sql", ".sh",
    }
)


class ConflictKind(str):
    PATH = "PATH"
    CASE = "CASE"
    MODULE = "MODULE"
    SYMBOL = "SYMBOL"
    DEPENDENCY_MANIFEST = "DEPENDENCY_MANIFEST"
    PROTECTED_REGION = "PROTECTED_REGION"
    BINARY = "BINARY"
    SCHEMA = "SCHEMA"


@dataclass(frozen=True)
class Conflict:
    kind: str
    logical_path: str
    detail: str
    ours_digest: str | None = None
    theirs_digest: str | None = None
    base_digest: str | None = None
    region: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "logical_path": self.logical_path,
            "detail": self.detail,
            "ours_digest": self.ours_digest,
            "theirs_digest": self.theirs_digest,
            "base_digest": self.base_digest,
            "region": self.region,
        }


@dataclass(frozen=True)
class MergeResult:
    logical_path: str
    merged: bytes | None
    conflicts: tuple[Conflict, ...]
    decisions: tuple[str, ...]
    strategy: str

    @property
    def clean(self) -> bool:
        return not self.conflicts and self.merged is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_path": self.logical_path,
            "strategy": self.strategy,
            "clean": self.clean,
            "merged_digest": sha256_bytes(self.merged) if self.merged is not None else None,
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "decisions": list(self.decisions),
        }


@dataclass
class OwnershipMap:
    """Path-level ownership. Longest matching prefix wins."""

    rules: dict[str, Ownership] = field(default_factory=dict)
    default: Ownership = Ownership.GENERATED

    def set(self, prefix: str, ownership: Ownership) -> None:
        self.rules[normalize_logical_path(prefix) if prefix else ""] = ownership

    def of(self, logical_path: str) -> Ownership:
        path = normalize_logical_path(logical_path)
        best: tuple[int, Ownership] = (-1, self.default)
        for prefix, ownership in self.rules.items():
            if prefix == path or path.startswith(prefix.rstrip("/") + "/"):
                if len(prefix) > best[0]:
                    best = (len(prefix), ownership)
        return best[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "default": str(self.default),
            "rules": {prefix: str(value) for prefix, value in sorted(self.rules.items())},
        }


# --------------------------------------------------------------------------
# protected regions
# --------------------------------------------------------------------------
def extract_protected_regions(text: str) -> dict[str, list[str]]:
    """Return ``{region_name: lines}`` for each marked human-owned block."""
    regions: dict[str, list[str]] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        begin = PROTECTED_BEGIN.match(line)
        end = PROTECTED_END.match(line)
        if begin:
            if current is not None:
                raise ConflictError("nested protected regions are not supported", region=begin.group("name"))
            current = begin.group("name")
            buffer = []
            continue
        if end:
            name = end.group("name")
            if current != name:
                raise ConflictError("mismatched protected region markers", region=name)
            regions[name] = buffer
            current = None
            continue
        if current is not None:
            buffer.append(line)
    if current is not None:
        raise ConflictError("unterminated protected region", region=current)
    return regions


def splice_protected_regions(generated: str, preserved: Mapping[str, Sequence[str]]) -> tuple[str, list[str]]:
    """Put the human's region contents back into freshly generated output."""
    out: list[str] = []
    applied: list[str] = []
    current: str | None = None
    for line in generated.splitlines():
        begin = PROTECTED_BEGIN.match(line)
        end = PROTECTED_END.match(line)
        if begin:
            current = begin.group("name")
            out.append(line)
            if current in preserved:
                out.extend(preserved[current])
                applied.append(current)
            continue
        if end:
            out.append(line)
            current = None
            continue
        if current is not None and current in preserved:
            continue  # the generated placeholder is replaced by the human text
        out.append(line)
    trailing = "\n" if generated.endswith("\n") else ""
    return "\n".join(out) + trailing, applied


# --------------------------------------------------------------------------
# three-way merge
# --------------------------------------------------------------------------
def three_way_merge(
    logical_path: str,
    base: bytes | None,
    ours: bytes,
    theirs: bytes,
    ownership: Ownership = Ownership.SHARED,
) -> MergeResult:
    """Merge ``theirs`` (newly generated) into ``ours`` (on disk) against ``base``.

    ``ours`` is what the user currently has; ``theirs`` is the new generation.
    Non-text payloads fail closed rather than guessing.
    """
    decisions: list[str] = []
    if ours == theirs:
        return MergeResult(logical_path, ours, (), ("identical content",), "identity")

    if ownership is Ownership.USER:
        return MergeResult(
            logical_path,
            ours,
            (),
            ("user-owned path: generated content is not applied",),
            "user-owned",
        )
    if ownership is Ownership.EXTERNAL:
        return MergeResult(
            logical_path,
            ours,
            (),
            ("externally managed path: left untouched",),
            "external",
        )
    if ownership is Ownership.GENERATED:
        if base is not None and base != ours:
            return MergeResult(
                logical_path,
                None,
                (
                    Conflict(
                        ConflictKind.PATH,
                        logical_path,
                        "generated-owned file was edited by hand",
                        ours_digest=sha256_bytes(ours),
                        theirs_digest=sha256_bytes(theirs),
                        base_digest=sha256_bytes(base),
                    ),
                ),
                ("refusing to discard a hand edit to a generated-owned file",),
                "generated-owned",
            )
        return MergeResult(logical_path, theirs, (), ("generated-owned: replaced",), "generated-owned")

    suffix = "." + logical_path.rsplit(".", 1)[-1] if "." in logical_path else ""
    if not _is_text(ours) or not _is_text(theirs) or suffix not in TEXT_MERGEABLE_SUFFIXES:
        return MergeResult(
            logical_path,
            None,
            (
                Conflict(
                    ConflictKind.BINARY,
                    logical_path,
                    "binary or unsupported file type cannot be merged",
                    ours_digest=sha256_bytes(ours),
                    theirs_digest=sha256_bytes(theirs),
                    base_digest=sha256_bytes(base) if base is not None else None,
                ),
            ),
            ("fail closed on unmergeable content",),
            "fail-closed",
        )

    ours_text = ours.decode("utf-8")
    theirs_text = theirs.decode("utf-8")

    if ownership is Ownership.GENERATED_PROTECTED:
        try:
            preserved = extract_protected_regions(ours_text)
        except ConflictError as exc:
            return MergeResult(
                logical_path,
                None,
                (Conflict(ConflictKind.PROTECTED_REGION, logical_path, str(exc)),),
                ("protected region markers are malformed",),
                "protected-region",
            )
        merged_text, applied = splice_protected_regions(theirs_text, preserved)
        missing = sorted(set(preserved) - set(applied))
        if missing:
            return MergeResult(
                logical_path,
                None,
                tuple(
                    Conflict(
                        ConflictKind.PROTECTED_REGION,
                        logical_path,
                        "the new generation no longer contains this protected region",
                        region=name,
                        ours_digest=sha256_bytes(ours),
                        theirs_digest=sha256_bytes(theirs),
                    )
                    for name in missing
                ),
                (f"preserved {len(applied)} regions",),
                "protected-region",
            )
        decisions.append(f"preserved protected regions: {', '.join(applied) or 'none'}")
        return MergeResult(logical_path, merged_text.encode("utf-8"), (), tuple(decisions), "protected-region")

    base_text = base.decode("utf-8") if base is not None and _is_text(base) else ""
    merged_lines, hunks = _merge_lines(
        base_text.splitlines(keepends=True),
        ours_text.splitlines(keepends=True),
        theirs_text.splitlines(keepends=True),
    )
    if hunks:
        return MergeResult(
            logical_path,
            None,
            tuple(
                Conflict(
                    ConflictKind.PATH,
                    logical_path,
                    f"overlapping edit at lines {start}-{end}",
                    ours_digest=sha256_bytes(ours),
                    theirs_digest=sha256_bytes(theirs),
                    base_digest=sha256_bytes(base) if base is not None else None,
                )
                for start, end in hunks
            ),
            ("three-way merge found overlapping edits",),
            "three-way",
        )
    decisions.append("three-way merge applied cleanly")
    return MergeResult(logical_path, "".join(merged_lines).encode("utf-8"), (), tuple(decisions), "three-way")


def _is_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _merge_lines(
    base: Sequence[str], ours: Sequence[str], theirs: Sequence[str]
) -> tuple[list[str], list[tuple[int, int]]]:
    """Line-level three-way merge over matching blocks from the common base."""
    matcher_ours = difflib.SequenceMatcher(None, base, ours, autojunk=False)
    matcher_theirs = difflib.SequenceMatcher(None, base, theirs, autojunk=False)
    ours_ops = {(i1, i2): (j1, j2) for tag, i1, i2, j1, j2 in matcher_ours.get_opcodes() if tag != "equal"}
    theirs_ops = {
        (i1, i2): (j1, j2) for tag, i1, i2, j1, j2 in matcher_theirs.get_opcodes() if tag != "equal"
    }

    conflicts: list[tuple[int, int]] = []
    for (oi1, oi2) in ours_ops:
        for (ti1, ti2) in theirs_ops:
            if oi1 < ti2 and ti1 < oi2:
                if ours[ours_ops[(oi1, oi2)][0] : ours_ops[(oi1, oi2)][1]] != theirs[
                    theirs_ops[(ti1, ti2)][0] : theirs_ops[(ti1, ti2)][1]
                ]:
                    conflicts.append((min(oi1, ti1), max(oi2, ti2)))
    if conflicts:
        return [], sorted(set(conflicts))

    # No overlap: apply both edit sets against the base.
    edits: list[tuple[int, int, list[str]]] = []
    for (i1, i2), (j1, j2) in ours_ops.items():
        edits.append((i1, i2, list(ours[j1:j2])))
    for (i1, i2), (j1, j2) in theirs_ops.items():
        edits.append((i1, i2, list(theirs[j1:j2])))
    edits.sort(key=lambda item: item[0])

    merged: list[str] = []
    cursor = 0
    for start, end, replacement in edits:
        if start < cursor:
            return [], [(start, end)]
        merged.extend(base[cursor:start])
        merged.extend(replacement)
        cursor = end
    merged.extend(base[cursor:])
    return merged, []


# --------------------------------------------------------------------------
# tree-level conflict detection
# --------------------------------------------------------------------------
def detect_tree_conflicts(
    entries: Mapping[str, str],
    existing: Mapping[str, str] | None = None,
    ownership: OwnershipMap | None = None,
    dependency_files: Iterable[str] = (),
) -> list[Conflict]:
    """Detect path/case/module/dependency conflicts *before* publication."""
    ownership = ownership or OwnershipMap()
    existing = existing or {}
    conflicts: list[Conflict] = []

    folded: dict[str, str] = {}
    for path in sorted(entries):
        key = path.casefold()
        if key in folded and folded[key] != path:
            conflicts.append(
                Conflict(ConflictKind.CASE, path, f"case-collides with {folded[key]!r}")
            )
        folded[key] = path

    ordered = sorted(entries)
    for index, path in enumerate(ordered):
        prefix = path + "/"
        for other in ordered[index + 1 :]:
            if not other.startswith(prefix):
                break
            conflicts.append(
                Conflict(ConflictKind.MODULE, path, f"file also used as a directory by {other!r}")
            )

    for path, digest in sorted(entries.items()):
        owner = ownership.of(path)
        current = existing.get(path)
        if current is None or current == digest:
            continue
        if owner is Ownership.USER:
            conflicts.append(
                Conflict(
                    ConflictKind.PATH,
                    path,
                    "generation would overwrite user-owned content",
                    ours_digest=current,
                    theirs_digest=digest,
                )
            )
        elif owner is Ownership.EXTERNAL:
            conflicts.append(
                Conflict(
                    ConflictKind.PATH,
                    path,
                    "path is managed outside ELMOS",
                    ours_digest=current,
                    theirs_digest=digest,
                )
            )

    for path in sorted(set(dependency_files)):
        if path in entries and path in existing and entries[path] != existing[path]:
            conflicts.append(
                Conflict(
                    ConflictKind.DEPENDENCY_MANIFEST,
                    path,
                    "dependency manifest changed on both sides; use the deterministic merger",
                    ours_digest=existing[path],
                    theirs_digest=entries[path],
                )
            )
    return conflicts


# --------------------------------------------------------------------------
# deterministic structured mergers
# --------------------------------------------------------------------------
def merge_dependency_manifest(
    base: Mapping[str, str], ours: Mapping[str, str], theirs: Mapping[str, str]
) -> tuple[dict[str, str], list[Conflict]]:
    """Union of dependencies; a version disagreement on the same key conflicts."""
    merged: dict[str, str] = dict(ours)
    conflicts: list[Conflict] = []
    for name in sorted(set(base) | set(ours) | set(theirs)):
        in_base = base.get(name)
        in_ours = ours.get(name)
        in_theirs = theirs.get(name)
        if in_ours == in_theirs:
            if in_ours is None:
                merged.pop(name, None)
            continue
        if in_ours == in_base:
            # We did not touch it; take the new generation, including removal.
            if in_theirs is None:
                merged.pop(name, None)
            else:
                merged[name] = in_theirs
            continue
        if in_theirs == in_base:
            # The generator did not touch it; keep the local decision.
            continue
        conflicts.append(
            Conflict(
                ConflictKind.DEPENDENCY_MANIFEST,
                name,
                f"version disagreement: ours={in_ours!r} theirs={in_theirs!r} base={in_base!r}",
            )
        )
    return dict(sorted(merged.items())), conflicts


def merge_registration_list(
    base: Sequence[str], ours: Sequence[str], theirs: Sequence[str]
) -> list[str]:
    """Deterministic union for routing tables and DI registrations."""
    removed = set(base) - set(theirs)
    return sorted((set(ours) | set(theirs)) - removed)


def merge_config_mapping(
    base: Mapping[str, Any], ours: Mapping[str, Any], theirs: Mapping[str, Any]
) -> tuple[dict[str, Any], list[Conflict]]:
    merged: dict[str, Any] = dict(ours)
    conflicts: list[Conflict] = []
    for key in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = base.get(key), ours.get(key), theirs.get(key)
        if o == t:
            continue
        if o == b:
            merged[key] = t
        elif t == b:
            continue
        elif isinstance(o, dict) and isinstance(t, dict):
            nested, nested_conflicts = merge_config_mapping(
                b if isinstance(b, dict) else {}, o, t
            )
            merged[key] = nested
            conflicts.extend(nested_conflicts)
        else:
            conflicts.append(
                Conflict(ConflictKind.SCHEMA, key, f"config disagreement: ours={o!r} theirs={t!r}")
            )
    return dict(sorted(merged.items())), conflicts


# --------------------------------------------------------------------------
# conflict persistence and resolution rules
# --------------------------------------------------------------------------
class ConflictStore:
    """Persists all three sides so a resolution can be replayed deterministically."""

    def __init__(self, cas: ContentAddressableStore) -> None:
        self.cas = cas

    def preserve(
        self,
        logical_path: str,
        conflicts: Sequence[Conflict],
        base: bytes | None,
        ours: bytes,
        theirs: bytes,
    ) -> str:
        base_digest = self.cas.put_bytes(base, artifact_kind="conflict-base") if base is not None else None
        ours_digest = self.cas.put_bytes(ours, artifact_kind="conflict-ours")
        theirs_digest = self.cas.put_bytes(theirs, artifact_kind="conflict-theirs")
        record = {
            "schema_version": SCHEMA_VERSION,
            "kind": "elmos.conflict/v1",
            "logical_path": logical_path,
            "base": base_digest,
            "ours": ours_digest,
            "theirs": theirs_digest,
            "conflicts": [conflict.to_dict() for conflict in conflicts],
        }
        return self.cas.put_bytes(canonical_json_bytes(record), artifact_kind="conflict-record")

    def load(self, digest: str) -> dict[str, Any]:
        document = self.cas.get_document(digest)
        if not isinstance(document, dict):
            raise ConflictError("conflict record is malformed", digest=digest)
        return document


@dataclass
class ResolutionRules:
    """Recorded decisions so a retry produces the same merge, not a new prompt."""

    rules: dict[str, dict[str, Any]] = field(default_factory=dict)

    @staticmethod
    def key(logical_path: str, base: bytes | None, ours: bytes, theirs: bytes) -> str:
        return digest_of(
            {
                "logical_path": logical_path,
                "base": sha256_bytes(base) if base is not None else None,
                "ours": sha256_bytes(ours),
                "theirs": sha256_bytes(theirs),
            }
        )

    def record(
        self,
        logical_path: str,
        base: bytes | None,
        ours: bytes,
        theirs: bytes,
        choice: str,
        actor: str,
        payload: bytes | None = None,
    ) -> str:
        if choice not in ("ours", "theirs", "manual"):
            raise ConflictError("unknown resolution choice", choice=choice)
        key = self.key(logical_path, base, ours, theirs)
        self.rules[key] = {
            "logical_path": logical_path,
            "choice": choice,
            "actor": actor,
            "payload_digest": sha256_bytes(payload) if payload is not None else None,
            "payload": payload,
        }
        return key

    def apply(
        self, logical_path: str, base: bytes | None, ours: bytes, theirs: bytes
    ) -> bytes | None:
        rule = self.rules.get(self.key(logical_path, base, ours, theirs))
        if rule is None:
            return None
        if rule["choice"] == "ours":
            return ours
        if rule["choice"] == "theirs":
            return theirs
        payload = rule.get("payload")
        return payload if isinstance(payload, bytes) else None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: {name: value for name, value in rule.items() if name != "payload"}
            for key, rule in sorted(self.rules.items())
        }
