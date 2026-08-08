from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .intake import approve_request, create_draft
from .models import (
    SUPPORTED_AUTH_MODES,
    SUPPORTED_LANGUAGES,
    SUPPORTED_PERSISTENCE,
    SUPPORTED_PROJECT_KINDS,
    RequestValidationError,
)
from .verification import runtime_commands, verify_workspace
from .workspace import COMPATIBLE_MANIFEST_VERSIONS, WorkspaceConflictError, generate_workspace


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("REQUEST_FILE_MUST_BE_REGULAR")
    if path.stat().st_size > 1_048_576:
        raise ValueError("REQUEST_FILE_TOO_LARGE")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return loaded


def _write_json(path: Path, value: dict[str, Any]) -> None:
    output = path.expanduser()
    if output.exists() and (output.is_symlink() or not output.is_file()):
        raise ValueError("OUTPUT_MUST_BE_REGULAR_FILE")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.elmos-",
        suffix=".tmp",
        dir=output.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def _draft_from_intent(intent: dict[str, Any]) -> dict[str, Any]:
    languages = intent.get("languages", intent.get("targets", SUPPORTED_DEFAULT_TARGETS))
    if not isinstance(languages, list) or not all(isinstance(item, str) for item in languages):
        raise ValueError("INTENT_LANGUAGES_MUST_BE_ARRAY")
    business_rules = intent.get("business_rules", [])
    if not isinstance(business_rules, list):
        raise ValueError("INTENT_BUSINESS_RULES_MUST_BE_ARRAY")
    return create_draft(
        name=str(intent.get("name", "")),
        description=str(intent.get("description", "")),
        entity=str(intent["entity"]) if intent.get("entity") else None,
        entities=intent.get("entities") if isinstance(intent.get("entities"), list) else None,
        relations=intent.get("relations", []) if isinstance(intent.get("relations", []), list) else [],
        business_rules=business_rules,
        permissions=intent.get("permissions", []) if isinstance(intent.get("permissions", []), list) else [],
        namespace=str(intent["namespace"]) if intent.get("namespace") else None,
        languages=languages,
        project_kind=str(intent.get("project_kind", "api")),
        persistence=str(intent.get("persistence", "in-memory")),
        auth_mode=str(intent.get("auth_mode", "none")),
        requirement_sources=(
            intent.get("requirement_sources", [])
            if isinstance(intent.get("requirement_sources", []), list)
            else []
        ),
        source_bundle_sha256=(
            str(intent["source_bundle_sha256"])
            if intent.get("source_bundle_sha256")
            else None
        ),
    )


SUPPORTED_DEFAULT_TARGETS = list(SUPPORTED_LANGUAGES)


def _archive_entry(archive: zipfile.ZipFile, source: Path, arcname: str) -> int:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"ARCHIVE_SOURCE_UNSAFE:{arcname}")
    size = source.stat().st_size
    if size > 64 * 1024 * 1024:
        raise ValueError(f"ARCHIVE_SOURCE_TOO_LARGE:{arcname}")
    info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = 0o755 if source.stat().st_mode & 0o111 else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return size


