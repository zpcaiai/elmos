"""Static integration validator; never executes content from the supplied ZIP."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
PACKAGE = REPOSITORY / "skills/subskills/elmos-openhands-absorption-p0-p1-v1.0.0 (1).zip"
MANIFEST = ROOT / "src/elmos_openhands/implementation_manifest.json"
EXPECTED_ZIP_SHA256 = "72d151a4d76d3ec4e1e7b7d7401e4c1e390a9ed1a49da19ce4061e45725c3c99"
EXPECTED_SKILLS = {
    "P0-01": ("Stateless Agent Runtime", "P0-01-stateless-agent-runtime"),
    "P0-02": ("Immutable Execution Event Ledger", "P0-02-immutable-event-ledger"),
    "P0-03": ("Action-Observation Tool Protocol", "P0-03-action-observation-protocol"),
    "P0-04": ("Durable Persistence, Checkpoint & Replay", "P0-04-durable-persistence-replay"),
    "P0-05": ("Workspace & Sandbox Abstraction", "P0-05-workspace-abstraction"),
    "P0-06": ("Agent Server & Distributed Runtime Plane", "P0-06-agent-server-runtime-plane"),
    "P0-07": ("Evidence-aware Context / Condenser Engine", "P0-07-evidence-aware-context-engine"),
    "P0-08": ("Action Firewall & Security Analyzer", "P0-08-action-firewall-security"),
    "P0-09": ("Hooks & Verification Gates", "P0-09-hooks-verification-gates"),
    "P1-01": ("Progressive Skill Disclosure & Skill Router", "P1-01-progressive-skill-disclosure"),
    "P1-02": ("Commercial Capability Package / Plugin System", "P1-02-capability-package"),
    "P1-03": ("Durable Multi-Agent Delegation DAG", "P1-03-durable-agent-dag"),
    "P1-04": ("Agent Provider Adapter / ACP Layer", "P1-04-agent-provider-adapters"),
    "P1-05": ("Browser / UI Evidence & Replay", "P1-05-browser-evidence-replay"),
}
EXPECTED_COMPONENTS = {
    "__init__", "__main__", "api", "artifacts", "browser", "browser_drivers", "cli", "context",
    "dag", "errors", "evidence", "firewall", "gates", "governance", "ledger", "models",
    "observability", "orchestration", "packages", "persistence", "plane", "policy", "postgres",
    "projections", "protocol", "provider_sessions", "providers", "qualification", "replay", "runtime",
    "sandbox", "service", "skill_routing", "skills", "supervisor", "tools", "workspace", "workspace_api",
}
EXPECTED_EXTERNAL_GATES = {
    "real_temporal_postgresql", "production_sandbox", "external_providers", "browser_devices",
    "golden_repositories", "load_chaos", "independent_security_review",
}


def main() -> int:
    errors: list[str] = []
    source_digest = _source_digest(errors)
    archive_slugs = _validate_archive(errors)
    manifest = _load_manifest(errors)
    _validate_components(errors)
    _validate_schemas_and_migrations(errors)
    _validate_manifest(manifest, archive_slugs, errors)
    result = {
        "status": "PASS" if not errors else "FAIL",
        "source_zip_sha256": source_digest,
        "source_zip_member_count": 50,
        "implemented_skills": len(EXPECTED_SKILLS),
        "components": len(EXPECTED_COMPONENTS),
        "external_qualification": {} if not manifest else manifest.get("external_qualification", {}),
        "certification": None if not manifest else manifest.get("certification"),
        "release_status": None if not manifest else manifest.get("release_status"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


def _source_digest(errors: list[str]) -> str:
    source_digest = hashlib.sha256(PACKAGE.read_bytes()).hexdigest() if PACKAGE.is_file() else ""
    if source_digest != EXPECTED_ZIP_SHA256:
        errors.append("source ZIP digest is absent or changed")
    return source_digest


def _validate_archive(errors: list[str]) -> set[str]:
    if not PACKAGE.is_file():
        return set()
    slugs: set[str] = set()
    try:
        with zipfile.ZipFile(PACKAGE) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != 50 or len(names) != len(set(names)):
                errors.append(f"source ZIP member set changed or contains duplicates: {len(names)}")
            total = 0
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                total += info.file_size
                if path.is_absolute() or ".." in path.parts or "\x00" in info.filename:
                    errors.append(f"source ZIP contains an unsafe path: {info.filename}")
                if stat.S_ISLNK(mode):
                    errors.append(f"source ZIP contains a symlink: {info.filename}")
                if info.file_size > 16 * 1024 * 1024 or total > 128 * 1024 * 1024:
                    errors.append("source ZIP exceeds the bounded static-inspection size")
                parts = path.parts
                if len(parts) == 4 and parts[1] == "skills" and parts[3] == "SKILL.md":
                    slugs.add(parts[2])
    except (OSError, zipfile.BadZipFile) as error:
        errors.append(f"source ZIP cannot be inspected safely: {error}")
    expected_slugs = {value[1] for value in EXPECTED_SKILLS.values()}
    if slugs != expected_slugs:
        errors.append("source ZIP exact Skill identities changed")
    return slugs


def _load_manifest(errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"implementation manifest is invalid: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append("implementation manifest root must be an object")
        return {}
    return value


def _validate_components(errors: list[str]) -> None:
    source = ROOT / "src/elmos_openhands"
    actual = {path.stem for path in source.glob("*.py")}
    for component in sorted(EXPECTED_COMPONENTS - actual):
        errors.append(f"component is missing: {component}")


def _validate_schemas_and_migrations(errors: list[str]) -> None:
    for schema in ("execution-event.schema.json", "action-observation.schema.json"):
        try:
            value = json.loads((ROOT / "src/elmos_openhands/schemas" / schema).read_text(encoding="utf-8"))
            if not isinstance(value, dict) or "$schema" not in value:
                errors.append(f"schema is not a versioned JSON Schema object: {schema}")
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"invalid schema {schema}: {error}")
    required_migrations = (
        "migrations/postgres/0001_openhands_absorption.sql",
        "migrations/postgres/0002_openhands_production_runtime.sql",
        "migrations/postgres/rollback/0001_openhands_absorption.down.sql",
        "migrations/postgres/rollback/0002_openhands_production_runtime.down.sql",
    )
    for relative in required_migrations:
        path = ROOT / relative
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"migration/rollback is missing: {relative}")
    grpc_contract = ROOT / "contracts/runtime-gateway-v1.proto"
    if not grpc_contract.is_file() or "package elmos.openhands.v1;" not in grpc_contract.read_text(encoding="utf-8"):
        errors.append("versioned gRPC runtime contract is missing")


def _validate_manifest(manifest: dict[str, Any], archive_slugs: set[str], errors: list[str]) -> None:
    if not manifest:
        return
    source = manifest.get("source_package")
    if not isinstance(source, dict) or source.get("sha256") != EXPECTED_ZIP_SHA256 or source.get("member_count") != 50 or source.get("trust_boundary") != "UNTRUSTED_SPECIFICATION_NEVER_EXECUTED":
        errors.append("implementation manifest source provenance is invalid")
    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict) or implementation.get("code_status") != "IMPLEMENTED":
        errors.append("implementation manifest does not mark the code implementation complete")
    rows = manifest.get("skills")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_SKILLS):
        errors.append("implementation manifest must contain exactly 14 Skills")
        return
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append("implementation manifest contains a non-object Skill")
            continue
        skill_id = row.get("id")
        expected = EXPECTED_SKILLS.get(skill_id)
        if expected is None or skill_id in seen:
            errors.append(f"implementation manifest has an unknown/duplicate Skill: {skill_id}")
            continue
        seen.add(skill_id)
        if (row.get("name"), row.get("source_slug")) != expected or row.get("source_slug") not in archive_slugs:
            errors.append(f"Skill identity/provenance mismatch: {skill_id}")
        if row.get("code_status") != "IMPLEMENTED":
            errors.append(f"Skill code is not marked IMPLEMENTED: {skill_id}")
        modules, tests = row.get("modules"), row.get("tests")
        if not isinstance(modules, list) or not modules or not isinstance(tests, list) or not tests:
            errors.append(f"Skill lacks module/test bindings: {skill_id}")
            continue
        for module in modules:
            if not isinstance(module, str) or not (ROOT / "src/elmos_openhands" / module).is_file():
                errors.append(f"Skill module binding is missing: {skill_id}:{module}")
        for test in tests:
            if not isinstance(test, str) or not (ROOT / "tests" / test).is_file():
                errors.append(f"Skill test binding is missing: {skill_id}:{test}")
    if seen != set(EXPECTED_SKILLS):
        errors.append("implementation manifest exact Skill set is incomplete")
    external = manifest.get("external_qualification")
    if not isinstance(external, dict) or set(external) != EXPECTED_EXTERNAL_GATES or any(value != "NOT_RUN" for value in external.values()):
        errors.append("external qualification must contain the exact fail-closed NOT_RUN gate set")
    if manifest.get("certification") != "NOT_CERTIFIED" or manifest.get("release_status") != "NOT_GA":
        errors.append("certification or release status is not fail-closed")


if __name__ == "__main__":
    raise SystemExit(main())
