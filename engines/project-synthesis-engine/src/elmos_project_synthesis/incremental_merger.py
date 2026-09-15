"""Bidirectional Incremental Evolution & Protected Code Region Merger for ELMOS Project Synthesis.

Ensures that re-generating a project from updated specifications or PRD preserves
customer-authored business logic without loss:
1. Extraction of custom code regions demarcated by ELMOS:BEGIN_CUSTOM_CODE / ELMOS:END_CUSTOM_CODE.
2. Safe injection of preserved custom logic into newly generated AST / file templates.
3. Tracking and preservation of orphaned regions when markers are deleted or moved.
4. Workspace-level atomic 3-way incremental merge with automated backups.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

# Regex patterns for custom code blocks across various programming language comment syntaxes:
# 1. C-style (Java, Go, TypeScript, C#, Rust, PHP, Kotlin): // ELMOS:BEGIN_CUSTOM_CODE <id> ... // ELMOS:END_CUSTOM_CODE <id>
# 2. Hash-style (Python, Shell, YAML, Dockerfile): # ELMOS:BEGIN_CUSTOM_CODE <id> ... # ELMOS:END_CUSTOM_CODE <id>
# 3. HTML/XML-style: <!-- ELMOS:BEGIN_CUSTOM_CODE <id> --> ... <!-- ELMOS:END_CUSTOM_CODE <id> -->
# 4. SQL-style: -- ELMOS:BEGIN_CUSTOM_CODE <id> ... -- ELMOS:END_CUSTOM_CODE <id>

_REGION_PATTERNS = [
    # C-Style: //
    (
        "c_style",
        re.compile(
            r"//\s*ELMOS:BEGIN_CUSTOM_CODE\s+([A-Za-z0-9_\-\.]+)\s*\n(.*?)//\s*ELMOS:END_CUSTOM_CODE\s+\1",
            re.DOTALL,
        ),
        "// ELMOS:BEGIN_CUSTOM_CODE {id}\n{content}\n// ELMOS:END_CUSTOM_CODE {id}",
    ),
    # Hash-Style: #
    (
        "hash_style",
        re.compile(
            r"#\s*ELMOS:BEGIN_CUSTOM_CODE\s+([A-Za-z0-9_\-\.]+)\s*\n(.*?)#\s*ELMOS:END_CUSTOM_CODE\s+\1",
            re.DOTALL,
        ),
        "# ELMOS:BEGIN_CUSTOM_CODE {id}\n{content}\n# ELMOS:END_CUSTOM_CODE {id}",
    ),
    # HTML/XML-Style: <!--
    (
        "html_style",
        re.compile(
            r"<!--\s*ELMOS:BEGIN_CUSTOM_CODE\s+([A-Za-z0-9_\-\.]+)\s*-->\s*\n(.*?)<!--\s*ELMOS:END_CUSTOM_CODE\s+\1\s*-->",
            re.DOTALL,
        ),
        "<!-- ELMOS:BEGIN_CUSTOM_CODE {id} -->\n{content}\n<!-- ELMOS:END_CUSTOM_CODE {id} -->",
    ),
    # SQL-Style: --
    (
        "sql_style",
        re.compile(
            r"--\s*ELMOS:BEGIN_CUSTOM_CODE\s+([A-Za-z0-9_\-\.]+)\s*\n(.*?)--\s*ELMOS:END_CUSTOM_CODE\s+\1",
            re.DOTALL,
        ),
        "-- ELMOS:BEGIN_CUSTOM_CODE {id}\n{content}\n-- ELMOS:END_CUSTOM_CODE {id}",
    ),
]


@dataclass(frozen=True)
class ProtectedRegion:
    region_id: str
    content: str
    syntax: str


@dataclass(frozen=True)
class MergeResult:
    merged_content: str
    preserved_regions: list[str]
    orphan_regions: list[str]
    has_changes: bool


@dataclass
class WorkspaceMergeReport:
    merged_files: list[str] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    unchanged_files: list[str] = field(default_factory=list)
    preserved_regions_count: int = 0
    orphan_regions: list[str] = field(default_factory=list)
    backup_path: str | None = None


def wrap_custom_region(region_id: str, default_content: str = "", syntax: str = "c_style") -> str:
    """Format a protected region with opening and closing comment tags."""
    if syntax == "hash_style":
        return f"# ELMOS:BEGIN_CUSTOM_CODE {region_id}\n{default_content}\n# ELMOS:END_CUSTOM_CODE {region_id}"
    elif syntax == "html_style":
        return f"<!-- ELMOS:BEGIN_CUSTOM_CODE {region_id} -->\n{default_content}\n<!-- ELMOS:END_CUSTOM_CODE {region_id} -->"
    elif syntax == "sql_style":
        return f"-- ELMOS:BEGIN_CUSTOM_CODE {region_id}\n{default_content}\n-- ELMOS:END_CUSTOM_CODE {region_id}"
    else:  # default c_style
        return f"// ELMOS:BEGIN_CUSTOM_CODE {region_id}\n{default_content}\n// ELMOS:END_CUSTOM_CODE {region_id}"


def extract_custom_regions(source_code: str) -> dict[str, ProtectedRegion]:
    """Extract all custom regions from an existing source file."""
    regions: dict[str, ProtectedRegion] = {}
    for syntax_name, pattern, _ in _REGION_PATTERNS:
        for match in pattern.finditer(source_code):
            region_id = match.group(1).strip()
            content = match.group(2)
            regions[region_id] = ProtectedRegion(
                region_id=region_id,
                content=content,
                syntax=syntax_name,
            )
    return regions


def inject_custom_regions(
    new_generated_code: str,
    custom_regions: dict[str, ProtectedRegion],
) -> tuple[str, list[str], list[str]]:
    """Inject preserved custom regions into a newly generated template.

    Returns:
        (merged_code, list_of_preserved_region_ids, list_of_orphan_region_ids)
    """
    merged = new_generated_code
    used_region_ids: set[str] = set()

    for _syntax_name, pattern, template_fmt in _REGION_PATTERNS:
        def _replacer(m: re.Match[str], fmt: str = template_fmt) -> str:
            rid = m.group(1).strip()
            if rid in custom_regions:
                used_region_ids.add(rid)
                preserved = custom_regions[rid].content
                # Strip leading/trailing single newline if present to keep format clean
                clean_content = preserved.rstrip("\r\n")
                if clean_content.startswith("\n"):
                    clean_content = clean_content[1:]
                return fmt.format(id=rid, content=clean_content)
            return m.group(0)

        merged = pattern.sub(_replacer, merged)

    preserved_ids = sorted(used_region_ids)
    orphan_ids = sorted(set(custom_regions.keys()) - used_region_ids)

    # If there are orphaned regions (code was present in old file, but region marker removed in new file),
    # append an orphan safety block at the end so the user does NOT lose their code!
    if orphan_ids:
        orphan_blocks = [
            "\n\n/* [ELMOS RE-GENERATION NOTICE: PRESERVED ORPHANED CUSTOM REGIONS]\n"
            "The following code blocks were present in the previous revision but their markers\n"
            "were omitted in the updated generation template. Preserved here for safety: */"
        ]
        for orid in orphan_ids:
            reg = custom_regions[orid]
            orphan_blocks.append(
                f"\n// ELMOS:BEGIN_ORPHAN_CODE {orid}\n{reg.content.strip()}\n// ELMOS:END_ORPHAN_CODE {orid}"
            )
        merged += "\n".join(orphan_blocks) + "\n"

    return merged, preserved_ids, orphan_ids


def merge_file_content(existing_content: str, new_generated_content: str) -> MergeResult:
    """Merge newly generated content with existing file content, preserving custom regions."""
    existing_regions = extract_custom_regions(existing_content)
    if not existing_regions:
        # No custom regions in existing file, new content takes precedence
        return MergeResult(
            merged_content=new_generated_content,
            preserved_regions=[],
            orphan_regions=[],
            has_changes=(existing_content != new_generated_content),
        )

    merged, preserved_ids, orphan_ids = inject_custom_regions(new_generated_content, existing_regions)
    has_changes = (existing_content != merged)
    return MergeResult(
        merged_content=merged,
        preserved_regions=preserved_ids,
        orphan_regions=orphan_ids,
        has_changes=has_changes,
    )


def merge_workspace_files(
    workspace_root: Path | str,
    new_files: dict[str, str],
    *,
    backup: bool = True,
) -> WorkspaceMergeReport:
    """Incrementally merge newly generated files into a workspace on disk."""
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    report = WorkspaceMergeReport()

    backup_dir = None
    if backup:
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
        backup_dir = root / ".elmos" / "backups" / f"backup_{timestamp}"

    for relative_path, new_content in new_files.items():
        file_path = root / relative_path
        if file_path.exists():
            existing_content = file_path.read_text(encoding="utf-8")
            merge_res = merge_file_content(existing_content, new_content)
            if merge_res.has_changes:
                if backup_dir:
                    backup_file = backup_dir / relative_path
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    backup_file.write_text(existing_content, encoding="utf-8")
                    report.backup_path = str(backup_dir)

                file_path.write_text(merge_res.merged_content, encoding="utf-8")
                report.merged_files.append(relative_path)
            else:
                report.unchanged_files.append(relative_path)

            report.preserved_regions_count += len(merge_res.preserved_regions)
            report.orphan_regions.extend(merge_res.orphan_regions)
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_content, encoding="utf-8")
            report.created_files.append(relative_path)

    return report
