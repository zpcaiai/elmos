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
# Artifacts every batch must declare. CORE drives the fail-closed gate; CONTRACT
# carries the scope, ownership and candidate-selection contracts.
CORE_ARTIFACTS = ["program", "evidence", "certification", "gate-result"]
CONTRACT_ARTIFACTS = [
    "pack",
    "profile",
    "support-matrix",
    "candidates",
    # certification.json and evidence.json are closed objects. These three carry
    # what will not fit inside them: the full measured threshold set, the
    # zero-tolerance evaluations, and the human-readable claim statements.
    "metrics",
    "zero-tolerance",
    "claims",
]
SCORING_DIMENSIONS = ("customerDemand", "riskReduction", "reuse", "readiness", "margin")
EVIDENCE_ROLES = (
    "execution",
    "provenance",
    "verification",
    "customer",
    "independent-review",
    "authorization",
    "recovery",
    "financial-reconciliation",
)
PLACEHOLDER_OWNERS = {"", "REPLACE_ME", "TBD", "unknown"}
ZERO_DIGEST = "sha256:" + "0" * 64


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
    declared = {path.name[: -len(".schema.json")] for path in schema_dir.glob("*.schema.json")}
    for name in CORE_ARTIFACTS + CONTRACT_ARTIFACTS:
        if name not in declared:
            errors.append(f"{schema_dir}/{name}.schema.json: missing")
    for name in sorted(declared):
        schema_path = schema_dir / f"{name}.schema.json"
        template_path = template_dir / f"{name}.json"
        try:
            schema = load_json(schema_path)
            jsonschema.validators.validator_for(schema).check_schema(schema)
            jsonschema.validate(load_json(template_path), schema)
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as exc:
            errors.append(f"{name}: {exc}")
    for template_path in sorted(template_dir.glob("*.json")):
        if template_path.stem not in declared:
            errors.append(f"{template_path}: has no matching schema")
    try:
        support_matrix = load_json(template_dir / "support-matrix.json")
        declared_capabilities = {
            entry.get("capabilityId")
            for entry in support_matrix.get("capabilities", [])
            if isinstance(entry, dict)
        }
        if declared_capabilities != names:
            errors.append("support-matrix template does not cover exactly the batch Skills")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"support-matrix template: {exc}")
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
    example_prefix = f"example-{load_json(source / 'pack.json')['packType']}"
    for template in source.glob("*.json"):
        payload = load_json(template)
        payload["batch"] = batch
        payload["packKey"] = key
        identifier = payload.get("id")
        if isinstance(identifier, str) and identifier.startswith(example_prefix):
            payload["id"] = key + identifier[len(example_prefix):]
        if "owner" in payload:
            payload["owner"] = owner
        (destination / template.name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    (destination / "evidence").mkdir()
    (destination / "holdout").mkdir()
    (destination / "representative").mkdir()
    return destination


def relative_to_pack(pack: Path, path: Path) -> str:
    return path.resolve().relative_to(pack.resolve()).as_posix()


def file_reference(pack: Path, path: Path) -> dict:
    return {
        "path": relative_to_pack(pack, path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def single_corpus_file(pack: Path, kind: str) -> Path:
    directory = pack / kind
    files = sorted(item for item in directory.rglob("*") if item.is_file() and item.stat().st_size > 0)
    if len(files) != 1:
        raise ValueError(
            f"{kind}/ must hold exactly one non-empty corpus file, found {len(files)}"
        )
    return files[0]


def build_manifest(
    batch: int,
    pack: Path,
    *,
    artifact: Path,
    environment: Path,
    executor: str,
    verifier: str,
    authorization_refs: list[str],
    replay_command: str,
    started_at: str,
    finished_at: str,
    attest_verifier_independent: bool,
    attest_corpus_independence: bool,
) -> dict:
    """Derive the evidence manifest from what is actually on disk.

    Everything machine-derivable (paths, digests, byte counts, claim bindings)
    is computed here. The two facts a filesystem cannot establish — that the
    verifier is independent of the executor, and that the corpora were not
    available while authoring — must be attested explicitly by the caller.
    """
    if executor == verifier:
        raise ValueError("executor and verifier must be different identities")
    if not attest_verifier_independent:
        raise ValueError(
            "verifier independence must be attested with --attest-verifier-independent"
        )
    if not attest_corpus_independence:
        raise ValueError(
            "corpus authoring independence must be attested with --attest-corpus-independence"
        )
    if not authorization_refs:
        raise ValueError("at least one authorization reference is required")

    program = load_json(pack / "program.json")
    certification = load_json(pack / "certification.json")
    evidence_document = load_json(pack / "evidence.json")

    # Evidence layout is a convention, not a guess: evidence/<role>/<id>.<ext>.
    claims_by_reference: dict[str, list[str]] = {}
    for claim in evidence_document.get("claims", []):
        for reference in claim.get("evidenceRefs", []) + claim.get("provenanceRefs", []):
            claims_by_reference.setdefault(reference, []).append(claim.get("claimId"))

    roles = {role for role in EVIDENCE_ROLES}
    entries: list[dict] = []
    for path in sorted((pack / "evidence").rglob("*")):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        relative = Path(relative_to_pack(pack, path))
        if len(relative.parts) < 3 or relative.parts[1] not in roles:
            raise ValueError(
                f"{relative} must live under evidence/<role>/ with role in {sorted(roles)}"
            )
        identifier = relative.stem
        bound = sorted(set(claims_by_reference.get(identifier, [])))
        if not bound:
            raise ValueError(f"evidence {identifier} is not referenced by any claim")
        entries.append({**file_reference(pack, path), "id": identifier, "role": relative.parts[1], "claimIds": bound})

    corpora = []
    for kind in ("holdout", "representative"):
        corpora.append({**file_reference(pack, single_corpus_file(pack, kind)), "kind": kind, "authoringAccess": False})

    domain_gates = []
    if batch == 45:
        for lower in range(38, 45):
            source = sorted((pack / "domain-gates").glob(f"batch{lower}*.json"))
            if len(source) != 1:
                raise ValueError(f"domain-gates/ must hold exactly one Batch {lower} gate result")
            domain_gates.append({**file_reference(pack, source[0]), "batch": lower})

    approvals = sorted(set(certification.get("approvedBy", [])))
    if not approvals:
        raise ValueError("certification.approvedBy must name at least one accountable approver")
    if program.get("owner") not in approvals:
        raise ValueError("the program owner must appear in certification.approvedBy")

    manifest = {
        "manifestVersion": 1,
        "batch": batch,
        "packKey": program["packKey"],
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact": file_reference(pack, artifact),
        "environment": file_reference(pack, environment),
        "execution": {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "replayCommand": replay_command,
            "executorId": executor,
            "verifierId": verifier,
            "verifierIndependent": True,
            "authorizationRefs": sorted(set(authorization_refs)),
        },
        "evidence": entries,
        "corpora": corpora,
        "approvals": approvals,
        "domainGates": domain_gates,
    }
    validate_document(manifest, COMMON_SCHEMA_ROOT / "evidence-manifest.schema.json")
    return manifest


def build_certification_request(batch: int, pack: Path, key_id: str) -> dict:
    """Bind a certification request to the exact bytes it is asking to certify."""
    manifest = load_json(pack / "evidence-manifest.json")
    program = load_json(pack / "program.json")
    if manifest.get("execution", {}).get("executorId") == key_id:
        raise ValueError("the certification authority must differ from the executor")
    approvals = manifest.get("approvals", [])
    if program.get("owner") not in approvals:
        raise ValueError("the program owner must approve the certification request")
    request = {
        "requestVersion": 1,
        "batch": batch,
        "packKey": program["packKey"],
        "requestedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "keyId": key_id,
        "approvedBy": sorted(set(approvals)),
        "programDigest": sha256_file(pack / "program.json"),
        "evidenceDigest": sha256_file(pack / "evidence.json"),
        "certificationDigest": sha256_file(pack / "certification.json"),
        "evidenceManifestDigest": sha256_file(pack / "evidence-manifest.json"),
    }
    validate_document(request, COMMON_SCHEMA_ROOT / "certification-request.schema.json")
    return request


def score_candidates(batch: int, path: Path, write: bool) -> dict:
    """Rank pack candidates by the unweighted mean of the five scoring dimensions.

    Deterministic and evidence-neutral: scoring only orders work, it never
    grants a status. A candidate with no evidence reference is reported as
    unevidenced so it cannot be promoted on score alone.
    """
    payload = load_json(path)
    validate_document(payload, ROOT / "schemas" / f"batch{batch}" / "candidates.schema.json")
    rows = payload.get("candidates", [])
    for row in rows:
        values = [float(row.get(dimension, 0.0)) for dimension in SCORING_DIMENSIONS]
        row["score"] = round(sum(values) / len(SCORING_DIMENSIONS), 4)
        row["unevidenced"] = not row.get("evidenceRefs")
    rows.sort(key=lambda row: (-row.get("score", 0.0), row.get("id", "")))
    payload["candidates"] = rows
    validate_document(payload, ROOT / "schemas" / f"batch{batch}" / "candidates.schema.json")
    if write:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def collect_gaps(batch: int, pack: Path) -> dict:
    """Enumerate every unmet obligation for a pack without granting any status.

    The fail-closed gate stops at the first structural problem, which makes it a
    poor inventory. This walks the whole contract surface instead so the output
    can be used as a work list.
    """
    template_dir = ROOT / "templates" / f"batch{batch}"
    schema_dir = ROOT / "schemas" / f"batch{batch}"
    expected = sorted(path.name[: -len(".schema.json")] for path in schema_dir.glob("*.schema.json"))
    skills = sorted(path.name for path in (ROOT / ".agents" / "skills").glob(f"b{batch}-*") if path.is_dir())
    gaps: list[dict] = []

    def add(category: str, severity: str, detail: str) -> None:
        gaps.append({"category": category, "severity": severity, "detail": detail})

    documents: dict[str, dict] = {}
    for name in expected:
        path = pack / f"{name}.json"
        if not path.is_file():
            add("artifact", "blocking", f"{name}.json is missing from the pack")
            continue
        try:
            payload = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            add("artifact", "blocking", f"{name}.json is unreadable: {exc}")
            continue
        documents[name] = payload
        try:
            validate_document(payload, schema_dir / f"{name}.schema.json")
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as exc:
            add("artifact", "blocking", f"{name}.json fails its schema: {exc}")

    for name in ("evidence-manifest.json", "certification-request.json", "certification-request.sig"):
        if not (pack / name).is_file():
            add("evidence", "blocking", f"{name} has not been produced")

    for name, payload in documents.items():
        owner = payload.get("owner")
        if owner is not None and str(owner).strip() in PLACEHOLDER_OWNERS:
            add("ownership", "blocking", f"{name}.json still carries a placeholder owner")

    pack_doc = documents.get("pack", {})
    for field in ("artifactDigest", "environmentDigest"):
        if pack_doc.get(field, ZERO_DIGEST) == ZERO_DIGEST:
            add("provenance", "blocking", f"pack.json {field} is still the zero digest")
    template_pack = load_json(template_dir / "pack.json")
    missing_batches = sorted(set(template_pack.get("requiredBatches", [])) - set(pack_doc.get("requiredBatches", [])))
    if missing_batches:
        add("scope", "blocking", f"pack.json does not bind required batches {missing_batches}")

    matrix = documents.get("support-matrix", {})
    covered = {
        entry.get("capabilityId"): entry
        for entry in matrix.get("capabilities", [])
        if isinstance(entry, dict)
    }
    for skill in skills:
        entry = covered.get(skill)
        if entry is None:
            add("coverage", "blocking", f"support matrix does not cover {skill}")
        elif entry.get("status") in (None, "research", "experimental", "blocked"):
            add("coverage", "open", f"{skill} is only {entry.get('status')} in the support matrix")
        elif not entry.get("evidenceRefs"):
            add("coverage", "blocking", f"{skill} claims {entry.get('status')} with no evidence reference")

    profile = documents.get("profile", {})
    template_profile = load_json(template_dir / "profile.json")
    thresholds = profile.get("metricThresholds", template_profile["metricThresholds"])
    certification = documents.get("certification", {})

    # certification.json is a closed object carrying only the gate-enforced
    # numbers, so the declared threshold set is tracked in metrics.json where a
    # never-measured metric is distinguishable from one that measured zero.
    recorded = {
        entry.get("name"): entry
        for entry in documents.get("metrics", {}).get("metrics", [])
        if isinstance(entry, dict)
    }
    for metric, threshold in sorted(thresholds.items()):
        entry = recorded.get(metric)
        if entry is None:
            add("metric", "blocking", f"{metric} is absent from metrics.json (threshold {threshold})")
            continue
        if not entry.get("measured") or entry.get("value") is None:
            add("metric", "blocking", f"{metric} has not been measured (threshold {threshold})")
            continue
        if not entry.get("evidenceRefs"):
            add("metric", "blocking", f"{metric} reports {entry.get('value')} with no evidence reference")
        value, comparator = entry.get("value"), entry.get("comparator", "min")
        if comparator == "min" and value < threshold:
            add("metric", "open", f"{metric} is {value}, below the required {threshold}")
        elif comparator == "max" and value > threshold:
            add("metric", "open", f"{metric} is {value}, above the permitted {threshold}")

    evaluated = {
        entry.get("name"): entry
        for entry in documents.get("zero-tolerance", {}).get("flags", [])
        if isinstance(entry, dict)
    }
    for flag in profile.get("zeroTolerance", template_profile["zeroTolerance"]):
        entry = evaluated.get(flag)
        if entry is None or not entry.get("evaluated") or entry.get("observed") is None:
            add("zero-tolerance", "blocking", f"{flag} has not been evaluated")
        elif entry.get("observed") != 0:
            add("zero-tolerance", "blocking", f"{flag} observed {entry.get('observed')}, must be zero")
        elif not entry.get("evidenceRefs"):
            add("zero-tolerance", "blocking", f"{flag} reports zero with no evidence reference")

    for corpus in ("holdout", "representative"):
        directory = pack / corpus
        populated = [item for item in directory.rglob("*") if item.is_file() and item.stat().st_size > 0] if directory.is_dir() else []
        if not populated:
            add("corpus", "blocking", f"{corpus} corpus is empty")
    evidence_dir = pack / "evidence"
    if not evidence_dir.is_dir() or not any(item.is_file() for item in evidence_dir.rglob("*")):
        add("evidence", "blocking", "evidence directory holds no artefacts")

    if not certification.get("approvedBy"):
        add("approval", "blocking", "no accountable approver is recorded on the certification")
    if certification.get("status") != "CERTIFIED":
        add("status", "open", f"certification status is {certification.get('status')}")

    claims = documents.get("evidence", {}).get("claims", [])
    narratives = {
        entry.get("claimId"): entry
        for entry in documents.get("claims", {}).get("claims", [])
        if isinstance(entry, dict)
    }
    if not claims:
        add("evidence", "blocking", "evidence.json declares no claims")
    for claim in claims:
        claim_id = claim.get("claimId")
        if claim.get("status") != "PASS":
            add("evidence", "open", f"claim {claim_id} is {claim.get('status')}")
        if claim.get("externalOperationExecuted") and not claim.get("authorizationRefs"):
            add("authorization", "blocking", f"claim {claim_id} performed an external operation without authorization")
        # A passing claim with no stated limitations reads as universal. Almost
        # none are: say what the run did not cover.
        if claim.get("status") == "PASS":
            narrative = narratives.get(claim_id)
            if narrative is None:
                add("claim-scope", "blocking", f"claim {claim_id} passes with no statement in claims.json")
            elif not narrative.get("limitations"):
                add("claim-scope", "blocking", f"claim {claim_id} passes with no stated limitations")
    for claim_id in sorted(set(narratives) - {claim.get("claimId") for claim in claims}):
        add("claim-scope", "open", f"claims.json describes {claim_id}, which evidence.json does not declare")

    if batch == 45:
        for lower in range(38, 45):
            certified = list((ROOT / "mature-product-packs" / f"batch{lower}").glob("*/gate-result.json"))
            passing = []
            for path in certified:
                try:
                    result = load_json(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if result.get("status") == "CERTIFIED" and result.get("eligible") is True:
                    passing.append(path)
            if not passing:
                add("aggregate", "blocking", f"Batch {lower} has no certified domain gate to aggregate")

    blocking = sum(1 for gap in gaps if gap["severity"] == "blocking")
    return {
        "batch": batch,
        "packKey": documents.get("program", {}).get("packKey", pack.name),
        "generatedBy": "scripts/mature_product_toolkit.py gaps",
        "expectedArtifacts": expected,
        "skillCount": len(skills),
        "blockingCount": blocking,
        "openCount": len(gaps) - blocking,
        "certifiable": False if gaps else None,
        "gaps": gaps,
    }


def write_gap_report(pack: Path, inventory: dict) -> None:
    (pack / "gap-inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Batch {inventory['batch']} gap inventory",
        "",
        f"- Pack: `{inventory['packKey']}`",
        f"- Skills in scope: {inventory['skillCount']}",
        f"- Blocking gaps: {inventory['blockingCount']}",
        f"- Open gaps: {inventory['openCount']}",
        "",
        "This inventory is a work list. It grants no status and is not evidence.",
        "",
    ]
    for severity in ("blocking", "open"):
        selected = [gap for gap in inventory["gaps"] if gap["severity"] == severity]
        if not selected:
            continue
        lines.extend([f"## {severity.title()}", ""])
        for gap in selected:
            lines.append(f"- [{gap['category']}] {gap['detail']}")
        lines.append("")
    (pack / "gap-report.md").write_text("\n".join(lines), encoding="utf-8")


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
    score_parser = sub.add_parser("score")
    score_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    score_parser.add_argument("candidates", type=Path)
    score_parser.add_argument("--write", action="store_true")
    gaps_parser = sub.add_parser("gaps")
    gaps_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    gaps_parser.add_argument("pack", type=Path)
    gaps_parser.add_argument(
        "--allow-blocking", action="store_true",
        help="refresh the inventory without failing; for scheduled refreshes, never for a release decision",
    )
    manifest_parser = sub.add_parser("manifest")
    manifest_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    manifest_parser.add_argument("pack", type=Path)
    manifest_parser.add_argument("--artifact", type=Path, required=True)
    manifest_parser.add_argument("--environment", type=Path, required=True)
    manifest_parser.add_argument("--executor", required=True)
    manifest_parser.add_argument("--verifier", required=True)
    manifest_parser.add_argument("--authorization", action="append", default=[])
    manifest_parser.add_argument("--replay-command", required=True)
    manifest_parser.add_argument("--started-at", required=True)
    manifest_parser.add_argument("--finished-at", required=True)
    manifest_parser.add_argument("--attest-verifier-independent", action="store_true")
    manifest_parser.add_argument("--attest-corpus-independence", action="store_true")
    request_parser = sub.add_parser("request")
    request_parser.add_argument("--batch", type=int, choices=BATCHES, required=True)
    request_parser.add_argument("pack", type=Path)
    request_parser.add_argument("--key-id", required=True)
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
    if args.command == "score":
        payload = score_candidates(args.batch, args.candidates, args.write)
        print(json.dumps(payload["candidates"], indent=2, ensure_ascii=False))
        return 0
    if args.command == "manifest":
        try:
            manifest = build_manifest(
                args.batch,
                args.pack,
                artifact=args.artifact,
                environment=args.environment,
                executor=args.executor,
                verifier=args.verifier,
                authorization_refs=args.authorization,
                replay_command=args.replay_command,
                started_at=args.started_at,
                finished_at=args.finished_at,
                attest_verifier_independent=args.attest_verifier_independent,
                attest_corpus_independence=args.attest_corpus_independence,
            )
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError) as exc:
            print(f"ERROR: {exc}")
            return 2
        (args.pack / "evidence-manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.pack / 'evidence-manifest.json'}")
        return 0
    if args.command == "request":
        try:
            request = build_certification_request(args.batch, args.pack, args.key_id)
        except (OSError, ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError) as exc:
            print(f"ERROR: {exc}")
            return 2
        request_path = args.pack / "certification-request.json"
        request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {request_path}")
        print("sign it with the offline certification key, then place the detached signature next to it:")
        print(f"  openssl dgst -sha256 -sign <private-key.pem> -out {args.pack / 'certification-request.sig'} {request_path}")
        return 0
    if args.command == "gaps":
        inventory = collect_gaps(args.batch, args.pack)
        write_gap_report(args.pack, inventory)
        for gap in inventory["gaps"]:
            print(f"GAP [{gap['severity']}/{gap['category']}] {gap['detail']}")
        print(f"blocking={inventory['blockingCount']} open={inventory['openCount']}")
        if args.allow_blocking:
            return 0
        return 1 if inventory["blockingCount"] else 0
    eligible, failures, status = evaluate_gate(args.batch, args.pack, args.trust_store)
    write_gate_result(args.batch, args.pack, eligible, failures, status)
    for failure in failures:
        print(f"GATE FAIL: {failure}")
    print(f"status={status} eligible={str(eligible).lower()}")
    return 0 if eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
