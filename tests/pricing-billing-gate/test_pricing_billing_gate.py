from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts/pricing-billing/run_pricing_billing_gate.py"
SPEC = importlib.util.spec_from_file_location("run_pricing_billing_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)

RSA_MODULUS_HEX = (
    "c79444a824fae60855847c180a9ca4871eef01943fd1f3d0a56887991edf1232"
    "292672e7c63554c7b4eb5b0262e60ddd4d7e340958efca0bc006d65ef3fe8e5"
    "6fbb845c649b872b0a20705d85c4110ce49f0870c373425e570727b9dcf202957"
    "456306bd665adb0dceb03675181d3bec978e6d279ab56ebdb957cd023bdc8f123"
    "c78ac0babae02d192012d84a5b29db8028d2af732e652a4e7c9947d463d7ce9"
    "cb22dc395f651eff6c95636eb540303c6ad64baf7a3767753290c0d0bfd5c0da"
    "bf0424f79b142190da4f9f7c807b1e5af1befc66335b065f7c485529da31f8a"
    "ec5f5a26c2ea9eeef924264497e0b2653a22167ef25466adc7fda03583c3f249b"
)
RSA_PRIVATE_EXPONENT_HEX = (
    "0c74ee261a8cc86fcbbaa5ae30775f7389943c627eeb414f0c0beeaeb9750de3"
    "309b543fb028e2fe46060c9ba5059be6ecafcc5aab00e878fc46d0f9833c27b1"
    "392be2bb021def96a3be51789425818186aeeb16f19921266572d7d15d3cb227d"
    "ece53fcdd571d660ab907e51e18b1054ede5664caecb9194168c0047c2d0386f"
    "0fde789c01f6a0a0696e4c76a4d0e90588b46ea7334690d128674b21b0e037da"
    "48aaf4d8399925936562ce5117721c28533722001673857febf1a1ec9c7453f0f"
    "977f3efc369e87607cfc0303125c060f31b256767d80d8c352d59ceddeb2f629"
    "868c88703c05797b67581417d2274ada092669f6e684a780be59eaef023a75"
)
RSA_MODULUS = int(RSA_MODULUS_HEX, 16)
RSA_PRIVATE_EXPONENT = int(RSA_PRIVATE_EXPONENT_HEX, 16)
RSA_EXPONENT = 65537
EXECUTOR = "executor@example.test"
VERIFIER = "verifier@example.test"
KEY_ID = "pricing-billing-test-verifier"
RUN_ID = "run:pricing-billing:test:1"
AUTHORIZATION_ID = "authorization:pricing-billing:test:1"
AUTHORIZATION_SCOPE = "pricing-billing-v1/readiness"
ENVIRONMENT_ID = "environment:pricing-billing:test:1"
ENVIRONMENT_PROFILE = "isolated-test"


def descriptor(path: Path, root: Path, role: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if role is not None:
        value["role"] = role
    return value


def canonical_payload(document: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "binding": document["binding"],
            "evidenceId": document["evidenceId"],
            "schemaVersion": document["schemaVersion"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_payload(payload: bytes) -> str:
    digest_info = GATE.RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload).digest()
    width = (RSA_MODULUS.bit_length() + 7) // 8
    padding_size = width - len(digest_info) - 3
    encoded = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
    signature = pow(
        int.from_bytes(encoded, "big"), RSA_PRIVATE_EXPONENT, RSA_MODULUS
    ).to_bytes(width, "big")
    return base64.b64encode(signature).decode("ascii")


def run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(
        command, cwd=cwd, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {command}\n{result.stderr}"
        )


class PricingBillingGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_archive = REPOSITORY_ROOT / GATE.ARCHIVE_RELATIVE
        cls.installed_manifest = REPOSITORY_ROOT / GATE.INSTALLED_MANIFEST_RELATIVE
        cls.runtime_binding = REPOSITORY_ROOT / GATE.RUNTIME_BINDING_RELATIVE
        if not cls.source_archive.is_file():
            raise AssertionError(f"source archive is unavailable: {cls.source_archive}")
        if not cls.installed_manifest.is_file():
            raise AssertionError(
                f"installed manifest is unavailable: {cls.installed_manifest}"
            )
        if not cls.runtime_binding.is_file():
            raise AssertionError(
                f"runtime binding is unavailable: {cls.runtime_binding}"
            )
        cls.installed_manifest_sha256 = hashlib.sha256(
            cls.installed_manifest.read_bytes()
        ).hexdigest()
        if cls.installed_manifest_sha256 != GATE.INSTALLED_MANIFEST_SHA256:
            raise AssertionError(
                "installed manifest digest drifted from the hard gate pin: "
                f"expected={GATE.INSTALLED_MANIFEST_SHA256} "
                f"actual={cls.installed_manifest_sha256}"
            )

        cls.fixture_temporary = tempfile.TemporaryDirectory(
            prefix="pricing-billing-gate-fixture-"
        )
        cls.addClassCleanup(cls.fixture_temporary.cleanup)
        cls.fixture_root = Path(cls.fixture_temporary.name)

        archive = cls.fixture_root / GATE.ARCHIVE_RELATIVE
        archive.parent.mkdir(parents=True)
        shutil.copyfile(cls.source_archive, archive)
        manifest = cls.fixture_root / GATE.INSTALLED_MANIFEST_RELATIVE
        manifest.parent.mkdir(parents=True)
        shutil.copyfile(cls.installed_manifest, manifest)
        runtime_document = json.loads(cls.runtime_binding.read_text(encoding="utf-8"))
        for relative in GATE._runtime_binding_paths(runtime_document):
            source = REPOSITORY_ROOT.joinpath(*relative.parts)
            target = cls.fixture_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        gate_script = cls.fixture_root / GATE.GATE_RELATIVE
        gate_script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, gate_script)
        engine_file = cls.fixture_root / GATE.ENGINE_RELATIVE / "baseline.json"
        engine_file.parent.mkdir(parents=True, exist_ok=True)
        engine_file.write_text(
            '{"engine":"deterministic test baseline","version":"1"}\n',
            encoding="utf-8",
        )

        run(["git", "init", "-q"], cls.fixture_root)
        run(["git", "config", "user.name", "ELMOS Gate Test"], cls.fixture_root)
        run(
            ["git", "config", "user.email", "gate-test@example.test"],
            cls.fixture_root,
        )
        fixture_paths = {
            GATE.ARCHIVE_RELATIVE.as_posix(),
            GATE.INSTALLED_MANIFEST_RELATIVE.as_posix(),
            GATE.RUNTIME_BINDING_RELATIVE.as_posix(),
            GATE.GATE_RELATIVE.as_posix(),
            GATE.ENGINE_RELATIVE.as_posix(),
            *(relative.as_posix() for relative in GATE._runtime_binding_paths(runtime_document)),
        }
        run(["git", "add", "--", *sorted(fixture_paths)], cls.fixture_root)
        run(["git", "commit", "-q", "-m", "fixture baseline"], cls.fixture_root)

        cls.catalog = GATE.load_requirement_catalog(archive)
        cls.catalog_records = GATE._load_requirement_catalog_records_bytes(
            archive.read_bytes()
        )
        cls.repository_state = GATE.inspect_repository_baseline(cls.fixture_root)
        cls.trust_store = {
            "schemaVersion": GATE.TRUST_STORE_SCHEMA_VERSION,
            "keys": [
                {
                    "algorithm": "RS256",
                    "exponent": RSA_EXPONENT,
                    "keyId": KEY_ID,
                    "modulus": RSA_MODULUS_HEX,
                    "principal": VERIFIER,
                    "roles": [
                        "authorization-approver",
                        "environment-verifier",
                        "external-evidence-verifier",
                        "independent-verifier",
                        "reconciliation-verifier",
                        "requirement-verifier",
                    ],
                    "status": "ACTIVE",
                }
            ],
        }
        cls.base_request = cls._build_ready_request()

    @classmethod
    def _binding(cls, subject_type: str, subject_id: str) -> dict[str, object]:
        repository = cls.repository_state
        return {
            "authorizationId": AUTHORIZATION_ID,
            "authorizationScope": AUTHORIZATION_SCOPE,
            "baselineSha256": repository["baselineSha256"],
            "engineGitTree": repository["engineGitTree"],
            "engineTreeSha256": repository["engineTreeSha256"],
            "environmentId": ENVIRONMENT_ID,
            "environmentProfile": ENVIRONMENT_PROFILE,
            "executor": EXECUTOR,
            "gateSha256": repository["gateSha256"],
            "installedManifestSha256": "sha256:" + GATE.INSTALLED_MANIFEST_SHA256,
            "outcome": "PASS",
            "repositoryCommit": repository["repositoryCommit"],
            "repositoryTree": repository["repositoryTree"],
            "runId": RUN_ID,
            "runtimeBindingSha256": repository["runtimeBindingSha256"],
            "scopedWorktreeSha256": repository["scopedWorktreeSha256"],
            "sourceArchiveSha256": "sha256:" + GATE.ARCHIVE_SHA256,
            "subjectId": subject_id,
            "subjectType": subject_type,
            "verifier": VERIFIER,
        }

    @classmethod
    def _pass_record(
        cls,
        sequence: int,
        subject_type: str,
        subject_id: str,
        role: str,
        *,
        priority: str | None = None,
    ) -> dict[str, object]:
        evidence_id = f"evidence:{subject_type}:{subject_id}"
        document: dict[str, object] = {
            "binding": cls._binding(subject_type, subject_id),
            "evidenceId": evidence_id,
            "schemaVersion": GATE.EVIDENCE_SCHEMA_VERSION,
        }
        document["signature"] = {
            "algorithm": "RS256",
            "keyId": KEY_ID,
            "value": sign_payload(canonical_payload(document)),
        }
        safe_name = "".join(
            character if character.isalnum() else "-"
            for character in f"{subject_type}-{subject_id}"
        )
        path = (
            cls.fixture_root
            / "evidence/pricing-billing"
            / f"{sequence:03d}-{safe_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        record: dict[str, object] = {
            "status": "PASS",
            "executor": EXECUTOR,
            "verifier": VERIFIER,
            "evidence": [descriptor(path, cls.fixture_root, role)],
        }
        if priority is not None:
            record["priority"] = priority
        return record

    @classmethod
    def _build_ready_request(cls) -> dict[str, object]:
        sequence = 0
        results: dict[str, object] = {}
        for identifier, priority in cls.catalog.items():
            if priority == "P0":
                results[identifier] = cls._pass_record(
                    sequence,
                    "requirement",
                    identifier,
                    "requirement",
                    priority=priority,
                )
                sequence += 1
            else:
                results[identifier] = "NOT_RUN"
        authorization = {
            **cls._pass_record(
                sequence,
                "authorization",
                AUTHORIZATION_ID,
                "authorization",
            ),
            "authorizationId": AUTHORIZATION_ID,
            "scope": AUTHORIZATION_SCOPE,
        }
        sequence += 1
        environment = {
            **cls._pass_record(
                sequence,
                "environment",
                ENVIRONMENT_ID,
                "environment",
            ),
            "environmentId": ENVIRONMENT_ID,
            "profile": ENVIRONMENT_PROFILE,
        }
        sequence += 1
        reconciliation: dict[str, object] = {}
        for domain in GATE.RECONCILIATION_DOMAINS:
            reconciliation[domain] = cls._pass_record(
                sequence,
                "reconciliation",
                domain,
                f"{domain}_reconciliation",
            )
            sequence += 1
        return {
            "schemaVersion": "1.0",
            "requestedDecision": "READY_FOR_EXTERNAL_GATE",
            "runId": RUN_ID,
            "approvedEvidenceRoots": ["evidence/pricing-billing"],
            "sourceArchive": descriptor(
                cls.fixture_root / GATE.ARCHIVE_RELATIVE, cls.fixture_root
            ),
            "installedManifest": descriptor(
                cls.fixture_root / GATE.INSTALLED_MANIFEST_RELATIVE,
                cls.fixture_root,
            ),
            "runtimeBinding": descriptor(
                cls.fixture_root / GATE.RUNTIME_BINDING_RELATIVE,
                cls.fixture_root,
            ),
            "repositoryState": copy.deepcopy(cls.repository_state),
            "authorization": authorization,
            "environment": environment,
            "requirementResults": results,
            "reconciliation": reconciliation,
            "externalEvidence": {
                domain: "NOT_RUN" for domain in GATE.EXTERNAL_EVIDENCE_DOMAINS
            },
        }

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pricing-billing-gate-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(self.fixture_root, self.root, dirs_exist_ok=True)
        self.request = copy.deepcopy(self.base_request)
        self.archive = self.root / GATE.ARCHIVE_RELATIVE
        self.manifest = self.root / GATE.INSTALLED_MANIFEST_RELATIVE
        self.runtime_binding = self.root / GATE.RUNTIME_BINDING_RELATIVE
        self.trust_store = copy.deepcopy(self.__class__.trust_store)

    def first_p0(
        self, request: dict[str, object] | None = None
    ) -> tuple[str, dict[str, object]]:
        request = request or self.request
        results = request["requirementResults"]
        assert isinstance(results, dict)
        identifier = next(
            key for key, priority in self.catalog.items() if priority == "P0"
        )
        record = results[identifier]
        assert isinstance(record, dict)
        return identifier, record

    def evidence_path(self, record: dict[str, object]) -> Path:
        evidence = record["evidence"]
        assert isinstance(evidence, list) and isinstance(evidence[0], dict)
        return self.root / str(evidence[0]["path"])

    def rewrite_evidence(
        self,
        record: dict[str, object],
        mutate: callable,
        *,
        resign: bool = True,
    ) -> dict[str, object]:
        path = self.evidence_path(record)
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document)
        if resign:
            document["signature"]["value"] = sign_payload(canonical_payload(document))
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        role = record["evidence"][0]["role"]
        record["evidence"] = [descriptor(path, self.root, str(role))]
        return document

    def evaluate(
        self,
        request: dict[str, object] | None = None,
        *,
        with_trust: bool = True,
    ) -> dict[str, object]:
        return GATE.evaluate(
            request or self.request,
            self.root,
            self.trust_store if with_trust else None,
        )

    def test_valid_signed_request_is_ready_but_never_certified(self) -> None:
        result = self.evaluate()
        self.assertEqual("READY_FOR_EXTERNAL_GATE", result["decision"])
        self.assertEqual([], result["blockers"])
        self.assertTrue(result["sourceArchiveVerified"])
        self.assertTrue(result["installedManifestVerified"])
        self.assertTrue(result["runtimeBindingVerified"])
        self.assertTrue(result["repositoryBaselineVerified"])
        self.assertTrue(result["independentTrustConfigured"])
        self.assertEqual(113, result["verifiedEvidenceCount"])
        self.assertEqual(180, result["requirementCatalogCount"])
        self.assertFalse(result["certified"])
        self.assertFalse(result["productionApproved"])
        self.assertFalse(result["gaApproved"])

    def test_no_operator_trust_store_can_never_be_ready(self) -> None:
        result = self.evaluate(with_trust=False)
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["independentTrustConfigured"])
        self.assertIn(
            "operator-supplied independent public trust store is required before readiness",
            result["blockers"],
        )

    def test_arbitrary_bytes_cannot_satisfy_a_pass_record(self) -> None:
        _identifier, record = self.first_p0()
        path = self.evidence_path(record)
        path.write_text('{"observed":"unrelated arbitrary bytes"}\n', encoding="utf-8")
        record["evidence"] = [descriptor(path, self.root, "requirement")]
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("exact signed-envelope fields" in item for item in result["blockers"])
        )

    def test_valid_signature_with_wrong_subject_binding_is_rejected(self) -> None:
        _identifier, record = self.first_p0()
        self.rewrite_evidence(
            record,
            lambda document: document["binding"].__setitem__("subjectId", "EB-18-010"),
        )
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("exact subject and gate context" in item for item in result["blockers"])
        )

    def test_evidence_cannot_be_reused_across_requirements(self) -> None:
        results = self.request["requirementResults"]
        assert isinstance(results, dict)
        identifiers = [
            identifier
            for identifier, priority in self.catalog.items()
            if priority == "P0"
        ][:2]
        first = results[identifiers[0]]
        second = results[identifiers[1]]
        assert isinstance(first, dict) and isinstance(second, dict)
        second["evidence"] = copy.deepcopy(first["evidence"])
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("reuses evidence path" in item for item in result["blockers"])
        )

    def test_evidence_identity_and_inode_cannot_be_reused(self) -> None:
        results = self.request["requirementResults"]
        assert isinstance(results, dict)
        identifiers = [
            identifier
            for identifier, priority in self.catalog.items()
            if priority == "P0"
        ][:2]
        first = results[identifiers[0]]
        second = results[identifiers[1]]
        assert isinstance(first, dict) and isinstance(second, dict)
        first_path = self.evidence_path(first)
        second_path = self.evidence_path(second)

        shutil.copyfile(first_path, second_path)
        second["evidence"] = [descriptor(second_path, self.root, "requirement")]
        result = self.evaluate()
        self.assertTrue(any("reuses evidenceId" in item for item in result["blockers"]))

        self.setUp()
        results = self.request["requirementResults"]
        first = results[identifiers[0]]
        second = results[identifiers[1]]
        first_path = self.evidence_path(first)
        second_path = self.evidence_path(second)
        second_path.unlink()
        second_path.hardlink_to(first_path)
        second["evidence"] = [descriptor(second_path, self.root, "requirement")]
        result = self.evaluate()
        self.assertTrue(
            any("reuses evidence inode" in item for item in result["blockers"])
        )

    def test_requirement_evidence_cannot_be_reused_as_authorization(self) -> None:
        _identifier, requirement = self.first_p0()
        authorization = self.request["authorization"]
        assert isinstance(authorization, dict)
        authorization["evidence"] = copy.deepcopy(requirement["evidence"])
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("reuses evidence path" in item for item in result["blockers"])
        )

    def test_verifier_identity_must_match_trusted_signing_key(self) -> None:
        _identifier, record = self.first_p0()
        record["verifier"] = "attacker@example.test"
        self.rewrite_evidence(
            record,
            lambda document: document["binding"].__setitem__(
                "verifier", "attacker@example.test"
            ),
        )
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any(
                "verifier identity does not match the trusted signing key" in item
                for item in result["blockers"]
            )
        )

    def test_stale_manifest_binding_is_rejected_even_when_resigned(self) -> None:
        _identifier, record = self.first_p0()
        self.rewrite_evidence(
            record,
            lambda document: document["binding"].__setitem__(
                "installedManifestSha256", "sha256:" + ("0" * 64)
            ),
        )
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("exact subject and gate context" in item for item in result["blockers"])
        )

    def test_stale_repository_baseline_is_rejected(self) -> None:
        state = self.request["repositoryState"]
        assert isinstance(state, dict)
        state["repositoryCommit"] = "sha1:" + ("0" * 40)
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertIn(
            "repositoryState.repositoryCommit does not match the live baseline",
            result["blockers"],
        )
        self.assertFalse(result["repositoryBaselineVerified"])

    def test_checked_in_manifest_pin_drift_is_a_hard_assertion(self) -> None:
        actual = hashlib.sha256(self.installed_manifest.read_bytes()).hexdigest()
        self.assertEqual(GATE.INSTALLED_MANIFEST_SHA256, actual)

    def test_stale_installed_manifest_descriptor_pin_is_rejected(self) -> None:
        descriptor_value = self.request["installedManifest"]
        assert isinstance(descriptor_value, dict)
        descriptor_value["sha256"] = "sha256:" + ("0" * 64)
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["installedManifestVerified"])
        self.assertTrue(
            any(
                "installedManifest.sha256 does not bind" in item
                for item in result["blockers"]
            )
        )

    def test_missing_runtime_binding_descriptor_blocks_readiness(self) -> None:
        del self.request["runtimeBinding"]
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["runtimeBindingVerified"])
        self.assertIn("runtimeBinding descriptor is required", result["blockers"])

    def test_stale_runtime_binding_descriptor_is_rejected(self) -> None:
        descriptor_value = self.request["runtimeBinding"]
        assert isinstance(descriptor_value, dict)
        descriptor_value["sha256"] = "sha256:" + ("0" * 64)
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["runtimeBindingVerified"])
        self.assertTrue(
            any("runtimeBinding SHA-256 mismatch" in item for item in result["blockers"])
        )

    def test_runtime_binding_certification_claim_is_rejected_fail_closed(self) -> None:
        document = json.loads(self.runtime_binding.read_text(encoding="utf-8"))
        document["claimCeiling"]["certification"] = "CERTIFIED"
        self.runtime_binding.write_text(
            json.dumps(document, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        self.request["runtimeBinding"] = descriptor(self.runtime_binding, self.root)
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["runtimeBindingVerified"])
        self.assertIn("runtimeBinding claim ceiling is invalid", result["blockers"])

    def test_runtime_binding_manifest_pin_drift_is_rejected(self) -> None:
        document = json.loads(self.runtime_binding.read_text(encoding="utf-8"))
        document["installedManifest"]["sha256"] = "0" * 64
        reasons = GATE._validate_runtime_binding(
            (json.dumps(document, sort_keys=True) + "\n").encode("utf-8"),
            self.root,
            self.catalog_records,
        )
        self.assertIn(
            "runtimeBinding.installedManifest.sha256 does not match the pinned digest",
            reasons,
        )

    def test_runtime_binding_source_contract_drift_is_rejected(self) -> None:
        mutations = {
            "sourceBatch": "B99",
            "sourceStatement": "tampered source requirement",
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                document = json.loads(
                    self.runtime_binding.read_text(encoding="utf-8")
                )
                document["requirementTraceability"]["bindings"][0][field] = replacement
                reasons = GATE._validate_runtime_binding(
                    (json.dumps(document, sort_keys=True) + "\n").encode("utf-8"),
                    self.root,
                    self.catalog_records,
                )
                self.assertTrue(
                    any(f".{field} differs from the source archive" in item for item in reasons),
                    reasons,
                )

    def test_missing_requirement_result_blocks(self) -> None:
        identifier, _record = self.first_p0()
        del self.request["requirementResults"][identifier]
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertIn(f"requirement result missing: {identifier}", result["blockers"])

    def test_installed_manifest_must_bind_exact_requirement_inventory(self) -> None:
        manifest = json.loads(self.installed_manifest.read_text(encoding="utf-8"))
        manifest["skills"][0]["requirement_ids"].pop()
        reasons = GATE._validate_installed_manifest(
            (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8")
        )
        self.assertIn(
            "installed manifest must bind the exact ordered 180 requirement IDs",
            reasons,
        )

    def test_arbitrary_descriptor_digest_is_rejected(self) -> None:
        _identifier, record = self.first_p0()
        record["evidence"][0]["sha256"] = "sha256:" + ("0" * 64)
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(any("SHA-256 mismatch" in item for item in result["blockers"]))

    def test_dot_path_is_fail_closed_without_crashing_cli(self) -> None:
        request = copy.deepcopy(self.request)
        request["sourceArchive"]["path"] = "."
        request_path = self.root / "dot-path-request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(request_path),
                "--repository-root",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("BLOCKED", payload["decision"])
        self.assertTrue(payload["malformed"])
        self.assertTrue(
            any(
                "normalized repository-relative path" in item
                for item in payload["blockers"]
            )
        )
        with self.assertRaisesRegex(
            GATE.GateRequestError, "normalized repository-relative path"
        ):
            self.evaluate(request)

    def test_path_escape_is_rejected(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside-evidence.json"
        outside.write_text("outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        _identifier, record = self.first_p0()
        escaped = descriptor(outside, self.root.parent, "requirement")
        escaped["path"] = "../" + outside.name
        record["evidence"] = [escaped]
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any(
                "normalized repository-relative path" in item
                for item in result["blockers"]
            )
        )

    def test_final_and_intermediate_symlinks_are_rejected(self) -> None:
        _identifier, record = self.first_p0()
        original = self.evidence_path(record)
        link = original.with_name("linked-proof.json")
        link.symlink_to(original.name)
        linked = descriptor(original, self.root, "requirement")
        linked["path"] = link.relative_to(self.root).as_posix()
        record["evidence"] = [linked]
        result = self.evaluate()
        self.assertTrue(any("symbolic link" in item for item in result["blockers"]))

        self.setUp()
        _identifier, record = self.first_p0()
        original = self.evidence_path(record)
        actual = self.root / "actual-evidence"
        actual.mkdir()
        moved = actual / original.name
        shutil.copyfile(original, moved)
        link_dir = original.parent / "linked-directory"
        link_dir.symlink_to(actual, target_is_directory=True)
        linked = descriptor(moved, self.root, "requirement")
        linked["path"] = (link_dir / moved.name).relative_to(self.root).as_posix()
        record["evidence"] = [linked]
        result = self.evaluate()
        self.assertTrue(any("symbolic link" in item for item in result["blockers"]))

    def test_path_replacement_and_in_place_mutation_are_rejected(self) -> None:
        _identifier, record = self.first_p0()
        target = self.evidence_path(record)
        target_inode = target.stat().st_ino
        original_read = GATE.os.read
        swapped = False

        def racing_read(file_descriptor: int, size: int) -> bytes:
            nonlocal swapped
            block = original_read(file_descriptor, size)
            if not swapped and GATE.os.fstat(file_descriptor).st_ino == target_inode:
                swapped = True
                target.rename(target.with_name("proof.original.json"))
                target.write_text('{"replacement":true}\n', encoding="utf-8")
            return block

        with mock.patch.object(GATE.os, "read", side_effect=racing_read):
            result = self.evaluate()
        self.assertTrue(swapped)
        self.assertTrue(
            any(
                "changed while it was being verified" in item
                for item in result["blockers"]
            )
        )

        self.setUp()
        _identifier, record = self.first_p0()
        target = self.evidence_path(record)
        target_inode = target.stat().st_ino
        mutated = False

        def mutating_read(file_descriptor: int, size: int) -> bytes:
            nonlocal mutated
            block = original_read(file_descriptor, size)
            if not mutated and GATE.os.fstat(file_descriptor).st_ino == target_inode:
                mutated = True
                with target.open("ab") as handle:
                    handle.write(b"mutation\n")
                    handle.flush()
                    GATE.os.fsync(handle.fileno())
            return block

        with mock.patch.object(GATE.os, "read", side_effect=mutating_read):
            result = self.evaluate()
        self.assertTrue(mutated)
        self.assertTrue(
            any(
                "changed while it was being verified" in item
                for item in result["blockers"]
            )
        )

    def test_per_file_evidence_limit_blocks_large_file(self) -> None:
        _identifier, record = self.first_p0()
        path = self.evidence_path(record)
        path.write_bytes(b"x" * (GATE.MAX_EVIDENCE_FILE_BYTES + 1))
        record["evidence"] = [descriptor(path, self.root, "requirement")]
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("per-file byte limit" in item for item in result["blockers"])
        )

    def test_aggregate_evidence_limit_blocks_many_bounded_files(self) -> None:
        results = self.request["requirementResults"]
        assert isinstance(results, dict)
        records = [
            results[identifier]
            for identifier, priority in self.catalog.items()
            if priority == "P0"
        ][:20]
        for index, record in enumerate(records):
            assert isinstance(record, dict)
            path = self.evidence_path(record)
            path.write_bytes(bytes([65 + (index % 20)]) * GATE.MAX_EVIDENCE_FILE_BYTES)
            record["evidence"] = [descriptor(path, self.root, "requirement")]
        result = self.evaluate()
        self.assertEqual("BLOCKED", result["decision"])
        self.assertTrue(
            any("aggregate evidence byte limit" in item for item in result["blockers"])
        )
        self.assertLessEqual(result["evidenceBytesRead"], GATE.MAX_TOTAL_EVIDENCE_BYTES)

    def test_byte_count_mismatch_and_self_verification_are_rejected(self) -> None:
        _identifier, record = self.first_p0()
        record["evidence"][0]["bytes"] += 1
        result = self.evaluate()
        self.assertTrue(
            any("byte count mismatch" in item for item in result["blockers"])
        )

        self.setUp()
        _identifier, record = self.first_p0()
        record["verifier"] = record["executor"].upper()
        result = self.evaluate()
        self.assertTrue(any("self-verify" in item for item in result["blockers"]))

    def test_authorization_environment_and_reconciliation_fail_closed(self) -> None:
        for field in ("authorization", "environment"):
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                request[field] = {"status": "NOT_RUN"}
                result = self.evaluate(request)
                self.assertIn(f"{field} is not PASS: NOT_RUN", result["blockers"])
        for domain in GATE.RECONCILIATION_DOMAINS:
            with self.subTest(domain=domain):
                request = copy.deepcopy(self.request)
                request["reconciliation"][domain] = "INCONCLUSIVE"
                result = self.evaluate(request)
                self.assertIn(
                    f"{domain} reconciliation is unreconciled: INCONCLUSIVE",
                    result["blockers"],
                )

    def test_p0_not_run_blocks(self) -> None:
        identifier, _record = self.first_p0()
        self.request["requirementResults"][identifier] = "NOT_RUN"
        result = self.evaluate()
        self.assertIn(
            f"P0 requirement is not PASS: {identifier}: NOT_RUN",
            result["blockers"],
        )

    def test_certification_request_is_malformed(self) -> None:
        self.request["certified"] = True
        with self.assertRaisesRegex(
            GATE.GateRequestError, "may not request certification"
        ):
            self.evaluate()

    def test_cli_exit_contract_for_blocked_request(self) -> None:
        identifier, _record = self.first_p0()
        self.request["requirementResults"][identifier] = "NOT_RUN"
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps(self.request), encoding="utf-8")
        trust_path = self.root / "operator-trust.json"
        trust_path.write_text(json.dumps(self.trust_store), encoding="utf-8")
        command = [
            sys.executable,
            str(SCRIPT),
            str(request_path),
            "--repository-root",
            str(self.root),
            "--trust-store",
            str(trust_path),
        ]
        default = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(0, default.returncode, default.stderr)
        self.assertEqual("BLOCKED", json.loads(default.stdout)["decision"])
        required = subprocess.run(
            [*command, "--require-ready"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(3, required.returncode, required.stderr)

    def test_root_directory_cannot_be_used_as_a_trust_store(self) -> None:
        with self.assertRaisesRegex(
            GATE.GateRequestError, "trust store path must name a regular file"
        ):
            GATE.load_trust_store(Path("/"))
        request_path = self.root / "trust-root-request.json"
        request_path.write_text(json.dumps(self.request), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(request_path),
                "--repository-root",
                str(self.root),
                "--trust-store",
                "/",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("BLOCKED", payload["decision"])
        self.assertTrue(payload["malformed"])
        self.assertIn("trust store path must name a regular file", payload["blockers"])

    def test_request_input_limits_fail_closed(self) -> None:
        oversized_path = self.root / "oversized-request.json"
        oversized_path.write_bytes(b"{" + (b" " * GATE.MAX_REQUEST_BYTES))
        with self.assertRaisesRegex(GATE.GateRequestError, "per-file byte limit"):
            GATE.load_json_request(oversized_path)

        oversized = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(oversized_path),
                "--repository-root",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, oversized.returncode, oversized.stderr)
        oversized_payload = json.loads(oversized.stdout)
        self.assertEqual("BLOCKED", oversized_payload["decision"])
        self.assertTrue(oversized_payload["malformed"])
        self.assertTrue(
            any(
                "per-file byte limit" in blocker
                for blocker in oversized_payload["blockers"]
            )
        )

        deeply_nested: dict[str, object] = {
            "schemaVersion": "1.0",
            "requestedDecision": "READY_FOR_EXTERNAL_GATE",
            "runId": "run:pricing-billing:deep-request",
        }
        cursor = deeply_nested
        for _ in range(GATE.MAX_REQUEST_DEPTH + 1):
            child: dict[str, object] = {}
            cursor["nested"] = child
            cursor = child
        deep_path = self.root / "deep-request.json"
        deep_path.write_text(json.dumps(deeply_nested), encoding="utf-8")
        deep = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(deep_path),
                "--repository-root",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, deep.returncode, deep.stderr)
        deep_payload = json.loads(deep.stdout)
        self.assertEqual("BLOCKED", deep_payload["decision"])
        self.assertTrue(deep_payload["malformed"])
        self.assertTrue(
            any(
                "structural depth limit" in blocker
                for blocker in deep_payload["blockers"]
            )
        )

        parser_deep_path = self.root / "parser-deep-request.json"
        parser_deep_path.write_text(
            '{"nested":' * 1_500 + "null" + "}" * 1_500,
            encoding="utf-8",
        )
        parser_deep = subprocess.run(
            [sys.executable, str(SCRIPT), str(parser_deep_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, parser_deep.returncode, parser_deep.stderr)
        parser_deep_payload = json.loads(parser_deep.stdout)
        self.assertEqual("BLOCKED", parser_deep_payload["decision"])
        self.assertTrue(parser_deep_payload["malformed"])
        self.assertIn(
            "request exceeds the JSON nesting limit",
            parser_deep_payload["blockers"],
        )

        with self.assertRaisesRegex(
            GATE.GateRequestError, "per-container item limit"
        ):
            GATE._walk_forbidden_claims(
                {"items": [None] * (GATE.MAX_REQUEST_CONTAINER_ITEMS + 1)}
            )
        node_heavy = {
            "items": [[None] * 5 for _ in range(GATE.MAX_REQUEST_CONTAINER_ITEMS)]
        }
        with self.assertRaisesRegex(GATE.GateRequestError, "structural node limit"):
            GATE._walk_forbidden_claims(node_heavy)

    def test_checked_in_example_is_bound_and_explicitly_fail_closed(self) -> None:
        example_path = REPOSITORY_ROOT / "templates/pricing-billing/gate.example.json"
        request = GATE.load_json_request(example_path)
        result = GATE.evaluate(request, REPOSITORY_ROOT)
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["malformed"])
        self.assertTrue(result["sourceArchiveVerified"])
        self.assertTrue(result["installedManifestVerified"])
        self.assertTrue(result["runtimeBindingVerified"])
        self.assertFalse(result["repositoryBaselineVerified"])
        self.assertFalse(result["independentTrustConfigured"])
        runtime_binding_path = REPOSITORY_ROOT / GATE.RUNTIME_BINDING_RELATIVE
        runtime_binding_descriptor = request["runtimeBinding"]
        assert isinstance(runtime_binding_descriptor, dict)
        self.assertEqual(
            runtime_binding_path.stat().st_size,
            runtime_binding_descriptor["bytes"],
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(runtime_binding_path.read_bytes()).hexdigest(),
            runtime_binding_descriptor["sha256"],
        )
        self.assertEqual(180, result["requirementCatalogCount"])
        self.assertEqual({"NOT_RUN": 180}, result["requirementSummary"])
        self.assertEqual({"NOT_RUN": 108}, result["p0Summary"])
        self.assertFalse(result["certified"])
        self.assertFalse(result["productionApproved"])
        self.assertFalse(result["gaApproved"])
        manifest_descriptor = request["installedManifest"]
        self.assertEqual(
            "sha256:" + self.installed_manifest_sha256,
            manifest_descriptor["sha256"],
        )
        self.assertEqual(
            self.installed_manifest.stat().st_size,
            manifest_descriptor["bytes"],
        )


if __name__ == "__main__":
    unittest.main()
