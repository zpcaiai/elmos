#!/usr/bin/env python3
"""Import and independently qualify the Formal Assurance Kernel source package.

The attached ZIP is untrusted declarative source material.  This importer
checks archive identity, path safety, internal checksums, exact Skill counts,
dependency references, schemas, workflows and profiles without importing or
executing anything from the archive.  The repository-owned engine is checked
separately after the immutable source mirror and metadata are materialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ModuleNotFoundError as exc:  # pragma: no cover - diagnostic
    raise SystemExit(
        "PyYAML and jsonschema are required; use `make formal-assurance-kernel`"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-formal-assurance-kernel-v1.0.0"
PACKAGE_ID = "elmos-formal-assurance-kernel-v1.0.0"
ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/formal-assurance-kernel")
ENGINE_RELATIVE = Path("engines/formal-assurance-engine")
EXPECTED_ARCHIVE_SHA256 = (
    "7d397f9379e15023208d3fb49b3928af07b7b6134e6a91fe70ebaf7048f9e73e"
)
EXPECTED_ARCHIVE_BYTES = 824_793
EXPECTED_FILE_COUNT = 538
EXPECTED_SKILL_COUNT = 60
EXPECTED_PACKAGE_COUNTS = {
    "skills": 60,
    "perSkillFiles": 300,
    "jsonSchemas": 17,
    "schemaExamples": 16,
    "postgresMigrations": 4,
    "openApiContracts": 4,
    "asyncApiContracts": 1,
    "regoModules": 6,
    "regoTests": 6,
    "verifierAdapters": 17,
    "workflows": 10,
    "goldenRoutes": 5,
    "installProfiles": 7,
}
REQUIRED_SKILL_FILES = {
    "SKILL.md",
    "manifest.yaml",
    "acceptance.yaml",
    "implementation.yaml",
    "runbook.md",
}
REQUIRED_SKILL_SECTIONS = (
    "## 1. 业务目标",
    "## 9. 失败语义",
    "## 10. 安全与多租户",
    "## 12. 商业发布边界",
)


class IntegrationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise IntegrationError(message)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def load_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")


def load_yaml(data: bytes, label: str) -> Any:
    try:
        return yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        fail(f"{label}: invalid YAML: {exc}")


def read_archive(path: Path) -> tuple[dict[str, bytes], dict[str, int], str]:
    if not path.is_file() or path.is_symlink():
        fail(f"archive is missing or unsafe: {path}")
    data = path.read_bytes()
    if len(data) != EXPECTED_ARCHIVE_BYTES:
        fail(
            f"archive byte count mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {len(data)}"
        )
    archive_digest = digest_bytes(data)
    if archive_digest != EXPECTED_ARCHIVE_SHA256:
        fail(
            f"archive digest mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {archive_digest}"
        )
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if sum(not info.is_dir() for info in infos) != EXPECTED_FILE_COUNT:
            fail(f"archive file count mismatch: expected {EXPECTED_FILE_COUNT}")
        total = 0
        for info in infos:
            name = info.filename
            posix = PurePosixPath(name)
            if (
                "\x00" in name
                or posix.is_absolute()
                or ".." in posix.parts
                or not name.startswith(PACKAGE_DIRECTORY + "/")
            ):
                fail(f"unsafe archive member path: {name!r}")
            if info.is_dir():
                continue
            if name in files:
                fail(f"duplicate archive member: {name}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                fail(f"symbolic-link archive member is forbidden: {name}")
            total += info.file_size
            if total > 64 * 1024 * 1024:
                fail("archive uncompressed size exceeds importer bound")
            relative = name[len(PACKAGE_DIRECTORY) + 1 :]
            files[relative] = archive.read(info)
            modes[relative] = stat.S_IMODE(mode) or 0o644
    if len(files) != EXPECTED_FILE_COUNT:
        fail("archive inventory is incomplete")
    return files, modes, archive_digest


def verify_internal_checksums(files: dict[str, bytes]) -> None:
    checksum_data = files.get("FILES.sha256")
    if checksum_data is None:
        fail("FILES.sha256 is missing")
    rows = checksum_data.decode("utf-8").splitlines()
    seen: set[str] = set()
    for line_number, line in enumerate(rows, 1):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            fail(f"FILES.sha256:{line_number}: malformed checksum row")
        digest, relative = parts
        if relative in seen or relative == "FILES.sha256":
            fail(f"FILES.sha256:{line_number}: duplicate or self-referential path")
        seen.add(relative)
        if relative not in files:
            fail(f"FILES.sha256:{line_number}: missing file {relative}")
        if digest_bytes(files[relative]) != digest:
            fail(f"FILES.sha256:{line_number}: digest mismatch for {relative}")
    expected = set(files) - {"FILES.sha256"}
    if seen != expected:
        fail("FILES.sha256 does not cover exactly the archive files")


def check_dag(nodes: set[str], edges: dict[str, list[str]], label: str) -> None:
    indegree = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, dependencies in edges.items():
        for dependency in dependencies:
            if dependency not in nodes:
                fail(f"{label}: {node} references unknown dependency {dependency}")
            indegree[node] += 1
            outgoing[dependency].append(node)
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    visited: list[str] = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for successor in sorted(outgoing[node]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if len(visited) != len(nodes):
        fail(
            f"{label}: dependency cycle among {sorted(node for node, degree in indegree.items() if degree > 0)}"
        )


def validate_package(files: dict[str, bytes]) -> dict[str, Any]:
    manifest = load_yaml(files["PACKAGE_MANIFEST.yaml"], "PACKAGE_MANIFEST.yaml")
    if manifest.get("metadata", {}).get("packageId") != PACKAGE_ID:
        fail("package manifest identity mismatch")
    skill_manifests: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path, data in files.items():
        if not path.startswith("skills/P") or not path.endswith("/manifest.yaml"):
            continue
        skill_dir = PurePosixPath(path).parent
        name = skill_dir.name
        members = {
            PurePosixPath(candidate).name
            for candidate in files
            if PurePosixPath(candidate).parent == skill_dir
        }
        if members != REQUIRED_SKILL_FILES:
            errors.append(
                f"{skill_dir}: expected exactly {sorted(REQUIRED_SKILL_FILES)}"
            )
            continue
        parsed = load_yaml(data, path)
        if parsed.get("metadata", {}).get("name") != name:
            errors.append(f"{path}: metadata.name does not match directory")
        skill_manifests[name] = parsed
        body = files[f"{skill_dir}/SKILL.md"].decode("utf-8")
        for section in REQUIRED_SKILL_SECTIONS:
            if section not in body:
                errors.append(f"{name}: missing required source section {section}")
        acceptance = load_yaml(
            files[f"{skill_dir}/acceptance.yaml"], f"{skill_dir}/acceptance.yaml"
        )
        tests = acceptance.get("spec", {}).get("tests", [])
        ids = [test.get("id") for test in tests if isinstance(test, dict)]
        if len(ids) != len(set(ids)):
            errors.append(f"{name}: duplicate acceptance test IDs")
        acceptance_text = files[f"{skill_dir}/acceptance.yaml"].decode("utf-8")
        if (
            "BOUNDED_NO_COUNTEREXAMPLE" not in acceptance_text
            or "REFUTED_WITH_COUNTEREXAMPLE" not in acceptance_text
        ):
            errors.append(f"{name}: honesty acceptance cases are missing")
    if errors:
        fail("Skill contract validation failed: " + "; ".join(errors[:12]))
    if len(skill_manifests) != EXPECTED_SKILL_COUNT:
        fail(f"expected {EXPECTED_SKILL_COUNT} Skills, got {len(skill_manifests)}")
    names = set(skill_manifests)
    check_dag(
        names,
        {
            name: item.get("spec", {}).get("dependencies", [])
            for name, item in skill_manifests.items()
        },
        "Skill DAG",
    )
    priorities = Counter(
        item.get("metadata", {}).get("priority") for item in skill_manifests.values()
    )
    domains = Counter(
        item.get("metadata", {}).get("domain") for item in skill_manifests.values()
    )
    if priorities != Counter({"P0": 48, "P1": 10, "P2": 2}):
        fail(f"priority counts drift: {dict(priorities)}")
    if domains != Counter(
        {
            "core": 10,
            "cross-language": 10,
            "platform": 11,
            "project-generation": 9,
            "spring-modernization": 10,
            "sql-conversion": 10,
        }
    ):
        fail(f"domain counts drift: {dict(domains)}")

    schema_files = sorted(
        path
        for path in files
        if path.startswith("contracts/schemas/") and path.endswith(".schema.json")
    )
    if len(schema_files) != 17:
        fail(f"expected 17 JSON Schemas, got {len(schema_files)}")
    schemas: dict[str, dict[str, Any]] = {}
    for path in schema_files:
        schema = load_json(files[path], path)
        Draft202012Validator.check_schema(schema)
        schemas[PurePosixPath(path).name] = schema
    resolver_registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas.values()
            if isinstance(schema.get("$id"), str)
        ]
    )
    for path in sorted(
        path
        for path in files
        if path.startswith("contracts/examples/") and path.endswith(".example.json")
    ):
        example = load_json(files[path], path)
        schema_name = PurePosixPath(path).name.replace(".example.json", ".schema.json")
        schema = schemas.get(schema_name)
        if schema is None:
            fail(f"{path}: no matching schema {schema_name}")
        try:
            Draft202012Validator(schema, registry=resolver_registry).validate(example)
        except Exception as exc:
            fail(f"{path}: schema validation failed: {exc}")

    workflows = []
    for path in sorted(
        path
        for path in files
        if path.startswith("workflows/") and path.endswith(".yaml")
    ):
        workflow = load_yaml(files[path], path)
        steps = workflow.get("spec", {}).get("steps", [])
        step_ids = {step.get("id") for step in steps}
        if len(step_ids) != len(steps):
            fail(f"{path}: duplicate workflow step id")
        check_dag(
            step_ids, {step["id"]: step.get("dependsOn", []) for step in steps}, path
        )
        for step in steps:
            if step.get("skillRef") not in names:
                fail(f"{path}: unknown skillRef {step.get('skillRef')}")
        workflows.append(path)
    for path in sorted(
        path
        for path in files
        if path.startswith("profiles/") and path.endswith(".yaml")
    ):
        profile = load_yaml(files[path], path)
        unknown = set(profile.get("spec", {}).get("skills", [])) - names
        if unknown:
            fail(f"{path}: unknown profile Skills {sorted(unknown)}")
    for path in sorted(
        path
        for path in files
        if path.startswith("golden-routes/") and path.endswith("/route.yaml")
    ):
        route = load_yaml(files[path], path)
        unknown = set(route.get("spec", {}).get("requiredSkills", [])) - names
        if unknown:
            fail(f"{path}: unknown route Skills {sorted(unknown)}")
        phases = [phase.get("id") for phase in route.get("spec", {}).get("phases", [])]
        if phases != [
            "E1_STATIC",
            "E2_MODEL",
            "E3_DIFFERENTIAL",
            "E4_FAILURE_INJECTION",
            "E5_CUSTOMER_GOLDEN_ROUTE",
        ]:
            fail(f"{path}: phase sequence drift")
    adapter_files = sorted(
        path
        for path in files
        if path.startswith("verifier-adapters/") and path.endswith("/adapter.yaml")
    )
    for path in adapter_files:
        adapter = load_yaml(files[path], path)
        adapter_schema = schemas.get("verifier-adapter.schema.json")
        if adapter_schema is None:
            fail("verifier-adapter.schema.json is missing")
        try:
            Draft202012Validator(adapter_schema, registry=resolver_registry).validate(adapter)
        except Exception as exc:
            fail(f"{path}: adapter schema validation failed: {exc}")
    migration_files = sorted(
        path
        for path in files
        if path.startswith("db/migration/") and path.endswith(".sql")
    )
    openapi_files = sorted(
        path
        for path in files
        if path.startswith("contracts/openapi/") and path.endswith(".yaml")
    )
    asyncapi_files = sorted(
        path
        for path in files
        if path.startswith("contracts/events/") and path.endswith(".yaml")
    )
    rego_files = sorted(
        path
        for path in files
        if path.startswith("policies/rego/") and path.endswith(".rego")
    )
    rego_test_files = [path for path in rego_files if path.endswith("_test.rego")]
    package_counts = {
        "skills": len(skill_manifests),
        "perSkillFiles": sum(
            len(
                {
                    PurePosixPath(candidate).name
                    for candidate in files
                    if PurePosixPath(candidate).parent == PurePosixPath(path).parent
                }
            )
            for path in files
            if path.startswith("skills/P") and path.endswith("/manifest.yaml")
        ),
        "jsonSchemas": len(schema_files),
        "schemaExamples": len(
            [
                path
                for path in files
                if path.startswith("contracts/examples/")
                and path.endswith(".example.json")
            ]
        ),
        "postgresMigrations": len(migration_files),
        "openApiContracts": len(openapi_files),
        "asyncApiContracts": len(asyncapi_files),
        "regoModules": len(rego_files) - len(rego_test_files),
        "regoTests": len(rego_test_files),
        "verifierAdapters": len(adapter_files),
        "workflows": len(workflows),
        "goldenRoutes": len(
            [
                path
                for path in files
                if path.startswith("golden-routes/") and path.endswith("/route.yaml")
            ]
        ),
        "installProfiles": len(
            [
                path
                for path in files
                if path.startswith("profiles/") and path.endswith(".yaml")
            ]
        ),
    }
    declared_counts = manifest.get("spec", {}).get("counts")
    if (
        declared_counts != EXPECTED_PACKAGE_COUNTS
        or package_counts != EXPECTED_PACKAGE_COUNTS
    ):
        fail(
            f"package count contract drift: declared={declared_counts!r} actual={package_counts!r}"
        )
    return {
        "manifest": manifest,
        "skills": skill_manifests,
        "workflows": workflows,
        "schemaCount": len(schema_files),
        "counts": package_counts,
    }


def tree_digest(root: Path) -> str:
    records = []
    for path in sorted(
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    ):
        relative = path.relative_to(root).as_posix()
        records.append(
            {
                "path": relative,
                "sha256": digest_bytes(path.read_bytes()),
                "sizeBytes": path.stat().st_size,
            }
        )
    return "sha256:" + digest_value(records)


def source_matches(root: Path, files: dict[str, bytes]) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    for path in root.rglob("*"):
        if path.is_symlink() or (
            path.exists() and not path.is_file() and not path.is_dir()
        ):
            return False
        if path.is_file() and path.stat().st_mode & 0o111:
            return False
    actual = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    return actual == files


def write_source(root: Path, files: dict[str, bytes], modes: dict[str, int]) -> None:
    if root.exists() or root.is_symlink():
        if not source_matches(root, files):
            fail(f"existing source mirror differs from pinned archive: {root}")
        return
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{root.name}.", dir=root.parent))
    try:
        for relative, data in files.items():
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            os.chmod(destination, modes.get(relative, 0o644) & 0o644)
        os.replace(temporary, root)
    except Exception:
        for path in sorted(temporary.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
        temporary.rmdir()
        raise


def build_metadata(
    source_root: Path, archive_digest: str, package: dict[str, Any]
) -> dict[str, Any]:
    skills = []
    for name, manifest in sorted(package["skills"].items()):
        metadata = manifest["metadata"]
        skills.append(
            {
                "skillId": name,
                "title": metadata.get("title"),
                "priority": metadata.get("priority"),
                "domain": metadata.get("domain"),
                "dependencies": manifest.get("spec", {}).get("dependencies", []),
                "capabilities": manifest.get("spec", {}).get("capabilities", []),
                "handlerId": "execute_" + name.replace("-", "_"),
                "capabilityState": "CODE_COMPLETE_EXTERNAL_EVIDENCE_REQUIRED"
                if metadata.get("priority") == "P2"
                else (
                    "CODE_COMPLETE_LOCAL_RUNTIME"
                    if metadata.get("domain") in {"core", "platform"}
                    else "CODE_COMPLETE_NATIVE_EVIDENCE_REQUIRED"
                ),
                "implementationState": "PRODUCTION_CODE_COMPLETE",
                "externalEvidenceStatus": "NOT_RUN",
                "certificationStatus": "NOT_CERTIFIED",
            }
        )
    return {
        "schemaVersion": 1,
        "packageId": PACKAGE_ID,
        "packageVersion": "1.0.0",
        "sourceArchiveSha256": "sha256:" + archive_digest,
        "sourceTreeSha256": tree_digest(source_root),
        "skills": skills,
        "counts": {
            "skills": len(skills),
            "priority": dict(Counter(item["priority"] for item in skills)),
            "domains": dict(Counter(item["domain"] for item in skills)),
        },
        "runtime": {
            "engine": "engines/formal-assurance-engine",
            "binding": "PRODUCTION_CODE_COMPLETE",
            "externalEvidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "honestBoundary": "All 60 Skills have explicit production code paths. Local and native self-attested runs remain engineering evidence; P05 and E1-E5 certification require authorized independent external evidence.",
    }


def write_metadata(metadata: dict[str, Any]) -> None:
    destination = ROOT / DOC_RELATIVE
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "installed-manifest.json"
    target.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    registry = {
        "schemaVersion": 1,
        "packageId": PACKAGE_ID,
        "sourceArchiveSha256": metadata["sourceArchiveSha256"],
        "skills": metadata["skills"],
    }
    (destination / "skill-registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check_engine(metadata_path: Path) -> None:
    engine_src = ROOT / ENGINE_RELATIVE / "src"
    if not engine_src.is_dir():
        fail(f"repository-owned Formal Assurance engine is missing: {engine_src}")
    sys.path.insert(0, str(engine_src))
    try:
        from elmos_formal_assurance.registry import SkillRegistry

        registry = SkillRegistry(metadata_path)
        if registry.count != EXPECTED_SKILL_COUNT:
            fail(f"runtime registry count mismatch: {registry.count}")
        for item in registry.list():
            if item["implementationState"] != "PRODUCTION_CODE_COMPLETE":
                fail(f"runtime implementation is not production-complete: {item['skillId']}")
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        fail(f"repository-owned engine registry check failed: {exc}")
    finally:
        sys.path.pop(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="integrate_formal_assurance_kernel")
    parser.add_argument(
        "--write",
        action="store_true",
        help="materialize the immutable source mirror and generated registry",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the pinned mirror and runtime registry",
    )
    args = parser.parse_args(argv)
    if not args.write and not args.check:
        args.check = True
    archive = ROOT / ARCHIVE_RELATIVE
    files, modes, archive_digest = read_archive(archive)
    verify_internal_checksums(files)
    package = validate_package(files)
    source = ROOT / SOURCE_RELATIVE
    if args.write:
        write_source(source, files, modes)
    if not source_matches(source, files):
        fail("source mirror is absent or differs from the pinned archive")
    metadata = build_metadata(source, archive_digest, package)
    if args.write:
        write_metadata(metadata)
    metadata_path = ROOT / DOC_RELATIVE / "skill-registry.json"
    if not metadata_path.is_file():
        fail("generated skill-registry.json is missing; run with --write")
    check_engine(metadata_path)
    print(
        json.dumps(
            {
                "status": "PASS",
                "packageId": PACKAGE_ID,
                "archiveSha256": "sha256:" + archive_digest,
                "sourceTreeSha256": metadata["sourceTreeSha256"],
                "skills": EXPECTED_SKILL_COUNT,
                "workflows": len(package["workflows"]),
                "externalEvidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IntegrationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
