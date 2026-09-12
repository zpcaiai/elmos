#!/usr/bin/env python3
"""Safely import, extract, install, and verify the Elmos Router Industrial Skillpack.

The pinned ZIP is untrusted input. This script reads every member as bounded
data and never imports or executes package scripts, prompts, or workflows.
It preserves an immutable source tree in skills/elmos-router-industrial-skillpack
and installs Codex-compatible, provenance-bound wrappers in .agents/skills and
agent-skills/runtime, backed by engines/router-industrial-engine.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
from typing import Any, Mapping, Sequence
import zipfile

try:
    from tooling.skill_creator_tools import yaml_quote
except ModuleNotFoundError:
    from skill_creator_tools import yaml_quote


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-router-industrial-skillpack"
PACKAGE_NAME = "elmos-router-industrial-skillpack"
PACKAGE_VERSION = "1.0.0"
PACKAGE_ID = "elmos.router-industrial-skillpack"
NAMESPACE = "router-industrial-v1"

ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/router-industrial-skills")
ENGINE_RELATIVE = Path("engines/router-industrial-engine")
INSTALL_ROOTS = (Path("agent-skills/runtime"), Path(".agents/skills"))

EXPECTED_ARCHIVE_SHA256 = "90ebe2dcf3f4c9e21d80c508c268429d3944e7780a3054a7416bff59197d9319"
EXPECTED_ARCHIVE_BYTES = 42_130
EXPECTED_ARCHIVE_ENTRIES = 26
EXPECTED_UNCOMPRESSED_BYTES = 87_640

SKILLS_MAP = {
    "elmos-router-industrial": {
        "source_path": "SKILL.md",
        "description": "Master industrial model intelligence and routing subsystem for Elmos.",
        "runtime_handler": "execute_elmos_router_industrial",
        "phase": "orchestration",
    },
    "router-industrial-00-master-orchestrator": {
        "source_path": "skills/00-master-orchestrator/SKILL.md",
        "description": "Coordinate end-to-end routing plane execution, migration, and feature-flagged coexistence.",
        "runtime_handler": "execute_00_master_orchestrator",
        "phase": "orchestration",
    },
    "router-industrial-01-domain-contracts": {
        "source_path": "skills/01-domain-contracts/SKILL.md",
        "description": "Enforce provider-neutral typed domain contracts, execution plans, and schema validation.",
        "runtime_handler": "execute_01_domain_contracts",
        "phase": "contracts",
    },
    "router-industrial-02-model-provider-registry": {
        "source_path": "skills/02-model-provider-registry/SKILL.md",
        "description": "Manage versioned Model, Provider, and Deployment registries and dynamic health snapshots.",
        "runtime_handler": "execute_02_model_provider_registry",
        "phase": "registry",
    },
    "router-industrial-03-policy-and-security": {
        "source_path": "skills/03-policy-and-security/SKILL.md",
        "description": "Enforce 15 hard policy filters, fail-closed data residency, security context, and secret redaction.",
        "runtime_handler": "execute_03_policy_and_security",
        "phase": "policy",
    },
    "router-industrial-04-routing-engine": {
        "source_path": "skills/04-routing-engine/SKILL.md",
        "description": "Compute 4-phase deterministic route decisions, multi-factor scoring, and fallback sequences.",
        "runtime_handler": "execute_04_routing_engine",
        "phase": "routing",
    },
    "router-industrial-05-litellm-gateway": {
        "source_path": "skills/05-litellm-gateway/SKILL.md",
        "description": "Interface with LiteLLM proxy as a replaceable gateway while maintaining architectural authority.",
        "runtime_handler": "execute_05_litellm_gateway",
        "phase": "adapters",
    },
    "router-industrial-06-native-provider-adapters": {
        "source_path": "skills/06-native-provider-adapters/SKILL.md",
        "description": "Execute high-throughput native provider adapters for OpenAI, Anthropic, and self-hosted engines.",
        "runtime_handler": "execute_06_native_provider_adapters",
        "phase": "adapters",
    },
    "router-industrial-07-openrouter-adapter": {
        "source_path": "skills/07-openrouter-adapter/SKILL.md",
        "description": "Route long-tail, dynamic, and specialized open models through zero-data-retention OpenRouter.",
        "runtime_handler": "execute_07_openrouter_adapter",
        "phase": "adapters",
    },
    "router-industrial-08-resilience-and-replay": {
        "source_path": "skills/08-resilience-and-replay/SKILL.md",
        "description": "Enforce circuit breakers, jittered retries, CAS idempotency commit, and deterministic replay.",
        "runtime_handler": "execute_08_resilience_and_replay",
        "phase": "resilience",
    },
    "router-industrial-09-cost-rate-limit-accounting": {
        "source_path": "skills/09-cost-rate-limit-accounting/SKILL.md",
        "description": "Manage hierarchical budgets, rate limiters, token buckets, and append-only cost ledgers.",
        "runtime_handler": "execute_09_cost_rate_limit_accounting",
        "phase": "accounting",
    },
    "router-industrial-10-observability-and-evals": {
        "source_path": "skills/10-observability-and-evals/SKILL.md",
        "description": "Collect latency percentiles, telemetry spans with prompt redaction, and task benchmark evals.",
        "runtime_handler": "execute_10_observability_and_evals",
        "phase": "observability",
    },
    "router-industrial-11-deployment-and-operations": {
        "source_path": "skills/11-deployment-and-operations/SKILL.md",
        "description": "Validate deployment readiness, health probes, zero-downtime reconfiguration, and graceful drain.",
        "runtime_handler": "execute_11_deployment_and_operations",
        "phase": "operations",
    },
    "router-industrial-12-certification-and-rollout": {
        "source_path": "skills/12-certification-and-rollout/SKILL.md",
        "description": "Execute phased traffic ramping (1%->5%->25%->100%), anti-regression gates, and E0-E5 readiness.",
        "runtime_handler": "execute_12_certification_and_rollout",
        "phase": "certification",
    },
}


class IntegrationError(RuntimeError):
    pass


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def validate_archive(archive_path: Path) -> tuple[str, int, int, list[zipfile.ZipInfo]]:
    if not archive_path.is_file():
        raise IntegrationError(f"Archive not found: {archive_path}")

    with open(archive_path, "rb") as f:
        content = f.read()

    actual_sha = compute_sha256(content)
    actual_bytes = len(content)

    if actual_sha != EXPECTED_ARCHIVE_SHA256:
        raise IntegrationError(
            f"Archive SHA-256 mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {actual_sha}"
        )
    if actual_bytes != EXPECTED_ARCHIVE_BYTES:
        raise IntegrationError(
            f"Archive byte size mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {actual_bytes}"
        )

    with zipfile.ZipFile(archive_path, "r") as z:
        infolist = z.infolist()
        if len(infolist) != EXPECTED_ARCHIVE_ENTRIES:
            raise IntegrationError(
                f"Archive entry count mismatch: expected {EXPECTED_ARCHIVE_ENTRIES}, got {len(infolist)}"
            )
        uncompressed = sum(info.file_size for info in infolist)
        if uncompressed != EXPECTED_UNCOMPRESSED_BYTES:
            raise IntegrationError(
                f"Archive uncompressed size mismatch: expected {EXPECTED_UNCOMPRESSED_BYTES}, got {uncompressed}"
            )
        return actual_sha, actual_bytes, uncompressed, infolist


def generate_skill_wrapper(
    skill_name: str,
    meta: Mapping[str, str],
    source_content: str,
    source_sha: str,
) -> str:
    desc = meta["description"]
    handler = meta["runtime_handler"]
    phase = meta["phase"]
    source_rel = meta["source_path"]

    frontmatter = f"""---
