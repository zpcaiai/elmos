from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch32"
sys.path.insert(0, str(SCRIPTS))
import validate_frontend_formal_route_campaign_v2 as validator  # noqa: E402

sys.path.insert(0, str(ROOT / "tooling"))
import generate_frontend_formal_verification_pack as generator  # noqa: E402
import run_frontend_formal_toolchains as runtime_runner  # noqa: E402


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def runtime_pretty_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write(path: Path, value: object, *, canonical: bool = False) -> None:
    content = (
        canonical_bytes(value)
        if canonical
        else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    )
    path.write_bytes(content)


def frozen_v2_pack_available(default: Path, environment_name: str) -> bool:
    configured = os.environ.get(environment_name)
    candidate = Path(configured).resolve() if configured else default
    campaign_path = (
        candidate / "formal-campaign/frontend-formal-route-campaign-v2.json"
    )
    try:
        campaign = load(campaign_path)
        profiles = campaign["profiles"]
        driver = profiles[0]["runtime_driver_contract"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False
    return (
        isinstance(driver, dict)
        and driver.get("observer_protocol")
        == "block-specific-runtime-observation-v1"
        and driver.get("native_required_not_run_blocks") == ["api-network"]
        and driver.get("native_route_without_real_device_channel_status")
        == "NOT_RUN"
    )


class FrontendFormalRouteCampaignV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("ELMOS_FRONTEND_V2_CLIENT_PACK")
        cls.pack = (
            Path(configured).resolve()
            if configured
            else ROOT / "client-packs/frontend-72-route-equivalence-v2"
        )

    def test_exact_contract_constants_and_applicability(self) -> None:
        self.assertEqual(12, len(validator.BLOCK_IDS))
        self.assertEqual(72, len(validator.exact_routes()))
        self.assertEqual(300, validator.SELF_CONTAINED_REPLAY_TIMEOUT_SECONDS)
        self.assertEqual(
            runtime_runner.BLOCK_OBSERVER_SPECS,
            generator.BLOCK_OBSERVER_SPECS_V2,
        )
        self.assertEqual(
            runtime_runner.BLOCK_OBSERVER_SPECS,
            validator.BLOCK_OBSERVER_SPECS,
        )
        self.assertEqual(
            runtime_runner.INTERACTION_BLOCK_ACTUAL_KEYS,
            generator.RUNTIME_ACTUAL_KEYS_V2,
        )
        self.assertEqual(
            runtime_runner.INTERACTION_BLOCK_ACTUAL_KEYS,
            validator.RUNTIME_ACTUAL_KEYS,
        )
        self.assertEqual(
            runtime_runner.RUNTIME_CHANNEL_RECORD_KEYS,
            validator.TOOLCHAIN_CHANNEL_KEYS,
        )
        self.assertIn("harmony_sdk_root", validator.TOOLCHAIN_POLICY_KEYS)
        self.assertEqual(
            {"SELF_REPORTED_REDUCER_JSON", "RUNTIME_OBSERVED"},
            runtime_runner.FORBIDDEN_RUNTIME_ACTUAL_SOURCES,
        )
        self.assertEqual(
            ("browser", "android", "ios"),
            validator.REQUIRED_RUNTIME_CHANNELS["flutter"],
        )
        self.assertEqual(
            frozenset(generator.V2_IMPLEMENTATION_PATHS),
            validator.REQUIRED_IMPLEMENTATION_REPOSITORY_PATHS,
        )
        self.assertEqual(
            frozenset(generator.V2_REPLAY_PATHS),
            validator.REQUIRED_REPLAY_REPOSITORY_PATHS,
        )
        self.assertEqual(
            (
                runtime_runner.LOCKED_INTERACTION_ENGINE_NODE_TYPES_TREE_FILE_COUNT,
                runtime_runner.LOCKED_INTERACTION_ENGINE_NODE_TYPES_TREE_SHA256,
            ),
            (
                generator.LOCKED_V2_NODE_TYPES_TREE_FILE_COUNT,
                generator.LOCKED_V2_NODE_TYPES_TREE_SHA256,
            ),
        )
        self.assertEqual(
            (
                generator.LOCKED_V2_NODE_TYPES_TREE_FILE_COUNT,
                generator.LOCKED_V2_NODE_TYPES_TREE_SHA256,
            ),
            (
                validator.LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_FILE_COUNT,
                validator.LOCKED_ENGINE_VERIFIER_NODE_TYPES_TREE_SHA256,
            ),
        )

    def test_dimension_closure_schema_reference_is_resolvable(self) -> None:
        if validator.jsonschema is None:
            self.skipTest("jsonschema is unavailable")
        schema = load(
            ROOT / "schemas/batch32/frontend-formal-route-evidence-v2.schema.json"
        )
        probe = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
            "$ref": "#/$defs/dimensionClosure",
        }
        validator.jsonschema.Draft202012Validator(probe).validate(
            {
                "applicable": False,
                "comparison_count": 0,
                "pass_count": 0,
                "status": "NOT_APPLICABLE",
            }
        )
        external_schema_names = (
            "frontend-formal-external-corpus-manifest-v2.schema.json",
            "frontend-formal-external-evidence-v2.schema.json",
            "frontend-formal-external-replay-verifier-result-v2.schema.json",
            "frontend-formal-external-route-block-execution-v2.schema.json",
            "frontend-formal-external-route-block-replay-v2.schema.json",
            "frontend-formal-external-runtime-observation-v2.schema.json",
            "frontend-formal-external-trust-root-v2.schema.json",
            "frontend-formal-external-trust-store-v2.schema.json",
        )
        for name in external_schema_names:
            with self.subTest(schema=name):
                batch32_schema = load(ROOT / "schemas/batch32" / name)
                batch35_schema = load(ROOT / "schemas/batch35" / name)
                validator.jsonschema.Draft202012Validator.check_schema(batch32_schema)
                validator.jsonschema.Draft202012Validator.check_schema(batch35_schema)
                batch32_schema["$id"] = batch35_schema["$id"]
                self.assertEqual(batch32_schema, batch35_schema)
        self.assertEqual(
            "NOT_APPLICABLE",
            validator.aggregate_status([], applicable=False),
        )
        self.assertEqual(
            "MODEL_ONLY_NOT_RUNTIME",
            validator.max_runtime_influence(
                validator.EXPECTED_MODEL_INFLUENCE[
                    "route-navigation-deeplink-404"
                ],
                validator.expected_runtime_influence(
                    "route-navigation-deeplink-404"
                ),
            ),
        )

    def test_external_evidence_defaults_and_pack_self_root_fail_closed(self) -> None:
        declaration, capture = generator.external_evidence_not_run_v2()
        self.assertEqual({}, capture["results"])
        for field in (
            "independent_status",
            "holdout_status",
            "representative_status",
            "customer_status",
        ):
            self.assertEqual("NOT_RUN", declaration[field])

        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-self-root-negative-"
        ) as directory:
            pack = Path(directory) / "pack"
            pack.mkdir()
            four_organizations = (
                "org-approver",
                "org-executor",
                "org-verifier",
                "org-customer",
            )
            role_keys = (
                "key-approver",
                "key-executor",
                "key-verifier",
                "key-customer",
            )
            openssl = shutil.which("openssl")
            if openssl is None:
                self.skipTest("openssl is required for the Ed25519 forgery fixture")
            private_keys: dict[str, Path] = {}
            public_keys: dict[str, str] = {}
            for key_id in ("root-key", *role_keys):
                private_path = pack / f"{key_id}.private.pem"
                public_path = pack / f"{key_id}.public.pem"
                subprocess.run(
                    [
                        openssl,
                        "genpkey",
                        "-algorithm",
                        "ED25519",
                        "-out",
                        str(private_path),
                    ],
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    [
                        openssl,
                        "pkey",
                        "-in",
                        str(private_path),
                        "-pubout",
                        "-out",
                        str(public_path),
                    ],
                    capture_output=True,
                    check=True,
                )
                private_keys[key_id] = private_path
                public_keys[key_id] = public_path.read_text(encoding="utf-8")

            verifier_path = pack / "attacker-replay-verifier"
            verifier_bytes = (
                b"#!/bin/sh\n"
                b"if [ \"$1\" = \"--version\" ]; then "
                b"printf 'attacker-v1\\n'; exit 0; fi\n"
                b"exit 1\n"
            )
            verifier_path.write_bytes(verifier_bytes)
            verifier_path.chmod(0o755)
            organization_keys = tuple(
                zip(
                    four_organizations,
                    role_keys,
                    ("AUTHORIZATION", "EXECUTOR", "VERIFIER", "CUSTOMER"),
                )
            )
            root = {
                "schema_version": 2,
                "kind": "frontend-formal-external-trust-root-v2",
                "root_id": "attacker-self-root",
                "policy_id": "frontend-independent-evidence-policy-v2",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2030-01-01T00:00:00Z",
                "revoked": False,
                "trust_store_signing_keys": [
                    {
                        "key_id": "root-key",
                        "public_key_pem": public_keys["root-key"],
                        "valid_from": "2026-01-01T00:00:00Z",
                        "valid_until": "2030-01-01T00:00:00Z",
                        "revoked": False,
                    }
                ],
                "organization_key_allowlist": [
                    {
                        "organization_id": organization,
                        "key_id": key_id,
                        "role": role,
                        "public_key_sha256": digest(
                            public_keys[key_id].encode("utf-8")
                        ),
                    }
                    for organization, key_id, role in organization_keys
                ],
                "revocations": {
                    "key_ids": [],
                    "organization_ids": [],
                    "updated_at": "2026-01-01T00:00:00Z",
                },
                "replay_verifier": {
                    "verifier_id": "attacker-verifier",
                    "path": str(verifier_path.absolute()),
                    "realpath": str(verifier_path.resolve(strict=True)),
                    "sha256": digest(verifier_bytes),
                    "bytes": len(verifier_bytes),
                    "version": "attacker-v1",
                },
            }
            root_path = pack / "attacker-self-root.json"
            write(root_path, root)
            trust = {
                "schema_version": 2,
                "kind": "frontend-formal-external-trust-store-v2",
                "trust_store_id": "attacker-self-signed-store",
                "root_id": "attacker-self-root",
                "issued_at": "2026-06-01T00:00:00Z",
                "expires_at": "2028-01-01T00:00:00Z",
                "keys": [
                    {
                        "key_id": key_id,
                        "organization_id": organization,
                        "roles": [role],
                        "public_key_pem": public_keys[key_id],
                        "valid_from": "2026-01-01T00:00:00Z",
                        "valid_until": "2030-01-01T00:00:00Z",
                        "revoked": False,
                    }
                    for organization, key_id, role in organization_keys
                ],
                "revocations": {
                    "key_ids": [],
                    "organization_ids": [],
                    "updated_at": "2026-06-01T00:00:00Z",
                },
            }
            unsigned_trust = canonical_bytes(trust)
            payload_path = pack / "trust-store-payload.bin"
            signature_path = pack / "trust-store-signature.bin"
            payload_path.write_bytes(unsigned_trust)
            node = shutil.which("node")
            self.assertIsNotNone(node, "Node is required for the Ed25519 forgery fixture")
            completed = subprocess.run(
                [
                    str(node),
                    "-e",
                    (
                        "const fs=require('node:fs');"
                        "const crypto=require('node:crypto');"
                        "const [key,input,output]=process.argv.slice(1);"
                        "fs.writeFileSync(output,crypto.sign(null,"
                        "fs.readFileSync(input),fs.readFileSync(key)));"
                    ),
                    str(private_keys["root-key"]),
                    str(payload_path),
                    str(signature_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            trust["root_authorization"] = {
                "root_key_id": "root-key",
                "algorithm": "ed25519",
                "signed_payload_sha256": digest(unsigned_trust),
                "signature_base64": base64.b64encode(
                    signature_path.read_bytes()
                ).decode("ascii"),
            }
            three_key_root = json.loads(json.dumps(root))
            three_key_root["organization_key_allowlist"] = three_key_root[
                "organization_key_allowlist"
            ][:-1]
            three_key_trust = json.loads(json.dumps(trust))
            three_key_trust["keys"] = three_key_trust["keys"][:-1]
            with self.assertRaisesRegex(RuntimeError, "ALLOWLIST_MISSING"):
                generator._validate_external_trust_chain_v2(
                    trust_root=three_key_root,
                    trust=three_key_trust,
                    now=generator.datetime(2026, 8, 10, tzinfo=generator.UTC),
                )
            valid_self_chain = generator._validate_external_trust_chain_v2(
                trust_root=root,
                trust=trust,
                now=generator.datetime(2026, 8, 10, tzinfo=generator.UTC),
            )
            self.assertEqual("attacker-self-root", valid_self_chain["root_id"])
            invalid_trust = json.loads(json.dumps(trust))
            invalid_signature = bytearray(
                base64.b64decode(
                    invalid_trust["root_authorization"]["signature_base64"],
                    validate=True,
                )
            )
            invalid_signature[0] ^= 1
            invalid_trust["root_authorization"]["signature_base64"] = (
                base64.b64encode(invalid_signature).decode("ascii")
            )
            with self.assertRaisesRegex(
                RuntimeError, "V2_EXTERNAL_SIGNATURE_INVALID"
            ):
                generator._validate_external_trust_chain_v2(
                    trust_root=root,
                    trust=invalid_trust,
                    now=generator.datetime(2026, 8, 10, tzinfo=generator.UTC),
                )
            validator_errors: list[str] = []
            self.assertTrue(
                validator.verify_external_ed25519(
                    public_key_pem=public_keys["root-key"],
                    signature_base64=trust["root_authorization"]["signature_base64"],
                    payload=unsigned_trust,
                    label="test root authorization",
                    errors=validator_errors,
                ),
                validator_errors,
            )
            self.assertFalse(
                validator.verify_external_ed25519(
                    public_key_pem=public_keys["root-key"],
                    signature_base64=invalid_trust["root_authorization"][
                        "signature_base64"
                    ],
                    payload=unsigned_trust,
                    label="test invalid root authorization",
                    errors=validator_errors,
                )
            )
            self.assertIn(
                "test invalid root authorization signature is invalid",
                validator_errors,
            )
            errors: list[str] = []
            result = validator.validate_external_trust_chain_v2(
                pack=pack,
                trust_root_path=root_path,
                trust=trust,
                declaration={
                    "trust_root_id": "attacker-self-root",
                    "organization_ids": list(four_organizations),
                },
                replay_files={},
                errors=errors,
            )
            self.assertIsNone(result)
            self.assertTrue(
                any("trust root must remain outside the pack" in item for item in errors),
                errors,
            )

            evidence_path = pack / "attacker-intake.json"
            trust_path = pack / "attacker-trust-store.json"
            write(evidence_path, {})
            write(trust_path, trust)
            with self.assertRaisesRegex(
                RuntimeError, "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED"
            ):
                generator.add_external_evidence_v2(
                    pack_root=pack,
                    catalog=generator.ArtifactCatalog(pack),
                    evidence_path=evidence_path,
                    trust_store_path=trust_path,
                    trust_root_path=root_path,
                    scope_digest="sha256:" + "1" * 64,
                )
            with self.assertRaisesRegex(
                RuntimeError,
                "V2_EXTERNAL_EVIDENCE_TRUST_STORE_AND_EXTERNAL_ROOT_REQUIRED",
            ):
                generator.add_external_evidence_v2(
                    pack_root=pack,
                    catalog=generator.ArtifactCatalog(pack),
                    evidence_path=evidence_path,
                    trust_store_path=None,
                    trust_root_path=None,
                    scope_digest="sha256:" + "1" * 64,
                )

    def test_mixed_route_dimensions_do_not_cross_contaminate_browser(self) -> None:
        def block(browser_cross_status: str) -> dict[str, Any]:
            return {
                "runtime": {
                    "source": {"channels": {"browser": {"status": "PASSED"}}},
                    "target": {
                        "channels": {
                            "browser": {"status": "PASSED"},
                            "android": {"status": "NOT_RUN"},
                            "ios": {"status": "NOT_RUN"},
                        }
                    },
                    "cross_channel_equivalence": {
                        "dimension_closure": {
                            "browser": {
                                "applicable": True,
                                "status": browser_cross_status,
                            },
                            "native": {
                                "applicable": False,
                                "status": "NOT_APPLICABLE",
                            },
                            "runtime": {
                                "applicable": True,
                                "status": "NOT_RUN",
                            },
                        }
                    },
                }
            }

        mixed = generator.aggregate_route_runtime_dimensions_v2(
            blocks=[block("PASSED")],
            source_profile_id="react",
            target_profile_id="flutter",
        )
        self.assertEqual("PASSED", mixed["browser_status"])
        self.assertEqual("NOT_RUN", mixed["native_status"])
        self.assertEqual("NOT_RUN", mixed["runtime_status"])
        browser_gap = generator.aggregate_route_runtime_dimensions_v2(
            blocks=[block("NOT_RUN")],
            source_profile_id="react",
            target_profile_id="flutter",
        )
        self.assertEqual("NOT_RUN", browser_gap["browser_status"])

        native_pair_block = {
            "runtime": {
                endpoint: {
                    "channels": {
                        "browser": {"status": "PASSED"},
                        "android": {"status": "PASSED"},
                        "ios": {"status": "PASSED"},
                    }
                }
                for endpoint in ("source", "target")
            }
        }
        native_pair_block["runtime"]["cross_channel_equivalence"] = {
            "dimension_closure": {
                "browser": {"applicable": True, "status": "PASSED"},
                "native": {"applicable": True, "status": "PASSED"},
                "runtime": {"applicable": True, "status": "NOT_RUN"},
            }
        }
        native_pair = generator.aggregate_route_runtime_dimensions_v2(
            blocks=[native_pair_block],
            source_profile_id="flutter",
            target_profile_id="react-native",
        )
        self.assertEqual("PASSED", native_pair["browser_status"])
        self.assertEqual("PASSED", native_pair["native_status"])
        self.assertEqual("NOT_RUN", native_pair["runtime_status"])
        native_pair_block["runtime"]["cross_channel_equivalence"][
            "dimension_closure"
        ]["native"]["status"] = "NOT_RUN"
        native_gap = generator.aggregate_route_runtime_dimensions_v2(
            blocks=[native_pair_block],
            source_profile_id="flutter",
            target_profile_id="react-native",
        )
        self.assertEqual("PASSED", native_gap["browser_status"])
        self.assertEqual("NOT_RUN", native_gap["native_status"])

    def test_dynamic_partial_ceiling_rejects_api_pass_masquerade(self) -> None:
        browser_not_run = {
            "effect-lifecycle",
            "api-network",
            "identity-permission",
            "rendering-hydration",
            "native-platform",
        }
        contracts = {
            block_id: {
                "observer_kind": generator.BLOCK_OBSERVER_SPECS_V2[block_id][
                    "observer_kind"
                ],
                "measurement_surface": generator.BLOCK_OBSERVER_SPECS_V2[block_id][
                    "measurement_surface"
                ],
                "browser_status": (
                    "NOT_RUN" if block_id in browser_not_run else "PASSED"
                ),
                "browser_reason": f"engine browser reason for {block_id}",
                "native_status": "NOT_RUN" if block_id == "api-network" else "PASSED",
                "native_reason": (
                    "a single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation"
                    if block_id == "api-network"
                    else f"engine native ceiling for {block_id}"
                ),
            }
            for block_id in generator.SEMANTIC_BLOCKS
        }
        driver = {
            "block_observer_contracts": contracts,
            "browser_required_not_run_blocks": [
                block_id
                for block_id in generator.SEMANTIC_BLOCKS
                if block_id in browser_not_run
            ],
            "native_required_not_run_blocks": ["api-network"],
        }
        browser_ceiling = generator.browser_block_status_contract_v2(
            profile_id="react", driver=driver
        )
        native_ceiling = generator.native_block_status_ceiling_v2(
            profile_id="react", driver=driver
        )
        observed = json.loads(json.dumps(browser_ceiling))
        observed["api-network"] = {"status": "PASSED", "reason": None}
        with self.assertRaisesRegex(
            RuntimeError, "V2_RUNTIME_BROWSER_BLOCK_DECLARATION_DRIFT"
        ):
            generator.validate_observed_block_statuses_v2(
                profile_id="react",
                channel="browser",
                observed=observed,
                browser_ceiling=browser_ceiling,
                native_ceiling=native_ceiling,
            )

    def test_formal_ready_rejects_pua_and_preserves_unconditional_liveness(self) -> None:
        route_results = [
            {"model_formal_status": "PASSED", "unconditional": True}
            for _ in range(72)
        ]
        unconditional_campaign = {
            "assumptions": [],
            "unsupported_semantics": [],
            "unconditional_proof": True,
        }
        self.assertTrue(
            validator.formal_readiness_v2(
                model_formal_ready=True,
                route_results=route_results,
                campaign=unconditional_campaign,
            )
        )
        for field, value in (
            ("assumptions", ["bounded-domain assumption"]),
            ("unsupported_semantics", ["unproved runtime semantic"]),
        ):
            with self.subTest(field=field):
                campaign = {**unconditional_campaign, field: value}
                self.assertFalse(
                    validator.formal_readiness_v2(
                        model_formal_ready=True,
                        route_results=route_results,
                        campaign=campaign,
                    )
                )
        self.assertFalse(
            validator.formal_readiness_v2(
                model_formal_ready=False,
                route_results=route_results,
                campaign=unconditional_campaign,
            )
        )
        not_run_route_results = json.loads(json.dumps(route_results))
        not_run_route_results[0]["model_formal_status"] = "NOT_RUN"
        not_run_route_results[0]["unconditional"] = False
        self.assertFalse(
            validator.formal_readiness_v2(
                model_formal_ready=True,
                route_results=not_run_route_results,
                campaign=unconditional_campaign,
            )
        )

    def test_external_actual_contract_rejects_wrong_type_and_enum(self) -> None:
        actual = {
            "requestedPath": "/protected",
            "selectedRouteId": "route.protected",
            "selectedPath": "/protected",
            "resolution": "DECLARED",
            "deepLink": True,
            "requiresAuth": True,
        }
        self.assertTrue(
            generator.external_actual_value_valid_v2(
                "route-navigation-deeplink-404", actual
            )
        )
        self.assertTrue(
            validator.external_actual_value_valid_v2(
                "route-navigation-deeplink-404", actual
            )
        )
        for mutation in (
            {**actual, "deepLink": 1},
            {**actual, "resolution": "SELF_REPORTED_PASS"},
        ):
            self.assertFalse(
                generator.external_actual_value_valid_v2(
                    "route-navigation-deeplink-404", mutation
                )
            )
            self.assertFalse(
                validator.external_actual_value_valid_v2(
                    "route-navigation-deeplink-404", mutation
                )
            )

        api_actual = {
            "operationId": "search",
            "called": True,
            "method": "POST",
            "path": "/api/search",
            "outcome": "OPENED",
            "canceled": False,
            "staleIgnored": False,
            "cacheKey": "tenant:query",
        }
        native_actual = {
            "boundary": "ADAPTER",
            "lifecycle": "FOREGROUND",
            "attempted": True,
            "permission": "GRANTED",
            "available": True,
            "outcome": "SUCCESS",
            "recovery": "NOT_REQUIRED",
        }
        for module in (generator, validator):
            self.assertFalse(
                module.external_actual_value_valid_v2("api-network", api_actual)
            )
            self.assertFalse(
                module.external_actual_value_valid_v2(
                    "native-platform", native_actual
                )
            )
            self.assertTrue(
                module.external_actual_value_valid_v2(
                    "native-platform",
                    {**native_actual, "outcome": "NO_OP_REPORTED"},
                )
            )
            self.assertTrue(
                module.external_actual_value_valid_v2(
                    "form-binding-validation",
                    {
                        "formId": "search-form",
                        "fieldId": "query",
                        "value": "",
                        "submitted": False,
                        "valid": False,
                        "errorCode": None,
                    },
                )
            )
            self.assertTrue(
                module.external_actual_value_valid_v2(
                    "accessibility-focus",
                    {
                        "mainRole": "main",
                        "headingLevel": 1,
                        "formLabel": "Search",
                        "errorRole": None,
                        "liveRegion": "polite",
                        "keyboardSubmit": False,
                        "focusTarget": None,
                    },
                )
            )
            self.assertFalse(
                module.external_actual_value_valid_v2(
                    "component-template-view",
                    {
                        "componentId": "GeneratedPage",
                        "key": "route.home",
                        "title": "",
                        "text": "Home",
                        "visible": True,
                    },
                )
            )

        trust_issued_at = generator.datetime(2026, 6, 1, tzinfo=generator.UTC)
        trust_expires_at = generator.datetime(2027, 6, 1, tzinfo=generator.UTC)
        issued_at = generator.datetime(2026, 7, 1, tzinfo=generator.UTC)
        expires_at = generator.datetime(2027, 1, 1, tzinfo=generator.UTC)
        now = generator.datetime(2026, 8, 10, tzinfo=generator.UTC)
        for module in (generator, validator):
            self.assertTrue(
                module.external_authorization_time_valid_v2(
                    trust_issued_at=trust_issued_at,
                    trust_expires_at=trust_expires_at,
                    issued_at=issued_at,
                    expires_at=expires_at,
                    now=now,
                )
            )
            self.assertFalse(
                module.external_authorization_time_valid_v2(
                    trust_issued_at=generator.datetime(
                        2026, 7, 2, tzinfo=generator.UTC
                    ),
                    trust_expires_at=trust_expires_at,
                    issued_at=issued_at,
                    expires_at=expires_at,
                    now=now,
                )
            )
            self.assertFalse(
                module.external_authorization_time_valid_v2(
                    trust_issued_at=trust_issued_at,
                    trust_expires_at=trust_expires_at,
                    issued_at=issued_at,
                    expires_at=None,
                    now=now,
                )
            )
            self.assertFalse(
                module.external_authorization_time_valid_v2(
                    trust_issued_at=trust_issued_at,
                    trust_expires_at=generator.datetime(
                        2026, 12, 1, tzinfo=generator.UTC
                    ),
                    issued_at=issued_at,
                    expires_at=expires_at,
                    now=now,
                )
            )

        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-external-actual-negative-"
        ) as directory:
            observation_path = Path(directory) / "observation.json"
            scope_digest = "sha256:" + "1" * 64
            write(
                observation_path,
                {
                    "schema_version": 2,
                    "kind": "frontend-formal-runtime-observation-v2",
                    "scope_digest": scope_digest,
                    "route_id": "angular--to--react",
                    "block_id": "route-navigation-deeplink-404",
                    "profile_id": "angular",
                    "corpus_case_ids": ["case-1"],
                    "observer_protocol": "block-specific-runtime-observation-v1",
                    "model_values_used_as_actual": False,
                    "actuals": [
                        {
                            "case_id": "case-1",
                            "actual": {**actual, "deepLink": 1},
                        }
                    ],
                },
            )
            errors: list[str] = []
            self.assertIsNone(
                validator.external_actuals_v2(
                    path=observation_path,
                    scope_digest=scope_digest,
                    route_id="angular--to--react",
                    block_id="route-navigation-deeplink-404",
                    profile_id="angular",
                    case_ids={"case-1"},
                    schema_path=ROOT
                    / "schemas/batch32/frontend-formal-external-runtime-observation-v2.schema.json",
                    errors=errors,
                )
            )
            self.assertTrue(errors)

        external_schema = load(
            ROOT / "schemas/batch32/frontend-formal-external-evidence-v2.schema.json"
        )
        self.assertEqual(4, external_schema["properties"]["signatures"]["minItems"])
        self.assertIn(
            "CUSTOMER",
            external_schema["$defs"]["signature"]["properties"]["role"]["enum"],
        )

    def test_unconditional_proof_contract_closes_all_logical_layers(self) -> None:
        profile_channel_statuses = {
            profile_id: {
                channel: "PASSED"
                for channel in validator.RUNTIME_CHANNELS
            }
            for profile_id in validator.PROFILE_IDS
        }
        generator_unsupported = generator.unsupported_semantics_v2(
            arbitrary_customer_source="PROVED",
            profile_channel_statuses=profile_channel_statuses,
            independent_status="PASSED",
        )
        validator_unsupported = validator.unsupported_semantics_v2(
            arbitrary_customer_source="PROVED",
            profile_channel_statuses=profile_channel_statuses,
            independent_status="PASSED",
        )
        self.assertEqual([], generator_unsupported)
        self.assertEqual(generator_unsupported, validator_unsupported)

        route_results: list[dict[str, Any]] = []
        checked_blocks = 0
        for route_id in sorted(validator.exact_routes()):
            for block_id in validator.BLOCK_IDS:
                checked_blocks += 1
                self.assertEqual(
                    "theorem",
                    generator.formal_proof_contract_v2(
                        proof_status="PROVED",
                        unconditional_proof=True,
                        assumptions=[],
                        unsupported_semantics=[],
                        label=f"test:{route_id}:{block_id}",
                    ),
                )
                errors: list[str] = []
                self.assertEqual(
                    "theorem",
                    validator.formal_proof_contract_v2(
                        proof_status="PROVED",
                        unconditional_proof=True,
                        assumptions=[],
                        unsupported_semantics=[],
                        label=f"test:{route_id}:{block_id}",
                        errors=errors,
                    ),
                )
                self.assertEqual([], errors)
            route_results.append(
                {"model_formal_status": "PASSED", "unconditional": True}
            )
        self.assertEqual(864, checked_blocks)
        campaign = {
            "assumptions": [],
            "unsupported_semantics": validator_unsupported,
            "unconditional_proof": True,
        }
        self.assertTrue(
            validator.formal_readiness_v2(
                model_formal_ready=True,
                route_results=route_results,
                campaign=campaign,
            )
        )

        self.assertEqual(
            "assumption",
            generator.formal_proof_contract_v2(
                proof_status="PROVED_UNDER_ASSUMPTIONS",
                unconditional_proof=False,
                assumptions=["bounded-domain"],
                unsupported_semantics=["runtime-NOT_RUN"],
                label="test:pua",
            ),
        )
        pua_errors: list[str] = []
        self.assertEqual(
            "assumption",
            validator.formal_proof_contract_v2(
                proof_status="PROVED_UNDER_ASSUMPTIONS",
                unconditional_proof=False,
                assumptions=["bounded-domain"],
                unsupported_semantics=["runtime-NOT_RUN"],
                label="test:pua",
                errors=pua_errors,
            ),
        )
        self.assertEqual([], pua_errors)

        for proof_status, unconditional, assumptions, unsupported in (
            ("PROVED", True, ["bounded-domain"], []),
            ("PROVED", True, [], ["runtime-NOT_RUN"]),
            ("PROVED_UNDER_ASSUMPTIONS", False, [], []),
            ("PROVED_UNDER_ASSUMPTIONS", True, ["bounded-domain"], []),
        ):
            with self.subTest(
                proof_status=proof_status,
                unconditional=unconditional,
                assumptions=assumptions,
                unsupported=unsupported,
            ):
                with self.assertRaisesRegex(RuntimeError, "V2_FORMAL_"):
                    generator.formal_proof_contract_v2(
                        proof_status=proof_status,
                        unconditional_proof=unconditional,
                        assumptions=assumptions,
                        unsupported_semantics=unsupported,
                        label="test:mixed",
                    )
                errors = []
                validator.formal_proof_contract_v2(
                    proof_status=proof_status,
                    unconditional_proof=unconditional,
                    assumptions=assumptions,
                    unsupported_semantics=unsupported,
                    label="test:mixed",
                    errors=errors,
                )
                self.assertTrue(errors)

    def test_formal_schema_rejects_mixed_unconditional_claims(self) -> None:
        schema = load(
            ROOT / "schemas/batch32/frontend-formal-route-evidence-v2.schema.json"
        )
        formal_conditions = schema["$defs"]["formalEvidence"]["allOf"]
        self.assertEqual(
            ["PROVED", "PROVED_UNDER_ASSUMPTIONS"],
            [
                formal_conditions[index]["if"]["properties"]["status"]["const"]
                for index in (0, 1)
            ],
        )
        self.assertEqual(
            0,
            formal_conditions[0]["then"]["properties"]["assumptions"][
                "maxItems"
            ],
        )
        campaign_schema = load(
            ROOT / "schemas/batch32/frontend-formal-route-campaign-v2.schema.json"
        )
        self.assertEqual(
            0,
            campaign_schema["allOf"][0]["then"]["properties"][
                "unsupported_semantics"
            ]["maxItems"],
        )
        batch35_route_schema = load(
            ROOT / "schemas/batch35/frontend-formal-route-evidence-v2.schema.json"
        )
        batch35_campaign_schema = load(
            ROOT / "schemas/batch35/frontend-formal-route-campaign-v2.schema.json"
        )
        self.assertEqual(
            "../batch32/frontend-formal-route-evidence-v2.schema.json",
            batch35_route_schema["$ref"],
        )
        self.assertIn("formalEvidence", batch35_route_schema["$comment"])
        self.assertEqual(
            "../batch32/frontend-formal-route-campaign-v2.schema.json",
            batch35_campaign_schema["$ref"],
        )
        self.assertIn("unconditional-proof", batch35_campaign_schema["$comment"])
        if validator.jsonschema is None:
            return
        probe = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
            "$ref": "#/$defs/formalEvidence",
        }
        digest_value = "sha256:" + "1" * 64
        formal = {
            "obligation_symbol": "diff_route",
            "formal_input_artifact_id": "formal-input",
            "smt_artifact_id": "smt",
            "solver_result_artifact_id": "solver-result",
            "solver_binary_artifact_id": "solver-binary",
            "solver_binary_sha256": validator.v1.LOCKED_Z3_BINARY_SHA256,
            "solver_binary_bytes": 1,
            "vacuity_input_artifact_id": "vacuity-input",
            "vacuity_result_artifact_id": "vacuity-result",
            "block_result_artifact_id": "block-result",
            "composition_artifact_id": "composition",
            "layered_result_artifact_id": "layered-result",
            "formal_input_sha256": digest_value,
            "solver_input_sha256": digest_value,
            "solver_result_sha256": digest_value,
            "vacuity_input_sha256": digest_value,
            "vacuity_result_sha256": digest_value,
            "block_result_sha256": digest_value,
            "composition_sha256": digest_value,
            "layered_result_sha256": digest_value,
            "model_influence_max": "TRANSITION",
            "runtime_influence_max": "MODEL_ONLY_NOT_RUNTIME",
            "declaration_echo_excluded": True,
            "assumption_precheck": "SAT_NON_VACUOUS_DOMAIN",
            "status": "PROVED",
            "proof_strength": "theorem",
            "assumptions": [],
            "unsupported_semantics": [],
            "replay_status": "PASSED",
            "oracle_independence": "NOT_INDEPENDENT_SINGLE_ENGINE",
        }
        validator.jsonschema.Draft202012Validator(probe).validate(formal)
        for field, value in (
            ("assumptions", ["bounded-domain"]),
            ("unsupported_semantics", ["runtime-NOT_RUN"]),
            ("proof_strength", "assumption"),
        ):
            with self.subTest(field=field):
                mixed = {**formal, field: value}
                with self.assertRaises(validator.jsonschema.ValidationError):
                    validator.jsonschema.Draft202012Validator(probe).validate(mixed)

        pua = {
            **formal,
            "status": "PROVED_UNDER_ASSUMPTIONS",
            "proof_strength": "assumption",
            "assumptions": ["bounded-domain"],
            "unsupported_semantics": ["runtime-NOT_RUN"],
        }
        validator.jsonschema.Draft202012Validator(probe).validate(pua)
        with self.assertRaises(validator.jsonschema.ValidationError):
            validator.jsonschema.Draft202012Validator(probe).validate(
                {**pua, "assumptions": []}
            )

    def test_runtime_json_requires_content_addressed_pretty_sorted_bytes(self) -> None:
        payload = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-runtime-trace-artifact",
            "value": {"z": 2, "a": 1},
        }
        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-content-address-negative-"
        ) as directory:
            root = Path(directory) / "runtime"
            pack = Path(directory) / "pack"
            (root / "traces").mkdir(parents=True)
            pack.mkdir()

            content = runtime_pretty_bytes(payload)
            sha256 = digest(content)
            path = root / "traces" / f"{sha256.removeprefix('sha256:')}.json"
            path.write_bytes(content)
            reference = {
                "artifact_id": "",
                "role": "browser-network-trace",
                "profile_id": "react",
                "channel": "browser",
                "scenario_id": "scenario-001",
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256,
                "byte_count": len(content),
            }
            reference["artifact_id"] = generator.canonical_digest(
                {
                    key: value
                    for key, value in reference.items()
                    if key != "artifact_id"
                }
            )
            errors: list[str] = []
            validator.validate_content_addressed_runtime_json(
                reference=reference,
                path=path,
                payload=payload,
                label="unit-runtime-trace",
                errors=errors,
            )
            self.assertEqual([], errors)
            copied_id, copied_payload = generator._copy_runtime_ref_v2(
                evidence_root=root,
                pack_root=pack,
                catalog=generator.ArtifactCatalog(pack),
                profile_id="react",
                channel="browser",
                reference=reference,
                role="runtime-trace-v2:browser-network-trace",
            )
            self.assertEqual(reference["artifact_id"], copied_id)
            self.assertEqual(payload, copied_payload)

            wrong_path = root / "traces" / "not-content-addressed.json"
            wrong_path.write_bytes(content)
            wrong_reference = {**reference, "path": "traces/not-content-addressed.json"}
            errors = []
            validator.validate_content_addressed_runtime_json(
                reference=wrong_reference,
                path=wrong_path,
                payload=payload,
                label="unit-runtime-trace-wrong-name",
                errors=errors,
            )
            self.assertTrue(
                any("content-address/path/encoding drift" in item for item in errors),
                errors,
            )

            noncanonical_reference = {
                **reference,
                "path": f"traces//{sha256.removeprefix('sha256:')}.json",
            }
            errors = []
            validator.validate_content_addressed_runtime_json(
                reference=noncanonical_reference,
                path=path,
                payload=payload,
                label="unit-runtime-trace-noncanonical-path",
                errors=errors,
            )
            self.assertTrue(
                any("content-address/path/encoding drift" in item for item in errors),
                errors,
            )

            escaped_reference = {
                **reference,
                "path": f"../traces/{sha256.removeprefix('sha256:')}.json",
            }
            errors = []
            validator.validate_content_addressed_runtime_json(
                reference=escaped_reference,
                path=path,
                payload=payload,
                label="unit-runtime-trace-path-escape",
                errors=errors,
            )
            self.assertTrue(
                any("content-address/path/encoding drift" in item for item in errors),
                errors,
            )

            compact = canonical_bytes(payload)
            compact_sha256 = digest(compact)
            compact_path = (
                root
                / "traces"
                / f"{compact_sha256.removeprefix('sha256:')}.json"
            )
            compact_path.write_bytes(compact)
            compact_reference = {
                **reference,
                "path": compact_path.relative_to(root).as_posix(),
                "sha256": compact_sha256,
                "byte_count": len(compact),
            }
            compact_reference["artifact_id"] = generator.canonical_digest(
                {
                    key: value
                    for key, value in compact_reference.items()
                    if key != "artifact_id"
                }
            )
            errors = []
            validator.validate_content_addressed_runtime_json(
                reference=compact_reference,
                path=compact_path,
                payload=payload,
                label="unit-runtime-trace-compact",
                errors=errors,
            )
            self.assertTrue(
                any("content-address/path/encoding drift" in item for item in errors),
                errors,
            )
            with self.assertRaisesRegex(
                RuntimeError, "V2_RUNTIME_CONTENT_ADDRESS_OR_ENCODING_DRIFT"
            ):
                generator._copy_runtime_ref_v2(
                    evidence_root=root,
                    pack_root=Path(directory) / "compact-pack",
                    catalog=generator.ArtifactCatalog(
                        Path(directory) / "compact-pack"
                    ),
                    profile_id="react",
                    channel="browser",
                    reference=compact_reference,
                    role="runtime-trace-v2:browser-network-trace",
                )

    def test_runtime_scope_binds_live_host_tool_bytes_without_packing_binary(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-runtime-tool-negative-"
        ) as directory:
            tool = Path(directory) / "runtime-tool"
            content = b"#!/bin/sh\nprintf 'runtime-tool-v1\\n'\n"
            tool.write_bytes(content)
            tool.chmod(0o755)
            record = {
                "status": "PASSED",
                "runner_kind": "UNIT_RUNTIME",
                "execution_policy_digest": "sha256:" + "1" * 64,
                "runtime_tools": [
                    {
                        "role": "unit-runtime-tool",
                        "path": str(tool.absolute()),
                        "realpath": str(tool.resolve(strict=True)),
                        "sha256": digest(content),
                        "byte_count": len(content),
                        "version": "runtime-tool-v1",
                        "package_closure_digest": "sha256:" + "2" * 64,
                    }
                ],
                "tool_discovery": [],
            }
            scope = generator._runtime_scope_contract_v2(
                profile_id="flutter",
                channel="android",
                required=True,
                record=record,
            )
            self.assertEqual(record["runtime_tools"], scope["runtime_tools"])
            self.assertFalse(scope["portable_replay"])
            self.assertEqual("NOT_RUN", scope["portable_replay_status"])

            tool.write_bytes(content + b"# drift\n")
            tool.chmod(0o755)
            with self.assertRaisesRegex(
                RuntimeError, "V2_RUNTIME_SCOPE_TOOL_BYTES_DRIFT"
            ):
                generator._runtime_scope_contract_v2(
                    profile_id="flutter",
                    channel="android",
                    required=True,
                    record=record,
                )

    def test_runtime_scope_binds_each_browser_to_its_exact_tool_role(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-browser-matrix-role-negative-"
        ) as directory:
            root = Path(directory)
            chrome = root / "chrome"
            firefox = root / "firefox"
            chrome_bytes = b"#!/bin/sh\nprintf 'chrome-v1\\n'\n"
            firefox_bytes = b"#!/bin/sh\nprintf 'firefox-v1\\n'\n"
            chrome.write_bytes(chrome_bytes)
            firefox.write_bytes(firefox_bytes)
            chrome.chmod(0o755)
            firefox.chmod(0o755)

            record = {
                "status": "NOT_RUN",
                "reason": "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE",
                "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
                "execution_policy_digest": "sha256:" + "1" * 64,
                "runtime_tools": [
                    {
                        "role": "browser-chromium",
                        "path": str(chrome.absolute()),
                        "realpath": str(chrome.resolve(strict=True)),
                        "sha256": digest(chrome_bytes),
                        "byte_count": len(chrome_bytes),
                        "version": "Google Chrome for Testing 151.0.7922.77",
                        "package_closure_digest": "sha256:" + "2" * 64,
                    },
                    {
                        "role": "browser-firefox",
                        "path": str(firefox.absolute()),
                        "realpath": str(firefox.resolve(strict=True)),
                        "sha256": digest(firefox_bytes),
                        "byte_count": len(firefox_bytes),
                        "version": "Mozilla Firefox 151.0",
                        "package_closure_digest": "sha256:" + "3" * 64,
                    },
                ],
                "tool_discovery": [
                    {
                        "kind": "EXACT_BROWSER_MATRIX",
                        "policy_id": "node-web-chromium-firefox-v1",
                        "browser_matrix": [
                            {
                                "browser_id": "google-chrome",
                                "engine": "chromium",
                                "version": "Google Chrome for Testing 151.0.7922.77",
                                "executable_sha256": digest(chrome_bytes),
                            },
                            {
                                "browser_id": "mozilla-firefox",
                                "engine": "firefox",
                                "version": "Mozilla Firefox 151.0",
                                "executable_sha256": digest(firefox_bytes),
                            },
                        ],
                        "cross_browser": True,
                    }
                ],
            }

            generator._runtime_scope_contract_v2(
                profile_id="react",
                channel="browser",
                required=True,
                record=record,
            )
            errors: list[str] = []
            validator.runtime_scope_contract_v2(
                profile_id="react",
                channel="browser",
                record=record,
                errors=errors,
            )
            self.assertEqual([], errors)

            swapped = json.loads(json.dumps(record))
            values = swapped["tool_discovery"][0]["browser_matrix"]
            values[0]["executable_sha256"], values[1]["executable_sha256"] = (
                values[1]["executable_sha256"],
                values[0]["executable_sha256"],
            )
            with self.assertRaisesRegex(
                RuntimeError, "V2_NODE_BROWSER_MATRIX_DRIFT"
            ):
                generator._runtime_scope_contract_v2(
                    profile_id="react",
                    channel="browser",
                    required=True,
                    record=swapped,
                )
            errors = []
            validator.runtime_scope_contract_v2(
                profile_id="react",
                channel="browser",
                record=swapped,
                errors=errors,
            )
            self.assertTrue(
                any("browser matrix policy/tool digest drift" in item for item in errors)
            )

            duplicate_role = json.loads(json.dumps(record))
            duplicate_role["runtime_tools"][1]["role"] = "browser-chromium"
            with self.assertRaisesRegex(
                RuntimeError, "V2_RUNTIME_SCOPE_TOOL_ROLE_COLLISION"
            ):
                generator._runtime_scope_contract_v2(
                    profile_id="react",
                    channel="browser",
                    required=True,
                    record=duplicate_role,
                )
            errors = []
            validator.runtime_scope_contract_v2(
                profile_id="react",
                channel="browser",
                record=duplicate_role,
                errors=errors,
            )
            self.assertTrue(any("runtime tool role collision" in item for item in errors))

    def test_playwright_raw_binds_scenario_executable_and_browser_versions(self) -> None:
        profile_execution = {
            "profile_id": "react",
            "project_digest": "sha256:" + "1" * 64,
        }
        runtime_tools = [
            {
                "role": "browser-chromium",
                "realpath": "/runtime/cft-chrome",
                "sha256": "sha256:" + "2" * 64,
                "byte_count": 101,
            },
            {
                "role": "browser-firefox",
                "realpath": "/runtime/playwright-firefox",
                "sha256": "sha256:" + "3" * 64,
                "byte_count": 202,
            },
        ]
        matrix = [
            {
                "browser_id": "google-chrome",
                "engine": "chromium",
                "version": "Google Chrome for Testing 151.0.7922.77",
            },
            {
                "browser_id": "mozilla-firefox",
                "engine": "firefox",
                "version": "Mozilla Firefox 151.0",
            },
        ]
        record = {
            "runner_kind": "PLAYWRIGHT_BROWSER_INTERACTION",
            "runtime_tools": runtime_tools,
            "tool_discovery": [
                {
                    "kind": "EXACT_BROWSER_MATRIX",
                    "policy_id": "node-web-chromium-firefox-v1",
                    "browser_matrix": matrix,
                    "cross_browser": True,
                }
            ],
        }
        payload = {
            "schema_version": "1.0",
            "kind": "frontend-interaction-playwright-probe-result",
            "profile_id": "react",
            "project_digest": profile_execution["project_digest"],
            "proof_profile": "bounded-frontend-interaction-v1",
            "scenario_manifest_digest": generator.canonical_digest([]),
            "semantic_block_ids": list(generator.SEMANTIC_BLOCKS),
            "model_values_accepted_as_actual": False,
            "external_network": "BLOCKED",
            "status": "PASSED",
            "reason": None,
            "browser_runs": [
                {
                    "browser_id": "google-chrome",
                    "engine": "chromium",
                    "executable": {
                        "browser_id": "google-chrome",
                        "engine": "chromium",
                        "executable_path": "/runtime/cft-chrome",
                        "executable_sha256": "sha256:" + "2" * 64,
                        "executable_byte_count": 101,
                    },
                    "browser_version": "151.0.7922.77",
                    "status": "PASSED",
                    "reason": None,
                    "scenario_count": 0,
                    "scenarios": [],
                },
                {
                    "browser_id": "mozilla-firefox",
                    "engine": "firefox",
                    "executable": {
                        "browser_id": "mozilla-firefox",
                        "engine": "firefox",
                        "executable_path": "/runtime/playwright-firefox",
                        "executable_sha256": "sha256:" + "3" * 64,
                        "executable_byte_count": 202,
                    },
                    "browser_version": "151.0",
                    "status": "PASSED",
                    "reason": None,
                    "scenario_count": 0,
                    "scenarios": [],
                },
            ],
        }
        block_statuses = {
            block_id: {"status": "PASSED"}
            for block_id in generator.SEMANTIC_BLOCKS
        }

        def assert_generator_rejects(mutator: Callable[[dict[str, Any]], None]) -> None:
            candidate = json.loads(json.dumps(payload))
            mutator(candidate)
            with self.assertRaisesRegex(
                RuntimeError,
                "V2_PLAYWRIGHT_(RAW_PROOF_IDENTITY|SCENARIO_CLOSURE)_DRIFT",
            ):
                generator._validate_playwright_raw_proof_v2(
                    payload=candidate,
                    profile_execution=profile_execution,
                    record=record,
                    scenario_ids=[],
                    scenario_inputs={},
                    observations={},
                    block_statuses=block_statuses,
                )

        generator._validate_playwright_raw_proof_v2(
            payload=payload,
            profile_execution=profile_execution,
            record=record,
            scenario_ids=[],
            scenario_inputs={},
            observations={},
            block_statuses=block_statuses,
        )
        assert_generator_rejects(
            lambda candidate: candidate.__setitem__(
                "scenario_manifest_digest", "sha256:" + "9" * 64
            )
        )
        assert_generator_rejects(
            lambda candidate: candidate["browser_runs"][0]["executable"].__setitem__(
                "executable_path", "/attacker/chrome"
            )
        )
        assert_generator_rejects(
            lambda candidate: candidate["browser_runs"][1].__setitem__(
                "browser_version", "152.0"
            )
        )

        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-playwright-raw-identity-"
        ) as directory:
            raw_path = Path(directory) / "raw.json"

            def validator_errors(candidate: dict[str, Any]) -> list[str]:
                raw_bytes = runtime_pretty_bytes(candidate)
                raw_path.write_bytes(raw_bytes)
                raw_sha256 = digest(raw_bytes)
                packed_path = (
                    "formal-campaign/toolchain/runtime-evidence/react/browser/"
                    f"raw-probe/{raw_sha256.removeprefix('sha256:')}.json"
                )
                validation_record = json.loads(json.dumps(record))
                validation_record["tool_discovery"].append(
                    {
                        "kind": "PLAYWRIGHT_RAW_RESULT",
                        "path": str(raw_path.resolve()),
                        "sha256": raw_sha256,
                        "byte_count": len(raw_bytes),
                    }
                )
                errors: list[str] = []
                validator.validate_runtime_raw_proof_v2(
                    profile_id="react",
                    channel="browser",
                    profile_project_digest=profile_execution["project_digest"],
                    profile_manifest_digest="sha256:" + "4" * 64,
                    engine_scenario_manifest_digest="sha256:" + "5" * 64,
                    record=validation_record,
                    scenario_ids=[],
                    scenario_inputs={},
                    observations={},
                    block_statuses=block_statuses,
                    artifacts={
                        "raw-artifact": {
                            "role": "runtime-raw-probe-v2",
                            "path": packed_path,
                            "sha256": raw_sha256,
                            "bytes": len(raw_bytes),
                        }
                    },
                    artifact_files={"raw-artifact": raw_path},
                    declared_runtime_ids={"raw-artifact"},
                    errors=errors,
                )
                return errors

            self.assertEqual([], validator_errors(payload))
            candidate = json.loads(json.dumps(payload))
            candidate["browser_runs"][0]["browser_version"] = "150.0"
            self.assertTrue(
                any("Playwright scenario closure drift" in item for item in validator_errors(candidate))
            )

    def test_route_actual_is_derived_from_raw_dom_and_bound_scenario(self) -> None:
        measurement = {
            "page_url": "http://127.0.0.1:4173/",
            "active_route_attributes": {
                "data-route-id": "home",
                "data-route-path": "/",
                "data-deep-link": "false",
                "data-requires-auth": "false",
            },
            "declared_routes": [
                {
                    "route_id": "home",
                    "route_path": "/",
                    "deep_link": False,
                    "requires_auth": False,
                },
                {
                    "route_id": "admin",
                    "route_path": "/admin",
                    "deep_link": True,
                    "requires_auth": True,
                },
            ],
        }
        actual = generator.runtime_actual_from_block_measurement_v2(
            block_id="route-navigation-deeplink-404",
            value=measurement,
            label="unit-route",
            scenario_input={
                "routePath": "/admin",
                "authenticated": False,
                "permissionGranted": False,
                "tenantId": "tenant-a",
                "resourceTenantId": "tenant-a",
            },
        )
        self.assertEqual("AUTH_DENIED_FALLBACK", actual["resolution"])
        self.assertEqual("/admin", actual["requestedPath"])
        self.assertEqual(
            runtime_runner.derive_actual_from_block_measurement(
                "route-navigation-deeplink-404",
                measurement,
                scenario_input={
                    "routePath": "/admin",
                    "authenticated": False,
                    "permissionGranted": False,
                    "tenantId": "tenant-a",
                    "resourceTenantId": "tenant-a",
                },
                name="unit-route-runner",
            ),
            actual,
        )

        with self.assertRaisesRegex(
            RuntimeError, "V2_BLOCK_OBSERVER_SCENARIO_INPUT_MISSING"
        ):
            generator.runtime_actual_from_block_measurement_v2(
                block_id="route-navigation-deeplink-404",
                value=measurement,
                label="unit-route-without-scenario",
            )

        i18n_measurement = {
            "html_lang": "zh-CN",
            "translated_text": {
                "requested_locale": "zh-CN",
                "text": "已渲染文本",
            },
            "computed_theme_tokens": {
                "requested_theme": "LIGHT",
                "theme": "LIGHT",
            },
            "layout_measurement": {
                "viewport_width": 1024,
                "columns": 2,
                "computed_grid_template_columns": "500px 500px",
                "bounding_box": {
                    "x": 0.0,
                    "y": 10.0,
                    "width": 1000.0,
                    "height": 80.0,
                },
            },
        }
        scenario_input = {
            "locale": "zh-CN",
            "theme": "LIGHT",
            "viewportWidth": 1024,
        }
        generated_i18n = generator.runtime_actual_from_block_measurement_v2(
            block_id="i18n-theme-responsive",
            value=i18n_measurement,
            label="unit-i18n",
            scenario_input=scenario_input,
        )
        self.assertEqual(
            runtime_runner.derive_actual_from_block_measurement(
                "i18n-theme-responsive",
                i18n_measurement,
                scenario_input=scenario_input,
                name="unit-i18n-runner",
            ),
            generated_i18n,
        )

    def test_all_block_measurement_derivations_mirror_the_frozen_runner(self) -> None:
        from tests.frontend_formal_toolchains.test_runner import (
            runtime_block_measurement,
            runtime_scenario_input,
        )

        scenario_input = runtime_scenario_input()
        for block_id in runtime_runner.INTERACTION_BLOCK_IDS:
            with self.subTest(block_id=block_id):
                measurement = runtime_block_measurement(block_id)
                expected = runtime_runner.derive_actual_from_block_measurement(
                    block_id,
                    measurement,
                    scenario_input=scenario_input,
                    name=f"runner:{block_id}",
                )
                self.assertEqual(
                    expected,
                    generator.runtime_actual_from_block_measurement_v2(
                        block_id=block_id,
                        value=measurement,
                        label=f"generator:{block_id}",
                        scenario_input=scenario_input,
                    ),
                )
                self.assertEqual(
                    expected,
                    validator.runtime_actual_from_block_measurement(
                        block_id=block_id,
                        value=measurement,
                        label=f"validator:{block_id}",
                        scenario_input=scenario_input,
                    ),
                )

    def test_locked_emitter_rejects_constant_success_cli(self) -> None:
        artifact_files: dict[str, Path] = {}
        runtime_by_path: dict[str, str] = {}
        implementation_by_path: dict[str, str] = {}
        node_realpath = Path(shutil.which("node") or "node").resolve()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            for index, (runtime_path, repository_path) in enumerate(
                validator.ENGINE_VERIFIER_REPOSITORY_MAP.items()
            ):
                if not runtime_path.endswith(".js"):
                    continue
                runtime_id = f"runtime-{index}"
                source_id = f"source-{index}"
                runtime_by_path[runtime_path] = runtime_id
                artifact_files[runtime_id] = ROOT / repository_path
                source_path = repository_path.replace("/dist/src/", "/src/")
                source_path = source_path.removesuffix(".js") + ".ts"
                implementation_by_path[source_path] = source_id
                artifact_files[source_id] = ROOT / source_path
            typescript_id = "typescript"
            runtime_by_path[
                "formal-campaign/engine-verifier/node_modules/typescript/lib/typescript.js"
            ] = typescript_id
            artifact_files[typescript_id] = (
                ROOT
                / "engines/frontend-client-engine/node_modules/typescript/lib/typescript.js"
            )
            errors: list[str] = []
            validator.validate_engine_verifier_emit(
                node_realpath=node_realpath,
                runtime_by_path=runtime_by_path,
                implementation_by_repository_path=implementation_by_path,
                artifact_files=artifact_files,
                errors=errors,
            )
            self.assertEqual([], errors)
            cli_path = temporary / "frontend-interaction-formal-cli.js"
            cli_path.write_text(
                "process.stdout.write(JSON.stringify({valid:true,errors:[]}));\n",
                encoding="utf-8",
            )
            runtime_by_path[
                "formal-campaign/engine-verifier/src/frontend-interaction-formal-cli.js"
            ] = "tampered-cli"
            artifact_files["tampered-cli"] = cli_path
            errors = []
            validator.validate_engine_verifier_emit(
                node_realpath=node_realpath,
                runtime_by_path=runtime_by_path,
                implementation_by_repository_path=implementation_by_path,
                artifact_files=artifact_files,
                errors=errors,
            )
            self.assertTrue(any("does not match" in error for error in errors), errors)

    def test_v2_cli_generation_pins_proof_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="frontend-v2-cli-") as directory:
            evidence = Path(directory) / "raw.json"
            evidence.write_text("{}\n", encoding="utf-8")
            argv = [
                "generate_frontend_formal_verification_pack.py",
                "--repo-root",
                str(ROOT),
                "--contract-version",
                "2",
                "--engine-cli",
                "engines/frontend-client-engine/dist/src/frontend-interaction-formal-cli.js",
                "--toolchain-evidence",
                str(evidence),
                "--force",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    generator,
                    "run_checked",
                    side_effect=RuntimeError("stop-after-command-capture"),
                ) as checked,
                self.assertRaisesRegex(RuntimeError, "stop-after-command-capture"),
            ):
                generator.main()
            command = checked.call_args.args[0]
            self.assertEqual(
                ["--proof-profile", "bounded-frontend-interaction-v1"],
                command[2:4],
            )
            self.assertIn("--output", command)

    def test_v2_external_positive_protocol_rejects_before_io_or_build(self) -> None:
        nonexistent = ROOT / "does-not-exist-external-positive-v2"
        argv = [
            "generate_frontend_formal_verification_pack.py",
            "--repo-root",
            str(ROOT),
            "--contract-version",
            "2",
            "--engine-output",
            str(nonexistent / "engine"),
            "--toolchain-evidence",
            str(nonexistent / "toolchain.json"),
            "--external-evidence",
            str(nonexistent / "evidence.json"),
            "--external-trust-store",
            str(nonexistent / "trust-store.json"),
            "--external-trust-root",
            str(nonexistent / "trust-root.json"),
            "--force",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(generator, "run_checked") as engine,
            mock.patch.object(generator, "build_packs_v2") as build,
            mock.patch.object(generator, "copy_engine_output_v2") as copy,
            self.assertRaisesRegex(
                RuntimeError, "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED"
            ),
        ):
            generator.main()
        engine.assert_not_called()
        build.assert_not_called()
        copy.assert_not_called()

        with (
            mock.patch.object(generator, "verify_engine_campaign_v2") as engine,
            mock.patch.object(generator, "copy_engine_output_v2") as copy,
            self.assertRaisesRegex(
                RuntimeError, "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED"
            ),
        ):
            generator.build_common_campaign_v2(
                repo_root=ROOT,
                engine_root=nonexistent / "engine",
                common_root=nonexistent / "common",
                toolchain_evidence_path=nonexistent / "toolchain.json",
                external_evidence_path=nonexistent / "evidence.json",
            )
        engine.assert_not_called()
        copy.assert_not_called()

        staging_root = nonexistent / "staging"
        with (
            mock.patch.object(generator, "build_common_campaign_v2") as build,
            self.assertRaisesRegex(
                RuntimeError, "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED"
            ),
        ):
            generator.build_packs_v2(
                repo_root=ROOT,
                engine_root=nonexistent / "engine",
                staging_root=staging_root,
                toolchain_evidence_path=nonexistent / "toolchain.json",
                external_trust_root_path=nonexistent / "trust-root.json",
            )
        build.assert_not_called()
        self.assertFalse((staging_root / "common-v2").exists())

    def copy_pack(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-v2-negative-")
        destination = Path(temporary.name) / "pack"
        shutil.copytree(self.pack, destination)
        return temporary, destination

    def campaign(self, pack: Path) -> tuple[Path, dict[str, Any]]:
        path = pack / "formal-campaign/frontend-formal-route-campaign-v2.json"
        return path, load(path)

    def save_campaign(self, pack: Path, campaign: dict[str, Any]) -> None:
        path, _ = self.campaign(pack)
        write(path, campaign, canonical=True)
        campaign_digest = digest(path.read_bytes())
        manifest = load(pack / "pack.json")
        manifest["frontend_formal_campaign_v2_digest"] = campaign_digest
        manifest["frontend_formal_peer_v2"]["campaign_sha256"] = campaign_digest
        write(pack / "pack.json", manifest)

    @staticmethod
    def artifact(campaign: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        return next(row for row in campaign["artifacts"] if row["id"] == artifact_id)

    def rewrite_artifact(
        self,
        pack: Path,
        campaign: dict[str, Any],
        artifact_id: str,
        content: bytes,
    ) -> None:
        reference = self.artifact(campaign, artifact_id)
        artifact_path = pack / reference["path"]
        # Captured pack artifacts are intentionally read-only. Negative tests
        # mutate only their disposable copy, so make that copy owner-writable
        # before exercising the fully rehashed tamper path.
        artifact_path.chmod(artifact_path.stat().st_mode | 0o200)
        artifact_path.write_bytes(content)
        reference["sha256"] = digest(content)
        reference["bytes"] = len(content)

    def mutate_wrapper(
        self,
        pack: Path,
        campaign: dict[str, Any],
        mutate: Callable[[dict[str, Any]], None],
    ) -> None:
        wrapper_id = campaign["routes"][0]["route_evidence_artifact_id"]
        reference = self.artifact(campaign, wrapper_id)
        wrapper = load(pack / reference["path"])
        mutate(wrapper)
        self.rewrite_artifact(pack, campaign, wrapper_id, canonical_bytes(wrapper))

    def mutate_toolchain(
        self,
        pack: Path,
        campaign: dict[str, Any],
        mutate: Callable[[dict[str, Any]], None],
    ) -> None:
        artifact_id = campaign["toolchain_evidence"]["artifact_id"]
        reference = self.artifact(campaign, artifact_id)
        raw = load(pack / reference["path"])
        mutate(raw)
        self.rewrite_artifact(pack, campaign, artifact_id, canonical_bytes(raw))
        campaign["toolchain_evidence"]["artifact_sha256"] = reference["sha256"]
        campaign["toolchain_evidence"]["artifact_bytes"] = reference["bytes"]

    def assert_invalid(self, pack: Path, text: str) -> None:
        result = validator.validate_campaign(pack, execute_replay=False)
        self.assertEqual("invalid", result["status"], result)
        self.assertTrue(
            any(text in error for error in result["errors"]), result["errors"]
        )

    @unittest.skipUnless(
        frozen_v2_pack_available(
            ROOT / "client-packs/frontend-72-route-equivalence-v2",
            "ELMOS_FRONTEND_V2_CLIENT_PACK",
        ),
        "frozen block-specific v2 pack has not been staged or published",
    )
    def test_fully_rehashed_external_pass_declaration_fails_closed(self) -> None:
        temporary, pack = self.copy_pack()
        try:
            _, campaign = self.campaign(pack)
            campaign["external_evidence"] = {
                "provided": True,
                "status": "PASSED",
                "intake_artifact_id": "attacker-intake",
                "trust_store_artifact_id": "attacker-trust",
                "trust_root_id": "attacker-root",
                "trust_root_fingerprint": "sha256:" + "1" * 64,
                "trust_store_authorization_status": "PASSED",
                "replay_verifier_fingerprint": "sha256:" + "2" * 64,
                "artifact_ids": ["attacker-intake", "attacker-trust"],
                "scope_digest": campaign["peer_binding"]["scope_digest"],
                "authorization_status": "PASSED",
                "signature_status": "PASSED",
                "replay_status": "PASSED",
                "independent_status": "PASSED",
                "holdout_status": "PASSED",
                "representative_status": "PASSED",
                "customer_status": "PASSED",
                "organization_ids": ["org-executor", "org-verifier", "org-approver", "org-customer"],
            }
            self.save_campaign(pack, campaign)
            self.assert_invalid(pack, "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED")
        finally:
            temporary.cleanup()

    @unittest.skipUnless(
        frozen_v2_pack_available(
            ROOT / "client-packs/frontend-72-route-equivalence-v2",
            "ELMOS_FRONTEND_V2_CLIENT_PACK",
        ),
        "frozen block-specific v2 pack has not been staged or published",
    )
    def test_pack_and_fail_closed_negative_matrix(self) -> None:
        result = validator.validate_campaign(self.pack, execute_replay=False)
        self.assertEqual("valid", result["status"], result["errors"])
        self.assertEqual(
            (9, 72, 864, 18),
            (
                result["profile_count"],
                result["route_count"],
                result["block_count"],
                result["scenario_count"],
            ),
        )
        self.assertTrue(result["model_formal_ready"])
        self.assertFalse(result["formal_ready"])
        self.assertEqual(0, result["proved_route_count"])
        self.assertEqual(72, result["proved_under_assumptions_route_count"])
        self.assertFalse(result["browser_ready"])
        self.assertFalse(result["native_ready"])
        self.assertFalse(result["independent_ready"])
        self.assertFalse(result["certification_ready"])
        self.assertEqual(42, result["native_applicable_route_count"])
        self.assertEqual(0, result["native_passed_route_count"])

        _, pristine_campaign = self.campaign(self.pack)
        before = sorted(
            path.relative_to(self.pack).as_posix()
            for path in (self.pack / "formal-campaign").rglob("*")
            if path.is_file()
        )
        completed = subprocess.run(
            pristine_campaign["replay"]["command"],
            cwd=self.pack,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        after = sorted(
            path.relative_to(self.pack).as_posix()
            for path in (self.pack / "formal-campaign").rglob("*")
            if path.is_file()
        )
        self.assertEqual(before, after)

        mutations: tuple[
            tuple[str, Callable[[Path, dict[str, Any]], None], str], ...
        ] = (
            (
                "missing-block",
                lambda pack, campaign: self.mutate_wrapper(
                    pack, campaign, lambda wrapper: wrapper["blocks"].pop()
                ),
                "block closure/order",
            ),
            (
                "runtime-masquerade",
                lambda pack, campaign: self.mutate_wrapper(
                    pack,
                    campaign,
                    lambda wrapper: wrapper["blocks"][0]["runtime"]["source"][
                        "channels"
                    ]["browser"].update({"status": "PASSED"}),
                ),
                "runtime PASS lacks actual byte evidence",
            ),
            (
                "duplicate-route",
                lambda _pack, campaign: campaign["routes"].__setitem__(
                    1, campaign["routes"][0]
                ),
                "duplicate route",
            ),
            (
                "path-escape",
                lambda _pack, campaign: campaign["artifacts"][0].update(
                    {"path": "../escape"}
                ),
                "outside artifact_root",
            ),
            (
                "unregistered-artifact-root-file",
                lambda pack, _campaign: (
                    pack / "formal-campaign/unregistered-evidence.bin"
                ).write_bytes(b"unregistered"),
                "unregistered files under artifact_root",
            ),
            (
                "raw-runtime-masquerade",
                lambda pack, campaign: self.mutate_toolchain(
                    pack,
                    campaign,
                    lambda raw: next(
                        item
                        for item in raw["profile_executions"]
                        if item["profile_id"] == "jquery"
                    )["runtime_observations"]["browser"].update(
                        {"status": "PASSED"}
                    ),
                ),
                "declared runtime status reconstruction drift",
            ),
            (
                "raw-summary-tamper",
                lambda pack, campaign: self.mutate_toolchain(
                    pack,
                    campaign,
                    lambda raw: raw["summary"]["route_status_counts"].update(
                        {"NOT_RUN": 71, "PASSED": 1}
                    ),
                ),
                "summary reconstruction drift",
            ),
            (
                "toolchain-declaration-drift",
                lambda _pack, campaign: campaign["toolchain_evidence"].update(
                    {"producer_fingerprint": "sha256:" + "0" * 64}
                ),
                "campaign declaration/raw binding drift",
            ),
            (
                "raw-mutation-engine-binding-drift",
                lambda pack, campaign: self.mutate_toolchain(
                    pack,
                    campaign,
                    lambda raw: raw["mutation_replay"][0].update(
                        {"formal_input_digest": "sha256:" + "0" * 64}
                    ),
                ),
                "engine digest binding drift",
            ),
        )
        for name, mutate, expected in mutations:
            with self.subTest(name=name):
                temporary, pack = self.copy_pack()
                try:
                    _, campaign = self.campaign(pack)
                    mutate(pack, campaign)
                    self.save_campaign(pack, campaign)
                    self.assert_invalid(pack, expected)
                finally:
                    temporary.cleanup()

    @unittest.skipUnless(
        frozen_v2_pack_available(
            ROOT / "client-packs/frontend-72-route-equivalence-v2",
            "ELMOS_FRONTEND_V2_CLIENT_PACK",
        ),
        "frozen block-specific v2 pack has not been staged or published",
    )
    def test_fully_rehashed_node_types_dts_mutation_fails_closed(self) -> None:
        temporary, pack = self.copy_pack()
        try:
            _, campaign = self.campaign(pack)
            declaration = campaign["engine_verifier"]
            runtime_ids = [str(item) for item in declaration["runtime_artifact_ids"]]
            target = next(
                row
                for row in campaign["artifacts"]
                if row["id"] in runtime_ids
                and row["path"].endswith("/node_modules/@types/node/assert.d.ts")
            )
            content = (pack / target["path"]).read_bytes() + b"\n// mutation\n"
            self.rewrite_artifact(pack, campaign, target["id"], content)
            artifact_map = {row["id"]: row for row in campaign["artifacts"]}
            declaration["fingerprint"] = validator.v1.bundle_fingerprint(
                runtime_ids + [str(declaration["node_identity_artifact_id"])],
                artifact_map,
            )
            self.save_campaign(pack, campaign)
            self.assert_invalid(pack, "Node types tree identity drift")
        finally:
            temporary.cleanup()

    @unittest.skipUnless(
        frozen_v2_pack_available(
            ROOT / "client-packs/frontend-72-route-equivalence-v2",
            "ELMOS_FRONTEND_V2_CLIENT_PACK",
        ),
        "frozen block-specific v2 pack has not been staged or published",
    )
    def test_rejects_circular_oracle_and_stale_generator(self) -> None:
        temporary, pack = self.copy_pack()
        try:
            _, campaign = self.campaign(pack)
            graph_id = campaign["oracle_provenance"]["graph_artifact_id"]
            graph_ref = self.artifact(campaign, graph_id)
            graph = load(pack / graph_ref["path"])
            graph["edges"].append(
                {"from": "solver-result", "to": "formal-input", "relation": "REUSE"}
            )
            self.rewrite_artifact(pack, campaign, graph_id, canonical_bytes(graph))
            self.save_campaign(pack, campaign)
            self.assert_invalid(pack, "circular")
        finally:
            temporary.cleanup()

        temporary, pack = self.copy_pack()
        try:
            _, campaign = self.campaign(pack)
            manifest_id = campaign["implementation"]["manifest_artifact_id"]
            manifest_ref = self.artifact(campaign, manifest_id)
            bundle_manifest = load(pack / manifest_ref["path"])
            row = next(
                item
                for item in bundle_manifest["files"]
                if item["repository_path"]
                == "tooling/generate_frontend_formal_verification_pack.py"
            )
            artifact_id = row["artifact_id"]
            reference = self.artifact(campaign, artifact_id)
            content = (pack / reference["path"]).read_bytes() + b"\n# tampered\n"
            self.rewrite_artifact(pack, campaign, artifact_id, content)
            fingerprint = validator.v1.bundle_fingerprint(
                campaign["implementation"]["artifact_ids"],
                {row["id"]: row for row in campaign["artifacts"]},
            )
            campaign["implementation"]["fingerprint"] = fingerprint
            bundle_manifest["fingerprint"] = fingerprint
            self.rewrite_artifact(
                pack, campaign, manifest_id, canonical_bytes(bundle_manifest)
            )
            self.save_campaign(pack, campaign)
            self.assert_invalid(pack, "stale implementation live repository capture")
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
