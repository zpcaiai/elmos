import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK_KEYS = (
    "spring-boot-1-5-to-3-5-3",
    "spring-boot-1-5-to-4-1-0",
    "spring-boot-2-0-2-6-to-3-5-3",
    "spring-boot-2-0-2-6-to-4-1-0",
    "spring-boot-2-7-18-to-3-5-3",
    "spring-boot-2-7-18-to-4-1-0",
    "spring-boot-2-x-gradle-to-3-5-3",
    "spring-boot-2-x-gradle-to-4-1-0",
    "spring-boot-3-0-3-4-to-3-5-3",
    "spring-boot-3-0-3-4-to-4-1-0",
    "spring-boot-3-5-to-4-1-0",
    "spring-framework-5-3-mvc-to-boot-4-1-0",
    "spring-framework-5-3-mvc-to-spring-boot-3-5-3",
)
TRUST_STORES = (
    "certification/trust-store.json",
    "certification/batch1-37-trust-store.json",
    "certification/batch38-45-trust-store.json",
    "certification/mature-product-trust-store.json",
)
EXPERIMENTAL_NOT_RUN_GATES = (
    "source_build",
    "source_startup",
    "target_build",
    "target_startup",
    "behavior_equivalence",
    "negative_corpus",
    "holdout",
    "representative_repository",
    "performance",
    "security",
    "operability",
    "sbom",
    "rollback",
)


class SpringCertificationIntegrityTests(unittest.TestCase):
    def test_repository_owned_campaigns_are_revoked(self) -> None:
        for pack_key in PACK_KEYS:
            with self.subTest(pack=pack_key):
                pack = ROOT / "framework-packs" / pack_key
                manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
                certification = json.loads(
                    (pack / "certification/certification.json").read_text(encoding="utf-8")
                )
                evidence = json.loads(
                    (pack / "certification/evidence.json").read_text(encoding="utf-8")
                )
                support = json.loads(
                    (pack / "support-matrix.json").read_text(encoding="utf-8")
                )
                expected = "limited" if pack_key == "spring-boot-2-7-18-to-3-5-3" else "experimental"
                self.assertEqual(expected, manifest["status"])
                self.assertEqual(expected, certification["status"])
                self.assertEqual("NOT_CERTIFIED", certification["certification_decision"])
                self.assertEqual("NOT_RUN", evidence["external_execution_status"])
                self.assertFalse((pack / "certification/external-admission.json").exists())
                self.assertFalse(
                    (pack / "certification/campaign-runs/actor-ethan-certified").exists()
                )
                self.assertNotIn(
                    "certified", {item.get("status") for item in support["capabilities"]}
                )

                if expected == "experimental" and pack_key != (
                    "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
                ):
                    for gate in EXPERIMENTAL_NOT_RUN_GATES:
                        self.assertEqual("NOT_RUN", certification["gate_results"][gate])
                    self.assertEqual([], evidence["runs"])
                    self.assertTrue(
                        all(value is None for value in evidence["metrics"].values())
                    )

    def test_no_private_pem_exists_in_repository_snapshot(self) -> None:
        private_keys = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*.pem")
            if "private" in path.name.lower()
        ]
        self.assertEqual([], private_keys)

    def test_disclosed_repository_signer_is_revoked_everywhere(self) -> None:
        def matching_records(value):
            if isinstance(value, dict):
                identity = value.get("signer_id") or value.get("keyId")
                if identity == "ethan-independent-certifier":
                    yield value
                for child in value.values():
                    yield from matching_records(child)
            elif isinstance(value, list):
                for child in value:
                    yield from matching_records(child)

        for relative in TRUST_STORES:
            with self.subTest(trust_store=relative):
                document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                records = list(matching_records(document))
                self.assertTrue(records)
                self.assertTrue(all(record.get("revoked") is True for record in records))

    def test_revocation_migration_is_idempotent(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/batch30/revoke_repository_spring_certifications.py"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual([], json.loads(completed.stdout)["changed_paths"])

    def test_campaign_executor_rejects_repository_trust_material(self) -> None:
        command = [
            sys.executable,
            str(ROOT / "scripts/batch30/execute_spring_certification_campaign.py"),
            str(ROOT / "framework-packs/spring-boot-2-7-18-to-3-5-3"),
            "--external-intake",
            str(ROOT / "framework-packs/spring-boot-2-7-18-to-3-5-3/pack.json"),
            "--trust-store",
            str(ROOT / "framework-packs/spring-boot-2-7-18-to-3-5-3/pack.json"),
            "--evidence-root",
            str(ROOT / "framework-packs/spring-boot-2-7-18-to-3-5-3"),
        ]
        completed = subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True, check=False
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("outside the repository", completed.stderr)

    def test_dossier_assembler_rejects_repository_output(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/batch30/assemble_spring_dossier.py"),
                "--output-dir",
                str(ROOT / "certification/dossiers/unsafe"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("outside the repository", completed.stderr)

    def test_dossier_assembler_emits_only_an_unsigned_external_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "request"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/batch30/assemble_spring_dossier.py"),
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            manifest = json.loads(
                (output / "dossier-manifest.json").read_text(encoding="utf-8")
            )
            request = json.loads(
                (output / "certification-request.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["dossier_sha256"], request["dossier_sha256"])
            claimed = manifest.pop("dossier_sha256")
            canonical = json.dumps(
                manifest,
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
            self.assertEqual("sha256:" + hashlib.sha256(canonical).hexdigest(), claimed)
            self.assertEqual(
                "CANONICAL_JSON_WITHOUT_DOSSIER_SHA256",
                manifest["dossier_digest_scope"],
            )
            self.assertEqual("UNSIGNED", request["request_status"])
            self.assertIsNone(request["signer_id"])
            self.assertEqual([], list(output.rglob("*.pem")))

    def test_batch30_lock_is_available_on_this_platform(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "batch30_file_lock", ROOT / "scripts/batch30/file_lock.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            descriptor = os.open(Path(temporary) / "lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                module.lock_exclusive(descriptor)
                module.unlock(descriptor)
            finally:
                os.close(descriptor)

    def test_legacy_mvc_evidence_replay_is_platform_stable(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/batch30/validate_legacy_spring_mvc_pack.py"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("PASSED_LOCAL_EXACT_FIXTURE", completed.stdout)
        self.assertIn("NOT_CERTIFIED", completed.stdout)


if __name__ == "__main__":
    unittest.main()
