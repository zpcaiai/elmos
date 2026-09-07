from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

try:
    import jsonschema  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised by the dependency-free suite
    jsonschema = None

from elmos_software_factory.canonical import MAX_JSON_BYTES, canonical_digest
from elmos_software_factory import cli as cli_module
from elmos_software_factory.cli import main
from elmos_software_factory.evidence_intake import (
    evaluate_external_preflight,
    ingest_external_receipt,
)


def sha256(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def role(principal: str, organization: str) -> dict[str, str]:
    return {"principal_id": principal, "organization_id": organization}


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = ROOT / "engines" / "software-factory-engine" / "schemas"


def preflight() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scope": {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "campaign_id": "campaign-a",
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
        },
        "release_digest": sha256("release"),
        "provider_adapter": {
            "provider_id": "provider-a",
            "adapter_id": "adapter-a",
            "adapter_registry_digest": sha256("adapter-registry"),
            "executable_digest": sha256("adapter-executable"),
            "effect_class": "REVERSIBLE",
            "rollback_adapter_id": "rollback-a",
            "authorization_digest": sha256("provider-authorization"),
        },
        "independent_holdout": {
            "manifest_digest": sha256("holdout-corpus"),
            "case_count": 2,
            "owner": role("owner-a", "org-owner"),
            "executor": role("executor-a", "org-executor"),
            "verifier": role("verifier-a", "org-verifier"),
            "authorization_digest": sha256("holdout-authorization"),
        },
        "representative_workload": {
            "manifest_digest": sha256("representative-corpus"),
            "case_count": 1,
            "customer_authorizer": role("customer-a", "org-customer"),
            "authorization_digest": sha256("representative-authorization"),
        },
        "production_change": {
            "environment": "production-equivalent-a",
            "pkcs11_secret_reference": "pkcs11:token=external;object=release;type=private",
            "canary_plan_digest": sha256("canary-plan"),
            "rollback_plan_digest": sha256("rollback-plan"),
            "authorization_digest": sha256("production-authorization"),
        },
    }


class EvidenceIntakeHardeningTests(unittest.TestCase):
    @staticmethod
    def receipt(raw: bytes) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema_version": "1.0",
            "receipt_id": "receipt-a",
            "evidence_kind": "provider-contract",
            "scope": {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "campaign_id": "campaign-a",
                "policy_revision": "policy-v1",
                "source_revision": "source-v1",
            },
            "target_artifact_digest": sha256("target"),
            "environment_digest": sha256("environment"),
            "corpus_digest": sha256("corpus"),
            "authorization_digest": sha256("authorization"),
            "replay_digest": sha256("replay"),
            "raw_evidence": {
                "path": "raw/evidence.bin",
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "media_type": "application/octet-stream",
            },
            "author": role("author-a", "org-author"),
            "executor": role("executor-a", "org-executor"),
            "verifier": role("verifier-a", "org-verifier"),
            "execution_state": "PASSED",
            "signature_state": "UNVERIFIED_CALLER_ASSERTION",
        }
        return {**body, "receipt_digest": canonical_digest(body)}

    @staticmethod
    def policy(receipt_digest: str, revoked: str) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "policy_id": "policy-a",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "allowed_evidence_kinds": ["provider-contract"],
            "allowed_receipt_digests": [receipt_digest],
            "allowed_organizations": ["org-author", "org-executor", "org-verifier"],
            "revoked_principals": [revoked],
            "require_distinct_organizations": True,
            "trust_root_state": "NOT_CONFIGURED",
        }

    def test_revoked_author_executor_and_verifier_are_each_rejected(self) -> None:
        raw = b"external evidence\n"
        expected = {
            "author-a": "AUTHOR_REVOKED",
            "executor-a": "EXECUTOR_REVOKED",
            "verifier-a": "VERIFIER_REVOKED",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "raw/evidence.bin").write_bytes(raw)
            receipt = self.receipt(raw)
            receipt_digest = str(receipt["receipt_digest"])
            for principal, failure in expected.items():
                with self.subTest(principal=principal):
                    decision = ingest_external_receipt(
                        receipt,
                        evidence_root=root,
                        policy=self.policy(receipt_digest, principal),
                    )
                    self.assertEqual("EXTERNAL_RECEIPT_QUARANTINED", decision["status"])
                    self.assertIn(failure, decision["failures"])
                    self.assertEqual("NOT_RUN", decision["external_states"]["real_provider_execution"])

    def test_preflight_digest_binds_full_input_and_every_critical_digest_group(self) -> None:
        document = preflight()
        baseline = evaluate_external_preflight(document)
        reordered = {key: document[key] for key in reversed(tuple(document))}
        self.assertEqual(
            baseline["preflight_digest"],
            evaluate_external_preflight(reordered)["preflight_digest"],
        )
        self.assertEqual(canonical_digest(document), baseline["canonical_input_digest"])
        self.assertEqual(document["release_digest"], baseline["digest_bindings"]["release_digest"])
        self.assertFalse(baseline["external_operations_executed"])
        self.assertEqual("NOT_RUN", baseline["external_states"]["production_canary"])

        mutations: tuple[tuple[str, ...], ...] = (
            ("release_digest",),
            ("provider_adapter", "authorization_digest"),
            ("provider_adapter", "adapter_registry_digest"),
            ("provider_adapter", "executable_digest"),
            ("independent_holdout", "manifest_digest"),
            ("representative_workload", "manifest_digest"),
            ("production_change", "canary_plan_digest"),
            ("production_change", "rollback_plan_digest"),
            ("production_change", "authorization_digest"),
        )
        for index, path in enumerate(mutations):
            changed = copy.deepcopy(document)
            target: dict[str, Any] = changed
            for segment in path[:-1]:
                target = target[segment]
            target[path[-1]] = sha256(f"changed-{index}")
            with self.subTest(path=path):
                observed = evaluate_external_preflight(changed)
                self.assertNotEqual(baseline["preflight_digest"], observed["preflight_digest"])

        misleading = {
            "scope_and_release_bound",
            "digest_pinned_reversible_adapter",
            "holdout_roles_distinct",
            "holdout_organizations_distinct",
            "opaque_hsm_secret_reference",
            "canary_and_rollback_plans_bound",
        }
        self.assertTrue(misleading.isdisjoint(baseline["checks"]))
        self.assertFalse(baseline["checks"]["external_signatures_verified"])

        self_reversing = copy.deepcopy(document)
        self_reversing["provider_adapter"]["rollback_adapter_id"] = "adapter-a"
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            evaluate_external_preflight(self_reversing)

    @unittest.skipIf(jsonschema is None, "jsonschema is needed for schema parity checks")
    def test_intake_and_preflight_schemas_match_runtime_nested_contracts(self) -> None:
        raw = b"schema-bound evidence\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "raw/evidence.bin").write_bytes(raw)
            receipt = self.receipt(raw)
            policy = self.policy(str(receipt["receipt_digest"]), "revoked-unused")
            decision = ingest_external_receipt(receipt, evidence_root=root, policy=policy)

        values = {
            "external-evidence-receipt.schema.json": receipt,
            "evidence-intake-policy.schema.json": policy,
            "evidence-intake-decision.schema.json": decision,
            "external-preflight.schema.json": preflight(),
        }
        for schema_name, value in values.items():
            with self.subTest(schema=schema_name):
                schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
                jsonschema.Draft202012Validator(schema).validate(value)

        invalid = copy.deepcopy(preflight())
        invalid["provider_adapter"]["unexpected"] = "value"
        schema = json.loads((SCHEMA_ROOT / "external-preflight.schema.json").read_text(encoding="utf-8"))
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(invalid)
        with self.assertRaises(ValueError):
            evaluate_external_preflight(invalid)


