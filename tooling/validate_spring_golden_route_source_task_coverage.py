#!/usr/bin/env python3
"""Validate the source-task coverage ledger for the Spring Golden Route pack.

The pinned ZIP is specification data, not executable input.  This validator
opens only the archive's regular Markdown/JSON members, derives a stable task
identity from each unchecked Markdown checklist item, and compares those
source facts with the repository-owned installed manifest.  It never imports,
executes, or shells out to anything from the archive.

The source package does not assign IDs to its checklist items.  Consequently,
the repository ledger uses ``<source Skill id>-TASK-<ordinal>``.  The source
Skill ID, source path, source byte digest, source line, and task-line digest
remain part of every record so that a generated ID cannot conceal source
drift.  An inventory match is coverage evidence only; it is not task
implementation, runtime evidence, or certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-spring-golden-route-commercial-skills-v2.0.0"
PACKAGE_NAME = "elmos-spring-golden-route-commercial-skills"
PACKAGE_VERSION = "2.0.0"
ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
MANIFEST_RELATIVE = Path("docs/spring-golden-route-commercial-skills/installed-manifest.json")
LEDGER_RELATIVE = Path("docs/spring-golden-route-commercial-skills/source-task-coverage-ledger.json")

EXPECTED_ARCHIVE_SHA256 = (
    "952dce43681a56dbd3323ef03b334b08d5be980000e9c7ee3f0ac3e3bcd42c4e"
)
EXPECTED_ARCHIVE_BYTES = 1_228_281
EXPECTED_ARCHIVE_ENTRIES = 596
EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES = 2_127_024
EXPECTED_SKILLS = 196
EXPECTED_TASKS = 4_368
EXPECTED_FOUNDATION_SKILLS = 100
EXPECTED_COMMERCIAL_SKILLS = 96
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 512 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 4 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

SOURCE_ROOT = f"{PACKAGE_DIRECTORY}/"
SOURCE_PACKAGE_MANIFEST = "manifest/package.json"
SOURCE_CONTRACT_PREFIX = "contracts/"
SOURCE_TASK_CHECKBOX = re.compile(
    r"^(?P<indent>\s*)-\s*\[(?P<marker>[ xX])\]\s+(?P<text>.*?)\s*$"
)
MARKDOWN_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+(?P<heading>.+?)\s*$")
SAFE_MEMBER = re.compile(r"^[^/].*(?<!/)$")
TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]+-TASK-[0-9]{3}$")

NOT_RUN = "NOT_RUN"
NOT_CERTIFIED = "NOT_CERTIFIED"
TASK_STATUS = NOT_RUN
EXECUTION_STATUS = "BLOCKED"
BLOCK_REASON = "SOURCE_SPECIFICATION_ONLY_NO_AUTHORIZED_RUNTIME"


class InventoryError(RuntimeError):
    """Raised when source or installed task inventory is not exact."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _read_regular(path: Path, label: str) -> bytes:
    _require(path.exists() and not path.is_symlink() and path.is_file(), f"{label} is missing or unsafe: {path}")
    return path.read_bytes()


def _safe_member(name: str, label: str) -> None:
    _require(name and "\\" not in name and "\x00" not in name, f"unsafe {label}: {name!r}")
    path = PurePosixPath(name)
    _require(not path.is_absolute(), f"absolute {label}: {name}")
    _require(all(part not in {"", ".", ".."} for part in path.parts), f"escaping {label}: {name}")
    _require(path.as_posix() == name and SAFE_MEMBER.fullmatch(name) is not None, f"non-canonical {label}: {name}")