def _archive_source(root: Path, relative: PurePosixPath) -> Path:
    source = root.joinpath(*relative.parts)
    if source.is_symlink():
        raise ValueError(f"GENERATION_ARTIFACT_UNSAFE:{relative.as_posix()}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"GENERATION_ARTIFACT_MISSING:{relative.as_posix()}") from error
    if resolved != source or not source.is_file():
        raise ValueError(f"GENERATION_ARTIFACT_UNSAFE:{relative.as_posix()}")
    return source


def _archive_workspace(workspace: Path, destination: Path, *, evidence: Path | None = None) -> dict[str, Any]:
    expanded_workspace = workspace.expanduser()
    if expanded_workspace.is_symlink():
        raise ValueError("ARCHIVE_WORKSPACE_SYMLINK_FORBIDDEN")
    root = expanded_workspace.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("ARCHIVE_WORKSPACE_MUST_BE_DIRECTORY")
    manifest_path = _archive_source(root, PurePosixPath(".elmos/generation-manifest.json"))
    manifest = _read_json(manifest_path)
    if (
        manifest.get("engine") != "elmos.project-synthesis"
        or manifest.get("engine_version") not in COMPATIBLE_MANIFEST_VERSIONS
        or manifest.get("status") != "GENERATED"
    ):
        raise ValueError("GENERATION_MANIFEST_IDENTITY_INVALID")
    blueprint_path = _archive_source(root, PurePosixPath("requirements/project-blueprint.json"))
    blueprint = _read_json(blueprint_path)
    project = blueprint.get("project")
    archive_root = project.get("name") if isinstance(project, dict) else None
    if not isinstance(archive_root, str) or re.fullmatch(r"[a-z][a-z0-9-]{1,62}[a-z0-9]", archive_root) is None:
        raise ValueError("ARCHIVE_PROJECT_IDENTITY_INVALID")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries or len(entries) > 10_000:
        raise ValueError("GENERATION_MANIFEST_FILES_INVALID")
    expanded_destination = destination.expanduser()
    if expanded_destination.is_symlink():
        raise ValueError("ARCHIVE_OUTPUT_MUST_BE_REGULAR_FILE")
    destination = expanded_destination.resolve(strict=False)
    if destination.exists() and (destination.is_symlink() or not destination.is_file()):
        raise ValueError("ARCHIVE_OUTPUT_MUST_BE_REGULAR_FILE")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.elmos-",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    archived_paths: set[str] = set()
    total_bytes = 0
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for entry in entries:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("path"), str)
                    or not isinstance(entry.get("sha256"), str)
                    or len(entry["sha256"]) != 64
                    or any(character not in "0123456789abcdef" for character in entry["sha256"])
                ):
                    raise ValueError("GENERATION_MANIFEST_ENTRY_INVALID")
                relative = PurePosixPath(entry["path"])
                relative_text = relative.as_posix()
                if (
                    relative.is_absolute()
                    or not relative.parts
                    or ".." in relative.parts
                    or relative_text in archived_paths
                ):
                    raise ValueError("GENERATION_MANIFEST_PATH_UNSAFE")
                source = _archive_source(root, relative)
                if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                    raise ValueError(f"GENERATION_ARTIFACT_INTEGRITY_MISMATCH:{relative_text}")
                total_bytes += _archive_entry(archive, source, f"{archive_root}/{relative_text}")
                archived_paths.add(relative_text)
            required_paths = {
                "Makefile",
                "README.md",
                "requirements/approved-request.json",
                "requirements/project-blueprint.json",
                "scripts/projectctl.py",
            }
            if not required_paths <= archived_paths:
                raise ValueError("GENERATION_MANIFEST_REQUIRED_FILES_MISSING")
            derived_lockfiles = [
                root / "python" / "uv.lock",
                root / "typescript" / "pnpm-lock.yaml",
                root / "kotlin" / "gradle.lockfile",
                root / "rust" / "Cargo.lock",
                *sorted((root / "dotnet").glob("**/packages.lock.json")),
            ]
            for source in derived_lockfiles:
                if not source.is_file():
                    continue
                if source.resolve(strict=True) != source or source.is_symlink():
                    raise ValueError(f"ARCHIVE_DERIVED_SOURCE_UNSAFE:{source.relative_to(root)}")
                derived_relative = source.relative_to(root)
                if derived_relative.as_posix() in archived_paths:
                    continue
                total_bytes += _archive_entry(
                    archive, source, f"{archive_root}/{derived_relative.as_posix()}"
                )
                archived_paths.add(derived_relative.as_posix())
            total_bytes += _archive_entry(
                archive,
                manifest_path,
                f"{archive_root}/.elmos/generation-manifest.json",
            )
            if evidence is not None:
                total_bytes += _archive_entry(
                    archive,
                    evidence,
                    f"{archive_root}/.elmos/verification.json",
                )
            if total_bytes > 256 * 1024 * 1024:
                raise ValueError("ARCHIVE_UNCOMPRESSED_SIZE_LIMIT_EXCEEDED")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "ARCHIVED",
        "path": str(destination),
        "byte_count": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "artifact_count": len(archived_paths) + 1 + int(evidence is not None and evidence.is_file()),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-project-synthesis")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft = subparsers.add_parser("draft", help="Organize an initial natural-language request into a reviewable draft")
    draft.add_argument("--name", required=True)
    draft.add_argument("--description", required=True)
    draft.add_argument("--entity")
    draft.add_argument("--namespace")
    draft.add_argument("--language", action="append", choices=list(SUPPORTED_LANGUAGES))
    draft.add_argument("--project-kind", choices=list(SUPPORTED_PROJECT_KINDS), default="api")
    draft.add_argument("--persistence", choices=list(SUPPORTED_PERSISTENCE), default="in-memory")
    draft.add_argument("--auth-mode", choices=list(SUPPORTED_AUTH_MODES), default="none")
    draft.add_argument("--output", type=Path, required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze a typed natural-language intent JSON")
    analyze.add_argument("--intent", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)

    approve = subparsers.add_parser("approve", help="Hash-bind a reviewed requirement baseline")
    approve.add_argument("--request", type=Path, required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--output", type=Path, required=True)

    generate = subparsers.add_parser("generate", help="Generate projects from an approved requirement baseline")
    generate.add_argument("--request", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="Run real target builds and tests")
    verify.add_argument("--workspace", type=Path, required=True)
    verify.add_argument("--evidence", type=Path)

    pipeline = subparsers.add_parser(
        "pipeline",
        help="Approve a reviewed draft, generate, verify, and create a source artifact",
    )
    pipeline.add_argument("--request", type=Path, required=True)
    pipeline.add_argument("--actor", required=True)
    pipeline.add_argument("--output", type=Path, required=True)
    pipeline.add_argument("--evidence", type=Path, required=True)
    pipeline.add_argument("--archive", type=Path, required=True)

    runtime_plan = subparsers.add_parser("runtime-plan", help="Emit allowlisted runtime commands")
    runtime_plan.add_argument("--workspace", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "draft":
            result = create_draft(
                name=args.name,
                description=args.description,
                entity=args.entity,
                namespace=args.namespace,
                languages=args.language or SUPPORTED_LANGUAGES,
                project_kind=args.project_kind,
                persistence=args.persistence,
                auth_mode=args.auth_mode,
            )
            _write_json(args.output, result)
        elif args.command == "analyze":
            result = _draft_from_intent(_read_json(args.intent))
            _write_json(args.output, result)
        elif args.command == "approve":
            result = approve_request(_read_json(args.request), actor=args.actor)
            _write_json(args.output, result)
        elif args.command == "generate":
            result = generate_workspace(_read_json(args.request), args.output)
        elif args.command == "verify":
            result = verify_workspace(args.workspace)
            if args.evidence:
                _write_json(args.evidence, result)
        elif args.command == "pipeline":
            approved = approve_request(_read_json(args.request), actor=args.actor)
            manifest = generate_workspace(approved, args.output)
            evidence = verify_workspace(args.output)
            _write_json(args.evidence, evidence)
            archive = _archive_workspace(args.output, args.archive, evidence=args.evidence)
            runnable_languages = {
                item.get("language")
                for item in evidence["results"]
                if item.get("kind") == "startup-probe" and item.get("status") == "PASSED"
            }
            result = {
                "status": evidence["status"],
                "manifest": manifest,
                "verification": evidence,
                "archive": archive,
                "runtime_plan": [
                    plan for plan in runtime_commands(args.output) if plan["language"] in runnable_languages
                ],
                "production_delivery_status": "NOT_RUN",
                "external_certification_status": "NOT_RUN",
            }
        else:
            result = {
                "status": "READY",
                "workspace": str(args.workspace.resolve(strict=True)),
                "runtime_plan": runtime_commands(args.workspace),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("status") != "FAILED" else 1
    except (
        OSError,
        ValueError,
        RequestValidationError,
        WorkspaceConflictError,
        RuntimeError,
        json.JSONDecodeError,
    ) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