name: {yaml_quote(skill_name)}
description: {yaml_quote(desc)}
metadata:
  source_package: {yaml_quote(PACKAGE_NAME)}
  source_package_id: {yaml_quote(PACKAGE_ID)}
  source_version: {yaml_quote(PACKAGE_VERSION)}
  source_path: {yaml_quote(source_rel)}
  source_sha256: {yaml_quote('sha256:' + source_sha)}
  normalized_namespace: {yaml_quote(NAMESPACE)}
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: {yaml_quote(skill_name)}
  runtime_handler: {yaml_quote(handler)}
  runtime_phase: {yaml_quote(phase)}
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `{skill_name}`.
The extracted source mirror in `skills/{PACKAGE_DIRECTORY}/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `{skill_name}`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `{handler}`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
{source_content.strip()}
```
"""
    return frontmatter


def extract_and_install(repository_root: Path, archive_path: Path) -> dict[str, Any]:
    archive_sha, archive_bytes, uncompressed_bytes, infolist = validate_archive(archive_path)

    source_dir = repository_root / SOURCE_RELATIVE
    docs_dir = repository_root / DOC_RELATIVE

    source_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    extracted_files: dict[str, str] = {}
    with zipfile.ZipFile(archive_path, "r") as z:
        for info in infolist:
            filename = info.filename
            if not filename.startswith(f"{PACKAGE_DIRECTORY}/"):
                raise IntegrationError(f"Unexpected prefix in entry: {filename}")
            rel_name = filename[len(f"{PACKAGE_DIRECTORY}/") :]
            if not rel_name:
                continue

            # Check directory traversal
            dest = (source_dir / rel_name).resolve()
            if not str(dest).startswith(str(source_dir.resolve())):
                raise IntegrationError(f"Path traversal detected: {filename}")

            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                dest.chmod(0o755)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = z.read(filename)
                with open(dest, "wb") as f:
                    f.write(data)
                dest.chmod(0o644)
                extracted_files[rel_name] = compute_sha256(data)

    # Install skill wrappers into both install roots
    installed_skills: list[str] = []
    catalog_entries: list[dict[str, Any]] = []

    for skill_name, meta in SKILLS_MAP.items():
        src_path = meta["source_path"]
        src_file = source_dir / src_path
        if not src_file.exists():
            raise IntegrationError(f"Required source file not found: {src_file}")

        with open(src_file, "r", encoding="utf-8") as f:
            src_content = f.read()

        src_sha = compute_sha256(src_content.encode("utf-8"))
        wrapper_content = generate_skill_wrapper(skill_name, meta, src_content, src_sha)

        for root_rel in INSTALL_ROOTS:
            target_dir = repository_root / root_rel / skill_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "SKILL.md"
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(wrapper_content)
            target_file.chmod(0o644)

        installed_skills.append(skill_name)
        catalog_entries.append(
            {
                "skill_name": skill_name,
                "description": meta["description"],
                "phase": meta["phase"],
                "runtime_handler": meta["runtime_handler"],
                "source_path": meta["source_path"],
                "source_sha256": src_sha,
                "status": "INSTALLED",
            }
        )

    # Generate documentation manifests
    manifest_data = {
        "package": PACKAGE_NAME,
        "package_id": PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "archive": {
            "path": str(ARCHIVE_RELATIVE),
            "sha256": archive_sha,
            "bytes": archive_bytes,
            "entries": len(infolist),
            "uncompressed_bytes": uncompressed_bytes,
        },
        "skills_installed": installed_skills,
        "source_files": len(extracted_files),
        "install_roots": [str(r) for r in INSTALL_ROOTS],
    }

    manifest_path = docs_dir / "installed-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, sort_keys=True)
    manifest_path.chmod(0o644)

    catalog_path = docs_dir / "COMPILED_SKILL_CATALOG.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump({"skills": catalog_entries}, f, indent=2, sort_keys=True)
    catalog_path.chmod(0o644)

    readme_content = f"""# Elmos Router Industrial Skills

