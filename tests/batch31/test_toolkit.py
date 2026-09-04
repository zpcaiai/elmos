import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch31"


class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_skill_bundle.py"),
                str(ROOT / ".agents" / "skills"),
            ],
            check=True,
        )

    def test_schemas_and_templates(self):
        import jsonschema

        for schema_path in sorted((ROOT / "schemas" / "batch31").glob("*.schema.json")):
            schema = json.loads(schema_path.read_text())
            jsonschema.validators.validator_for(schema).check_schema(schema)
        pairs = [
            ("database-pack.json", "database-pack.schema.json"),
            ("support-matrix.json", "database-support-matrix.schema.json"),
            ("workload-fingerprint.json", "workload-fingerprint.schema.json"),
            ("canonical-db-ir.json", "canonical-db-ir.schema.json"),
            ("target-profile.json", "database-target-profile.schema.json"),
            ("data-migration-plan.json", "data-migration-plan.schema.json"),
            ("evidence.json", "database-evidence.schema.json"),
            ("certification.json", "database-certification.schema.json"),
        ]
        for template, schema in pairs:
            data = json.loads((ROOT / "templates" / "batch31" / template).read_text())
            sch = json.loads((ROOT / "schemas" / "batch31" / schema).read_text())
            jsonschema.validate(data, sch)

        launch_scope = json.loads(
            (ROOT / "docs/batch31/sql-line-launch-scope.json").read_text()
        )
        launch_schema = json.loads(
            (ROOT / "schemas/batch31/sql-line-launch-scope.schema.json").read_text()
        )
        jsonschema.validate(launch_scope, launch_schema)
        backlog = json.loads(
            (ROOT / "docs/batch31/evidence/sql-manual-review-backlog.json").read_text()
        )
        backlog_schema = json.loads(
            (ROOT / "schemas/batch31/manual-review-backlog.schema.json").read_text()
        )
        jsonschema.validate(backlog, backlog_schema)
        self.assertEqual(backlog["summary"]["total"], len(backlog["items"]))
        closure = json.loads(
            (ROOT / "docs/batch31/evidence/sql-route-closure-plan.json").read_text()
        )
        closure_schema = json.loads(
            (ROOT / "schemas/batch31/sql-route-closure-plan.schema.json").read_text()
        )
        jsonschema.validate(closure, closure_schema)
        self.assertEqual(
            closure["current"]["targetRouteCells"],
            closure["current"]["admittedCandidateUnits"] * 4,
        )
        self.assertEqual(
            closure["current"]["targetRouteCells"],
            closure["current"]["emittableRouteCells"]
            + closure["current"]["blockedRouteCells"],
        )
        self.assertEqual(
            closure["current"]["frozenSourceUnits"],
            closure["current"]["admittedCandidateUnits"]
            + closure["current"]["manualMigrationItems"]
            + closure["current"]["sourceFormatReviewItems"],
        )

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_database_pack.py"),
                    "--source-engine",
                    "oracle",
                    "--target-engine",
                    "postgresql",
                    "--source-version",
                    "19.22",
                    "--target-version",
                    "16.4",
                    "--source-edition",
                    "enterprise",
                    "--target-edition",
                    "community",
                    "--repo-root",
                    str(repo),
                ],
                check=True,
            )
            pack = repo / "database-packs" / "oracle-to-postgresql"
            m = json.loads((pack / "pack.json").read_text())
            m["owner"] = "database-team"
            m["maintenance_owner"] = "database-team"
            m["data_owner"] = "order-data-owner"
            m["source"]["driver_versions"] = ["ojdbc11-23.4"]
            m["source"]["charset"] = "AL32UTF8"
            m["source"]["collation"] = "BINARY"
            m["target"]["driver_versions"] = ["npgsql-8.0"]
            m["target"]["charset"] = "UTF8"
            m["target"]["collation"] = "C"
            (pack / "pack.json").write_text(json.dumps(m, indent=2) + "\n")
            s = json.loads((pack / "support-matrix.json").read_text())
            for cap in s["capabilities"]:
                cap["owner"] = "database-team"
            (pack / "support-matrix.json").write_text(json.dumps(s, indent=2) + "\n")
            p = json.loads((pack / "target-profile" / "profile.json").read_text())
            p["owner"] = "database-team"
            p["driver_versions"] = ["npgsql-8.0"]
            p["charset"] = "UTF8"
            p["collation"] = "C"
            p["provision"] = {
                "commands": ["docker compose up postgres"],
                "image_digests": ["sha256:test"],
            }
            (pack / "target-profile" / "profile.json").write_text(
                json.dumps(p, indent=2) + "\n"
            )
            d = json.loads(
                (pack / "migration" / "data-migration-plan.json").read_text()
            )
            d["owner"] = "data-team"
            d["source"] = m["source"]
            d["target"] = m["target"]
            d["rollback"] = {"strategy": "restore-source-authority"}
            (pack / "migration" / "data-migration-plan.json").write_text(
                json.dumps(d, indent=2) + "\n"
            )
            fingerprint = json.loads(
                (pack / "source-fingerprint" / "manifest.json").read_text()
            )
            fingerprint["snapshot_digest"] = "sha256:" + "a" * 64
            (pack / "source-fingerprint" / "manifest.json").write_text(
                json.dumps(fingerprint, indent=2) + "\n"
            )
            ir = json.loads((pack / "canonical-ir" / "model.json").read_text())
            ir["source_snapshot_digest"] = fingerprint["snapshot_digest"]
            (pack / "canonical-ir" / "model.json").write_text(
                json.dumps(ir, indent=2) + "\n"
            )
            route = json.loads((pack / "route-matrix.json").read_text())
            route["tuples"][0]["source"] = m["source"]
            route["tuples"][0]["target"] = m["target"]
            (pack / "route-matrix.json").write_text(json.dumps(route, indent=2) + "\n")
            cert = json.loads(
                (pack / "certification" / "certification.json").read_text()
            )
            cert["exact_tuple"] = {"source": m["source"], "target": m["target"]}
            (pack / "certification" / "certification.json").write_text(
                json.dumps(cert, indent=2) + "\n"
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_database_pack.py"), str(pack)],
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_canonical_ir.py"),
                    str(pack / "canonical-ir" / "model.json"),
                ],
                check=True,
            )

    def test_candidate_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "candidates.json"
            out = td / "result.json"
            src.write_text(
                json.dumps(
                    {
                        "weights": {
                            "customer_demand": 2,
                            "migration_value": 2,
                            "data_risk": -1,
                        },
                        "candidates": [
                            {
                                "pack_key": "oracle-to-postgresql",
                                "customer_demand": 4,
                                "migration_value": 4,
                                "data_risk": 1,
                                "evidence_notes": ["design partner"],
                            }
                        ],
                    }
                )
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "score_database_candidates.py"),
                    str(src),
                    "--output",
                    str(out),
                ],
                check=True,
            )
            self.assertEqual(
                json.loads(out.read_text())["results"][0]["decision"], "approve"
            )

    def test_conservative_gate_rejects_fake_certification(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "sqlite-3-53-3-to-postgresql-17-5"
            shutil.copytree(ROOT / "database-packs" / pack.name, pack)
            m = json.loads((pack / "pack.json").read_text())
            m["status"] = "certified"
            (pack / "pack.json").write_text(json.dumps(m, indent=2) + "\n")
            s = json.loads((pack / "support-matrix.json").read_text())
            for cap in s["capabilities"]:
                cap["status"] = "certified"
            (pack / "support-matrix.json").write_text(json.dumps(s, indent=2) + "\n")
            route = json.loads((pack / "route-matrix.json").read_text())
            route["tuples"][0]["status"] = "certified"
            (pack / "route-matrix.json").write_text(json.dumps(route, indent=2) + "\n")
            c = json.loads((pack / "certification" / "certification.json").read_text())
            c["status"] = "certified"
            (pack / "certification" / "certification.json").write_text(
                json.dumps(c, indent=2) + "\n"
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_database_gate.py"), str(pack)],
                check=False,
            )
            self.assertEqual(result.returncode, 2)

    def test_gate_rejects_tampered_evidence_digest(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "sqlite-3-53-3-to-postgresql-17-5"
            shutil.copytree(ROOT / "database-packs" / pack.name, pack)
            evidence = pack / "certification" / "local-engine-evidence.json"
            evidence.write_text(evidence.read_text() + "\n")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_database_gate.py"), str(pack)],
                check=False,
            )
            self.assertEqual(result.returncode, 2)

    def test_release_gate_blocks_engineering_only_pack(self):
        pack = ROOT / "database-packs" / "sqlite-3-53-3-to-postgresql-17-5"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_database_gate.py"),
                str(pack),
                "--require-release-ready",
            ],
            check=False,
        )
        self.assertEqual(result.returncode, 3)

    def test_validator_executes_formal_support_schema(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "sqlite-3-53-3-to-postgresql-17-5"
            shutil.copytree(ROOT / "database-packs" / pack.name, pack)
            support = json.loads((pack / "support-matrix.json").read_text())
            support["capabilities"][0].pop("domain")
            (pack / "support-matrix.json").write_text(
                json.dumps(support, indent=2) + "\n"
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_database_pack.py"), str(pack)],
                check=False,
            )
            self.assertEqual(result.returncode, 1)

    def test_manual_review_backlog_is_complete_stable_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "scan.json"
            output = root / "backlog.json"
            report.write_text(
                json.dumps(
                    {
                        "disposition_counts": {"MANUAL_MIGRATION_REQUIRED": 1},
                        "findings": [
                            {
                                "source_path": "V1__sample.sql",
                                "statement_index": 7,
                                "reason_code": "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                                "reason": "routine needs a typed hand port",
                                "family": "structure",
                                "excerpt": "CREATE FUNCTION sample()",
                                "disposition": "MANUAL_MIGRATION_REQUIRED",
                            },
                            {
                                "source_path": "V1__sample.sql",
                                "statement_index": 8,
                                "reason_code": "NONE",
                                "reason": "supported",
                                "family": None,
                                "excerpt": "CREATE TABLE sample(id int)",
                                "disposition": "AUTOMATED_TRANSLATION_CANDIDATE",
                            },
                        ],
                    }
                )
            )
            command = [
                sys.executable,
                str(SCRIPTS / "build_manual_review_backlog.py"),
                str(report),
                "--output",
                str(output),
            ]
            subprocess.run(command, check=True)
            backlog = json.loads(output.read_text())
            self.assertEqual(backlog["summary"]["total"], 1)
            self.assertTrue(backlog["summary"]["release_blocked"])
            self.assertEqual(backlog["items"][0]["status"], "OPEN")
            first_id = backlog["items"][0]["finding_id"]

            regenerated = root / "regenerated.json"
            subprocess.run(command[:-1] + [str(regenerated)], check=True)
            self.assertEqual(
                json.loads(regenerated.read_text())["items"][0]["finding_id"],
                first_id,
            )
            closed = subprocess.run(command + ["--require-closed"], check=False)
            self.assertEqual(closed.returncode, 3)


if __name__ == "__main__":
    unittest.main()
