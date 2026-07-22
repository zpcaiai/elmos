#!/usr/bin/env python3
"""Validate Product B33-B55 Skill packs and fail-closed evidence boundaries."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from validate_product_batch33_38_integration import (
    COMPLETE_MANIFEST,
    LEGACY_MANIFEST,
    ROOT,
    RUNTIME,
    fail,
    load_official_validator,
)


BATCH39_MANIFEST = ROOT / "docs" / "product-batches39-complete" / "skill-source-manifest.json"
BATCH40_55_MANIFEST = ROOT / "docs" / "product-batches40-55-complete" / "skill-source-manifest.json"
EXPECTED_BATCHES = {str(batch): 48 for batch in range(40, 56)}
EXPECTED_SUBBATCHES = {
    f"{batch}{suffix}": 16
    for batch in range(40, 56)
    for suffix in ("A", "B", "C")
}


def read_records(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))["records"]


def main() -> None:
    payload = json.loads(BATCH40_55_MANIFEST.read_text(encoding="utf-8"))
    records = payload["records"]
    if len(records) != 768 or payload.get("pack_skill_count") != 768:
        fail(f"expected 768 Product B40-B55 Skills, found {len(records)}")
    if any(record.get("family") != "elmos-product-commercialization-b40-b55-complete" for record in records):
        fail("Product B40-B55 source family drifted")
    batch_counts = Counter(str(record["batch"]) for record in records)
    subbatch_counts = Counter(record["subbatch"] for record in records)
    provenance_counts = Counter(record["provenance"] for record in records)
    if dict(batch_counts) != EXPECTED_BATCHES:
        fail(f"unexpected Product B40-B55 batch counts: {dict(batch_counts)}")
    if dict(subbatch_counts) != EXPECTED_SUBBATCHES:
        fail(f"unexpected Product B40-B55 subbatch counts: {dict(subbatch_counts)}")
    if provenance_counts != {
        "approved-conversation-design": 16,
        "generated-planning-edition": 752,
    }:
        fail(f"unexpected Product B40-B55 provenance: {dict(provenance_counts)}")
    if payload["namespace_policy"] != {
        "product_commercialization": "Product Batch B40-B55 Enterprise Domains",
        "migration_pack": "Migration Packs M40-M45",
    }:
        fail("Product B40-B55 and Migration Pack M40-M45 namespaces are not separated")
    if payload.get("external_execution_evidence") != "NOT_RUN":
        fail("Product B40-B55 external execution evidence must remain NOT_RUN")
    if payload.get("approved_conversation_design_count") != 16:
        fail("Product B40-B55 approved-design provenance count drifted")
    if payload.get("generated_planning_edition_count") != 752:
        fail("Product B40-B55 generated-planning provenance count drifted")
    if payload.get("superseded_prior_record_count") != 0:
        fail("Product B40-B55 must not silently supersede earlier Product Skills")

    package_record = payload["packages"][0]
    package = ROOT / package_record["directory"]
    package_manifest = package / "manifest.json"
    if hashlib.sha256(package_manifest.read_bytes()).hexdigest() != package_record["normalized_manifest_sha256"]:
        fail("Product B40-B55 normalized package manifest drifted")
    submitted = json.loads(package_manifest.read_text(encoding="utf-8"))
    if submitted.get("skillCount") != 768 or len(submitted.get("skills", [])) != 768:
        fail("Product B40-B55 submitted package inventory drifted")
    if submitted.get("approvedSkillCount") != 16 or submitted.get("generatedPlanningSkillCount") != 752:
        fail("Product B40-B55 package provenance totals drifted")
    normalization = submitted.get("nameNormalization", {})
    if normalization.get("renamed") != 456 or not normalization.get("sourceNamePreserved"):
        fail("Product B40-B55 deterministic name normalization drifted")
    if submitted.get("sourceManifestSha256") != package_record["source_manifest_sha256"]:
        fail("Product B40-B55 original manifest provenance drifted")
    if submitted.get("sourcePackageTreeSha256") != package_record["source_package_tree_sha256"]:
        fail("Product B40-B55 original package provenance drifted")

    prior_records: dict[str, dict[str, object]] = {}
    for manifest in (LEGACY_MANIFEST, COMPLETE_MANIFEST, BATCH39_MANIFEST):
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        if manifest_payload.get("external_execution_evidence") != "NOT_RUN":
            fail(f"prior Product manifest must remain NOT_RUN: {manifest}")
        prior_records.update({record["name"]: record for record in manifest_payload["records"]})
    prior_names = set(prior_records)
    if len(prior_records) != 339:
        fail(f"expected 339 canonical Product Skills through B39, found {len(prior_records)}")
    names = {record["name"] for record in records}
    if len(names) != 768:
        fail("Product B40-B55 normalized names are not unique")
    if prior_names.intersection(names):
        fail("Product B40-B55 unexpectedly collides with an earlier Product Skill")
    if len(prior_names.union(names)) != 1107:
        fail("canonical Product B33-B55 Skill total must be 1,107")
    if payload.get("canonical_product_skill_count_with_prior_families") != 1107:
        fail("Product B40-B55 canonical manifest total drifted")
    if sum(record["source_name"] != record["name"] for record in records) != 456:
        fail("Product B40-B55 alias record count drifted")
    if any(len(record["name"]) > 64 for record in records):
        fail("Product B40-B55 contains a Skill name longer than 64 characters")

    validate_skill = load_official_validator()
    for name, record in prior_records.items():
        runtime = RUNTIME / name / "SKILL.md"
        if not runtime.is_file():
            fail(f"prior canonical Product Runtime Skill is missing: {name}")
        if hashlib.sha256(runtime.read_bytes()).hexdigest() != record["sha256"]:
            fail(f"prior canonical Product Runtime digest mismatch: {name}")
        valid, message = validate_skill(runtime.parent)
        if not valid:
            fail(f"official prior Product validation failed for {name}: {message}")
        interface = (runtime.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
        if "default_prompt:" not in interface or f"${name}" not in interface:
            fail(f"prior Product interface does not invoke ${name}")

    package_names = {item["name"] for item in submitted["skills"]}
    if package_names != names:
        fail("Product B40-B55 package and source manifest inventories differ")
    for record in records:
        name = record["name"]
        source = ROOT / record["source_path"]
        runtime = RUNTIME / name / "SKILL.md"
        if not source.is_file() or not runtime.is_file():
            fail(f"Product B40-B55 Skill is not installed on both sides: {name}")
        expected_hash = record["sha256"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
            fail(f"Product B40-B55 package source digest mismatch: {name}")
        if hashlib.sha256(runtime.read_bytes()).hexdigest() != expected_hash:
            fail(f"Product B40-B55 Runtime digest mismatch: {name}")
        for skill_dir in (source.parent, runtime.parent):
            valid, message = validate_skill(skill_dir)
            if not valid:
                fail(f"official Product B40-B55 validation failed for {name}: {message}")
            interface = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            if "default_prompt:" not in interface or f"${name}" not in interface:
                fail(f"Product B40-B55 interface does not invoke ${name}")

    runtime_total = len(list(RUNTIME.glob("*/SKILL.md")))
    if runtime_total < 1647:
        fail(f"expected at least the 1,647 Runtime Skill baseline, found {runtime_total}")
    additive_runtime_skills = runtime_total - 1647
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for statement in (
        "Product Batch B34-B55",
        "M40-M45",
        "generated planning edition",
        "NOT_RUN",
    ):
        if statement not in agents:
            fail(f"repository Product B40-B55 instruction is missing: {statement}")

    print(
        json.dumps(
            {
                "official_skill_validation": {"valid": 1107, "failed": 0},
                "prior_product_runtime_skills_validated": 339,
                "prior_source_package_archives": "NOT_REVALIDATED",
                "batch40_55_skill_counts": dict(batch_counts),
                "batch40_55_subbatch_count": len(subbatch_counts),
                "batch40_55_complete_pack_skills": len(records),
                "batch40_55_normalized_names": 456,
                "provenance": dict(provenance_counts),
                "superseded_prior_records": 0,
                "canonical_product_skills": 1107,
                "runtime_skill_total": runtime_total,
                "additive_non_product_runtime_skills": additive_runtime_skills,
                "external_execution_evidence": "NOT_RUN",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