- **Package**: `{PACKAGE_NAME}`
- **Version**: `{PACKAGE_VERSION}`
- **Archive SHA-256**: `{archive_sha}`
- **Installed Skills**: {len(installed_skills)}
- **Runtime Engine**: `engines/router-industrial-engine`

## Architecture & Subsystems

1. **Domain Contracts & Error Taxonomy (`01`)**: Provider-neutral `RouteRequest`, `ModelExecutionPlan`, `RouteDecision`, and 17-class error taxonomy.
2. **Registry Subsystem (`02`)**: Thread-safe dynamic `Model`, `Provider`, and `Deployment` registry with real-time health snapshots.
3. **Policy & Security Guardrails (`03`)**: 15 hard eligibility filters, data residency fences, capability leases, and credential redaction.
4. **Routing Engine (`04`)**: 4-phase deterministic decision pipeline (Hard filter -> Scoring -> Diversity tie-break -> Fallback plan) with shadow routing.
5. **Execution Lane Adapters (`05`, `06`, `07`)**: LiteLLM proxy gateway, native high-throughput direct adapters (OpenAI, Anthropic, Self-Hosted vLLM), and OpenRouter long-tail router.
6. **Resilience & Replay (`08`)**: Scoped circuit breakers, jittered exponential backoff, stream epoch coordinator, exactly-once CAS idempotency commit, and deterministic replay.
7. **Cost, Rate-Limiting & Accounting (`09`)**: Hierarchical budgets, token buckets, concurrency semaphores, and append-only cost ledger with reconciliation.
8. **Observability & Benchmarks (`10`)**: Latency percentiles, span tracing with prompt hashing, and task benchmark quality scoring.
9. **Operations & Deployment (`11`)**: Readiness probes, graceful drain, and zero-downtime configuration updates.
10. **Certification & Phased Rollout (`12`)**: Phased traffic ramp (1% -> 5% -> 25% -> 100%), anti-regression gates, and E0-E5 readiness.

