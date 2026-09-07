#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from check_no_secrets import scan as secret_scan
from common import canonical_files, load_manifest, package_root, sha256_file
from manage_install import install, uninstall
from validate_schemas import validate as validate_schemas
from validate_skills import validate as validate_skills


def validate_required_files(root: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    for rel in manifest.get("required_docs", []):
        if not (root / rel).exists():
            errors.append(f"Missing required document: {rel}")
    for rel in [
        "install.sh", "uninstall.sh", "verify.sh",
        "install.ps1", "uninstall.ps1", "verify.ps1",
        "requirements-dev.txt", "fixtures/index.yaml",
        "plans/WORK-BREAKDOWN.yaml", "plans/RISK-REGISTER.yaml"
    ]:
        if not (root / rel).exists():
            errors.append(f"Missing required package file: {rel}")
    return errors


def validate_yaml_and_json_files(root: Path) -> list[str]:
    errors: list[str] = []
    for base in ["templates", "plans", "examples"]:
        for path in sorted((root / base).rglob("*")):
            if not path.is_file():
                continue
            try:
                if path.suffix in {".yaml", ".yml"}:
                    yaml.safe_load(path.read_text(encoding="utf-8"))
                elif path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{path.relative_to(root)}: {exc}")
    return errors


def validate_checksums(root: Path) -> list[str]:
    checksum_path = root / "CHECKSUMS.sha256"
    if not checksum_path.exists():
        return ["Missing CHECKSUMS.sha256"]
    errors: list[str] = []
    expected: dict[str, str] = {}
    for line_no, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            digest, rel = line.split("  ", 1)
        except ValueError:
            errors.append(f"CHECKSUMS.sha256:{line_no}: invalid format")
            continue
        expected[rel] = digest

    actual_files = {p.relative_to(root).as_posix(): p for p in canonical_files(root)}
    for rel, path in actual_files.items():
        if rel not in expected:
            errors.append(f"Checksum missing for {rel}")
            continue
        actual = sha256_file(path)
        if actual != expected[rel]:
            errors.append(f"Checksum mismatch for {rel}")
    for rel in expected:
        if rel not in actual_files:
            errors.append(f"Checksum references missing file {rel}")
    return errors


def install_smoke_test(root: Path) -> list[str]:
    errors: list[str] = []
    manifest = load_manifest(root)
    expected = {s["name"] for s in manifest["skills"]}
    with tempfile.TemporaryDirectory(prefix="elmos-skills-smoke-") as temp:
        project = Path(temp)
        result = install(project, "both", force=False, dry_run=False)
        if not result["ok"]:
            errors.extend([f"install smoke: {x}" for x in result["errors"]])
            return errors
        codex = {p.name for p in (project / ".agents" / "skills").iterdir() if p.is_dir()}
        claude = {p.name for p in (project / ".claude" / "skills").iterdir() if p.is_dir()}
        if codex != expected:
            errors.append(f"Codex installed set mismatch: expected {len(expected)}, got {len(codex)}")
        if claude != expected:
            errors.append(f"Claude installed set mismatch: expected {len(expected)}, got {len(claude)}")
        result = uninstall(project, "both", dry_run=False)
        if not result["ok"]:
            errors.extend([f"uninstall smoke: {x}" for x in result["errors"]])
        for path in [project / ".agents" / "skills", project / ".claude" / "skills"]:
            leftovers = [p.name for p in path.iterdir()] if path.exists() else []
            if leftovers:
                errors.append(f"Uninstall left files in {path}: {leftovers}")
    return errors


def run_unittests(root: Path) -> tuple[list[str], str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    errors = [] if proc.returncode == 0 else ["Unit tests failed"]
    return errors, proc.stdout


def verify(root: Path, skip_checksums: bool = False, skip_tests: bool = False) -> dict:
    manifest = load_manifest(root)
    errors: list[str] = []
    warnings: list[str] = []

    skill_result = validate_skills(root)
    errors.extend(skill_result["errors"])
    warnings.extend(skill_result["warnings"])

    schema_result = validate_schemas(root)
    errors.extend(schema_result["errors"])

    secret_result = secret_scan(root)
    for finding in secret_result["findings"]:
        errors.append(f"Secret finding {finding['kind']} at {finding['path']}:{finding['line']}")

    errors.extend(validate_required_files(root, manifest))
    errors.extend(validate_yaml_and_json_files(root))
    errors.extend(install_smoke_test(root))

    test_output = ""
    if not skip_tests:
        test_errors, test_output = run_unittests(root)
        errors.extend(test_errors)

    if not skip_checksums:
        errors.extend(validate_checksums(root))

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "skills": skill_result["skill_count"],
            "tasks": skill_result["task_count"],
            "schemas": schema_result["schema_count"],
            "fixtures": schema_result["fixture_count"],
            "files": len(canonical_files(root)),
        },
        "test_output": test_output,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--skip-checksums", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    result = verify(root, skip_checksums=args.skip_checksums, skip_tests=args.skip_tests)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["test_output"], end="")
        for warning in result["warnings"]:
            print(f"WARN: {warning}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        c = result["counts"]
        print(
            f"skills={c['skills']} tasks={c['tasks']} schemas={c['schemas']} "
            f"fixtures={c['fixtures']} files={c['files']} ok={result['ok']}"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