def _read_archive(root: Path) -> dict[str, bytes]:
    """Read bounded regular-file ZIP members after checking its pinned digest."""

    archive = root / ARCHIVE_RELATIVE
    _require(archive.exists() and not archive.is_symlink() and archive.is_file(), f"archive is missing or unsafe: {archive}")
    archive_bytes = archive.stat().st_size
    _require(archive_bytes == EXPECTED_ARCHIVE_BYTES, "archive byte count mismatch")
    _require(_sha256_file(archive) == EXPECTED_ARCHIVE_SHA256, "archive SHA-256 mismatch")

    records: dict[str, bytes] = {}
    total = 0
    try:
        handle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise InventoryError(f"invalid ZIP archive: {exc}") from exc
    with handle:
        infos = handle.infolist()
        _require(len(infos) == EXPECTED_ARCHIVE_ENTRIES, "archive entry count mismatch")
        for info in infos:
            _require(info.filename.startswith(SOURCE_ROOT), f"unexpected archive root: {info.filename}")
            _safe_member(info.filename, "archive path")
            relative = info.filename[len(SOURCE_ROOT) :]
            _safe_member(relative, "archive member")
            _require(relative not in records, f"duplicate archive member: {relative}")
            _require(not (info.flag_bits & 0x1), f"encrypted archive member: {relative}")
            _require(not info.is_dir(), f"directory archive member: {relative}")
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            _require(stat.S_IFMT(unix_mode) in {0, stat.S_IFREG}, f"non-regular archive member: {relative}")
            _require(0 <= info.file_size <= MAX_ARCHIVE_ENTRY_BYTES, f"oversized archive member: {relative}")
            if info.file_size:
                _require(info.compress_size > 0, f"invalid archive compression size: {relative}")
                _require(info.file_size / info.compress_size <= MAX_COMPRESSION_RATIO, f"archive compression ratio too high: {relative}")
            total += info.file_size
            _require(total <= MAX_ARCHIVE_TOTAL_BYTES, "archive exceeds total uncompressed limit")
            try:
                data = handle.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise InventoryError(f"cannot read archive member {relative}: {exc}") from exc
            _require(len(data) == info.file_size, f"archive member size mismatch: {relative}")
            records[relative] = data
    _require(total == EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES, "archive uncompressed byte count mismatch")
    return records


def _load_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"invalid JSON {label}: {exc}") from exc


def _load_installed_manifest(root: Path) -> tuple[dict[str, Any], str]:
    path = root / MANIFEST_RELATIVE
    data = _read_regular(path, "installed manifest")
    value = _load_json(data, MANIFEST_RELATIVE.as_posix())
    _require(isinstance(value, dict), "installed manifest must be an object")
    _require(value.get("schema_version") == "elmos.spring-golden-route.installed-manifest.v2", "installed manifest schema version mismatch")
    _require(value.get("package") == PACKAGE_NAME, "installed manifest package mismatch")
    _require(value.get("package_version") == PACKAGE_VERSION, "installed manifest package version mismatch")
    _require(value.get("source_archive_sha256") == f"sha256:{EXPECTED_ARCHIVE_SHA256}", "installed manifest archive digest mismatch")
    _require(value.get("source_archive_bytes") == EXPECTED_ARCHIVE_BYTES, "installed manifest archive byte count mismatch")
    _require(value.get("source_archive_entries") == EXPECTED_ARCHIVE_ENTRIES, "installed manifest archive entry count mismatch")
    _require(value.get("source_archive_uncompressed_bytes") == EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES, "installed manifest archive size mismatch")
    _require(value.get("skill_count") == EXPECTED_SKILLS, "installed manifest Skill count mismatch")
    _require(value.get("contract_count") == EXPECTED_SKILLS, "installed manifest contract count mismatch")
    _require(value.get("implementation_state") == "SPECIFICATION_IMPORTED", "installed manifest implementation state must remain SPECIFICATION_IMPORTED")
    _require(value.get("runtime_evidence_status") == NOT_RUN, "installed manifest runtime evidence must remain NOT_RUN")
    _require(value.get("customer_evidence_status") == NOT_RUN, "installed manifest customer evidence must remain NOT_RUN")
    _require(value.get("external_evidence_status") == NOT_RUN, "installed manifest external evidence must remain NOT_RUN")
    _require(value.get("certification") == NOT_CERTIFIED, "installed manifest certification must remain NOT_CERTIFIED")
    skills = value.get("skills")
    _require(isinstance(skills, list) and len(skills) == EXPECTED_SKILLS, "installed manifest Skill inventory mismatch")
    ids: set[str] = set()
    names: set[str] = set()
    for record in skills:
        _require(isinstance(record, dict), "installed manifest Skill record must be an object")
        source_id = record.get("source_id")
        source_name = record.get("source_name")
        _require(isinstance(source_id, str) and source_id and source_id not in ids, f"invalid or duplicate installed source ID: {source_id!r}")
        _require(isinstance(source_name, str) and source_name and source_name not in names, f"invalid or duplicate installed Skill name: {source_name!r}")
        ids.add(source_id)
        names.add(source_name)
        _require(record.get("implementation_state") == "SPECIFICATION_IMPORTED", f"installed Skill implementation state changed: {source_name}")
        _require(record.get("runtime_evidence_status") == NOT_RUN, f"installed Skill runtime evidence changed: {source_name}")
        _require(record.get("customer_evidence_status") == NOT_RUN, f"installed Skill customer evidence changed: {source_name}")
        _require(record.get("external_evidence_status") == NOT_RUN, f"installed Skill external evidence changed: {source_name}")
        _require(record.get("certification") == NOT_CERTIFIED, f"installed Skill certification changed: {source_name}")
        _require(record.get("side_effects_authorized") is False, f"installed Skill side-effect authorization changed: {source_name}")
    return value, _sha256_bytes(data)


