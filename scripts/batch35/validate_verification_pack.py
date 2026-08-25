#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from _common import load, local_ref_path

try:
    import jsonschema
except ImportError as exc:
    jsonschema = None
    JSONSCHEMA_IMPORT_ERROR = str(exc)
else:
    JSONSCHEMA_IMPORT_ERROR = None
VALIDATION_EXCEPTIONS = (OSError, TypeError, ValueError)
if jsonschema is not None:
    VALIDATION_EXCEPTIONS += (
        jsonschema.exceptions.SchemaError,
        jsonschema.exceptions.ValidationError,
    )
PAIRS = [
    ("pack.json", "verification-pack.schema.json"),
    ("support-matrix.json", "verification-support-matrix.schema.json"),
    ("validation-profile.json", "validation-profile.schema.json"),
    ("oracle-registry.json", "oracle-registry.schema.json"),
    ("properties/sample.json", "property-spec.schema.json"),
    ("metamorphic/sample.json", "metamorphic-relation.schema.json"),
    ("mutation/campaign.json", "mutation-campaign.schema.json"),
    ("fuzz/campaign.json", "fuzz-campaign.schema.json"),
    ("models/model.json", "model-spec.schema.json"),
    ("solver/proof.json", "solver-proof.schema.json"),
    ("counterexamples/sample.json", "counterexample.schema.json"),
    ("assurance/assurance-case.json", "assurance-case.schema.json"),
    ("certification/certification.json", "verification-certification.schema.json"),
]

CONTENT_BOUND_CONTRACTS = {
    "pack.json",
    "support-matrix.json",
    "validation-profile.json",
    "oracle-registry.json",
    "properties/sample.json",
    "metamorphic/sample.json",
    "mutation/campaign.json",
    "fuzz/campaign.json",
    "models/model.json",
    "solver/proof.json",
    "counterexamples/sample.json",
    "assurance/assurance-case.json",
    "certification/evidence.json",
    "certification/certification.json",
    "corpus/development/manifest.json",
    "corpus/negative/manifest.json",
    "corpus/holdout/manifest.json",
    "corpus/representative-workloads/manifest.json",
}


def declared_evidence_refs(pack):
    refs = set()
    for rel in (
        "certification/evidence.json",
        "certification/certification.json",
        "solver/proof.json",
    ):
        path = local_ref_path(pack, rel)
        if path is not None:
            document = load(path)
            refs.update(document.get("evidence_refs", []))
            if rel == "certification/evidence.json":
                refs.update(document.get("repository_binding_records", []))
            if rel == "solver/proof.json":
                for field in ("model_ref", "certificate_ref", "concrete_replay_ref"):
                    if isinstance(document.get(field), str):
                        refs.add(document[field])
    assurance = local_ref_path(pack, "assurance/assurance-case.json")
    if assurance is not None:
        assurance_document = load(assurance)
        refs.update(assurance_document.get("evidence", []))
        for claim in assurance_document.get("claims", []):
            refs.update(claim.get("evidence_refs", []))
    support = local_ref_path(pack, "support-matrix.json")
    if support is not None:
        for capability in load(support).get("capabilities", []):
            refs.update(capability.get("evidence_refs", []))
    oracle_registry = local_ref_path(pack, "oracle-registry.json")
    if oracle_registry is not None:
        for oracle in load(oracle_registry).get("oracles", []):
            refs.update(oracle.get("evidence_refs", []))
    for key in ("development", "negative", "holdout", "representative-workloads"):
        manifest = local_ref_path(pack, f"corpus/{key}/manifest.json")
        if manifest is None:
            continue
        corpus_document = load(manifest)
        refs.update(corpus_document.get("evidence_refs", []))
        if key == "representative-workloads" and isinstance(
            corpus_document.get("authorization_ref"), str
        ):
            refs.add(corpus_document["authorization_ref"])
    counterexample = local_ref_path(pack, "counterexamples/sample.json")
    if counterexample is not None:
        counterexample_document = load(counterexample)
        for field in ("input_ref", "trace_ref", "schedule_ref"):
            if isinstance(counterexample_document.get(field), str):
                refs.add(counterexample_document[field])
    fuzz_campaign = local_ref_path(pack, "fuzz/campaign.json")
    if fuzz_campaign is not None:
        fuzz_document = load(fuzz_campaign)
        for field in ("seed_corpus", "dictionary_refs"):
            values = fuzz_document.get(field, [])
            if isinstance(values, list):
                refs.update(value for value in values if isinstance(value, str))
    return refs


