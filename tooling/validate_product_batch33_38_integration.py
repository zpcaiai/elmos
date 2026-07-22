#!/usr/bin/env python3
"""Validate Product B33-B39 Skills, complete packs and evidence boundaries.

The filename is retained as a compatibility entry point; new callers should
use ``validate_product_batch33_39_integration.py``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_MANIFEST = ROOT / "docs" / "product-batches33-38" / "skill-source-manifest.json"
COMPLETE_MANIFEST = ROOT / "docs" / "product-batches34-38-complete" / "skill-source-manifest.json"
BATCH39_MANIFEST = ROOT / "docs" / "product-batches39-complete" / "skill-source-manifest.json"
RUNTIME = ROOT / "agent-skills" / "runtime"
OFFICIAL_VALIDATOR = Path("/Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py")

EXPECTED_SKILLS = {
    "33-core": 17, "33-mature": 18, "34": 40, "35": 28, "36": 41,
    "37A": 16, "37B": 16, "37C": 16, "38A": 16,
}
EXPECTED_COMPLETE_SKILLS = {"34": 18, "35": 33, "36": 41, "37": 48, "38": 48}
EXPECTED_BATCH39_SKILLS = {"39A": 16, "39B": 16, "39C": 16}
EXPECTED_TABLES = {
    "V42__product_source_control_and_workspace.sql": 279,
    "V43__product_secure_execution_plane.sql": 419,
    "V44__product_artifact_evidence_fabric.sql": 174,
    "V45__product_external_evidence_producers.sql": 146,
    "V46__product_assurance_analytics.sql": 214,
    "V47__product_continuous_authorization.sql": 185,
}
REQUIRED_MODULES = (
    "source-control-workspace-governance", "secure-execution-plane",
    "evidence-assurance-fabric", "continuous-authorization",
)


def fail(message: str) -> None:
    raise SystemExit(message)


def load_official_validator():
    if not OFFICIAL_VALIDATOR.is_file():
        fail(f"official Skill validator missing: {OFFICIAL_VALIDATOR}")
    spec = importlib.util.spec_from_file_location("elmos_official_skill_validator", OFFICIAL_VALIDATOR)
    if spec is None or spec.loader is None:
        fail("cannot load official Skill validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_skill


def main() -> None:
    legacy_payload = json.loads(LEGACY_MANIFEST.read_text(encoding="utf-8"))
    legacy_records = legacy_payload["records"]
    if len(legacy_records) != 208:
        fail(f"expected 208 legacy Product Skills, found {len(legacy_records)}")
    legacy_counts = Counter(record["batch"] for record in legacy_records)
    if dict(legacy_counts) != EXPECTED_SKILLS:
        fail(f"unexpected legacy Product Skill counts: {dict(legacy_counts)}")
    if legacy_payload["namespace_policy"] != {
        "product_commercialization": "Product Batch 33-38", "migration_pack": "M35-M45"
    }:
        fail("Product and Migration Pack namespaces are not explicitly separated")
    if legacy_payload["external_execution_evidence"] != "NOT_RUN":
        fail("external Product execution evidence must remain NOT_RUN")
    source = Path(legacy_payload["source"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != legacy_payload["source_sha256"]:
        fail("commercial specification digest changed; rerun the Skill sync")

    complete_payload = json.loads(COMPLETE_MANIFEST.read_text(encoding="utf-8"))
    complete_records = complete_payload["records"]
    if len(complete_records) != 188:
        fail(f"expected 188 complete-pack Product Skills, found {len(complete_records)}")
    complete_counts = Counter(str(record["product_batch"]) for record in complete_records)
    if dict(complete_counts) != EXPECTED_COMPLETE_SKILLS:
        fail(f"unexpected complete-pack Product Skill counts: {dict(complete_counts)}")
    if complete_payload["namespace_policy"] != {
        "product_commercialization": "Product Batch B34-B38 Complete",
        "migration_pack": "Migration Pack M35-M45",
    }:
        fail("complete Product packs and Migration Packs are not explicitly separated")
    if complete_payload["external_execution_evidence"] != "NOT_RUN":
        fail("complete-pack external execution evidence must remain NOT_RUN")
    for package in complete_payload["packages"]:
        manifest = ROOT / package["directory"] / "manifest.json"
        if not manifest.is_file() or hashlib.sha256(manifest.read_bytes()).hexdigest() != package["manifest_sha256"]:
            fail(f"complete Product package manifest drifted: {package['directory']}")

    batch39_payload = json.loads(BATCH39_MANIFEST.read_text(encoding="utf-8"))
    batch39_records = batch39_payload["records"]
    if len(batch39_records) != 48:
        fail(f"expected 48 Product B39 Skills, found {len(batch39_records)}")
    batch39_counts = Counter(record["batch"] for record in batch39_records)
    if dict(batch39_counts) != EXPECTED_BATCH39_SKILLS:
        fail(f"unexpected Product B39 Skill counts: {dict(batch39_counts)}")
    if batch39_payload["namespace_policy"] != {
        "product_commercialization": "Product Batch B39 Finance",
        "migration_pack": "Migration Pack M39 Global SRE",
    }:
        fail("Product B39 Finance and Migration Pack M39 Global SRE are not explicitly separated")
    if batch39_payload["external_execution_evidence"] != "NOT_RUN":
        fail("Product B39 external execution evidence must remain NOT_RUN")
    for package in batch39_payload["packages"]:
        manifest = ROOT / package["directory"] / "manifest.json"
        if not manifest.is_file() or hashlib.sha256(manifest.read_bytes()).hexdigest() != package["manifest_sha256"]:
            fail(f"Product B39 package manifest drifted: {package['directory']}")

    legacy_names = {record["name"] for record in legacy_records}
    complete_names = {record["name"] for record in complete_records}
    superseded = legacy_names.intersection(complete_names)
    if superseded != set(complete_payload["superseded_legacy_records"]):
        fail("complete Product pack supersession map drifted")
    canonical_records = {record["name"]: record for record in legacy_records}
    canonical_records.update({record["name"]: record for record in complete_records})
    if len(canonical_records) != 291 or complete_payload["canonical_product_skill_count_with_legacy_b33_b38"] != 291:
        fail(f"expected 291 canonical Product B33-B38 Skills, found {len(canonical_records)}")
    if set(canonical_records).intersection(record["name"] for record in batch39_records):
        fail("Product B39 unexpectedly collides with an earlier Product Skill")
    canonical_records.update({record["name"]: record for record in batch39_records})
    if len(canonical_records) != 339 or batch39_payload["canonical_product_skill_count_with_prior_families"] != 339:
        fail(f"expected 339 canonical Product B33-B39 Skills, found {len(canonical_records)}")

    validate_skill = load_official_validator()
    names: set[str] = set()
    for record in canonical_records.values():
        name = record["name"]
        if name in names:
            fail(f"duplicate installed Skill name: {name}")
        names.add(name)
        skill_dir = RUNTIME / name
        valid, message = validate_skill(skill_dir)
        if not valid:
            fail(f"official validation failed for {name}: {message}")
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        if hashlib.sha256(skill.encode()).hexdigest() != record["sha256"]:
            fail(f"Skill source digest mismatch: {name}")
        if record.get("family") in {
            "elmos-product-commercialization-complete",
            "elmos-product-commercialization-b39-complete",
        }:
            submitted = ROOT / record["source_path"]
            if not submitted.is_file() or hashlib.sha256(submitted.read_bytes()).hexdigest() != record["sha256"]:
                fail(f"complete package source digest mismatch: {name}")
            submitted_interface = (submitted.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
            if f"${name}" not in submitted_interface or "default_prompt:" not in submitted_interface:
                fail(f"complete package interface does not explicitly invoke ${name}")
        interface = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
        if f"${name}" not in interface or "default_prompt:" not in interface:
            fail(f"Skill interface does not explicitly invoke ${name}")

    runtime_total = len(list(RUNTIME.glob("*/SKILL.md")))
    if runtime_total < len(canonical_records):
        fail("runtime Skill catalog is smaller than the Product manifest")

    migration_root = ROOT / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration"
    declared: list[tuple[str, str]] = []
    for filename, expected in EXPECTED_TABLES.items():
        content = (migration_root / filename).read_text(encoding="utf-8")
        values = re.findall(r"\('([a-z_]+)', '([a-z0-9_]+)'\)", content)
        if len(values) != expected:
            fail(f"{filename}: expected {expected} table declarations, found {len(values)}")
        declared.extend(values)
        for invariant in (
            "FORCE ROW LEVEL SECURITY", "current_setting(''app.organization_id'', true)",
            "external_operation_executed = false", "elmos_forbid_append_only_mutation",
            "READY_FOR_HUMAN_DECISION", "independent_verifier_id",
        ):
            if invariant not in content:
                fail(f"{filename}: missing persistence invariant {invariant}")
        if "secret_value" in content:
            fail(f"{filename}: secret material field is forbidden")
    if len(declared) != 1417 or len(set(declared)) != 1416:
        fail("Product persistence table declaration totals drifted")

    parent = (ROOT / "pom.xml").read_text(encoding="utf-8")
    control_pom = (ROOT / "apps" / "control-plane" / "pom.xml").read_text(encoding="utf-8")
    for module in REQUIRED_MODULES:
        if f"<module>modules/{module}</module>" not in parent:
            fail(f"root reactor missing {module}")
        if not (ROOT / "modules" / module / "pom.xml").is_file():
            fail(f"module POM missing: {module}")
        artifact = "elmos-" + module
        if f"<artifactId>{artifact}</artifactId>" not in control_pom:
            fail(f"control-plane dependency missing: {artifact}")

    controller = ROOT / "apps" / "control-plane" / "src" / "main" / "java" / "io" / "elmos" / "controlplane" / "ProductCommercializationController.java"
    if not controller.is_file() or "externalExecutionEvidence\", \"NOT_RUN" not in controller.read_text(encoding="utf-8"):
        fail("Product commercialization capability API must preserve NOT_RUN")

    print(json.dumps({
        "official_skill_validation": {"valid": len(canonical_records), "failed": 0},
        "runtime_skill_total": runtime_total,
        "legacy_product_skill_counts": dict(legacy_counts),
        "complete_pack_skill_counts": dict(complete_counts),
        "complete_pack_skills": len(complete_records),
        "batch39_skill_counts": dict(batch39_counts),
        "batch39_complete_pack_skills": len(batch39_records),
        "superseded_legacy_records": len(superseded),
        "canonical_product_skills": len(canonical_records),
        "persistence": {"declarations": len(declared), "unique_tables": len(set(declared)), "migrations": 6},
        "modules": list(REQUIRED_MODULES),
        "external_execution_evidence": "NOT_RUN",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
