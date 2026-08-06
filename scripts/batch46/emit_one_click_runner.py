#!/usr/bin/env python3
"""Emit the one-click smoke entries for a generated or converted project.

Writes into the project itself so the user needs nothing from the ELMOS
repository to run it:

    run-smoke.sh / run-smoke.ps1     single-command entry
    Makefile.smoke                   `make -f Makefile.smoke smoke`
    docker-compose.smoke.yml         container entry (when applicable)
    smoke/tools/                     vendored, stdlib-only runner
    smoke/assertions.json            what "smoke passed" means for this project
    smoke/runner-manifest.json       entries, availability and lease policy

An entry that cannot be honestly supported is emitted as `unavailable` with a
reason. It is never faked, and the zero-dependency entry is never produced by
silently swapping a database engine the project does not declare support for.

Usage:
    python3 scripts/batch46/emit_one_click_runner.py <project-root> --write
"""
from __future__ import annotations

import argparse
import json
import shutil
import stat
from pathlib import Path
from typing import Any

from smoke_common import (
    DEFAULT_FREE_QUOTA_SECONDS,
    DEFAULT_GRACE_SECONDS,
    RUNNER_ENTRIES,
    SCHEMA_PREFIX,
    canonical_digest,
    read_json,
    smoke_dir,
    utc_now,
    write_json,
)

VENDORED_TOOLS = ("smoke_common.py", "smoke_lease.py", "run_smoke.py")

DB_IMAGES = {
    "postgres": {
        "image": "postgres:16-alpine",
        "port": 5432,
        "env": {"POSTGRES_PASSWORD": "smoke-local-only", "POSTGRES_USER": "smoke", "POSTGRES_DB": "smoke"},
        "init_dir": "/docker-entrypoint-initdb.d",
        "healthcheck": ["CMD-SHELL", "pg_isready -U smoke"],
    },
    "mysql": {
        "image": "mysql:8",
        "port": 3306,
        "env": {"MYSQL_ROOT_PASSWORD": "smoke-local-only", "MYSQL_DATABASE": "smoke"},
        "init_dir": "/docker-entrypoint-initdb.d",
        "healthcheck": ["CMD-SHELL", "mysqladmin ping -h 127.0.0.1 --silent"],
    },
    "redis": {"image": "redis:7-alpine", "port": 6379, "env": {}, "init_dir": None,
              "healthcheck": ["CMD", "redis-cli", "ping"]},
    "mongodb": {"image": "mongo:7", "port": 27017, "env": {}, "init_dir": "/docker-entrypoint-initdb.d",
                "healthcheck": ["CMD-SHELL", "mongosh --quiet --eval 'db.runCommand(1)'"]},
}

RUN_SMOKE_SH = """#!/usr/bin/env bash
# ELMOS Batch 46 one-click smoke run.
#
#   ./run-smoke.sh              start, seed, probe, assert, then stop after the
#                               free {quota} minute runtime lease
#   ./run-smoke.sh --entry compose
#   ./run-smoke.sh --ttl 120    shorter lease
#   ./run-smoke.sh --no-hold    assert and tear down immediately
#
# The lease is enforced: when it expires every service this script started is
# stopped and every byte of smoke data it created is deleted.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "run-smoke: python3 is required to drive the smoke run" >&2
  exit 3
fi

exec python3 smoke/tools/run_smoke.py --project . "$@"
"""

RUN_SMOKE_PS1 = """# ELMOS Batch 46 one-click smoke run (Windows).
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) { Write-Error "run-smoke: python3 is required to drive the smoke run"; exit 3 }
& $python.Source "smoke/tools/run_smoke.py" "--project" "." @args
exit $LASTEXITCODE
"""

