from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engines" / "frontend-client-engine"
GENERATOR_PATH = ROOT / "tooling" / "generate_frontend_formal_verification_pack.py"
VALIDATOR_PATH = (
    ROOT / "scripts" / "batch32" / "validate_frontend_formal_route_campaign.py"
)


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = load_module("frontend_formal_pack_generator_test", GENERATOR_PATH)
validator = load_module("frontend_formal_campaign_validator_test", VALIDATOR_PATH)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_pretty(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class FrontendFormalCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="frontend-formal-campaign-tests-"
        )
        cls.root = Path(cls.temporary.name)
        subprocess.run(
            ["pnpm", "run", "build"],
            cwd=ENGINE,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.engine_output = cls.root / "engine-output"
        subprocess.run(
            [
                "node",
                str(ENGINE / "dist" / "src" / "frontend-formal-cli.js"),
                "--output",
                str(cls.engine_output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.toolchain_evidence = cls.root / "toolchain-evidence.json"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tooling" / "run_frontend_formal_toolchains.py"),
                str(cls.engine_output / "frontend-formal-route-campaign.json"),
                "--output",
                str(cls.toolchain_evidence),
                "--profile",
                "harmony-arkui",
                "--no-network",
                "--timeout-seconds",
                "2",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        staging = cls.root / "staging"
        client, verification = generator.build_packs(
            ROOT,
            cls.engine_output,
            staging,
            cls.toolchain_evidence,
        )
        cls.client_base = cls.root / "client-base"
        cls.verification_base = cls.root / "verification-base"
        shutil.copytree(client, cls.client_base)
        shutil.copytree(verification, cls.verification_base)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def copy_pack(self, *, verification: bool = False) -> Path:
        source = self.verification_base if verification else self.client_base
        destination = Path(self.temporary.name) / next(tempfile._get_candidate_names())
        shutil.copytree(source, destination)
        return destination

    def campaign(self, pack: Path) -> tuple[Path, dict[str, Any]]:
        path = pack / "formal-campaign" / "frontend-formal-route-campaign.json"
        return path, load(path)

    def save_campaign(self, pack: Path, campaign: dict[str, Any]) -> None:
        campaign_path, _ = self.campaign(pack)
        content = canonical_bytes(campaign)
        campaign_path.write_bytes(content)
        manifest = load(pack / "pack.json")
        campaign_digest = digest(content)
        manifest["frontend_formal_campaign_digest"] = campaign_digest
        manifest["frontend_formal_peer"]["campaign_sha256"] = campaign_digest
        write_pretty(pack / "pack.json", manifest)

    def artifact(self, campaign: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        return next(item for item in campaign["artifacts"] if item["id"] == artifact_id)

    def write_artifact(
        self,
        pack: Path,
        campaign: dict[str, Any],
        artifact_id: str,
        content: bytes,
    ) -> dict[str, Any]:
        reference = self.artifact(campaign, artifact_id)
        (pack / reference["path"]).write_bytes(content)
        reference["sha256"] = digest(content)
        reference["bytes"] = len(content)
        return reference

    def mutate_wrapper(
        self,
        pack: Path,
        campaign: dict[str, Any],
        mutate: Callable[[dict[str, Any]], None],
        route_index: int = 0,
    ) -> dict[str, Any]:
        route = campaign["routes"][route_index]
        wrapper_id = route["route_evidence_artifact_id"]
        wrapper_ref = self.artifact(campaign, wrapper_id)
        wrapper = load(pack / wrapper_ref["path"])
        mutate(wrapper)
        self.write_artifact(pack, campaign, wrapper_id, canonical_bytes(wrapper))
        return wrapper

    def validate(self, pack: Path) -> dict[str, Any]:
        return validator.validate_campaign(pack, execute_replay=False)

    def assert_invalid(self, pack: Path, contains: str | None = None) -> None:
        result = self.validate(pack)
        self.assertEqual("invalid", result["status"], result)
        if contains is not None:
            self.assertTrue(
                any(contains in error for error in result["errors"]), result["errors"]
            )

    def test_valid_aggregate_separates_bounded_profile_from_full_formal_readiness(
        self,
    ) -> None:
        result = self.validate(self.client_base)
        self.assertEqual("valid", result["status"], result["errors"])
        self.assertTrue(result["bounded_proof_profile_ready"])
        self.assertFalse(result["formal_ready"])
        self.assertEqual(
            "PARTIAL_PROVED_UNDER_ASSUMPTIONS",
            result["local_equivalence_status"],
        )
        self.assertEqual(72, result["route_count"])
        self.assertEqual(9, result["profile_count"])
        self.assertFalse(result["certification_ready"])
        self.assertNotIn("certification_decision", result)
        _, campaign = self.campaign(self.client_base)
        self.assertEqual("NOT_RUN", campaign["toolchain_evidence"]["status"])
        self.assertTrue(
            all(
                route["runtime_evidence_status"] == "MODEL_ONLY"
                for route in campaign["routes"]
            )
        )

    def test_v1_toolchain_identity_uses_current_exact_runner_payload(self) -> None:
        _, campaign = self.campaign(self.client_base)
        declaration = campaign["toolchain_evidence"]
        reference = self.artifact(campaign, declaration["artifact_id"])
        raw = load(self.client_base / reference["path"])
        expected_payload = {
            "producer": raw["producer"],
            "implementation_closure": None,
            "engine_preverification_digest": None,
            "campaign_sha256": raw["campaign"]["sha256"],
            "proof_profile": "bounded-navigation-v1",
            "semantic_block_ids": [],
            "scenario_manifest_digest": None,
            "scenario_policy": None,
            "mutation_replay_digest": digest(canonical_bytes([])),
            "policy": raw["policy"],
            "profile_execution_ids": [
                item["execution_id"] for item in raw["profile_executions"]
            ],
            "route_execution_bindings": [
                {
                    "route_id": item["route_id"],
                    "source_execution_id": item["source_execution_id"],
                    "target_execution_id": item["target_execution_id"],
                    "status": item["status"],
                }
                for item in raw["route_records"]
            ],
        }
        self.assertEqual(
            {
                "algorithm": "sha256(canonical-json(identity_payload))",
                "identity_payload": expected_payload,
                "sha256": digest(canonical_bytes(expected_payload)),
                "scope": "producer+engine-preverification+implementation+campaign+scenario+policy+profile-executions+route-bindings",
            },
            raw["evidence_identity"],
        )

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        declaration = campaign["toolchain_evidence"]
        artifact_id = declaration["artifact_id"]
        reference = self.artifact(campaign, artifact_id)
        raw = load(pack / reference["path"])
        old_payload = {
            "producer": raw["producer"],
            "campaign_sha256": raw["campaign"]["sha256"],
            "policy": raw["policy"],
            "profile_execution_ids": [
                item["execution_id"] for item in raw["profile_executions"]
            ],
            "route_execution_bindings": [
                {
                    "route_id": item["route_id"],
                    "source_execution_id": item["source_execution_id"],
                    "target_execution_id": item["target_execution_id"],
                    "status": item["status"],
                }
                for item in raw["route_records"]
            ],
        }
        raw["evidence_identity"] = {
            "sha256": digest(canonical_bytes(old_payload)),
            "scope": "producer+campaign+policy+profile-executions+route-bindings",
        }
        content = canonical_bytes(raw)
        self.write_artifact(pack, campaign, artifact_id, content)
        declaration["artifact_sha256"] = digest(content)
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "toolchain raw evidence identity drift")

    def test_rejects_route_matrix_and_exact_profile_drift(self) -> None:
        mutations = (
            ("missing", lambda campaign: campaign["routes"].pop(), "route closure"),
            (
                "duplicate",
                lambda campaign: campaign["routes"].__setitem__(
                    1, campaign["routes"][0]
                ),
                "duplicate route",
            ),
            (
                "self",
                lambda campaign: campaign["routes"][0].update(
                    {
                        "route_id": "angular--to--angular",
                        "source_profile_id": "angular",
                        "target_profile_id": "angular",
                    }
                ),
                "self route",
            ),
            (
                "version",
                lambda campaign: campaign["profiles"][0]["profile"].update(
                    {"framework_version": "999.0.0"}
                ),
                "profile tuple drift",
            ),
            (
                "platform",
                lambda campaign: campaign["profiles"][0]["profile"].update(
                    {"platforms": ["IOS"]}
                ),
                "profile tuple drift",
            ),
            (
                "profile-digest",
                lambda campaign: campaign["profiles"][0].update(
                    {"profile_digest": "sha256:" + "0" * 64}
                ),
                "profile digest mismatch",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                pack = self.copy_pack()
                _, campaign = self.campaign(pack)
                mutate(campaign)
                self.save_campaign(pack, campaign)
                self.assert_invalid(pack, message)

    def test_rejects_artifact_bytes_escape_symlink_and_unused_refs(self) -> None:
        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        campaign["artifacts"][0]["bytes"] += 1
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "byte count mismatch")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        campaign["artifacts"][0]["path"] = "formal-campaign/../escape"
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "escapes")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        reference = campaign["artifacts"][0]
        target = pack / reference["path"]
        original = target.read_bytes()
        target.unlink()
        replacement = pack / "symlink-target.bin"
        replacement.write_bytes(original)
        target.symlink_to(replacement)
        self.assert_invalid(pack, "symlink")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        path = pack / "formal-campaign" / "unused.bin"
        path.write_bytes(b"unused")
        campaign["artifacts"].append(
            {
                "id": "unused-artifact",
                "role": "unused",
                "path": "formal-campaign/unused.bin",
                "sha256": digest(b"unused"),
                "bytes": 6,
            }
        )
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "unused artifact refs")

    def test_rejects_semantic_pointer_span_hash_and_missing_block(self) -> None:
        changes = (
            (
                "pointer",
                lambda wrapper: wrapper["semantic_blocks"][0]["canonical_ir"].update(
                    {"pointer": "/missing"}
                ),
                "pointer is invalid",
            ),
            (
                "span",
                lambda wrapper: wrapper["semantic_blocks"][0]["canonical_ir"][
                    "span"
                ].update({"start": 1}),
                "canonical location",
            ),
            (
                "hash",
                lambda wrapper: wrapper["semantic_blocks"][0].update(
                    {"semantic_hash": "sha256:" + "0" * 64}
                ),
                "semantic PASS drift",
            ),
            (
                "block",
                lambda wrapper: wrapper["semantic_blocks"].pop(),
                "fewer than 12 items",
            ),
        )
        for name, mutate, message in changes:
            with self.subTest(name=name):
                pack = self.copy_pack()
                _, campaign = self.campaign(pack)
                self.mutate_wrapper(pack, campaign, mutate)
                self.save_campaign(pack, campaign)
                self.assert_invalid(pack, message)

    def test_rejects_fake_independent_oracle_zero_cases_and_model_as_native(
        self,
    ) -> None:
        pack = self.copy_pack()
        _, campaign = self.campaign(pack)

        def copied_oracle(wrapper: dict[str, Any]) -> None:
            case = load(
                pack
                / self.artifact(campaign, wrapper["behavior"]["artifact_id"])["path"]
            )["cases"][0]
            case["independent_expected"] = dict(case["canonical_expected"])
            behavior_id = wrapper["behavior"]["artifact_id"]
            payload = load(pack / self.artifact(campaign, behavior_id)["path"])
            payload["cases"][0] = case
            updated = self.write_artifact(
                pack, campaign, behavior_id, canonical_bytes(payload)
            )
            next(
                ref for ref in wrapper["artifact_refs"] if ref["id"] == behavior_id
            ).update(updated)

        self.mutate_wrapper(pack, campaign, copied_oracle)
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "copied as independent")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)

        def zero_cases(wrapper: dict[str, Any]) -> None:
            behavior_id = wrapper["behavior"]["artifact_id"]
            payload = load(pack / self.artifact(campaign, behavior_id)["path"])
            payload["cases"] = []
            updated = self.write_artifact(
                pack, campaign, behavior_id, canonical_bytes(payload)
            )
            next(
                ref for ref in wrapper["artifact_refs"] if ref["id"] == behavior_id
            ).update(updated)
            wrapper["behavior"].update({"case_count": 0, "pass_count": 0})

        self.mutate_wrapper(pack, campaign, zero_cases)
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "zero-case behavior")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        self.mutate_wrapper(
            pack,
            campaign,
            lambda wrapper: wrapper["behavior"].update(
                {
                    "source_runtime_kind": "browser",
                    "target_runtime_kind": "browser",
                    "native_execution": True,
                }
            ),
        )
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "two-sided passing probes")

    def test_rejects_solver_linkage_fake_unsat_and_nonproof_masquerade(self) -> None:
        pack = self.copy_pack()
        _, campaign = self.campaign(pack)

        def fake_unsat(wrapper: dict[str, Any]) -> None:
            result_id = wrapper["formal"]["solver_result_artifact_id"]
            payload = load(pack / self.artifact(campaign, result_id)["path"])
            payload["stdout"] = "unsat\nsat\n"
            updated = self.write_artifact(
                pack, campaign, result_id, canonical_bytes(payload)
            )
            next(
                ref for ref in wrapper["artifact_refs"] if ref["id"] == result_id
            ).update(updated)
            wrapper["formal"]["solver_result_sha256"] = updated["sha256"]

        self.mutate_wrapper(pack, campaign, fake_unsat)
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "fake or malformed UNSAT")

        for status in ("UNKNOWN", "TIMEOUT", "NOT_RUN", "AXIOM", "BOUNDED"):
            with self.subTest(status=status):
                pack = self.copy_pack()
                _, campaign = self.campaign(pack)
                campaign["routes"][0]["formal_status"] = status

                def masquerade(wrapper: dict[str, Any]) -> None:
                    wrapper["formal"].update(
                        {
                            "status": status,
                            "composition_status": "PROVED_UNDER_ASSUMPTIONS",
                        }
                    )

                self.mutate_wrapper(pack, campaign, masquerade)
                self.save_campaign(pack, campaign)
                self.assert_invalid(pack, "solver/formal status drift")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        self.mutate_wrapper(
            pack,
            campaign,
            lambda wrapper: wrapper["formal"].update({"unconditional": True}),
        )
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "conditional/unresolved proof is unconditional")

    def test_rejects_tampered_raw_solver_result_when_all_links_are_rehashed(
        self,
    ) -> None:
        pack = self.copy_pack()
        _, campaign = self.campaign(pack)

        def tamper_raw_solver(wrapper: dict[str, Any]) -> None:
            formal = wrapper["formal"]
            normalized_id = formal["solver_result_artifact_id"]
            normalized = load(pack / self.artifact(campaign, normalized_id)["path"])
            raw_id = normalized["raw_solver_result_artifact_id"]
            layered_id = normalized["raw_layered_result_artifact_id"]

            raw = load(pack / self.artifact(campaign, raw_id)["path"])
            raw["stdout"] = "unsat\nsat\n"
            raw_ref = self.write_artifact(
                pack,
                campaign,
                raw_id,
                (json.dumps(raw, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )

            layered = load(pack / self.artifact(campaign, layered_id)["path"])
            layered["links"]["solver_result_digest"] = raw_ref["sha256"]
            layered_ref = self.write_artifact(
                pack,
                campaign,
                layered_id,
                (json.dumps(layered, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                ),
            )

            normalized.update(
                {
                    "stdout": raw["stdout"],
                    "raw_solver_result_sha256": raw_ref["sha256"],
                    "raw_layered_result_sha256": layered_ref["sha256"],
                    "raw_layered_solver_result_sha256": raw_ref["sha256"],
                }
            )
            normalized_ref = self.write_artifact(
                pack, campaign, normalized_id, canonical_bytes(normalized)
            )
            formal.update(
                {
                    "solver_result_sha256": normalized_ref["sha256"],
                    "raw_solver_result_sha256": raw_ref["sha256"],
                    "raw_layered_result_sha256": layered_ref["sha256"],
                    "raw_layered_solver_result_sha256": raw_ref["sha256"],
                }
            )
            by_id = {item["id"]: item for item in wrapper["artifact_refs"]}
            by_id[raw_id].update(raw_ref)
            by_id[layered_id].update(layered_ref)
            by_id[normalized_id].update(normalized_ref)

        self.mutate_wrapper(pack, campaign, tamper_raw_solver)
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "fake or malformed UNSAT")

    def test_rejects_stale_fingerprints_and_corpus_overlap(self) -> None:
        for field, message in (
            ("implementation", "stale implementation fingerprint"),
            ("replay", "stale replay fingerprint"),
        ):
            with self.subTest(field=field):
                pack = self.copy_pack()
                _, campaign = self.campaign(pack)
                campaign[field]["fingerprint"] = "sha256:" + "0" * 64
                self.save_campaign(pack, campaign)
                self.assert_invalid(pack, message)

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        case_id = campaign["corpora"]["development"]["case_ids"][0]
        campaign["corpora"]["negative"]["case_ids"] = [case_id]
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "corpus overlap")

    def test_generator_is_content_addressed_and_live_freshness_bound(self) -> None:
        generator_repository_path = (
            "tooling/generate_frontend_formal_verification_pack.py"
        )
        _, base_campaign = self.campaign(self.client_base)
        implementation = base_campaign["implementation"]
        manifest_ref = self.artifact(
            base_campaign, implementation["manifest_artifact_id"]
        )
        manifest = load(self.client_base / manifest_ref["path"])
        rows = {item["repository_path"]: item for item in manifest.get("files", [])}
        self.assertEqual(
            validator.REQUIRED_IMPLEMENTATION_REPOSITORY_PATHS,
            frozenset(rows),
        )
        self.assertIn(generator_repository_path, rows)

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        manifest_ref = self.artifact(
            campaign, campaign["implementation"]["manifest_artifact_id"]
        )
        manifest = load(pack / manifest_ref["path"])
        generator_row = next(
            item
            for item in manifest["files"]
            if item["repository_path"] == generator_repository_path
        )
        generator_id = generator_row["artifact_id"]
        generator_ref = self.artifact(campaign, generator_id)
        tampered = (pack / generator_ref["path"]).read_bytes() + b"\n# tampered\n"
        self.write_artifact(pack, campaign, generator_id, tampered)
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "stale implementation fingerprint")

        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        manifest_id = campaign["implementation"]["manifest_artifact_id"]
        manifest_ref = self.artifact(campaign, manifest_id)
        manifest = load(pack / manifest_ref["path"])
        generator_row = next(
            item
            for item in manifest["files"]
            if item["repository_path"] == generator_repository_path
        )
        generator_row["repository_path"] = "AGENTS.md"
        self.write_artifact(pack, campaign, manifest_id, canonical_bytes(manifest))
        self.save_campaign(pack, campaign)
        self.assert_invalid(pack, "stale implementation live repository capture")

    def test_rejects_stale_toolchain_producer_even_when_raw_artifact_is_rehashed(
        self,
    ) -> None:
        pack = self.copy_pack()
        _, campaign = self.campaign(pack)
        declaration = campaign["toolchain_evidence"]
        artifact_id = declaration["artifact_id"]
        reference = self.artifact(campaign, artifact_id)
        raw_path = pack / reference["path"]
        raw = load(raw_path)
        raw["producer"]["sha256"] = "sha256:" + "0" * 64
        content = (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self.write_artifact(pack, campaign, artifact_id, content)
        declaration["artifact_sha256"] = digest(content)
        profile_index = {item["profile"]["id"]: item for item in campaign["profiles"]}
        route_index = {item["route_id"]: item for item in campaign["routes"]}
        artifact_index = {item["id"]: item for item in campaign["artifacts"]}
        artifact_files = {
            item["id"]: pack / item["path"] for item in campaign["artifacts"]
        }
        errors: list[str] = []
        validator.validate_toolchain_evidence(
            campaign,
            profile_index,
            route_index,
            artifact_index,
            artifact_files,
            set(),
            errors,
        )
        self.assertTrue(
            any("producer" in error and "stale" in error for error in errors), errors
        )

    def test_native_trace_must_be_derived_from_full_actual_dom_route(self) -> None:
        canonical_event = {
            "operation": "SELECT_DECLARED_PATH",
            "input_path": "/account",
            "resolution": "DECLARED",
            "route": {
                "id": "route.account",
                "path": "/account",
                "title": "Account",
                "text": "Account content",
                "requiresAuth": True,
                "deepLink": False,
            },
            "render": {
                "navigationLabel": "Main navigation",
                "mainRole": "main",
                "headingLevel": 1,
            },
        }

        def run(field: str | None = None, value: object | None = None) -> list[str]:
            with tempfile.TemporaryDirectory() as directory:
                behavior_path = Path(directory) / "behavior.json"
                normalized = {
                    **canonical_event,
                    "route": dict(canonical_event["route"]),
                    "render": dict(canonical_event["render"]),
                }
                if field is not None:
                    normalized["route"][field] = value
                probes = [
                    {
                        "name": "declared-1",
                        "status": "PASSED",
                        "dom_sha256": "sha256:" + "4" * 64,
                        "normalized_observation": normalized,
                    }
                ]
                toolchain_id = "toolchain-evidence"
                source_execution_id = "sha256:" + "1" * 64
                target_execution_id = "sha256:" + "2" * 64

                def trace(execution_id: str) -> dict[str, Any]:
                    return {
                        "runtime_kind": "browser",
                        "native_execution": True,
                        "events": normalized,
                        "evidence": {
                            "toolchain_evidence_artifact_id": toolchain_id,
                            "execution_id": execution_id,
                            "probe_name": "declared-1",
                            "dom_sha256": "sha256:" + "4" * 64,
                            "normalized_observation_sha256": validator.canonical_digest(
                                normalized
                            ),
                        },
                    }

                case = {
                    "case_id": "native-case",
                    "canonical_expected": {
                        "oracle_kind": "canonical-spec",
                        "provenance_artifact_id": "canonical-oracle",
                        "events": canonical_event,
                    },
                    "independent_expected": {
                        "oracle_kind": "independent-spec",
                        "provenance_artifact_id": "independent-oracle",
                        "events": canonical_event,
                    },
                    "source_trace": trace(source_execution_id),
                    "target_trace": trace(target_execution_id),
                    "status": "PASSED",
                }
                behavior_path.write_bytes(
                    canonical_bytes(
                        {
                            "schema_version": 1,
                            "route_id": "angular--to--react",
                            "runtime_kind": "browser",
                            "cases": [case],
                        }
                    )
                )
                behavior = {
                    "artifact_id": "behavior",
                    "canonical_oracle_artifact_id": "canonical-oracle",
                    "independent_oracle_artifact_id": "independent-oracle",
                    "source_runtime_kind": "browser",
                    "target_runtime_kind": "browser",
                    "case_count": 1,
                    "pass_count": 1,
                    "status": "PASSED",
                    "native_execution": True,
                    "native_evidence_status": "PASSED",
                    "toolchain_evidence_artifact_id": toolchain_id,
                    "source_execution_id": source_execution_id,
                    "target_execution_id": target_execution_id,
                    "source_build_status": "PASSED",
                    "target_build_status": "PASSED",
                    "source_browser_status": "PASSED",
                    "target_browser_status": "PASSED",
                }
                wrapper = {
                    "source_profile_id": "angular",
                    "target_profile_id": "react",
                    "behavior": behavior,
                }
                context = {
                    "artifact_id": toolchain_id,
                    "routes": {
                        "angular--to--react": {
                            "source_execution_id": source_execution_id,
                            "target_execution_id": target_execution_id,
                            "source_build_status": "PASSED",
                            "target_build_status": "PASSED",
                            "source_browser_status": "PASSED",
                            "target_browser_status": "PASSED",
                            "native_behavior_status": "PASSED",
                        }
                    },
                    "profiles": {
                        "angular": {
                            "execution_id": source_execution_id,
                            "browser_journey": {"probes": probes},
                        },
                        "react": {
                            "execution_id": target_execution_id,
                            "browser_journey": {"probes": probes},
                        },
                    },
                }
                errors: list[str] = []
                validator.validate_behavior(
                    "angular--to--react",
                    wrapper,
                    {"behavior": {"role": "behavior-traces"}},
                    {"behavior": behavior_path},
                    {"behavior"},
                    context,
                    errors,
                )
                return errors

        self.assertEqual([], run())
        for field, value in (
            ("id", "route.admin"),
            ("path", "/admin"),
            ("requiresAuth", False),
        ):
            with self.subTest(field=field):
                errors = run(field, value)
                self.assertTrue(
                    any("actual-DOM-derived" in error for error in errors), errors
                )

    def test_experimental_gate_never_certifies_partial_campaign(self) -> None:
        pack = self.copy_pack()
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "batch32" / "run_client_gate.py"),
                str(pack),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = load(pack / "certification" / "gate-result.json")
        self.assertEqual("PASSED", result["structural_status"])
        self.assertTrue(result["bounded_proof_profile_ready"])
        self.assertFalse(result["formal_ready"])
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])


if __name__ == "__main__":
    unittest.main()