def validate_local_evidence_consistency(pack, pack_manifest, evidence, errors):
    metrics = evidence.get("metrics", {})
    binding_records = evidence.get("repository_binding_records", [])
    if binding_records and not isinstance(binding_records, list):
        errors.append("repository_binding_records must be an array")
        binding_records = []
    for ref in binding_records:
        path = local_ref_path(pack, ref)
        if path is None:
            errors.append(f"repository binding record path is unsafe or missing: {ref}")
            continue
        try:
            record = load(path)
        except (OSError, ValueError) as e:
            errors.append(f"repository binding record invalid: {ref}: {e}")
            continue
        tests = record.get("tests")
        passed = record.get("passed")
        failed = record.get("failed")
        exact_integer_totals = all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (tests, passed, failed)
        )
        if (
            not exact_integer_totals
            or tests < 1
            or passed != tests
            or failed != 0
            or record.get("status") != "passed"
        ):
            errors.append(
                f"repository binding test totals are not an exact pass: {ref}"
            )
            continue
        if (
            metrics.get("local_tests") is not None
            and metrics.get("local_tests") != tests
        ):
            errors.append(f"local_tests metric does not match binding record: {ref}")
        if metrics.get("local_test_pass_rate") is not None and metrics.get(
            "local_test_pass_rate"
        ) != (passed / tests):
            errors.append(f"local_test_pass_rate does not match binding record: {ref}")
        scope = pack_manifest.get("scope", {})
        required_bindings = {
            "source": ("source_digest", "source_artifact_digest"),
            "test": ("test_digest", "target_artifact_digest"),
            "environment": ("environment_digest", "environment_digest"),
        }
        digest_pattern = re.compile(r"^sha256:[0-9a-f]{64}$")
        repository_bindings = record.get("repository_bindings")
        if not isinstance(repository_bindings, list):
            errors.append(f"repository_bindings must be an array: {ref}")
            repository_bindings = []
        bindings_by_role = {}
        for binding in repository_bindings:
            if not isinstance(binding, dict):
                continue
            role = binding.get("role")
            if role in bindings_by_role:
                errors.append(f"duplicate repository binding role {role}: {ref}")
                continue
            if role in required_bindings:
                bindings_by_role[role] = binding
        for role, (record_field, scope_field) in required_bindings.items():
            value = record.get(record_field)
            if not isinstance(value, str) or not digest_pattern.fullmatch(value):
                errors.append(
                    f"{record_field} must be an exact SHA-256 digest: {ref}"
                )
                continue
            if value != scope.get(scope_field):
                errors.append(f"{record_field} does not match pack scope: {ref}")
            binding = bindings_by_role.get(role)
            if binding is None:
                errors.append(f"repository binding role {role} is missing: {ref}")
            elif binding.get("sha256") != value:
                errors.append(
                    f"{record_field} does not match the {role} repository binding: {ref}"
                )
    certification_path = local_ref_path(pack, "certification/certification.json")
    if certification_path is not None:
        try:
            certification = load(certification_path)
        except (OSError, ValueError) as exc:
            errors.append(f"certification document is invalid: {exc}")
            return
        if certification.get("exact_scope") != pack_manifest.get("scope"):
            errors.append("certification exact_scope does not match pack scope")
        certification_metrics = certification.get("metrics", {})
        for key in metrics.keys() & certification_metrics.keys():
            if metrics[key] != certification_metrics[key]:
                errors.append(f"conflicting evidence and certification metric: {key}")
        evidence_counts = evidence.get("zero_tolerance", {})
        certification_counts = certification.get("zero_tolerance", {})
        for key in evidence_counts.keys() & certification_counts.keys():
            if evidence_counts[key] != certification_counts[key]:
                errors.append(f"conflicting evidence and certification count: {key}")