## Verification

Run:
```bash
make router-industrial-skills
```
"""
    readme_path = docs_dir / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    readme_path.chmod(0o644)

    return manifest_data


def verify_installation(repository_root: Path, archive_path: Path) -> dict[str, Any]:
    archive_sha, archive_bytes, uncompressed_bytes, infolist = validate_archive(archive_path)

    source_dir = repository_root / SOURCE_RELATIVE
    if not source_dir.is_dir():
        raise IntegrationError(f"Source directory missing: {source_dir}")

    docs_dir = repository_root / DOC_RELATIVE
    manifest_path = docs_dir / "installed-manifest.json"
    if not manifest_path.is_file():
        raise IntegrationError(f"Installed manifest missing: {manifest_path}")

    catalog_path = docs_dir / "COMPILED_SKILL_CATALOG.json"
    if not catalog_path.is_file():
        raise IntegrationError(f"Compiled skill catalog missing: {catalog_path}")

    # Check extracted files
    with zipfile.ZipFile(archive_path, "r") as z:
        for info in infolist:
            filename = info.filename
            if not filename.startswith(f"{PACKAGE_DIRECTORY}/"):
                continue
            rel_name = filename[len(f"{PACKAGE_DIRECTORY}/") :]
            if not rel_name or info.is_dir():
                continue
            dest = source_dir / rel_name
            if not dest.is_file():
                raise IntegrationError(f"Extracted source file missing: {dest}")
            actual_sha = compute_file_sha256(dest)
            expected_sha = compute_sha256(z.read(filename))
            if actual_sha != expected_sha:
                raise IntegrationError(f"Source file corrupted/drifted: {dest}")

    # Check skills in both install roots
    for skill_name in SKILLS_MAP:
        for root_rel in INSTALL_ROOTS:
            skill_md = repository_root / root_rel / skill_name / "SKILL.md"
            if not skill_md.is_file():
                raise IntegrationError(f"Skill missing in {root_rel}: {skill_name}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    return {
        "status": "VERIFIED",
        "archive_sha256": archive_sha,
        "skills_count": len(SKILLS_MAP),
        "source_files_count": len(infolist),
        "manifest": manifest_data,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Extract archive and install skills")
    mode.add_argument("--check", action="store_true", help="Verify extraction, checksums, and installed skills")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root path")
    parser.add_argument("--archive", type=Path, help="Override path to zip archive")

    args = parser.parse_args(argv)
    repository_root = args.root.resolve()
    archive_path = args.archive.resolve() if args.archive else repository_root / ARCHIVE_RELATIVE

    try:
        if args.write:
            result = extract_and_install(repository_root, archive_path)
            print(json.dumps({"decision": "EXTRACTED_AND_INSTALLED", "details": result}, indent=2))
        else:
            result = verify_installation(repository_root, archive_path)
            print(json.dumps({"decision": "INSTALLATION_VERIFIED", "details": result}, indent=2))
        return 0
    except IntegrationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
