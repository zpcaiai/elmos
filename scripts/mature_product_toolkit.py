#!/usr/bin/env python3
"""Deterministic scaffolding and fail-closed gates for Batches 38-45.

Batches 35, 36, and 37 use their richer dedicated validators and gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
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
COMMON_SCHEMA_ROOT = ROOT / "schemas" / "mature-product"
MAX_EVIDENCE_AGE = timedelta(days=30)


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_document(payload: dict, schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    validator.validate(payload)


def parse_timestamp(value: object, label: str, failures: list[str]) -> datetime | None:
    if not isinstance(value, str):
        failures.append(f"{label} timestamp missing")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"{label} timestamp is invalid")
        return None
    if parsed.tzinfo is None:
        failures.append(f"{label} timestamp must include a timezone")
        return None
    return parsed.astimezone(timezone.utc)


def validate_file_ref(pack: Path, ref: object, label: str, failures: list[str]) -> Path | None:
    if not isinstance(ref, dict):
        failures.append(f"{label} file reference is invalid")
        return None
    raw_path = ref.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        failures.append(f"{label} path is missing")
        return None
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        failures.append(f"{label} path must stay inside the pack")
        return None
    target = (pack / relative).resolve()
    try:
        target.relative_to(pack.resolve())
    except ValueError:
        failures.append(f"{label} path escapes the pack")
        return None
    if not target.is_file():
        failures.append(f"{label} file is missing: {raw_path}")
        return None
    if target.stat().st_size != ref.get("bytes"):
        failures.append(f"{label} byte count does not match: {raw_path}")
    if sha256_file(target) != ref.get("sha256"):
        failures.append(f"{label} digest does not match: {raw_path}")
    return target


def validate_signature(
    batch: int,
    pack: Path,
    trust_store_path: Path | None,
    program: dict,
    manifest: dict,
    failures: list[str],
) -> None:
    request_path = pack / "certification-request.json"
    signature_path = pack / "certification-request.sig"
    if trust_store_path is None:
        failures.append("external trust store is required")
        return
    try:
        request = load_json(request_path)
        trust_store = load_json(trust_store_path)
        validate_document(
            request, COMMON_SCHEMA_ROOT / "certification-request.schema.json"
        )
        validate_document(trust_store, COMMON_SCHEMA_ROOT / "trust-store.schema.json")
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as exc:
        failures.append(f"certification request or trust store is invalid: {exc}")
        return
    if not signature_path.is_file() or signature_path.stat().st_size == 0:
        failures.append("certification request signature is missing")
        return
    if request.get("batch") != batch or request.get("packKey") != program.get("packKey"):
        failures.append("certification request scope does not match the pack")
    expected_digests = {
        "programDigest": sha256_file(pack / "program.json"),
        "evidenceDigest": sha256_file(pack / "evidence.json"),
        "certificationDigest": sha256_file(pack / "certification.json"),
        "evidenceManifestDigest": sha256_file(pack / "evidence-manifest.json"),
    }
    for field, expected in expected_digests.items():
        if request.get(field) != expected:
            failures.append(f"certification request {field} does not match")
    requested_at = parse_timestamp(request.get("requestedAt"), "certification request", failures)
    now = datetime.now(timezone.utc)
    if requested_at and (requested_at > now + timedelta(minutes=5) or now - requested_at > MAX_EVIDENCE_AGE):
        failures.append("certification request is stale or future-dated")
    approved_by = request.get("approvedBy", [])
    if not set(approved_by).issubset(set(manifest.get("approvals", []))):
        failures.append("certification request approvals are not bound to the evidence manifest")
    if program.get("owner") not in approved_by:
        failures.append("program owner must approve the certification request")
    if request.get("keyId") == manifest.get("execution", {}).get("executorId"):
        failures.append("certification authority must differ from the executor")
    keys = [item for item in trust_store.get("keys", []) if item.get("keyId") == request.get("keyId")]
    if len(keys) != 1:
        failures.append("certification key is missing or ambiguous in the trust store")
        return
    key = keys[0]
    if key.get("revoked"):
        failures.append("certification key is revoked")
    if batch not in key.get("authorizedBatches", []):
        failures.append("certification key is not authorized for this Batch")
    raw_public_key = key.get("publicKeyPath")
    public_key = (trust_store_path.parent / raw_public_key).resolve() if isinstance(raw_public_key, str) else Path()
    try:
        public_key.relative_to(trust_store_path.parent.resolve())
    except ValueError:
        failures.append("public key path escapes the trust store")
        return
    if not public_key.is_file():
        failures.append("trusted public key is missing")
        return
    try:
        completed = subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-verify",
                str(public_key),
                "-signature",
                str(signature_path),
                str(request_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        failures.append(f"certification signature verifier is unavailable: {exc}")
        return
    if completed.returncode != 0:
        failures.append("certification request signature verification failed")


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
    for name in (
        "evidence-manifest.schema.json",
        "certification-request.schema.json",
        "trust-store.schema.json",
    ):
        try:
            jsonschema.Draft202012Validator.check_schema(load_json(COMMON_SCHEMA_ROOT / name))
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.SchemaError) as exc:
            errors.append(f"common schema {name}: {exc}")
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


def evaluate_gate(
    batch: int, pack: Path, trust_store_path: Path | None
) -> tuple[bool, list[str], str]:
    spec = BATCHES[batch]
    failures: list[str] = []
    try:
        program = load_json(pack / "program.json")
        certification = load_json(pack / "certification.json")
        evidence = load_json(pack / "evidence.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, [f"required pack document is invalid: {exc}"], "BLOCKED"
    for name, payload in (("program", program), ("evidence", evidence), ("certification", certification)):
        try:
            validate_document(
                payload, ROOT / "schemas" / f"batch{batch}" / f"{name}.schema.json"
            )
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
    manifest_path = pack / "evidence-manifest.json"
    try:
        manifest = load_json(manifest_path)
        validate_document(
            manifest, COMMON_SCHEMA_ROOT / "evidence-manifest.schema.json"
        )
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as exc:
        failures.append(f"evidence manifest is invalid: {exc}")
        manifest = {}
    if manifest:
        if manifest.get("batch") != batch or manifest.get("packKey") != program.get("packKey"):
            failures.append("evidence manifest scope does not match the pack")
        generated_at = parse_timestamp(manifest.get("generatedAt"), "evidence manifest", failures)
        execution = manifest.get("execution", {})
        started_at = parse_timestamp(execution.get("startedAt"), "execution start", failures)
        finished_at = parse_timestamp(execution.get("finishedAt"), "execution finish", failures)
        now = datetime.now(timezone.utc)
        if generated_at and (generated_at > now + timedelta(minutes=5) or now - generated_at > MAX_EVIDENCE_AGE):
            failures.append("evidence manifest is stale or future-dated")
        if started_at and finished_at and finished_at < started_at:
            failures.append("execution finish precedes start")
        if finished_at and generated_at and finished_at > generated_at:
            failures.append("evidence manifest predates execution completion")
        if execution.get("executorId") == execution.get("verifierId"):
            failures.append("executor and independent verifier must differ")
        validate_file_ref(pack, manifest.get("artifact"), "artifact", failures)
        validate_file_ref(pack, manifest.get("environment"), "environment", failures)
        if manifest.get("artifact", {}).get("sha256") == manifest.get("environment", {}).get("sha256"):
            failures.append("artifact and environment digests must differ")
        evidence_entries = manifest.get("evidence", [])
        evidence_ids = [item.get("id") for item in evidence_entries if isinstance(item, dict)]
        evidence_paths = [item.get("path") for item in evidence_entries if isinstance(item, dict)]
        evidence_digests = [item.get("sha256") for item in evidence_entries if isinstance(item, dict)]
        if len(evidence_ids) != len(set(evidence_ids)):
            failures.append("evidence IDs must be unique")
        if len(evidence_paths) != len(set(evidence_paths)) or len(evidence_digests) != len(set(evidence_digests)):
            failures.append("evidence paths and digests must be distinct")
        evidence_by_id = {item.get("id"): item for item in evidence_entries if isinstance(item, dict)}
        claim_ids = {claim.get("claimId") for claim in claims if isinstance(claim, dict)}
        for entry in evidence_entries:
            if isinstance(entry, dict) and not set(entry.get("claimIds", [])).issubset(claim_ids):
                failures.append(f"evidence {entry.get('id')} binds an unknown claim")
        roles = {item.get("role") for item in evidence_entries if isinstance(item, dict)}
        for role in ("execution", "provenance", "verification"):
            if role not in roles:
                failures.append(f"required evidence role missing: {role}")
        for index, entry in enumerate(evidence_entries):
            validate_file_ref(pack, entry, f"evidence[{index}]", failures)
        corpus_entries = manifest.get("corpora", [])
        corpus_kinds = [item.get("kind") for item in corpus_entries if isinstance(item, dict)]
        if sorted(corpus_kinds) != ["holdout", "representative"]:
            failures.append("exactly one holdout and one representative corpus are required")
        corpus_digests = [item.get("sha256") for item in corpus_entries if isinstance(item, dict)]
        if len(corpus_digests) != len(set(corpus_digests)):
            failures.append("holdout and representative corpus digests must differ")
        for index, entry in enumerate(corpus_entries):
            validate_file_ref(pack, entry, f"corpora[{index}]", failures)
        for claim in claims:
            claim_id = claim.get("claimId", "unknown")
            for ref_id in claim.get("evidenceRefs", []):
                entry = evidence_by_id.get(ref_id)
                if entry is None:
                    failures.append(f"claim {claim_id} evidence ref is not in the manifest: {ref_id}")
                elif claim_id not in entry.get("claimIds", []):
                    failures.append(f"claim {claim_id} is not bound by evidence ref {ref_id}")
            for ref_id in claim.get("provenanceRefs", []):
                entry = evidence_by_id.get(ref_id)
                if entry is None or entry.get("role") != "provenance":
                    failures.append(f"claim {claim_id} provenance ref is invalid: {ref_id}")
        if set(certification.get("evidenceRefs", [])) != set(evidence_ids):
            failures.append("certification evidenceRefs must exactly match the evidence manifest")
        domain_gates = manifest.get("domainGates", [])
        if batch == 45:
            customer_entries = [item for item in evidence_entries if item.get("role") == "customer"]
            independent_entries = [item for item in evidence_entries if item.get("role") == "independent-review"]
            if len(customer_entries) < 2:
                failures.append("Batch 45 requires at least two customer evidence records")
            if not independent_entries:
                failures.append("Batch 45 requires independent review evidence")
            domain_batches = [item.get("batch") for item in domain_gates if isinstance(item, dict)]
            if sorted(domain_batches) != list(range(38, 45)):
                failures.append("Batch 45 requires exact certified domain gates for Batches 38-44")
            for index, entry in enumerate(domain_gates):
                target = validate_file_ref(pack, entry, f"domainGates[{index}]", failures)
                if target:
                    try:
                        gate = load_json(target)
                        validate_document(
                            gate,
                            ROOT / "schemas" / f"batch{entry.get('batch')}" / "gate-result.schema.json",
                        )
                    except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as exc:
                        failures.append(f"domain gate is invalid: {exc}")
                    else:
                        if gate.get("batch") != entry.get("batch") or gate.get("status") != "CERTIFIED" or gate.get("eligible") is not True:
                            failures.append(f"Batch {entry.get('batch')} domain gate is not certified")
        elif domain_gates:
            failures.append("domainGates are only accepted by the Batch 45 aggregate gate")
        validate_signature(
            batch,
            pack,
            trust_store_path,
            program,
            manifest,
            failures,
        )
    eligible = not failures
    status = "CERTIFIED" if eligible else "BLOCKED"
    return eligible, failures, status


def write_gate_result(batch: int, pack: Path, eligible: bool, failures: list[str], status: str) -> None:
    try:
        pack_key = load_json(pack / "program.json").get("packKey", pack.name)
    except (OSError, ValueError, json.JSONDecodeError):
        pack_key = pack.name
    result = {
        "batch": batch,
        "packKey": pack_key,
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
    gate_parser.add_argument("--trust-store", type=Path)
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
    eligible, failures, status = evaluate_gate(args.batch, args.pack, args.trust_store)
    write_gate_result(args.batch, args.pack, eligible, failures, status)
    for failure in failures:
        print(f"GATE FAIL: {failure}")
    print(f"status={status} eligible={str(eligible).lower()}")
    return 0 if eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