def _source_manifest(records: Mapping[str, bytes]) -> dict[str, Any]:
    _require(SOURCE_PACKAGE_MANIFEST in records, "source package manifest is missing")
    value = _load_json(records[SOURCE_PACKAGE_MANIFEST], SOURCE_PACKAGE_MANIFEST)
    _require(isinstance(value, dict), "source package manifest must be an object")
    _require(value.get("package") == PACKAGE_NAME, "source package identity mismatch")
    _require(value.get("version") == PACKAGE_VERSION, "source package version mismatch")
    _require(value.get("skill_count") == EXPECTED_SKILLS, "source package Skill count mismatch")
    _require(value.get("batch_count") == 22, "source package batch count mismatch")
    skills = value.get("skills")
    _require(isinstance(skills, list) and len(skills) == EXPECTED_SKILLS, "source package Skill inventory mismatch")
    ids: set[str] = set()
    names: set[str] = set()
    origins = Counter()
    for record in skills:
        _require(isinstance(record, dict), "source package Skill record must be an object")
        source_id = record.get("id")
        name = record.get("name")
        path = record.get("path")
        _require(isinstance(source_id, str) and source_id and source_id not in ids, f"invalid or duplicate source Skill ID: {source_id!r}")
        _require(isinstance(name, str) and name and name not in names, f"invalid or duplicate source Skill name: {name!r}")
        _require(isinstance(path, str) and path == f"skills/{name}/SKILL.md", f"source Skill path mismatch: {name}")
        _safe_member(path, "source Skill path")
        ids.add(source_id)
        names.add(name)
        origins[record.get("origin")] += 1
    _require(origins == {"foundation": EXPECTED_FOUNDATION_SKILLS, "commercial-extension": EXPECTED_COMMERCIAL_SKILLS}, "source Skill origin inventory mismatch")
    return value


def _frontmatter_name(text: str, expected_name: str) -> None:
    """Check the small identity part needed before parsing source tasks."""

    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    _require(match is not None, f"source Skill frontmatter is missing: {expected_name}")
    frontmatter = match.group(1)
    _require(re.search(rf"^name:\s*{re.escape(expected_name)}\s*$", frontmatter, re.MULTILINE) is not None, f"source Skill frontmatter name mismatch: {expected_name}")