MAKEFILE_SMOKE = """# ELMOS Batch 46 smoke targets.
SMOKE_PYTHON ?= python3
SMOKE_TTL ?= {quota_seconds}

.PHONY: smoke smoke-seed smoke-compose smoke-zero-dep smoke-status smoke-stop

smoke:
\t$(SMOKE_PYTHON) smoke/tools/run_smoke.py --project . --entry script --ttl $(SMOKE_TTL)

smoke-compose:
\t$(SMOKE_PYTHON) smoke/tools/run_smoke.py --project . --entry compose --ttl $(SMOKE_TTL)

smoke-zero-dep:
\t$(SMOKE_PYTHON) smoke/tools/run_smoke.py --project . --entry zero-dep --ttl $(SMOKE_TTL)

smoke-seed:
\t$(SMOKE_PYTHON) smoke/tools/run_smoke.py --project . --seed-only

smoke-status:
\t$(SMOKE_PYTHON) smoke/tools/smoke_lease.py status --project .

smoke-stop:
\t$(SMOKE_PYTHON) smoke/tools/smoke_lease.py stop --project . --reason manual
"""


def _entry_availability(profile: dict[str, Any], requirements: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stacks = profile.get("stacks", [])
    primary = next((s for s in stacks if s.get("role") == "primary"), stacks[0] if stacks else None)
    datastores = profile.get("datastores", [])
    entries: dict[str, dict[str, Any]] = {}

    if primary and primary.get("start_command"):
        entries["script"] = {"status": "available", "command": "./run-smoke.sh"}
    else:
        entries["script"] = {
            "status": "unavailable",
            "reason": "no start command detected; declare stacks[].start_command in smoke/profile.json",
        }

    container_stores = [d for d in datastores if d["engine"] in DB_IMAGES]
    has_dockerfile = bool(profile.get("dockerfile"))
    if container_stores or has_dockerfile:
        entries["compose"] = {
            "status": "available",
            "command": "./run-smoke.sh --entry compose",
            "requires": ["docker", "docker compose"],
            "app_runs_in_container": has_dockerfile,
            "note": None if has_dockerfile else "compose provides datastores only; the app runs on the host",
        }
    else:
        entries["compose"] = {
            "status": "unavailable",
            "reason": "no Dockerfile and no containerisable datastore detected",
        }

    entries["make"] = {"status": entries["script"]["status"], "command": "make -f Makefile.smoke smoke"}
    if entries["make"]["status"] != "available":
        entries["make"]["reason"] = entries["script"].get("reason")

    unsubstitutable = [d["engine"] for d in datastores if d.get("embedded_substitute_status") != "available"
                       and d["engine"] not in ("redis", "kafka", "rabbitmq")]
    if not datastores:
        entries["zero-dep"] = {"status": "available", "command": "./run-smoke.sh --entry zero-dep",
                               "note": "project declares no datastore"}
    elif unsubstitutable:
        entries["zero-dep"] = {
            "status": "unavailable",
            "reason": (
                f"no approved embedded substitute for {', '.join(sorted(set(unsubstitutable)))}; "
                "an engine swap that the project does not declare support for would change semantics"
            ),
        }
    else:
        substitutes = sorted({d["embedded_substitute"] for d in datastores if d.get("embedded_substitute")})
        entries["zero-dep"] = {
            "status": "available",
            "command": "./run-smoke.sh --entry zero-dep",
            "substitutes": substitutes,
            "semantic_warning": (
                "an embedded substitute is not the production engine; zero-dep results are "
                "smoke evidence only and never route, dialect or performance evidence"
            ),
        }
    return entries


def build_assertions(profile: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    stacks = profile.get("stacks", [])
    primary = next((s for s in stacks if s.get("role") == "primary"), stacks[0] if stacks else {})
    checks: list[dict[str, Any]] = [
        {"id": "process-started", "kind": "process", "required": True,
         "expect": "the start command produces a live process"},
        {"id": "port-listening", "kind": "tcp", "required": bool(primary.get("default_port")),
         "port_source": "runtime", "timeout_seconds": 120,
         "expect": "the service accepts a TCP connection on the allocated port"},
    ]
    readiness = primary.get("readiness_path")
    checks.append({
        "id": "http-readiness",
        "kind": "http",
        "required": bool(readiness),
        "method": "GET",
        "path": readiness or "/",
        "accept_status": [200, 204] if readiness else [200, 204, 301, 302, 400, 401, 403, 404],
        "timeout_seconds": 120,
        "expect": "readiness endpoint answers" if readiness
                  else "root path answers with a non-5xx status (no readiness contract declared)",
    })
    endpoints = requirements.get("candidate_smoke_endpoints", [])
    # A functional check that hits the readiness endpoint proves nothing beyond
    # readiness, so prefer any other contract-declared path.
    endpoints = sorted(
        endpoints,
        key=lambda e: (e.get("path") == readiness, e.get("path") in ("/", "/health"), e.get("path", "")),
    )
    if endpoints:
        first = endpoints[0]
        checks.append({
            "id": "http-functional",
            "kind": "http",
            "required": True,
            "method": first["method"],
            "path": first["path"],
            "accept_status": [200, 201, 202, 204],
            "expect": "one contract-declared endpoint serves a response backed by seeded data",
            "source": first.get("source"),
        })
    else:
        checks.append({
            "id": "http-functional",
            "kind": "http",
            "required": False,
            "status_when_absent": "NOT_RUN",
            "expect": "no API contract detected; declare one endpoint to make this a real functional check",
        })
    if any(d.get("kind") == "table" for d in requirements.get("datasets", [])):
        checks.append({
            "id": "seed-visible",
            "kind": "datastore",
            "required": False,
            "expect": "seeded rows are readable through the running service or the ephemeral datastore",
            "status_when_absent": "NOT_RUN",
        })
    checks.extend([
        {"id": "graceful-shutdown", "kind": "lifecycle", "required": True,
         "expect": "SIGTERM is honoured within the grace period without orphaned children"},
        {"id": "lease-teardown", "kind": "lifecycle", "required": True,
         "expect": "lease expiry stops every started service and deletes all ephemeral smoke data"},
    ])
    return {
        "schema": f"{SCHEMA_PREFIX}.smoke-assertions/1",
        "generated_at": utc_now(),
        "scope": "functional smoke only",
        "not_evidence_for": [
            "route or dialect equivalence", "performance", "security", "accessibility",
            "certification of any migration pack",
        ],
        "checks": checks,
    }


def build_compose(project_root: Path, profile: dict[str, Any]) -> str | None:
    datastores = [d for d in profile.get("datastores", []) if d["engine"] in DB_IMAGES]
    has_dockerfile = bool(profile.get("dockerfile"))
    if not datastores and not has_dockerfile:
        return None
    lines = [
        "# ELMOS Batch 46 smoke topology. Ephemeral by design:",
        "# `docker compose -f docker-compose.smoke.yml down -v` removes every volume.",
        "name: smoke-run",
        "services:",
    ]
    for store in datastores:
        spec = DB_IMAGES[store["engine"]]
        name = store["engine"]
        lines.append(f"  {name}:")
        lines.append(f"    image: {spec['image']}")
        lines.append("    restart: \"no\"")
        if spec["env"]:
            lines.append("    environment:")
            for key, value in spec["env"].items():
                lines.append(f"      {key}: \"{value}\"")
        lines.append("    ports:")
        lines.append(f"      - \"127.0.0.1:${{SMOKE_{name.upper()}_PORT:-{spec['port']}}}:{spec['port']}\"")
        if spec["init_dir"] and (smoke_dir(project_root) / "seed" / "seed.sql").is_file():
            lines.append("    volumes:")
            lines.append(f"      - ./smoke/seed/seed.sql:{spec['init_dir']}/00-smoke-seed.sql:ro")
        lines.append("    healthcheck:")
        lines.append(f"      test: {json.dumps(spec['healthcheck'])}")
        lines.append("      interval: 3s")
        lines.append("      retries: 20")
        lines.append("    tmpfs:")
        lines.append("      - /var/lib/smoke-scratch")
    if has_dockerfile:
        lines.append("  app:")
        lines.append("    build:")
        lines.append("      context: .")
        lines.append(f"      dockerfile: {profile['dockerfile']}")
        lines.append("    restart: \"no\"")
        lines.append("    env_file:")
        lines.append("      - ./smoke/seed/env.smoke")
        lines.append("    ports:")
        lines.append("      - \"127.0.0.1:${SMOKE_PORT:-8080}:${SMOKE_CONTAINER_PORT:-8080}\"")
        if datastores:
            lines.append("    depends_on:")
            for store in datastores:
                lines.append(f"      {store['engine']}:")
                lines.append("        condition: service_healthy")
    lines.append("")
    return "\n".join(lines)


def emit(root: Path, write: bool, tools_source: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    profile = read_json(smoke_dir(root) / "profile.json")
    requirements = read_json(smoke_dir(root) / "minimal-data-requirements.json")

    for candidate in ("Dockerfile", "Dockerfile.smoke", "src/Dockerfile"):
        if (root / candidate).is_file():
            profile["dockerfile"] = candidate
            break

    entries = _entry_availability(profile, requirements)
    assertions = build_assertions(profile, requirements)
    compose = build_compose(root, profile)

    quota_minutes = DEFAULT_FREE_QUOTA_SECONDS // 60
    written: list[str] = []
    if write:
        write_json(smoke_dir(root) / "profile.json", profile)
        write_json(smoke_dir(root) / "assertions.json", assertions)

        tools_dir = smoke_dir(root) / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        for name in VENDORED_TOOLS:
            source = Path(tools_source) / name
            if not source.is_file():
                raise SystemExit(f"error: missing runner source {source}")
            shutil.copyfile(source, tools_dir / name)
            written.append(f"smoke/tools/{name}")

        sh_path = root / "run-smoke.sh"
        sh_path.write_text(RUN_SMOKE_SH.format(quota=quota_minutes), encoding="utf-8")
        sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append("run-smoke.sh")

        (root / "run-smoke.ps1").write_text(RUN_SMOKE_PS1, encoding="utf-8")
        written.append("run-smoke.ps1")

        (root / "Makefile.smoke").write_text(
            MAKEFILE_SMOKE.format(quota_seconds=DEFAULT_FREE_QUOTA_SECONDS), encoding="utf-8"
        )
        written.append("Makefile.smoke")

        if compose:
            (root / "docker-compose.smoke.yml").write_text(compose, encoding="utf-8")
            written.append("docker-compose.smoke.yml")

    manifest: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.runner-manifest/1",
        "generated_at": utc_now(),
        "profile_digest": profile.get("profile_digest"),
        "requirements_digest": requirements.get("requirements_digest"),
        "entries": {name: entries.get(name, {"status": "unavailable", "reason": "not evaluated"})
                    for name in RUNNER_ENTRIES},
        "default_entry": "script" if entries["script"]["status"] == "available" else next(
            (name for name in RUNNER_ENTRIES if entries.get(name, {}).get("status") == "available"), None
        ),
        "lease_policy": {
            "free_quota_seconds": DEFAULT_FREE_QUOTA_SECONDS,
            "grace_seconds": DEFAULT_GRACE_SECONDS,
            "auto_renew": False,
            "extend_policy": "explicit-only",
            "on_expiry": "stop every started service, remove containers and volumes, delete ephemeral smoke data",
        },
        "written_files": written,
        "unknown": profile.get("unknown", []) + requirements.get("unknown", []),
    }
    manifest["runner_manifest_digest"] = canonical_digest(
        {k: v for k, v in manifest.items() if k not in ("generated_at", "runner_manifest_digest")}
    )
    if write:
        write_json(smoke_dir(root) / "runner-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit one-click smoke entries into a project")
    parser.add_argument("project_root")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--tools-source", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    manifest = emit(Path(args.project_root), args.write, Path(args.tools_source))
    if args.write:
        print("wrote: " + ", ".join(manifest["written_files"]))
    else:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
