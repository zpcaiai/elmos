#!/usr/bin/env python3
"""Deterministic scaffolding and fail-closed gates for Batches 38-45.

Batches 35, 36, and 37 use their richer dedicated validators and gates.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]
BATCHES = {
    38: {"count": 22, "first": 1325, "last": 1346, "metrics": {"editionConformanceRate": ("min", 1.0), "upgradeRollbackPassRate": ("min", 1.0), "recoveryPassRate": ("min", 1.0)}},
    39: {"count": 22, "first": 1347, "last": 1368, "metrics": {"sloPassRate": ("min", 1.0), "restorePassRate": ("min", 1.0), "incidentExercisePassRate": ("min", 1.0)}},
    40: {"count": 24, "first": 1369, "last": 1392, "metrics": {"supplyChainCoverageRate": ("min", 0.95), "signaturePassRate": ("min", 1.0), "criticalVulnerabilityCount": ("max", 0.0)}},
    41: {"count": 20, "first": 1393, "last": 1412, "metrics": {"knowledgeProvenanceCoverageRate": ("min", 0.95), "privacyIsolationPassRate": ("min", 1.0), "predictionCalibrationPassRate": ("min", 1.0)}},
    42: {"count": 22, "first": 1413, "last": 1434, "metrics": {"agentEvalPassRate": ("min", 1.0), "policyViolationCount": ("max", 0.0), "killSwitchPassRate": ("min", 1.0)}},
    43: {"count": 20, "first": 1435, "last": 1454, "metrics": {"compatibilityMatrixPassRate": ("min", 1.0), "upgradePassRate": ("min", 1.0), "unsupportedBreakingChangeCount": ("max", 0.0)}},
    44: {"count": 20, "first": 1455, "last": 1474, "metrics": {"meteringReconciliationRate": ("min", 1.0), "budgetGuardrailPassRate": ("min", 1.0), "grossMarginEvidenceCoverageRate": ("min", 0.95)}},
    45: {"count": 22, "first": 1475, "last": 1496, "metrics": {"maturityDimensionPassRate": ("min", 1.0), "independentReviewPassRate": ("min", 1.0), "unresolvedCriticalRiskCount": ("max", 0.0)}},
}
REQUIRED_SECTIONS = (
    "## Workflow",
    "## Verification",
    "## Stop and escalate when",
    "## Definition of done",
)


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def validate_batch(batch: int) -> list[str]:
    spec = BATCHES[batch]
    errors: list[str] = []
    skill_dirs = sorted((ROOT / ".agents" / "skills").glob(f"b{batch}-*"))
    if len(skill_dirs) != spec["count"]:
        errors.append(f"expected {spec['count']} Skills, found {len(skill_dirs)}")
    names: set[str] = set()
    ids: list[int] = []
    for directory in skill_dirs:
        path = directory / "SKILL.md"
        if not path.is_file():
            errors.append(f"{directory}: SKILL.md missing")
            continue
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            errors.append(f"{path}: invalid front matter")
            continue
        try:
            metadata = yaml.safe_load(parts[1])
        except yaml.YAMLError as exc:
            errors.append(f"{path}: invalid YAML: {exc}")
            continue
        if not isinstance(metadata, dict) or set(metadata) != {"name", "description"}:
            errors.append(f"{path}: front matter must contain only name and description")
            continue
        if metadata["name"] != directory.name or metadata["name"] in names:
            errors.append(f"{path}: invalid or duplicate name")
        names.add(metadata["name"])
        if not isinstance(metadata["description"], str) or len(metadata["description"]) < 40:
            errors.append(f"{path}: description too short")
        match = re.search(r"^## Skill (\d+)(?::|\b)", text, re.MULTILINE)
        if not match:
            errors.append(f"{path}: Skill ID missing")
        else:
            ids.append(int(match.group(1)))
        for section in REQUIRED_SECTIONS:
            if section not in text:
                errors.append(f"{path}: missing {section}")
        agent_yaml = directory / "agents" / "openai.yaml"
        if not agent_yaml.is_file():
            errors.append(f"{directory}: agents/openai.yaml missing")
        else:
            try:
                agent = yaml.safe_load(agent_yaml.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{agent_yaml}: invalid YAML: {exc}")
                agent = None
            prompt = agent.get("interface", {}).get("default_prompt", "") if isinstance(agent, dict) else ""
            if f"${directory.name}" not in prompt:
                errors.append(f"{agent_yaml}: default_prompt must mention ${directory.name}")
    if sorted(ids) != list(range(spec["first"], spec["last"] + 1)):
        errors.append(f"Skill IDs must be contiguous {spec['first']}-{spec['last']}")

    schema_dir = ROOT / "schemas" / f"batch{batch}"
    template_dir = ROOT / "templates" / f"batch{batch}"
    for name in ("program", "evidence", "certification", "gate-result"):
        schema_path = schema_dir / f"{name}.schema.json"
        template_path = template_dir / f"{name}.json"
        try:
            schema = load_json(schema_path)
            jsonschema.validators.validator_for(schema).check_schema(schema)
            jsonschema.validate(load_json(template_path), schema)
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as exc:
            errors.append(f"{name}: {exc}")
    for required in (
        ROOT / "docs" / f"batch{batch}" / "AUTHORITY.md",
        ROOT / "docs" / f"batch{batch}" / "IMPLEMENTATION_CONTRACT.md",
        ROOT / "docs" / f"batch{batch}" / "QUALITY_GATES.md",
        ROOT / "docs" / f"batch{batch}" / "EVIDENCE_BOUNDARY.md",
    ):
        if not required.is_file():
            errors.append(f"{required}: missing")
    return errors


def scaffold(batch: int, key: str, owner: str, output_root: Path) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", key):
        raise ValueError("key must be 3-63 lowercase letters, digits, or hyphens")
    if not owner.strip():
        raise ValueError("owner is required")
    destination = output_root / f"batch{batch}" / key
    destination.mkdir(parents=True, exist_ok=False)
    source = ROOT / "templates" / f"batch{batch}"
    for template in source.glob("*.json"):
        payload = load_json(template)
        payload["batch"] = batch
        payload["packKey"] = key
        if "owner" in payload:
            payload["owner"] = owner
        (destination / template.name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    (destination / "evidence").mkdir()
    (destination / "holdout").mkdir()
    (destination / "representative").mkdir()
    return destination


def evaluate_gate(batch: int, pack: Path) -> tuple[bool, list[str], str]:
    spec = BATCHES[batch]
    program = load_json(pack / "program.json")
    certification = load_json(pack / "certification.json")
    evidence = load_json(pack / "evidence.json")
    failures: list[str] = []
    for name, payload in (("program", program), ("evidence", evidence), ("certification", certification)):
        try:
            schema = load_json(ROOT / "schemas" / f"batch{batch}" / f"{name}.schema.json")
            jsonschema.validate(payload, schema)
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError) as exc:
            failures.append(f"{name} schema validation failed: {exc}")
    pack_keys = {program.get("packKey"), evidence.get("packKey"), certification.get("packKey")}
    if len(pack_keys) != 1:
        failures.append("program, evidence, and certification packKey values differ")
    if certification.get("status") != "CERTIFIED":
        failures.append("certification status is not CERTIFIED")
    if not certification.get("evidenceRefs"):
        failures.append("certification evidenceRefs are empty")
    if certification.get("holdoutPassRate", 0) < 1.0:
        failures.append("holdoutPassRate below 1.0")
    if certification.get("representativePassRate", 0) < 1.0:
        failures.append("representativePassRate below 1.0")
    if certification.get("criticalFindings", 1) != 0:
        failures.append("criticalFindings must be zero")
    metrics = certification.get("metrics", {})
    for name, (operator, threshold) in spec["metrics"].items():
        value = metrics.get(name)
        if not isinstance(value, (int, float)):
            failures.append(f"metric {name} missing")
        elif operator == "min" and value < threshold:
            failures.append(f"metric {name} below {threshold}")
        elif operator == "max" and value > threshold:
            failures.append(f"metric {name} above {threshold}")
    claims = evidence.get("claims", [])
    if not claims:
        failures.append("evidence claims are empty")
    for claim in claims:
        claim_id = claim.get("claimId", "unknown")
        if claim.get("status") != "PASS":
            failures.append(f"claim {claim_id} is not PASS")
        if not claim.get("evidenceRefs"):
            failures.append(f"claim {claim_id} evidenceRefs are empty")
        if claim.get("externalOperationExecuted") and not claim.get("authorizationRefs"):
            failures.append(f"claim {claim_id} external operation lacks authorizationRefs")
    eligible = not failures
    status = "CERTIFIED" if eligible else "BLOCKED"
    return eligible, failures, status


def write_gate_result(batch: int, pack: Path, eligible: bool, failures: list[str], status: str) -> None:
    result = {
        "batch": batch,
        "packKey": load_json(pack / "program.json")["packKey"],
        "eligible": eligible,
        "status": status,
        "failures": failures,
        "evidenceRefs": [] if not eligible else load_json(pack / "certification.json")["evidenceRefs"],
        "externalOperationExecuted": False,
    }
    (pack / "gate-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Batch {batch} gate", "", f"Status: `{status}`", "", "## Failures", ""]
    lines.extend(f"- {failure}" for failure in failures)
    if not failures:
        lines.append("- None")
    (pack / "gate-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    scaffold_parser = sub.add_parser("scaffold")
    scaffold_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    scaffold_parser.add_argument("--key", required=True)
    scaffold_parser.add_argument("--owner", required=True)
    scaffold_parser.add_argument("--output-root", type=Path, default=ROOT / "mature-product-packs")
    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    gate_parser.add_argument("pack", type=Path)
    args = parser.parse_args()

    if args.command == "validate":
        errors = validate_batch(args.batch)
        for error in errors:
            print(f"ERROR: {error}")
        if errors:
            return 1
        print(f"OK: Batch {args.batch} Skill bundle")
        return 0
    if args.command == "scaffold":
        print(scaffold(args.batch, args.key, args.owner, args.output_root))
        return 0
    eligible, failures, status = evaluate_gate(args.batch, args.pack)
    write_gate_result(args.batch, args.pack, eligible, failures, status)
    for failure in failures:
        print(f"GATE FAIL: {failure}")
    print(f"status={status} eligible={str(eligible).lower()}")
    return 0 if eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
