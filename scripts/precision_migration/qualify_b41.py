#!/usr/bin/env python3
"""Execute all ten B41 handlers on valid and fail-closed local fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "b41-qualification" / "results.json"

from scripts.precision_migration.adapters import (
    AdapterRegistry,
    execute,
    resolve_handler,
)
from scripts.precision_migration.runtime import Registry, canonical_digest
from scripts.precision_migration.trust import TrustStore

TEST_TYPES = ("positive", "negative", "integration", "holdout", "representative")


def content_ref(path: Path, *, tampered: bool = False) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "uri": path.resolve().as_uri(),
        "digest": "sha256:" + ("0" * 64 if tampered else hashlib.sha256(content).hexdigest()),
        "size_bytes": len(content),
        "media_type": "application/json",
        "sensitivity": "internal",
        "version": "b41-fixture-v1",
    }


def request(skill: str, reference: dict[str, Any], role: str, key: Path | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"fixture_role": role}
    if skill.endswith("certificate-signing"):
        if key is None:
            raise ValueError("certificate signing fixture requires a key")
        parameters.update({
            "signing_backend": "local-openssl-ed25519",
            "signing_key_path": str(key),
            "key_id": "local-b41-qualification-key",
            "payload_asset_index": 0,
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
        })
    return {
        "request_id": f"b41-{skill}-{role}",
        "skill": skill,
        "mode": "validate",
        "inputs": {"assets": [reference], "parameters": parameters},
        "policy": {"unresolved_differences": "block", "allow_test_weakening": False, "require_provenance": True, "risk_level": "medium", "request_actor": "b41-local-executor"},
        "evidence": [],
        "semantic_losses": [],
        "approvals": [],
    }


def result(skill: str, test_type: str, observation: dict[str, Any]) -> dict[str, Any]:
    body = {"skill": skill, "test_type": test_type, "state": "PASS", "evidence": observation}
    return {**body, "result_digest": canonical_digest(body)}


def build() -> dict[str, Any]:
    registry = Registry.load()
    adapters = AdapterRegistry.load()
    entries = sorted(
        (entry for entry in adapters.payload["entries"] if entry.get("batch") == 41 and entry.get("kind") == "skill"),
        key=lambda item: item["skill"],
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="precision-b41-qualification-") as temporary:
        root = Path(temporary).resolve()
        private = root / "certificate-signer.private.pem"
        public = root / "certificate-signer.public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
        trust_path = root / "trust-store.json"
        trust_path.write_text(json.dumps({
            "schema_version": 1,
            "keys": [{
                "key_id": "local-b41-qualification-key",
                "roles": ["certificate-signer"],
                "public_key_path": public.name,
                "not_before": "2025-01-01T00:00:00Z",
                "not_after": "2030-01-01T00:00:00Z",
                "revoked": False,
            }],
            "revoked_record_ids": [],
        }, sort_keys=True), encoding="utf-8")
        trust = TrustStore.load(trust_path)
        references = {}
        for role in ("development", "holdout", "representative"):
            path = root / f"{role}.json"
            path.write_text(json.dumps({"fixture_role": role, "evidence": "bounded-local"}, sort_keys=True) + "\n", encoding="utf-8")
            references[role] = content_ref(path)
        for entry in entries:
            skill = entry["skill"]
            handler = resolve_handler(entry)
            if handler is None or not callable(handler):
                raise ValueError(f"B41 handler did not resolve: {skill}")
            results.append(result(skill, "integration", {"handler_id": entry["handler_id"], "entrypoint": entry["handler_entrypoint"]}))
            for role, test_type in (("development", "positive"), ("holdout", "holdout"), ("representative", "representative")):
                output = root / "outputs" / skill / role
                response = execute(
                    request(skill, references[role], role, private),
                    output,
                    evidence_roots=[root],
                    trust_store=trust,
                    adapter_registry=adapters,
                    skill_registry=registry,
                )
                if not response.get("artifacts") or response.get("execution_state") not in {"LOCAL_EXECUTED", "CONDITIONALLY_VERIFIED"}:
                    raise ValueError(f"B41 valid execution returned an unexpected state: {skill}/{role}")
                results.append(result(skill, test_type, {"execution_state": response["execution_state"], "exit_code": response["exit_code"], "bounded_local": True}))
            negative_output = root / "outputs" / skill / "negative"
            if skill.endswith("semantic-loss-report"):
                negative_request = request(skill, references["development"], "negative", private)
                negative_request["semantic_losses"] = [{"classification": "APPROXIMATE", "reason": "negative fixture"}]
                response = execute(negative_request, negative_output, evidence_roots=[root], trust_store=trust, adapter_registry=adapters, skill_registry=registry)
                report = json.loads((negative_output / "semantic-loss-report.json").read_text(encoding="utf-8"))
                rejected = response["exit_code"] == 0 and report["decision"] == "BLOCK"
            else:
                rejected = False
                try:
                    negative_response = execute(request(skill, content_ref(root / "development.json", tampered=True), "negative", private), negative_output, evidence_roots=[root], trust_store=trust, adapter_registry=adapters, skill_registry=registry)
                except (OSError, ValueError):
                    rejected = True
                else:
                    artifact_path = Path(negative_response["artifacts"][0]["uri"].removeprefix("file://"))
                    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                    unresolved = artifact.get("unresolved", artifact.get("obligations", []))
                    rejected = (
                        isinstance(unresolved, list) and bool(unresolved)
                    ) or artifact.get("decision") == "FAILED" or artifact.get("package_decision") == "FAILED"
            if not rejected:
                raise ValueError(f"B41 negative fixture was not rejected: {skill}")
            results.append(result(skill, "negative", {"fail_closed": True}))
    if len(entries) != 10 or len(results) != 50:
        raise ValueError("B41 qualification inventory mismatch")
    results.sort(key=lambda item: (item["skill"], TEST_TYPES.index(item["test_type"])))
    return {
        "schema_version": 1,
        "suite": "precision-migration-b41-bounded-local-v1",
        "skill_count": 10,
        "result_count": 50,
        "test_types": list(TEST_TYPES),
        "all_tests_passed": True,
        "execution_scope": "BOUNDED_LOCAL",
        "hsm_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("B41 qualification results drifted; regenerate them")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "skills": 10, "results": 50, "hsm": "NOT_RUN"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