def validate_pack_identity_consistency(pack, pack_manifest, errors):
    pack_key = pack_manifest.get("pack_key")
    scope = pack_manifest.get("scope", {})
    documents = {}
    for rel in (
        "certification/evidence.json",
        "certification/certification.json",
        "oracle-registry.json",
        "validation-profile.json",
        "properties/sample.json",
        "metamorphic/sample.json",
        "counterexamples/sample.json",
        "assurance/assurance-case.json",
    ):
        path = local_ref_path(pack, rel)
        if path is None:
            continue
        try:
            documents[rel] = load(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{rel} is invalid: {exc}")
    for rel in (
        "certification/evidence.json",
        "certification/certification.json",
        "oracle-registry.json",
    ):
        if documents.get(rel, {}).get("pack_key") != pack_key:
            errors.append(f"{rel} pack_key does not match pack")
    profile = documents.get("validation-profile.json", {})
    if profile.get("risk_tier") != scope.get("risk_tier"):
        errors.append("validation profile risk_tier does not match pack scope")
    claim_ids = {
        claim.get("claim_id")
        for claim in profile.get("claims", [])
        if isinstance(claim, dict)
    }
    for rel in (
        "properties/sample.json",
        "metamorphic/sample.json",
        "counterexamples/sample.json",
    ):
        claim_id = documents.get(rel, {}).get("claim_id")
        if claim_id not in claim_ids:
            errors.append(f"{rel} claim_id is not declared by the validation profile")
    assurance_claim_ids = {
        claim.get("claim_id")
        for claim in documents.get("assurance/assurance-case.json", {}).get(
            "claims", []
        )
        if isinstance(claim, dict)
    }
    if not assurance_claim_ids.issubset(claim_ids):
        errors.append("assurance claim IDs are not declared by the validation profile")
    oracle_ids = {
        oracle.get("oracle_id")
        for oracle in documents.get("oracle-registry.json", {}).get("oracles", [])
        if isinstance(oracle, dict)
    }
    for claim in profile.get("claims", []):
        if not isinstance(claim, dict):
            continue
        missing = set(claim.get("required_oracles", [])) - oracle_ids
        if missing:
            errors.append(
                f"claim {claim.get('claim_id')} references unknown required oracles: {sorted(missing)}"
            )


def validate_local_fuzz_inputs(pack, errors):
    campaign_path = local_ref_path(pack, "fuzz/campaign.json")
    if campaign_path is None:
        return
    try:
        campaign = load(campaign_path)
    except (OSError, ValueError) as exc:
        errors.append(f"fuzz campaign is invalid: {exc}")
        return
    for field in ("seed_corpus", "dictionary_refs"):
        values = campaign.get(field, [])
        if not isinstance(values, list):
            errors.append(f"fuzz {field} must be an array")
            continue
        for ref in values:
            if (
                not isinstance(ref, str)
                or ref.startswith(("http://", "https://"))
                or local_ref_path(pack, ref) is None
            ):
                errors.append(
                    f"fuzz {field} ref must be a safe pack-local file: {ref!r}"
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()
    pack = args.pack
    repository_root = (
        args.repository_root
        if args.repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    schemas = Path(__file__).resolve().parents[2] / "schemas/batch35"
    errors = []
    if jsonschema is None:
        errors.append(
            "jsonschema dependency is required for fail-closed validation: "
            f"{JSONSCHEMA_IMPORT_ERROR}"
        )
    for rel, schema in PAIRS:
        document_path = local_ref_path(pack, rel)
        if document_path is None:
            errors.append(f"missing or unsafe {rel}")
            continue
        try:
            data = load(document_path)
            if jsonschema is not None:
                jsonschema.validate(data, load(schemas / schema))
        except VALIDATION_EXCEPTIONS as e:
            errors.append(f"{rel}: {e}")
    oracle_registry_path = local_ref_path(pack, "oracle-registry.json")
    if (
        oracle_registry_path is not None
        and subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("validate_oracle_registry.py")),
                str(oracle_registry_path),
            ],
            check=False,
        ).returncode
    ):
        errors.append("oracle registry validation failed")
    model_path = local_ref_path(pack, "models/model.json")
    if (
        model_path is not None
        and subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("validate_model_spec.py")),
                str(model_path),
            ],
            check=False,
        ).returncode
    ):
        errors.append("model spec validation failed")
    pack_path = local_ref_path(pack, "pack.json")
    try:
        p = load(pack_path) if pack_path is not None else {}
    except (OSError, ValueError) as exc:
        errors.append(f"pack document is invalid: {exc}")
        p = {}
    for key in ("owner", "maintenance_owner"):
        if p.get(key) in (None, "", "TODO"):
            errors.append(f"pack {key} is not assigned")
    for key, val in p.get("scope", {}).items():
        if isinstance(val, str) and "TODO" in val:
            errors.append(f"scope {key} is placeholder")
    certification_status = None
    certification_path = local_ref_path(pack, "certification/certification.json")
    if certification_path is not None:
        try:
            certification_status = load(certification_path).get("status")
        except (OSError, ValueError) as exc:
            errors.append(f"certification document is invalid: {exc}")
    if p.get("status") == "certified" or certification_status == "certified":
        validate_pack_identity_consistency(pack, p, errors)
        validate_local_fuzz_inputs(pack, errors)
    evidence_path = local_ref_path(pack, "certification/evidence.json")
    if evidence_path is not None:
        try:
            evidence = load(evidence_path)
        except (OSError, ValueError) as exc:
            errors.append(f"certification evidence document is invalid: {exc}")
            evidence = {}
        validate_local_evidence_consistency(pack, p, evidence, errors)
        integrity_ref = evidence.get("integrity_manifest")
        if integrity_ref:
            integrity_path = local_ref_path(pack, integrity_ref)
            if integrity_path is None:
                errors.append("evidence integrity manifest path is unsafe or missing")
                integrity_path = None
            verifier = (
                Path(__file__).resolve().parents[1] / "verify_evidence_manifest.py"
            )
            binding_records = [
                str(path)
                for ref in evidence.get("repository_binding_records", [])
                if (path := local_ref_path(pack, ref)) is not None
            ]
            command = [
                sys.executable,
                str(verifier),
                str(pack),
                str(integrity_path) if integrity_path is not None else "",
            ]
            if integrity_path is not None and binding_records:
                command.extend(
                    ["--repository-root", str(repository_root)]
                )
                for record in binding_records:
                    command.extend(["--binding-record", record])
            if integrity_path is None:
                pass
            elif subprocess.run(command, check=False).returncode:
                errors.append("evidence integrity validation failed")
            else:
                bound = {
                    entry.get("path")
                    for entry in load(integrity_path).get("entries", [])
                    if isinstance(entry, dict)
                }
                try:
                    declared_refs = declared_evidence_refs(pack)
                except (OSError, TypeError, ValueError) as exc:
                    errors.append(f"declared evidence references are invalid: {exc}")
                    declared_refs = set()
                for ref in declared_refs | CONTENT_BOUND_CONTRACTS:
                    if ref not in bound:
                        errors.append(
                            f"evidence or verification contract is not content-bound: {ref}"
                        )
    if errors:
        print("\n".join("ERROR: " + x for x in errors), file=sys.stderr)
        return 1
    print(f"OK: verification pack {p.get('pack_key')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