def _task_records(source: Mapping[str, Any], archive: Mapping[str, bytes], installed: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    skill_summaries: list[dict[str, Any]] = []
    installed_skills = installed.get("skills")
    assert isinstance(installed_skills, list)
    installed_by_id = {record.get("source_id"): record for record in installed_skills if isinstance(record, dict)}
    seen_ids: set[str] = set()
    global_ordinal = 0

    for skill in source["skills"]:
        source_id = skill["id"]
        name = skill["name"]
        source_path = skill["path"]
        contract_path = f"{SOURCE_CONTRACT_PREFIX}{name}.json"
        _require(source_path in archive, f"source Skill member is missing: {source_path}")
        _require(contract_path in archive, f"source contract member is missing: {contract_path}")
        skill_bytes = archive[source_path]
        contract_bytes = archive[contract_path]
        skill_sha = _sha256_bytes(skill_bytes)
        contract_sha = _sha256_bytes(contract_bytes)
        installed_record = installed_by_id.get(source_id)
        _require(installed_record is not None, f"installed manifest is missing source Skill: {source_id}")
        _require(installed_record.get("source_name") == name, f"installed source Skill name mismatch: {source_id}")
        _require(installed_record.get("source_batch") == skill.get("batch"), f"installed source Skill batch mismatch: {source_id}")
        _require(installed_record.get("source_origin") == skill.get("origin"), f"installed source Skill origin mismatch: {source_id}")
        _require(installed_record.get("source_path") == source_path, f"installed source Skill path mismatch: {source_id}")
        _require(installed_record.get("source_sha256") == f"sha256:{skill_sha}", f"installed source Skill digest mismatch: {source_id}")
        _require(installed_record.get("source_contract_path") == contract_path, f"installed source contract path mismatch: {source_id}")
        _require(installed_record.get("source_contract_sha256") == f"sha256:{contract_sha}", f"installed source contract digest mismatch: {source_id}")

        try:
            text = skill_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InventoryError(f"source Skill is not UTF-8: {source_path}") from exc
        _frontmatter_name(text, name)
        current_section = "(preamble)"
        current_level = 0
        skill_tasks: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            heading = MARKDOWN_HEADING.match(line)
            if heading:
                current_section = heading.group("heading")
                current_level = len(heading.group("marks"))
            match = SOURCE_TASK_CHECKBOX.match(line)
            if match is None:
                continue
            marker = match.group("marker")
            _require(marker == " ", f"source checklist is already checked or malformed: {source_path}:{line_number}")
            skill_ordinal = len(skill_tasks) + 1
            task_id = f"{source_id}-TASK-{skill_ordinal:03d}"
            _require(TASK_ID.fullmatch(task_id) is not None, f"generated source task ID is invalid: {task_id}")
            _require(task_id not in seen_ids, f"generated source task ID collision: {task_id}")
            seen_ids.add(task_id)
            global_ordinal += 1
            source_line_digest = _sha256_bytes(line.encode("utf-8"))
            task = {
                "global_ordinal": global_ordinal,
                "skill_task_ordinal": skill_ordinal,
                "task_id": task_id,
                "source_skill_id": source_id,
                "source_skill_name": name,
                "source_batch": skill["batch"],
                "source_origin": skill["origin"],
                "source_path": source_path,
                "source_line": line_number,
                "source_section": current_section,
                "source_section_level": current_level,
                "source_checkbox": "unchecked",
                "source_text": line,
                "task_text": match.group("text").strip(),
                "source_skill_sha256": f"sha256:{skill_sha}",
                "source_contract_path": contract_path,
                "source_contract_sha256": f"sha256:{contract_sha}",
                "source_task_line_sha256": f"sha256:{source_line_digest}",
                "task_status": TASK_STATUS,
                "execution_status": EXECUTION_STATUS,
                "block_reason": BLOCK_REASON,
                "runtime_evidence_status": NOT_RUN,
                "customer_evidence_status": NOT_RUN,
                "external_evidence_status": NOT_RUN,
                "certification": NOT_CERTIFIED,
                "side_effects_authorized": False,
            }
            skill_tasks.append(task)
            tasks.append(task)
        _require(skill_tasks, f"source Skill has no unchecked tasks: {source_id}")
        skill_summaries.append(
            {
                "source_skill_id": source_id,
                "source_skill_name": name,
                "source_batch": skill["batch"],
                "source_origin": skill["origin"],
                "source_path": source_path,
                "source_skill_sha256": f"sha256:{skill_sha}",
                "source_contract_path": contract_path,
                "source_contract_sha256": f"sha256:{contract_sha}",
                "task_count": len(skill_tasks),
                "task_ids": [task["task_id"] for task in skill_tasks],
                "task_status_counts": dict(Counter(task["task_status"] for task in skill_tasks)),
                "execution_status_counts": dict(Counter(task["execution_status"] for task in skill_tasks)),
            }
        )
    _require(len(tasks) == EXPECTED_TASKS, f"source task count mismatch: {len(tasks)}")
    return tasks, skill_summaries


def build_expected(root: Path = ROOT) -> dict[str, Any]:
    """Build the deterministic ledger from the pinned archive and install manifest."""

    root = root.expanduser().absolute()
    _require(root.exists() and root.is_dir() and not root.is_symlink(), f"repository root is missing or unsafe: {root}")
    archive = _read_archive(root)
    source = _source_manifest(archive)
    installed, installed_digest = _load_installed_manifest(root)
    tasks, skill_summaries = _task_records(source, archive, installed)
    _require([record["source_skill_id"] for record in skill_summaries] == [record["source_id"] for record in installed["skills"]], "source and installed Skill order differs")
    _require(dict(Counter(record["source_origin"] for record in skill_summaries)) == {"foundation": EXPECTED_FOUNDATION_SKILLS, "commercial-extension": EXPECTED_COMMERCIAL_SKILLS}, "task source-origin coverage mismatch")

    section_counts = Counter(task["source_section"] for task in tasks)
    batch_counts = Counter(task["source_batch"] for task in tasks)
    status_counts = Counter(task["task_status"] for task in tasks)
    execution_counts = Counter(task["execution_status"] for task in tasks)
    ledger = {
        "schema_version": "elmos.spring-golden-route.source-task-coverage-ledger.v1",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "installed_namespace": installed.get("installed_namespace"),
        "canonical_source": ARCHIVE_RELATIVE.as_posix(),
        "source_archive_sha256": f"sha256:{EXPECTED_ARCHIVE_SHA256}",
        "source_archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "source_archive_entries": EXPECTED_ARCHIVE_ENTRIES,
        "source_archive_uncompressed_bytes": EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES,
        "installed_manifest_path": MANIFEST_RELATIVE.as_posix(),
        "installed_manifest_sha256": f"sha256:{installed_digest}",
        "skill_count": EXPECTED_SKILLS,
        "foundation_skill_count": EXPECTED_FOUNDATION_SKILLS,
        "commercial_skill_count": EXPECTED_COMMERCIAL_SKILLS,
        "task_count": EXPECTED_TASKS,
        "task_id_scheme": "<source_skill_id>-TASK-<three-digit-ordinal-per-source-skill>",
        "task_id_authority": "REPOSITORY_DERIVED_STABLE_SOURCE_ORDER_SOURCE_PACKAGE_HAS_NO_TASK_IDS",
        "source_checkbox_policy": "Every source checklist item must remain unchecked; checked items fail closed.",
        "coverage_state": "SOURCE_INVENTORIED",
        "implementation_state": "SPECIFICATION_IMPORTED",
        "task_status": TASK_STATUS,
        "execution_status": EXECUTION_STATUS,
        "block_reason": BLOCK_REASON,
        "runtime_evidence_status": NOT_RUN,
        "customer_evidence_status": NOT_RUN,
        "external_evidence_status": NOT_RUN,
        "certification": NOT_CERTIFIED,
        "side_effects_authorized": False,
        "archive_code_execution": "DENIED",
        "source_task_count_by_section": dict(sorted(section_counts.items())),
        "source_task_count_by_batch": dict(sorted(batch_counts.items())),
        "task_status_counts": dict(sorted(status_counts.items())),
        "execution_status_counts": dict(sorted(execution_counts.items())),
        "skills": skill_summaries,
        "tasks": tasks,
        "evidence_boundary": {
            "inventory_evidence": "LOCAL_STATIC_SOURCE_AND_INSTALLED_MANIFEST_MATCH",
            "source_tasks_executed": False,
            "real_spring_jvm_build_startup": NOT_RUN,
            "migration_equivalence_security_customer_independent_evidence": NOT_RUN,
            "production_certification": NOT_CERTIFIED,
        },
    }
    return ledger


def _ledger_path(root: Path) -> Path:
    return root / LEDGER_RELATIVE


def check(root: Path = ROOT) -> dict[str, Any]:
    expected = build_expected(root)
    path = _ledger_path(root)
    actual_bytes = _read_regular(path, "source-task coverage ledger")
    _require(actual_bytes == _json_bytes(expected), f"source-task coverage ledger drifted: {LEDGER_RELATIVE}")
    return {
        "decision": "SOURCE_TASK_INVENTORY_VERIFIED",
        "skills": expected["skill_count"],
        "tasks": expected["task_count"],
        "task_status": expected["task_status"],
        "execution_status": expected["execution_status"],
        "runtime_evidence_status": expected["runtime_evidence_status"],
        "certification": expected["certification"],
        "ledger_sha256": f"sha256:{_sha256_bytes(actual_bytes)}",
    }


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        _require(path.is_file() and not path.is_symlink(), f"unsafe ledger destination: {path}")
        _require(path.read_bytes() == payload, f"refusing to overwrite a different ledger: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise InventoryError(f"ledger destination appeared during write: {path}") from exc
        finally:
            if temporary.exists():
                temporary.unlink()
    except OSError as exc:
        raise InventoryError(f"cannot publish ledger: {path}: {exc}") from exc


def write(root: Path = ROOT) -> dict[str, Any]:
    expected = build_expected(root)
    payload = _json_bytes(expected)
    _write_atomic(_ledger_path(root), payload)
    return check(root)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate the pinned archive, installed manifest, and checked-in ledger")
    mode.add_argument("--write", action="store_true", help="create the ledger when the destination is absent")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = check(args.root) if args.check else write(args.root)
    except InventoryError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