class CliHardeningTests(unittest.TestCase):
    @staticmethod
    def invoke(arguments: list[str]) -> tuple[int, dict[str, Any]]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(arguments)
        payload = json.loads(output.getvalue())
        if not isinstance(payload, dict):
            raise AssertionError("CLI output must be an object")
        return exit_code, payload

    def test_loader_rejects_symlink_fifo_oversize_and_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            linked = root / "linked.json"
            linked.symlink_to(target)
            fifo = root / "request.fifo"
            os.mkfifo(fifo)
            oversized = root / "oversized.json"
            with oversized.open("wb") as stream:
                stream.truncate(MAX_JSON_BYTES + 1)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"key": 1, "key": 2}', encoding="utf-8")

            for path, message in (
                (linked, "opened safely"),
                (fifo, "regular file"),
                (oversized, "exceeds"),
                (duplicate, "duplicate key"),
            ):
                with self.subTest(path=path.name):
                    code, result = self.invoke(["digest", "--request", str(path)])
                    self.assertEqual(2, code)
                    self.assertEqual("FAILED", result["status"])
                    self.assertIn(message, result["error"]["message"])

    def test_loader_fails_closed_without_required_safe_open_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            request.write_text("{}", encoding="utf-8")
            for flag in ("O_NOFOLLOW", "O_NONBLOCK"):
                with self.subTest(flag=flag), patch.object(cli_module.os, flag, 0):
                    code, result = self.invoke(["digest", "--request", str(request)])
                    self.assertEqual(2, code)
                    self.assertEqual("REQUEST_INVALID", result["error"]["code"])
                    self.assertIn(flag, result["error"]["message"])

    def test_every_new_subcommand_has_a_direct_fail_closed_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            archive = root / "archive"
            archive.mkdir()
            linked_archive = root / "archive-link"
            linked_archive.symlink_to(archive, target_is_directory=True)
            cases = (
                ["archive-inspect", "--source-root", str(linked_archive)],
                [
                    "campaign-run",
                    "--manifest",
                    str(invalid),
                    "--evidence-root",
                    str(root),
                ],
                [
                    "campaign-replay",
                    "--manifest",
                    str(invalid),
                    "--receipt",
                    str(invalid),
                    "--evidence-root",
                    str(root),
                ],
                [
                    "evidence-ingest",
                    "--receipt",
                    str(invalid),
                    "--policy",
                    str(invalid),
                    "--evidence-root",
                    str(root),
                ],
                ["external-preflight", "--config", str(invalid)],
            )
            for arguments in cases:
                with self.subTest(command=arguments[0]):
                    code, result = self.invoke(arguments)
                    self.assertEqual(2, code)
                    self.assertEqual("REQUEST_INVALID", result["error"]["code"])

    def test_external_preflight_cli_never_returns_execution_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "preflight.json"
            config.write_text(json.dumps(preflight()), encoding="utf-8")
            code, result = self.invoke(["external-preflight", "--config", str(config)])
        self.assertEqual(3, code)
        self.assertFalse(result["external_operations_executed"])
        self.assertEqual("NOT_RUN", result["external_states"]["production_writes"])
        self.assertEqual("NOT_CERTIFIED", result["external_states"]["external_certification"])


if __name__ == "__main__":
    unittest.main()
