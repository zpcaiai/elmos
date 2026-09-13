from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.certification.ethan_external_exchange import (
    PROTOCOL,
    ROOT,
    ExchangeError,
    _ensure_external_output,
    canonical_bytes,
    digest_bytes,
    public_key_fingerprint,
    validate_plan,
    verify_response_bundle,
)


NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class EthanExternalExchangeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ethan-exchange-fixture-")
        self.root = Path(self.temporary.name)
        self.private_key = self.root / "fixture.private.pem"
        self.public_key = self.root / "fixture.public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.private_key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(self.private_key),
                "-pubout",
                "-out",
                str(self.public_key),
            ],
            check=True,
            capture_output=True,
        )
        self.fingerprint = public_key_fingerprint(self.public_key)
        self.plan = json.loads(
            (ROOT / "certification/ethan-certifier/external-certification-plan.json").read_text()
        )
        self.request = self.build_request()
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.request_path = self.bundle / "request.json"
        self.response_path = self.bundle / "response.unsigned.json"
        self.signature_path = self.bundle / "response.sig"
        self.request_path.write_text(json.dumps(self.request, indent=2, sort_keys=True) + "\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build_request(self) -> dict[str, object]:
        challenge = "12" * 32
        return {
            "schema_version": 1,
            "protocol": PROTOCOL,
            "request_id": "ethan-aaaaaaaaaaaa-121212121212",
            "issued_at": "2026-09-13T10:00:00Z",
            "expires_at": "2026-09-20T10:00:00Z",
            "challenge_nonce": challenge,
            "requester": {"actor_id": "elmos-release-control", "organization_id": "elmos"},
            "certifier": self.plan["certifier"],
            "subject": {
                "repository_url": "https://github.com/zpcaiai/elmos.git",
                "remote_ref": "origin/codex/revoke-certification-keys",
                "target_sha": "a" * 40,
                "tree_oid": "b" * 40,
            },
            "plan_digest": digest_bytes(canonical_bytes(self.plan)),
            "plan": self.plan,
            "tooling": {
                "external_runner_path": "certification/ethan-certifier/external_runner.py",
                "external_runner_sha256": digest_bytes(
                    (ROOT / "certification/ethan-certifier/external_runner.py").read_bytes()
                ),
                "protocol_path": "certification/ethan-certifier/EXTERNAL_CERTIFICATION_PROTOCOL.md",
                "protocol_sha256": digest_bytes(
                    (ROOT / "certification/ethan-certifier/EXTERNAL_CERTIFICATION_PROTOCOL.md").read_bytes()
                ),
            },
            "controls": {
                "private_key_must_remain_external": True,
                "detached_exact_sha_required": True,
                "clean_worktree_before_and_after_required": True,
                "shell_execution_prohibited": True,
                "independent_fingerprint_channel_required": True,
                "repository_auto_certification_prohibited": True,
            },
        }

    def reference(self, relative: str, payload: bytes) -> dict[str, object]:
        path = self.bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return {"path": relative, "sha256": digest_bytes(payload), "size_bytes": len(payload)}

    def build_response(self) -> dict[str, object]:
        results = []
        for line in self.plan["business_lines"]:
            commands = []
            for command in line["commands"]:
                prefix = f"commands/{command['id']}"
                commands.append(
                    {
                        "id": command["id"],
                        "argv": command["argv"],
                        "exit_code": 0,
                        "started_at": "2026-09-13T10:01:00Z",
                        "completed_at": "2026-09-13T10:02:00Z",
                        "stdout": self.reference(f"{prefix}/stdout.log", b"PASS\n"),
                        "stderr": self.reference(f"{prefix}/stderr.log", b""),
                    }
                )
            evidence = []
            for evidence_class in line["external_evidence_classes"]:
                relative = f"external-evidence/{line['id']}/{evidence_class}.json"
                evidence.append(
                    {
                        "class": evidence_class,
                        "synthetic": False,
                        "independent": True,
                        "content": self.reference(relative, b'{"fixture":"external"}\n'),
                    }
                )
            results.append(
                {"id": line["id"], "status": "PASS", "commands": commands, "external_evidence": evidence}
            )
        return {
            "schema_version": 1,
            "protocol": PROTOCOL,
            "request_id": self.request["request_id"],
            "request_digest": digest_bytes(canonical_bytes(self.request)),
            "target_sha": self.request["subject"]["target_sha"],
            "tree_oid": self.request["subject"]["tree_oid"],
            "challenge_nonce": self.request["challenge_nonce"],
            "certifier": {
                **self.request["certifier"],
                "public_key_fingerprint": self.fingerprint,
            },
            "independent_execution": {
                "environment_id": "ethan-clean-room-01",
                "provider": "independent-provider",
                "region": "independent-region-1",
                "executor_actor_id": "ethan-executor",
                "executor_organization_id": "ethan-independent-certification",
                "repository_owner_controlled": False,
                "private_key_repository_accessible": False,
                "detached_head_verified": True,
                "clean_worktree_before_verified": True,
                "clean_worktree_after_verified": True,
                "started_at": "2026-09-13T10:00:00Z",
                "completed_at": "2026-09-13T11:00:00Z",
            },
            "business_line_results": results,
            "unknowns": [],
            "overall_decision": "PASS",
        }

    def sign(self, response: dict[str, object]) -> None:
        self.response_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.private_key),
                "-rawin",
                "-in",
                str(self.response_path),
                "-out",
                str(self.signature_path),
            ],
            check=True,
            capture_output=True,
        )

    def verify(self) -> dict[str, object]:
        return verify_response_bundle(
            request_path=self.request_path,
            response_path=self.response_path,
            signature_path=self.signature_path,
            public_key_path=self.public_key,
            expected_fingerprint=self.fingerprint,
            now=NOW,
        )

    def test_plan_excludes_m29_and_has_six_exact_business_lines(self) -> None:
        validate_plan(self.plan)
        self.assertEqual(self.plan["excluded_business_lines"], ["M29"])
        self.assertEqual(len(self.plan["business_lines"]), 6)
        self.assertNotIn("M29", {line["id"] for line in self.plan["business_lines"]})

    def test_every_planned_make_target_exists(self) -> None:
        makefiles = [ROOT / "Makefile", *sorted(ROOT.glob("Makefile.*"))]
        declared = set()
        for makefile in makefiles:
            for raw_line in makefile.read_text(encoding="utf-8").splitlines():
                if raw_line and not raw_line.startswith(("\t", " ")) and ":" in raw_line:
                    declared.add(raw_line.split(":", 1)[0].strip())
        for line in self.plan["business_lines"]:
            for command in line["commands"]:
                self.assertEqual(command["argv"][0], "make")
                self.assertIn(command["argv"][1], declared)

    def test_valid_external_bundle_is_only_ready_for_domain_gates(self) -> None:
        self.sign(self.build_response())
        result = self.verify()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["decision"], "READY_FOR_DOMAIN_GATES")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")

    def test_fingerprint_must_come_from_the_expected_independent_value(self) -> None:
        self.sign(self.build_response())
        with self.assertRaisesRegex(ExchangeError, "independently delivered fingerprint"):
            verify_response_bundle(
                request_path=self.request_path,
                response_path=self.response_path,
                signature_path=self.signature_path,
                public_key_path=self.public_key,
                expected_fingerprint="sha256:" + "0" * 64,
                now=NOW,
            )

    def test_changed_signed_response_is_rejected(self) -> None:
        response = self.build_response()
        self.sign(response)
        response["target_sha"] = "c" * 40
        self.response_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
        with self.assertRaisesRegex(ExchangeError, "signature verification failed"):
            self.verify()

    def test_partial_external_evidence_scope_is_rejected(self) -> None:
        response = self.build_response()
        response["business_line_results"][0]["external_evidence"].pop()
        self.sign(response)
        with self.assertRaisesRegex(ExchangeError, "external evidence scope mismatch"):
            self.verify()

    def test_private_key_cannot_be_accepted_as_public_key(self) -> None:
        with self.assertRaisesRegex(ExchangeError, "private-key material"):
            public_key_fingerprint(self.private_key)

    def test_portable_runner_has_no_private_key_or_signing_interface(self) -> None:
        runner = (ROOT / "certification/ethan-certifier/external_runner.py").read_text()
        self.assertNotIn('add_argument("--private-key"', runner)
        self.assertNotIn('"-sign"', runner)

    def test_request_output_cannot_be_inside_repository(self) -> None:
        with self.assertRaisesRegex(ExchangeError, "outside the repository"):
            _ensure_external_output(ROOT / "certification" / "forbidden-output")


if __name__ == "__main__":
    unittest.main()
