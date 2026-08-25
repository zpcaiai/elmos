from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copy2, copytree
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch35"


def run_command(command, **kwargs):
    check = kwargs.pop("check", False)
    return subprocess.run(command, check=check, **kwargs)


def load(p):
    return json.loads(Path(p).read_text())


def write(p, o):
    Path(p).write_text(json.dumps(o, indent=2) + "\n")


def complete_pack(pack):
    m = load(pack / "pack.json")
    m["owner"] = "verification-team"
    m["maintenance_owner"] = "quality-team"
    m["scope"].update(
        {
            "source_artifact_digest": "sha256:source",
            "target_artifact_digest": "sha256:target",
            "environment_digest": "sha256:env",
        }
    )
    write(pack / "pack.json", m)
    c = load(pack / "certification/certification.json")
    c["owner"] = "quality-team"
    c["exact_scope"] = m["scope"]
    write(pack / "certification/certification.json", c)
    for d in ["corpus/negative", "corpus/holdout", "corpus/representative-workloads"]:
        (pack / d / "sample.txt").write_text("evidence\n")
    (pack / "certification/sample-evidence.txt").write_text("evidence\n")


def refresh_integrity_manifest(pack):
    manifest = load(pack / "certification/evidence-manifest.json")
    for entry in manifest["entries"]:
        content = (pack / entry["path"]).read_bytes()
        entry.update(
            {"byte_size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
    write(pack / "certification/evidence-manifest.json", manifest)


def materialize_bound_repository(pack, repository):
    evidence = load(pack / "certification/evidence.json")
    for record_ref in evidence.get("repository_binding_records", []):
        record = load(pack / record_ref)
        for binding in record.get("repository_bindings", []):
            source = ROOT / binding["path"]
            target = repository / binding["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(source, target)


def forge_repository_certification_claim(pack):
    manifest = load(pack / "pack.json")
    manifest["status"] = "certified"
    for field in [
        "controlled_public_dns_rebinding_campaign",
        "independent_holdout",
        "representative_production_workload",
    ]:
        manifest["scope"][field] = "passed"
    write(pack / "pack.json", manifest)
    certification = load(pack / "certification/certification.json")
    certification.update(
        {
            "status": "certified",
            "exact_scope": manifest["scope"],
            "approved_at": "2026-08-11T00:00:00Z",
        }
    )
    evidence = load(pack / "certification/evidence.json")
    for document in [certification, evidence]:
        document["metrics"]["representative_workload_pass_rate"] = 1.0
        document["metrics"]["assurance_claim_support_rate"] = 1.0
    evidence["zero_tolerance"].update(
        {"critical_unknown_obligations": 0, "unsupported_p0_claims": 0}
    )
    write(pack / "certification/certification.json", certification)
    write(pack / "certification/evidence.json", evidence)
    profile = load(pack / "validation-profile.json")
    profile["approvals"] = ["self-declared-profile-approval"]
    write(pack / "validation-profile.json", profile)
    oracles = load(pack / "oracle-registry.json")
    oracles["approvals"] = ["self-declared-oracle-approval"]
    oracles["oracles"][0]["independence"] = "independent"
    write(pack / "oracle-registry.json", oracles)
    assurance = load(pack / "assurance/assurance-case.json")
    assurance["approvals"] = ["self-declared-assurance-approval"]
    assurance["claims"][0]["status"] = "supported"
    write(pack / "assurance/assurance-case.json", assurance)
    holdout = load(pack / "corpus/holdout/manifest.json")
    holdout.update(
        {
            "independence": "independently-verified",
            "independent_verifier": "self-declared-verifier",
        }
    )
    write(pack / "corpus/holdout/manifest.json", holdout)
    representative = load(pack / "corpus/representative-workloads/manifest.json")
    authorization_path = "certification/representative-authorization.json"
    authorization = {
        "schema_version": 1,
        "authorization_id": "self-declared-authorization",
        "status": "approved",
        "pack_key": manifest["pack_key"],
        "source_digest": manifest["scope"]["source_artifact_digest"],
        "dataset_digest": representative["dataset_digest"],
        "workload_key": manifest["scope"]["workload_key"],
        "authorized_by": "self-declared-authorizer",
        "approved_at": "2026-08-11T00:00:00Z",
    }
    write(pack / authorization_path, authorization)
    representative.update(
        {
            "provenance": "production-derived",
            "authorization_ref": authorization_path,
        }
    )
    write(pack / "corpus/representative-workloads/manifest.json", representative)
    evidence_manifest = load(pack / "certification/evidence-manifest.json")
    authorization_bytes = (pack / authorization_path).read_bytes()
    evidence_manifest["entries"].append(
        {
            "path": authorization_path,
            "byte_size": len(authorization_bytes),
            "sha256": hashlib.sha256(authorization_bytes).hexdigest(),
        }
    )
    evidence_manifest["entries"].sort(key=lambda entry: entry["path"])
    write(pack / "certification/evidence-manifest.json", evidence_manifest)
    refresh_integrity_manifest(pack)


class Tests(unittest.TestCase):
    def test_skill_bundle(self):
        run_command(
            [
                sys.executable,
                str(SCRIPTS / "validate_skill_bundle.py"),
                str(ROOT / ".agents/skills"),
            ],
            check=True,
        )

    def test_schemas_templates(self):
        import jsonschema

        for p in sorted((ROOT / "schemas/batch35").glob("*.schema.json")):
            jsonschema.validators.validator_for(load(p)).check_schema(load(p))
        pairs = [
            ("verification-pack.json", "verification-pack.schema.json"),
            ("support-matrix.json", "verification-support-matrix.schema.json"),
            ("validation-profile.json", "validation-profile.schema.json"),
            ("oracle-registry.json", "oracle-registry.schema.json"),
            ("property-spec.json", "property-spec.schema.json"),
            ("metamorphic-relation.json", "metamorphic-relation.schema.json"),
            ("mutation-campaign.json", "mutation-campaign.schema.json"),
            ("fuzz-campaign.json", "fuzz-campaign.schema.json"),
            ("model-spec.json", "model-spec.schema.json"),
            ("solver-proof.json", "solver-proof.schema.json"),
            ("counterexample.json", "counterexample.schema.json"),
            ("assurance-case.json", "assurance-case.schema.json"),
            ("certification.json", "verification-certification.schema.json"),
        ]
        for t, s in pairs:
            jsonschema.validate(
                load(ROOT / "templates/batch35" / t), load(ROOT / "schemas/batch35" / s)
            )

    def test_scaffold_validate(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_verification_pack.py"),
                    "--pack-key",
                    "payment-verification",
                    "--migration-route",
                    "java-to-csharp",
                    "--workload-key",
                    "payment",
                    "--repo-root",
                    str(repo),
                ],
                check=True,
            )
            pack = repo / "verification-packs/payment-verification"
            complete_pack(pack)
            run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ],
                check=True,
            )

    def test_oracle_rejects_authoritative_llm(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "o.json"
            o = load(ROOT / "templates/batch35/oracle-registry.json")
            o["oracles"][0].update(
                {"type": "llm-advisory", "trust_level": "authoritative"}
            )
            write(p, o)
            self.assertEqual(
                run_command(
                    [
                        sys.executable,
                        str(SCRIPTS / "validate_oracle_registry.py"),
                        str(p),
                    ]
                ).returncode,
                1,
            )

    def test_model_rejects_unknown_state(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.json"
            m = load(ROOT / "templates/batch35/model-spec.json")
            m["commands"][0]["to"] = "missing"
            write(p, m)
            self.assertEqual(
                run_command(
                    [sys.executable, str(SCRIPTS / "validate_model_spec.py"), str(p)]
                ).returncode,
                1,
            )

    def test_candidate_scoring(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "score_verification_candidates.py"),
                    str(ROOT / "templates/batch35/verification-candidates.json"),
                    "--output",
                    str(out),
                ],
                check=True,
            )
            self.assertEqual(load(out)["results"][0]["decision"], "approve")

    def test_gate_rejects_fake_certification(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_verification_pack.py"),
                    "--pack-key",
                    "payment-verification",
                    "--migration-route",
                    "java-to-csharp",
                    "--workload-key",
                    "payment",
                    "--repo-root",
                    str(repo),
                ],
                check=True,
            )
            pack = repo / "verification-packs/payment-verification"
            complete_pack(pack)
            m = load(pack / "pack.json")
            m["status"] = "certified"
            write(pack / "pack.json", m)
            c = load(pack / "certification/certification.json")
            c["status"] = "certified"
            write(pack / "certification/certification.json", c)
            self.assertEqual(
                run_command(
                    [
                        sys.executable,
                        str(SCRIPTS / "run_verification_gate.py"),
                        str(pack),
                    ]
                ).returncode,
                2,
            )

    def test_research_gate_is_explicitly_not_certified(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_verification_pack.py"),
                    "--pack-key",
                    "research-verification",
                    "--migration-route",
                    "local-regression",
                    "--workload-key",
                    "sample",
                    "--repo-root",
                    str(repo),
                ],
                check=True,
            )
            pack = repo / "verification-packs/research-verification"
            complete_pack(pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_decision"], "NOT_CERTIFIED")
            self.assertFalse(result["certification_requested"])
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertTrue(result["certification_blockers"])

    def test_gate_reports_independence_and_production_provenance_blockers(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            blockers = load(pack / "certification/gate-result.json")[
                "certification_blockers"
            ]
            self.assertIn("holdout corpus is not independently verified", blockers)
            self.assertIn(
                "representative workload corpus is not production-derived", blockers
            )
            self.assertIn(
                "P0 claim claim.source-boundaries has no independent external oracle evidence",
                blockers,
            )

    def test_gate_links_unresolved_proof_to_its_p0_property(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            profile = load(pack / "validation-profile.json")
            profile["techniques"].append("solver")
            write(pack / "validation-profile.json", profile)
            # The copied evidence manifest must bind the deliberately changed profile so
            # the gate reaches proof evaluation instead of failing only on stale bytes.
            manifest = load(pack / "certification/evidence-manifest.json")
            entry = (
                next(
                    item
                    for item in manifest["entries"]
                    if item["path"] == "validation-profile.json"
                )
                if any(
                    item["path"] == "validation-profile.json"
                    for item in manifest["entries"]
                )
                else None
            )
            if entry:
                content = (pack / "validation-profile.json").read_bytes()
                entry.update(
                    {
                        "byte_size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
                write(pack / "certification/evidence-manifest.json", manifest)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            self.assertIn(
                "required P0 property proof is not proved",
                load(pack / "certification/gate-result.json")["certification_blockers"],
            )

    def test_disproved_proof_cannot_prepare_external_gate(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            profile = load(pack / "validation-profile.json")
            profile["techniques"].append("solver")
            write(pack / "validation-profile.json", profile)
            proof = load(pack / "solver/proof.json")
            proof["status"] = "disproved"
            write(pack / "solver/proof.json", proof)
            refresh_integrity_manifest(pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn(
                "required P0 property proof is not proved",
                result["certification_blockers"],
            )

    def test_unknown_technique_and_missing_scope_do_not_prepare_readiness(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            profile = load(pack / "validation-profile.json")
            profile["techniques"].append("unregistered-technique")
            write(pack / "validation-profile.json", profile)
            refresh_integrity_manifest(pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            self.assertIn(
                "unknown required verification technique: unregistered-technique",
                load(pack / "certification/gate-result.json")["certification_blockers"],
            )
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            manifest = load(pack / "pack.json")
            del manifest["scope"]["controlled_public_dns_rebinding_campaign"]
            write(pack / "pack.json", manifest)
            certification = load(pack / "certification/certification.json")
            certification["exact_scope"] = manifest["scope"]
            write(pack / "certification/certification.json", certification)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertTrue(
                any(
                    blocker.startswith(
                        "scope controlled_public_dns_rebinding_campaign must be passed"
                    )
                    for blocker in result["certification_blockers"]
                )
            )

    def test_gate_rejects_mismatched_p0_proof_identity(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            profile = load(pack / "validation-profile.json")
            profile["techniques"].append("solver")
            write(pack / "validation-profile.json", profile)
            proof = load(pack / "solver/proof.json")
            proof["property_id"] = "property.unrelated"
            write(pack / "solver/proof.json", proof)
            refresh_integrity_manifest(pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            self.assertIn(
                "required P0 property proof identity does not match",
                load(pack / "certification/gate-result.json")["certification_blockers"],
            )

    def test_missing_independent_oracle_evidence_is_rejected(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            registry = load(pack / "oracle-registry.json")
            registry["oracles"][0].update(
                {
                    "independence": "independent",
                    "evidence_refs": ["does-not-exist.json"],
                }
            )
            write(pack / "oracle-registry.json", registry)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn(
                "P0 claim claim.source-boundaries has no independent external oracle evidence",
                result["certification_blockers"],
            )

    def test_missing_required_oracle_is_rejected(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            registry = load(pack / "oracle-registry.json")
            registry["oracles"] = registry["oracles"][:1]
            write(pack / "oracle-registry.json", registry)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertTrue(
                any(
                    "references missing required oracles" in blocker
                    for blocker in result["certification_blockers"]
                )
            )

    def test_repository_json_cannot_self_issue_certification(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 0)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_decision"], "NOT_CERTIFIED")
            self.assertEqual(
                result["certification_readiness"], "READY_FOR_EXTERNAL_GATE"
            )
            self.assertEqual(
                result["maximum_local_decision"], "READY_FOR_EXTERNAL_GATE"
            )
            local_result = pack / "certification/local-test-result.json"
            local_result.write_text(local_result.read_text() + "tampered\n")
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_decision"], "BLOCKED")
            self.assertEqual(result["certification_readiness"], "BLOCKED")

    def test_incomplete_evaluation_replaces_stale_ready_result(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            self.assertEqual(
                load(pack / "certification/gate-result.json")[
                    "certification_readiness"
                ],
                "READY_FOR_EXTERNAL_GATE",
            )
            (pack / "pack.json").write_text("{\n")
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_decision"], "BLOCKED")
            self.assertEqual(result["certification_readiness"], "BLOCKED")

    def test_missing_integrity_manifest_blocks_readiness(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            evidence = load(pack / "certification/evidence.json")
            del evidence["integrity_manifest"]
            write(pack / "certification/evidence.json", evidence)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn(
                "content-addressed evidence manifest is required",
                result["certification_blockers"],
            )

    def test_validator_rejects_escaping_control_references(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pack = root / source.name
            copytree(source, pack)
            outside = root / "outside.json"
            write(outside, {"status": "passed"})
            evidence = load(pack / "certification/evidence.json")
            evidence["integrity_manifest"] = "../outside.json"
            write(pack / "certification/evidence.json", evidence)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)

    def test_validator_rejects_symlinked_binding_record(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pack = root / source.name
            copytree(source, pack)
            outside = root / "outside.json"
            write(outside, {"status": "passed"})
            link = pack / "certification/linked-record.json"
            link.symlink_to(outside)
            evidence = load(pack / "certification/evidence.json")
            evidence["repository_binding_records"] = [
                "certification/linked-record.json"
            ]
            write(pack / "certification/evidence.json", evidence)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)

    def test_gate_refuses_symlinked_output_targets(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        for output_name in ("gate-result.json", "gate-report.md"):
            with (
                self.subTest(output_name=output_name),
                tempfile.TemporaryDirectory() as d,
            ):
                root = Path(d)
                pack = root / source.name
                copytree(source, pack)
                outside = root / "outside.txt"
                outside.write_text("sentinel\n")
                output = pack / "certification" / output_name
                output.unlink()
                output.symlink_to(outside)
                completed = run_command(
                    [
                        sys.executable,
                        str(SCRIPTS / "run_verification_gate.py"),
                        str(pack),
                    ]
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(outside.read_text(), "sentinel\n")

    def test_manifest_only_corpus_is_not_data_evidence(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            (pack / "corpus/holdout/cases.json").unlink()
            corpus = load(pack / "corpus/holdout/manifest.json")
            corpus["evidence_refs"] = ["certification/local-test-result.json"]
            write(pack / "corpus/holdout/manifest.json", corpus)
            manifest = load(pack / "certification/evidence-manifest.json")
            manifest["entries"] = [
                entry
                for entry in manifest["entries"]
                if entry["path"] != "corpus/holdout/cases.json"
            ]
            write(pack / "certification/evidence-manifest.json", manifest)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            blockers = load(pack / "certification/gate-result.json")[
                "certification_blockers"
            ]
            self.assertIn(
                "holdout corpus dataset_digest does not match a content-bound corpus data ref",
                blockers,
            )

    def test_corpus_digest_must_be_exact_and_match_data(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            corpus = load(pack / "corpus/negative/manifest.json")
            corpus["dataset_digest"] = "sha256:x"
            write(pack / "corpus/negative/manifest.json", corpus)
            refresh_integrity_manifest(pack)
            run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                check=True,
            )
            blockers = load(pack / "certification/gate-result.json")[
                "certification_blockers"
            ]
            self.assertIn(
                "negative corpus dataset_digest is not exact SHA-256", blockers
            )
            self.assertIn(
                "negative corpus dataset_digest does not match a content-bound corpus data ref",
                blockers,
            )

    def test_validator_fails_closed_without_jsonschema(self):
        pack = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        completed = run_command(
            [
                sys.executable,
                "-S",
                str(SCRIPTS / "validate_verification_pack.py"),
                str(pack),
            ]
        )
        self.assertEqual(completed.returncode, 1)

    def test_not_run_corpus_cannot_certify(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_verification_pack.py"),
                    "--pack-key",
                    "corpus-verification",
                    "--migration-route",
                    "java-to-csharp",
                    "--workload-key",
                    "payment",
                    "--repo-root",
                    str(repo),
                ],
                check=True,
            )
            pack = repo / "verification-packs/corpus-verification"
            complete_pack(pack)
            m = load(pack / "pack.json")
            m["status"] = "certified"
            write(pack / "pack.json", m)
            c = load(pack / "certification/certification.json")
            c["status"] = "certified"
            c["metrics"] = {
                k: 1.0
                for k in [
                    "property_pass_rate",
                    "metamorphic_pass_rate",
                    "mutation_score",
                    "fuzz_campaign_pass_rate",
                    "model_transition_coverage",
                    "p0_contract_pass_rate",
                    "data_money_invariant_pass_rate",
                    "security_property_pass_rate",
                    "query_equivalence_pass_rate",
                    "numeric_verification_pass_rate",
                    "counterexample_replay_pass_rate",
                    "representative_workload_pass_rate",
                    "source_map_coverage",
                    "evidence_trace_coverage",
                    "assurance_claim_support_rate",
                ]
            }
            write(pack / "certification/certification.json", c)
            for corpus_key in ["negative", "holdout", "representative-workloads"]:
                write(
                    pack / f"corpus/{corpus_key}/manifest.json",
                    {
                        "status": "not-run",
                        "source_digest": "sha256:source",
                        "dataset_digest": "sha256:data",
                        "evidence_refs": ["certification/sample-evidence.txt"],
                    },
                )
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(
                any(
                    "status must be passed" in failure
                    for failure in load(pack / "certification/gate-result.json")[
                        "failures"
                    ]
                )
            )

    def test_content_addressed_evidence_rejects_tampering(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            result = pack / "certification/local-test-result.json"
            result.write_text(result.read_text() + "tampered\n")
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)

    def test_content_addressed_contract_rejects_profile_tampering(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            profile = pack / "validation-profile.json"
            changed = load(profile)
            changed["version"] += 1
            write(profile, changed)
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)

    def test_non_finite_metrics_fail_closed(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        for forged_value in (float("nan"), float("inf"), float("-inf")):
            with (
                self.subTest(forged_value=forged_value),
                tempfile.TemporaryDirectory() as d,
            ):
                pack = Path(d) / source.name
                copytree(source, pack)
                certification = load(pack / "certification/certification.json")
                certification["metrics"]["property_pass_rate"] = forged_value
                write(pack / "certification/certification.json", certification)
                refresh_integrity_manifest(pack)
                validator = run_command(
                    [
                        sys.executable,
                        str(SCRIPTS / "validate_verification_pack.py"),
                        str(pack),
                    ]
                )
                gate = run_command(
                    [
                        sys.executable,
                        str(SCRIPTS / "run_verification_gate.py"),
                        str(pack),
                    ]
                )
                self.assertNotEqual(validator.returncode, 0)
                self.assertNotEqual(gate.returncode, 0)

    def test_fuzz_seed_corpus_is_content_bound(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            seed = pack / "corpus/development/seed.json"
            seed.write_text('{"tampered":true}\n')
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)

    def test_remote_fuzz_seed_and_external_evidence_do_not_prepare_readiness(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            campaign = load(pack / "fuzz/campaign.json")
            campaign["seed_corpus"] = ["https://example.invalid/seed.json"]
            write(pack / "fuzz/campaign.json", campaign)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            evidence = load(pack / "certification/evidence.json")
            evidence["evidence_refs"] = ["https://example.invalid/evidence.json"]
            write(pack / "certification/evidence.json", evidence)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn(
                "external evidence ref is not locally content-bound: https://example.invalid/evidence.json",
                result["certification_blockers"],
            )

    def test_binding_counts_and_zero_tolerance_conflicts_fail_closed(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            record = load(pack / "certification/local-test-result.json")
            record["tests"] = True
            write(pack / "certification/local-test-result.json", record)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            certification = load(pack / "certification/certification.json")
            certification["zero_tolerance"] = {"security_property_violations": 0}
            write(pack / "certification/certification.json", certification)
            evidence = load(pack / "certification/evidence.json")
            evidence["zero_tolerance"]["security_property_violations"] = 1
            write(pack / "certification/evidence.json", evidence)
            refresh_integrity_manifest(pack)
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")

    def test_local_test_count_must_match_bound_result(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            evidence = load(pack / "certification/evidence.json")
            evidence["metrics"]["local_tests"] += 1
            write(pack / "certification/evidence.json", evidence)
            manifest = load(pack / "certification/evidence-manifest.json")
            entry = next(
                item
                for item in manifest["entries"]
                if item["path"] == "certification/evidence.json"
            )
            content = (pack / "certification/evidence.json").read_bytes()
            entry.update(
                {
                    "byte_size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
            write(pack / "certification/evidence-manifest.json", manifest)
            completed = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ]
            )
            self.assertEqual(completed.returncode, 1)

    def test_repository_binding_scope_digests_are_required(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            record = load(pack / "certification/local-test-result.json")
            for field in ("source_digest", "test_digest", "environment_digest"):
                record.pop(field)
            write(pack / "certification/local-test-result.json", record)
            refresh_integrity_manifest(pack)
            validation = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(validation.returncode, 1)
            self.assertIn(
                "source_digest must be an exact SHA-256 digest", validation.stderr
            )
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn("verification pack validation failed", result["failures"])

    def test_unrelated_real_file_cannot_replace_a_scoped_binding(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            record = load(pack / "certification/local-test-result.json")
            unrelated = ROOT / "README.md"
            payload = unrelated.read_bytes()
            source_binding = next(
                binding
                for binding in record["repository_bindings"]
                if binding.get("role") == "source"
            )
            source_binding.update(
                {
                    "path": "README.md",
                    "byte_size": len(payload),
                    "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                }
            )
            record["repository_bindings"].sort(key=lambda item: item["path"])
            write(pack / "certification/local-test-result.json", record)
            refresh_integrity_manifest(pack)
            validation = run_command(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_verification_pack.py"),
                    str(pack),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(validation.returncode, 1)
            self.assertIn(
                "source_digest does not match the source repository binding",
                validation.stderr,
            )
            completed = run_command(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)]
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn("verification pack validation failed", result["failures"])

    def test_gate_fails_closed_when_original_pack_changes_after_validation(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / source.name
            copytree(source, pack)
            sys.path.insert(0, str(SCRIPTS))
            try:
                import run_verification_gate as gate
            finally:
                sys.path.pop(0)
            real_run = gate.subprocess.run

            def mutate_after_validation(*args, **kwargs):
                completed = real_run(*args, **kwargs)
                if str(args[0][1]).endswith("validate_verification_pack.py"):
                    readme = pack / "README.md"
                    readme.write_text(readme.read_text() + "concurrent mutation\n")
                return completed

            with (
                mock.patch.object(
                    gate.subprocess, "run", side_effect=mutate_after_validation
                ),
                mock.patch.object(sys, "argv", ["run_verification_gate.py", str(pack)]),
            ):
                returncode = gate.main()
            self.assertEqual(returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertIn(
                "verification pack changed during gate evaluation",
                result["failures"],
            )

    def test_repository_bound_file_drift_after_validation_is_blocked(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pack = root / "pack"
            repository = root / "repository"
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            materialize_bound_repository(pack, repository)
            sys.path.insert(0, str(SCRIPTS))
            try:
                import run_verification_gate as gate
            finally:
                sys.path.pop(0)
            real_run = gate.subprocess.run

            def mutate_repository_after_validation(*args, **kwargs):
                completed = real_run(*args, **kwargs)
                if str(args[0][1]).endswith("validate_verification_pack.py"):
                    bound = (
                        repository
                        / "apps/web-console/app/lib/server/generationSourceIngestion.ts"
                    )
                    bound.write_text(bound.read_text() + "\n// concurrent drift\n")
                return completed

            with (
                mock.patch.object(
                    gate.subprocess,
                    "run",
                    side_effect=mutate_repository_after_validation,
                ),
                mock.patch.object(sys, "argv", ["run_verification_gate.py", str(pack)]),
            ):
                returncode = gate.main(repository_root=repository)
            self.assertEqual(returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_decision"], "BLOCKED")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertTrue(
                any(
                    "repository binding evaluation failed" in failure
                    or "repository binding changed" in failure
                    for failure in result["failures"]
                )
            )

    def test_final_output_write_window_drift_leaves_machine_result_blocked(self):
        source = ROOT / "verification-packs/elmos-project-generation-source-ingestion"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pack = root / "pack"
            repository = root / "repository"
            copytree(source, pack)
            forge_repository_certification_claim(pack)
            materialize_bound_repository(pack, repository)
            sys.path.insert(0, str(SCRIPTS))
            try:
                import run_verification_gate as gate
            finally:
                sys.path.pop(0)
            real_write = gate.write_gate_output
            writes = 0

            def mutate_during_final_writes(*args, **kwargs):
                nonlocal writes
                real_write(*args, **kwargs)
                writes += 1
                if writes == 3:
                    readme = pack / "README.md"
                    readme.write_text(readme.read_text() + "final write drift\n")

            with (
                mock.patch.object(
                    gate, "write_gate_output", side_effect=mutate_during_final_writes
                ),
                mock.patch.object(sys, "argv", ["run_verification_gate.py", str(pack)]),
            ):
                returncode = gate.main(repository_root=repository)
            self.assertEqual(returncode, 2)
            result = load(pack / "certification/gate-result.json")
            self.assertEqual(result["certification_decision"], "BLOCKED")
            self.assertEqual(result["certification_readiness"], "BLOCKED")
            self.assertRegex(
                result["evaluated_pack_digest"], r"^sha256:[0-9a-f]{64}$"
            )
            self.assertIn(
                "verification pack changed while final gate outputs were written",
                result["failures"],
            )

    def test_existing_three_line_pack_keeps_exact_scope_binding(self):
        pack = ROOT / "verification-packs/elmos-three-line-workflow-protocol"
        completed = run_command(
            [sys.executable, str(SCRIPTS / "validate_verification_pack.py"), str(pack)]
        )
        self.assertEqual(completed.returncode, 0)

    def test_repository_binding_rejects_source_drift(self):
        verifier = ROOT / "scripts/verify_evidence_manifest.py"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            pack = repo / "pack"
            pack.mkdir()
            source = repo / "source.txt"
            source.write_text("safe\n")
            content = source.read_bytes()
            record = pack / "record.json"
            write(
                record,
                {
                    "repository_bindings": [
                        {
                            "path": "source.txt",
                            "byte_size": len(content),
                            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                        }
                    ]
                },
            )
            manifest = pack / "manifest.json"
            run_command(
                [
                    sys.executable,
                    str(verifier),
                    str(pack),
                    str(manifest),
                    "--write",
                    "--include",
                    "record.json",
                ],
                check=True,
            )
            source.write_text("drifted\n")
            completed = run_command(
                [
                    sys.executable,
                    str(verifier),
                    str(pack),
                    str(manifest),
                    "--repository-root",
                    str(repo),
                    "--binding-record",
                    str(record),
                ]
            )
            self.assertEqual(completed.returncode, 1)


if __name__ == "__main__":
    unittest.main()
