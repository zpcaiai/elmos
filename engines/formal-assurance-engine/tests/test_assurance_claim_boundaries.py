from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from elmos_formal_assurance.artifact_store import (
    AesGcmEnvelopeCipher,
    ArtifactStoreError,
    ContentAddressedArtifactStore,
)
from elmos_formal_assurance.canonical import canonical_json, digest_bytes
from elmos_formal_assurance.hermetic_environment_builder import (
    EnvironmentPlanError,
    ToolchainArtifact,
    ToolchainManifest,
    export_hermetic_toolchain,
)
from elmos_formal_assurance.lean_dafny_bridge import (
    FormalProofBridgeError,
    FormalProofKernelBridge,
    Lean4Generator,
)
from elmos_formal_assurance.handlers import HandlerError
from elmos_formal_assurance.contracts import TrustedIdentity
from elmos_formal_assurance.runtime import FormalAssuranceRuntime, RuntimeConfig
from elmos_formal_assurance.store import StateStore
from elmos_formal_assurance.sbom_attestation_signer import (
    AttestationError,
    HmacLocalAttestationSigner,
    SbomAttestationSigner,
    SbomComponent,
    sign_artifact_sbom,
)


def exact_digest(character: str) -> str:
    return "sha256:" + character * 64


def component() -> SbomComponent:
    return SbomComponent(
        name="lean4",
        version="4.8.0",
        purl="pkg:generic/leanprover/lean4@4.8.0",
        component_type="application",
        hashes={"SHA-256": exact_digest("1")},
    )


def toolchain_manifest() -> ToolchainManifest:
    return ToolchainManifest(
        target_platform="linux/arm64",
        base_image="registry.example/formal-toolchain",
        base_image_digest=exact_digest("2"),
        nixpkgs_revision="3" * 40,
        nixpkgs_source_digest=exact_digest("4"),
        toolchains=(
            ToolchainArtifact(
                name="lean",
                version="4.8.0",
                executable_path="/opt/lean/bin/lean",
                sha256=exact_digest("5"),
            ),
            ToolchainArtifact(
                name="dafny",
                version="4.4.0",
                executable_path="/opt/dafny/dafny",
                sha256=exact_digest("6"),
            ),
        ),
    )


class EncryptedArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cipher = AesGcmEnvelopeCipher(
            b"a" * 32, key_id="artifact-test-key"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_runtime_artifact_root_fails_closed_without_encryption_cipher(self) -> None:
        with self.assertRaises(ArtifactStoreError):
            ContentAddressedArtifactStore(self.root / "direct-missing-key")
        with self.assertRaises(ValueError):
            RuntimeConfig(artifact_root=self.root / "missing-key")
        with self.assertRaises(ValueError):
            RuntimeConfig(artifact_envelope_cipher=self.cipher)

    def test_plaintext_is_not_persisted_and_same_digest_is_idempotent(self) -> None:
        store = ContentAddressedArtifactStore(
            self.root / "cas", envelope_cipher=self.cipher
        )
        plaintext = b"tenant-confidential-proof-evidence"
        first = store.put(
            "tenant-a",
            plaintext,
            media_type="application/octet-stream",
            retention_class="AUDIT",
        )
        second = store.put(
            "tenant-a",
            plaintext,
            media_type="application/octet-stream",
            retention_class="AUDIT",
        )
        self.assertEqual(first, second)
        self.assertTrue(first["encrypted"])
        metadata = store.metadata("tenant-a", first["sha256"])
        self.assertEqual(metadata["encryption"]["state"], "ENCRYPTED")
        self.assertNotIn("tenant-a", json.dumps(metadata, sort_keys=True))
        content_files = [
            path
            for path in (self.root / "cas").rglob("*")
            if path.is_file()
            and not path.name.endswith(".json")
            and not path.name.endswith(".lock")
        ]
        self.assertEqual(len(content_files), 1)
        self.assertNotIn(plaintext, content_files[0].read_bytes())
        self.assertEqual(store.get("tenant-a", first["sha256"]), plaintext)

    def test_ciphertext_metadata_and_key_tampering_fail_authentication(self) -> None:
        store = ContentAddressedArtifactStore(
            self.root / "cas", envelope_cipher=self.cipher
        )
        reference = store.put(
            "tenant-a",
            b"proof",
            media_type="text/plain",
            retention_class="AUDIT",
        )
        digest_hex = reference["sha256"].removeprefix("sha256:")
        tenant_directory = next((self.root / "cas").iterdir())
        content = tenant_directory / digest_hex[:2] / digest_hex
        content.chmod(0o600)
        tampered = bytearray(content.read_bytes())
        tampered[-1] ^= 1
        content.write_bytes(tampered)
        with self.assertRaises(ArtifactStoreError):
            store.get("tenant-a", reference["sha256"])

        other = ContentAddressedArtifactStore(
            self.root / "other",
            envelope_cipher=AesGcmEnvelopeCipher(
                b"b" * 32, key_id="other-artifact-key"
            ),
        )
        other_reference = other.put(
            "tenant-a",
            b"proof",
            media_type="text/plain",
            retention_class="AUDIT",
        )
        wrong_key = ContentAddressedArtifactStore(
            self.root / "other",
            envelope_cipher=AesGcmEnvelopeCipher(
                b"c" * 32, key_id="other-artifact-key"
            ),
        )
        with self.assertRaises(ArtifactStoreError):
            wrong_key.get("tenant-a", other_reference["sha256"])


class ProofBridgeClaimBoundaryTests(unittest.TestCase):
    def test_generation_is_deterministic_and_never_reports_native_proof(self) -> None:
        bridge = FormalProofKernelBridge()
        mapping = exact_digest("7")
        context = {
            "lean4": {
                "hypotheses": ["x >= 0"],
                "conclusion": "x + 0 = x",
                "tactics": ["simp"],
                "semanticMappingDigest": mapping,
            },
            "dafny": {
                "params": [{"name": "x", "type": "int"}],
                "returns": [{"name": "result", "type": "int"}],
                "requires": ["x >= 0"],
                "ensures": ["result == x"],
                "body": "result := x;",
                "semanticMappingDigest": mapping,
            },
            "assumptionHash": exact_digest("8"),
            "tcbHash": exact_digest("9"),
            "environmentDigest": exact_digest("a"),
        }
        first = bridge.synthesize_proof_certificate(
            "identity_theorem", "forall x, x + 0 = x", context=context
        )
        second = bridge.synthesize_proof_certificate(
            "identity_theorem", "forall x, x + 0 = x", context=context
        )
        self.assertEqual(first, second)
        self.assertEqual(first["verification_status"], "NATIVE_VERIFICATION_NOT_RUN")
        self.assertEqual(first["proof_status"], "NOT_RUN")
        self.assertFalse(first["certificate_issued"])
        self.assertEqual(first["certification_status"], "NOT_CERTIFIED")
        self.assertFalse(first["gaps"])
        self.assertNotIn("PROVED_VERIFIED", json.dumps(first, sort_keys=True))

        changed = bridge.synthesize_proof_certificate(
            "identity_theorem", "forall x, x + 1 > x", context=context
        )
        self.assertNotEqual(first["request_digest"], changed["request_digest"])
        self.assertNotEqual(first["formula_digest"], changed["formula_digest"])

    def test_missing_sources_and_proof_bodies_stay_explicit(self) -> None:
        result = FormalProofKernelBridge().synthesize_proof_certificate(
            "unbound_obligation", "P -> P"
        )
        self.assertEqual(result["generated_sources"], {})
        self.assertIn("LEAN4_SOURCE_NOT_GENERATED", result["gaps"])
        self.assertIn("DAFNY_SOURCE_NOT_GENERATED", result["gaps"])

        source = Lean4Generator.generate_theorem("candidate", [], "True")
        self.assertIn("ELMOS_PROOF_BODY_REQUIRED", source)
        self.assertNotIn("sorry", source.lower())
        self.assertNotIn("admit", source.lower())

    def test_unknown_context_and_unsafe_identifiers_fail_closed(self) -> None:
        bridge = FormalProofKernelBridge()
        with self.assertRaises(FormalProofBridgeError):
            bridge.synthesize_proof_certificate(
                "proof", "True", context={"nativeResult": "passed"}
            )
        with self.assertRaises(FormalProofBridgeError):
            Lean4Generator.generate_theorem("proof; axiom forged", [], "True", ["trivial"])


class AttestationClaimBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.issued_at = "2026-08-30T00:00:00Z"
        self.materials = [
            {"uri": "git+https://example.invalid/repository", "sha256": exact_digest("b")}
        ]

    def test_unsigned_provenance_is_not_promoted(self) -> None:
        service = SbomAttestationSigner()
        provenance = service.sign_slsa_provenance(
            artifact_name="service.jar",
            artifact_digest=exact_digest("c"),
            builder_id="urn:elmos:builder:local",
            build_type="urn:elmos:build:formal-transformation:v1",
            invocation_digest=exact_digest("d"),
            environment_digest=exact_digest("e"),
            materials=self.materials,
            issued_at=self.issued_at,
        )
        self.assertEqual(provenance.signing_status, "SIGNATURE_NOT_RUN")
        self.assertIsNone(provenance.signature)
        serialized = canonical_json(provenance.to_dict())
        self.assertNotIn(b"SLSA_LEVEL_4", serialized)
        self.assertNotIn(b"reproducible", serialized)

    def test_sbom_core_digest_is_recomputable_without_self_reference(self) -> None:
        sbom = SbomAttestationSigner().generate_cyclonedx_sbom(
            artifact_name="service.jar",
            artifact_version="1.2.3",
            artifact_digest=exact_digest("c"),
            components=[component()],
            issued_at=self.issued_at,
        )
        properties = {
            item["name"]: item["value"] for item in sbom["properties"]
        }
        core_document = {key: value for key, value in sbom.items() if key != "properties"}
        self.assertEqual(
            properties["elmos:coreDocumentDigest"],
            digest_bytes(canonical_json(core_document)),
        )
        self.assertNotIn("elmos:documentDigest", properties)

    def test_local_signature_is_exactly_labelled_and_tamper_detected(self) -> None:
        signer = HmacLocalAttestationSigner(
            b"s" * 32, key_id="local-attestation-test"
        )
        result = sign_artifact_sbom(
            artifact_name="service.jar",
            artifact_version="1.2.3",
            artifact_digest=exact_digest("c"),
            components=[component()],
            builder_id="urn:elmos:builder:local",
            build_type="urn:elmos:build:formal-transformation:v1",
            invocation_digest=exact_digest("d"),
            environment_digest=exact_digest("e"),
            materials=self.materials,
            issued_at=self.issued_at,
            signer=signer,
        )
        self.assertEqual(result["status"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(result["slsaLevel"], "NOT_ASSESSED")
        self.assertEqual(result["externalSignatureStatus"], "NOT_RUN")
        signature = result["provenance"]["signature"]
        self.assertEqual(signature["algorithm"], "HMAC-SHA256")
        self.assertNotIn("Ed25519", json.dumps(result, sort_keys=True))

        provenance = SbomAttestationSigner(signer).sign_slsa_provenance(
            artifact_name="service.jar",
            artifact_digest=exact_digest("c"),
            builder_id="urn:elmos:builder:local",
            build_type="urn:elmos:build:formal-transformation:v1",
            invocation_digest=exact_digest("d"),
            environment_digest=exact_digest("e"),
            materials=self.materials,
            issued_at=self.issued_at,
        )
        assert provenance.signature is not None
        self.assertTrue(
            signer.verify(canonical_json(provenance.statement), provenance.signature)
        )
        self.assertFalse(
            signer.verify(
                canonical_json({**provenance.statement, "tampered": True}),
                provenance.signature,
            )
        )

    def test_fake_or_missing_crypto_inputs_fail_closed(self) -> None:
        with self.assertRaises(AttestationError):
            HmacLocalAttestationSigner(b"short", key_id="bad-key")
        with self.assertRaises((AttestationError, ValueError)):
            SbomComponent(
                name="z3",
                version="4.12.2",
                purl="pkg:generic/z3@4.12.2",
                component_type="application",
                hashes={"SHA-256": "4a8b..."},
            )
        with self.assertRaises(AttestationError):
            SbomAttestationSigner().generate_cyclonedx_sbom(
                artifact_name="service.jar",
                artifact_version="1.2.3",
                artifact_digest=exact_digest("c"),
                components=[component()],
                issued_at="2026-02-31T00:00:00Z",
            )


class EnvironmentPlanClaimBoundaryTests(unittest.TestCase):
    def test_pinned_plan_has_no_network_install_or_runtime_claim(self) -> None:
        manifest = toolchain_manifest()
        result = export_hermetic_toolchain("dockerfile", manifest=manifest)
        content = result["content"]
        self.assertIn("@sha256:" + "2" * 64, content)
        self.assertIn("USER 65532:65532", content)
        self.assertNotIn("apt-get", content)
        self.assertNotIn("curl", content)
        self.assertEqual(result["nativeBuildStatus"], "NOT_RUN")
        self.assertEqual(result["hermeticityStatus"], "NOT_VERIFIED")
        self.assertEqual(result["slsaLevel"], "NOT_ASSESSED")
        self.assertEqual(result["certificationStatus"], "NOT_CERTIFIED")

        devcontainer = export_hermetic_toolchain(
            "devcontainer", manifest=manifest
        )
        config = json.loads(devcontainer["content"])
        self.assertEqual(config["remoteUser"], "65532")
        self.assertIn("--network=none", config["runArgs"])
        self.assertIn("--read-only", config["runArgs"])

    def test_unpinned_or_implicit_environment_fails_closed(self) -> None:
        with self.assertRaises(EnvironmentPlanError):
            export_hermetic_toolchain("nix")
        with self.assertRaises(EnvironmentPlanError):
            ToolchainManifest(
                target_platform="linux/amd64",
                base_image="ubuntu:latest",
                base_image_digest=exact_digest("2"),
                nixpkgs_revision="nixos-24.05",
                nixpkgs_source_digest=exact_digest("4"),
                toolchains=toolchain_manifest().toolchains,
            )


class CoreSkillClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = StateStore()
        self.runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                artifact_root=Path(self.temporary.name) / "artifacts",
                artifact_envelope_cipher=AesGcmEnvelopeCipher(
                    b"z" * 32, key_id="closure-test-key"
                ),
            ),
        )
        self.identity = TrustedIdentity("tenant-a", "operator-a", "project-a")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def dispatch(
        self, skill_id: str, subject_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        return self.runtime.dispatch(
            skill_id,
            {
                "scope": {
                    "tenantId": "tenant-a",
                    "accountId": "account-a",
                    "projectId": "project-a",
                    "sourceArtifactDigest": "a" * 64,
                    "targetArtifactDigest": "b" * 64,
                    "environmentDigest": "c" * 64,
                    "workloadKey": "closure-tests",
                },
                "subjectId": subject_id,
                "idempotencyKey": "key-" + subject_id,
                **payload,
            },
            self.identity,
        )

    def test_model_release_blocks_unexplained_and_minor_breaking_changes(self) -> None:
        result = self.dispatch(
            "elmos-formal-model-versioning",
            "model-release-a",
            {
                "fromVersion": "1.2.0",
                "toVersion": "1.3.0",
                "fromModel": {"fields": {"amount": "decimal"}},
                "toModel": {"fields": {"amount": "float"}},
                "changeGraph": [
                    {
                        "path": "$.fields.amount",
                        "classification": "BREAKING",
                        "reason": "money precision changed",
                    }
                ],
            },
        )
        self.assertEqual(result["proofStatus"], "ASSUMPTION_REQUIRED")
        output = result["output"]
        self.assertEqual(output["compatibility"], "BREAKING")
        self.assertTrue(output["compatibilityReport"]["violations"])
        self.assertFalse(output["historicalEvidenceOverwritten"])
        persisted = self.store.get_document(
            self.runtime._scope(result["scope"], self.identity),
            "formal_model_release",
            "model-release-a",
        )
        self.assertEqual(persisted["document"]["toModelDigest"], output["toModelDigest"])

    def test_model_changes_require_version_increment_and_baseline_replay(self) -> None:
        unchanged_version = self.dispatch(
            "elmos-formal-model-versioning",
            "model-release-same-version",
            {
                "fromVersion": "1.2.0",
                "toVersion": "1.2.0",
                "fromModel": {"field": "integer"},
                "toModel": {"field": "decimal"},
                "changeGraph": [
                    {
                        "path": "$.field",
                        "classification": "COMPATIBLE",
                        "reason": "widened numeric domain",
                    }
                ],
            },
        )
        self.assertEqual(unchanged_version["proofStatus"], "ASSUMPTION_REQUIRED")
        self.assertIn(
            "changed model release requires a semantic version increment",
            unchanged_version["output"]["violations"],
        )

        compatible = self.dispatch(
            "elmos-formal-model-versioning",
            "model-release-replay",
            {
                "fromVersion": "1.2.0",
                "toVersion": "1.3.0",
                "fromModel": {"field": "integer"},
                "toModel": {"field": "decimal"},
                "changeGraph": [
                    {
                        "path": "$.field",
                        "classification": "COMPATIBLE",
                        "reason": "widened numeric domain",
                    }
                ],
                "proofBaselines": [
                    {"id": "baseline-one", "digest": exact_digest("d")}
                ],
            },
        )
        self.assertEqual(compatible["output"]["compatibility"], "COMPATIBLE")
        self.assertEqual(compatible["output"]["replayStatus"], "NOT_RUN")
        self.assertEqual(compatible["proofStatus"], "ASSUMPTION_REQUIRED")

        regressed = self.dispatch(
            "elmos-formal-model-versioning",
            "model-release-regressed",
            {"fromVersion": "2.0.0", "toVersion": "1.9.9"},
        )
        self.assertEqual(regressed["proofStatus"], "ASSUMPTION_REQUIRED")
        self.assertIn(
            "model release cannot regress its semantic version",
            regressed["output"]["violations"],
        )

    def test_report_uses_one_machine_model_and_keeps_bounded_language(self) -> None:
        artifact = self.runtime.artifact_store.put(
            "tenant-a",
            b"bounded evidence",
            media_type="text/plain",
            retention_class="AUDIT",
        )
        result = self.dispatch(
            "elmos-formal-assurance-report",
            "report-a",
            {
                "outcomes": [
                    {
                        "skillId": "elmos-data-invariant-verifier",
                        "proofStatus": "BOUNDED_NO_COUNTEREXAMPLE",
                        "assuranceLevel": "A1_BOUNDED",
                        "mode": "BOUNDED",
                        "bound": {"samples": 8},
                        "artifactRefs": [artifact],
                    }
                ],
                "coverage": {"required": 1, "evaluated": 1},
                "riskRegister": [],
            },
        )
        output = result["output"]
        self.assertEqual(output["statusCounts"], {"BOUNDED_NO_COUNTEREXAMPLE": 1})
        self.assertIn("bounded search found no counterexample", output["machineJson"])
        self.assertNotIn("fully proved", output["markdown"].lower())
        self.assertTrue(output["machineHumanConsistent"])
        self.assertEqual(len(output["artifactRefs"]), 3)
        self.assertTrue(all(item["encrypted"] for item in output["artifactRefs"]))
        self.assertEqual(output["pdfRenderingStatus"], "NOT_RUN")

    def test_report_rejects_inflated_or_incoherent_proof_states(self) -> None:
        with self.assertRaises(HandlerError):
            self.dispatch(
                "elmos-formal-assurance-report",
                "report-inflated",
                {
                    "outcomes": [
                        {
                            "proofStatus": "PROVED_CERTIFIED",
                            "assuranceLevel": "A0_TESTED",
                            "mode": "CERTIFIED",
                        }
                    ]
                },
            )

        artifact = self.runtime.artifact_store.put(
            "tenant-a",
            b"locally verified certified-proof receipt",
            media_type="application/json",
            retention_class="AUDIT",
        )
        valid = self.dispatch(
            "elmos-formal-assurance-report",
            "report-proved-with-local-evidence",
            {
                "outcomes": [
                    {
                        "proofStatus": "PROVED_CERTIFIED",
                        "assuranceLevel": "A3_CERTIFIED",
                        "mode": "CERTIFIED",
                        "assumptionHash": exact_digest("1"),
                        "tcbHash": exact_digest("2"),
                        "artifactRefs": [artifact],
                    }
                ]
            },
        )
        self.assertEqual(
            valid["output"]["statusCounts"], {"PROVED_CERTIFIED": 1}
        )
        self.assertEqual(valid["certificationStatus"], "NOT_CERTIFIED")
        with self.assertRaises(HandlerError):
            self.dispatch(
                "elmos-formal-assurance-report",
                "report-proved-without-evidence",
                {
                    "outcomes": [
                        {
                            "proofStatus": "PROVED_CERTIFIED",
                            "assuranceLevel": "A3_CERTIFIED",
                            "mode": "CERTIFIED",
                            "assumptionHash": exact_digest("1"),
                            "tcbHash": exact_digest("2"),
                        }
                    ]
                },
            )

    def test_tcb_closure_separates_kernel_solver_and_never_promotes_trust(self) -> None:
        result = self.dispatch(
            "elmos-trusted-computing-base-registry",
            "tcb-a",
            {
                "components": [
                    {
                        "id": "lean-kernel",
                        "version": "4.8.0",
                        "digest": exact_digest("1"),
                        "role": "KERNEL",
                    },
                    {
                        "id": "z3-solver",
                        "version": "4.12.2",
                        "digest": exact_digest("2"),
                        "role": "SOLVER",
                    },
                ]
            },
        )
        output = result["output"]
        self.assertTrue(output["kernelAndSolverTrustSeparated"])
        self.assertEqual(output["tcbClosure"]["trustLevels"]["kernelChecked"], 1)
        self.assertEqual(output["tcbClosure"]["trustLevels"]["solverTrusted"], 1)
        self.assertEqual(output["tcbClosure"]["productionTrustStatus"], "NOT_TRUSTED")

    def test_tcb_normalizes_sbom_digest_and_requires_exact_mutation_action(self) -> None:
        result = self.dispatch(
            "elmos-trusted-computing-base-registry",
            "tcb-normalized",
            {
                "components": [
                    {
                        "id": "solver-one",
                        "version": "1.0.0",
                        "digest": "1" * 64,
                        "role": "SOLVER",
                        "sbomRef": {"sha256": "2" * 64},
                    }
                ]
            },
        )
        self.assertEqual(
            result["output"]["components"][0]["sbomDigest"], exact_digest("2")
        )
        with self.assertRaises(HandlerError):
            self.dispatch(
                "elmos-trusted-computing-base-registry",
                "tcb-wrong-action",
                {"action": "update", "trustedComponent": {}},
            )

    def test_proof_carrying_manifest_is_commit_artifact_and_status_bound(self) -> None:
        artifact = self.runtime.artifact_store.put(
            "tenant-a",
            b"proof certificate bytes",
            media_type="application/octet-stream",
            retention_class="AUDIT",
        )
        result = self.dispatch(
            "elmos-proof-carrying-conversion",
            "proof-package-a",
            {
                "sourceCommit": "1" * 40,
                "targetCommit": "2" * 40,
                "sourceManifestDigest": exact_digest("3"),
                "targetManifestDigest": exact_digest("4"),
                "assumptionDigest": exact_digest("5"),
                "tcbDigest": exact_digest("6"),
                "artifacts": [{**artifact, "path": "certificates/proof.bin"}],
                "proofResults": [
                    {
                        "runId": "run-package-a",
                        "obligationId": "obligation-package-a",
                        "status": "BOUNDED_NO_COUNTEREXAMPLE",
                        "assuranceLevel": "A1_BOUNDED",
                        "engine": "local",
                        "mode": "BOUNDED",
                        "assumptionHash": exact_digest("5"),
                        "tcbHash": exact_digest("6"),
                        "bound": {"samples": 4},
                    }
                ],
                "machineStatus": "BOUNDED_NO_COUNTEREXAMPLE",
                "marketingStatus": "bounded search found no counterexample",
            },
        )
        output = result["output"]
        self.assertEqual(output["manifest"]["machineStatus"], "BOUNDED_NO_COUNTEREXAMPLE")
        self.assertTrue(output["machineMarketingConsistent"])
        self.assertTrue(output["offlineReplayReady"])
        self.assertEqual(output["signatureRequest"]["status"], "NOT_RUN")
        self.assertEqual(result["proofStatus"], "UNSUPPORTED")

    def test_proof_carrying_requires_artifacts_results_and_normalizes_bindings(self) -> None:
        incomplete = self.dispatch(
            "elmos-proof-carrying-conversion",
            "proof-package-empty",
            {"artifacts": []},
        )
        self.assertIn("artifacts", incomplete["output"]["missingBindingIndexes"])
        self.assertIn("proofResults", incomplete["output"]["missingBindingIndexes"])

        artifact = self.runtime.artifact_store.put(
            "tenant-a",
            b"proof certificate bytes",
            media_type="application/octet-stream",
            retention_class="AUDIT",
        )
        normalized = self.dispatch(
            "elmos-proof-carrying-conversion",
            "proof-package-normalized",
            {
                "sourceCommit": "1" * 40,
                "targetCommit": "2" * 40,
                "sourceManifestDigest": "3" * 64,
                "targetManifestDigest": "4" * 64,
                "assumptionDigest": "5" * 64,
                "tcbDigest": "6" * 64,
                "artifacts": [{**artifact, "path": "proof/certificate.bin"}],
                "proofResults": [
                    {
                        "runId": "run-normalized",
                        "obligationId": "obligation-normalized",
                        "status": "BOUNDED_NO_COUNTEREXAMPLE",
                        "assuranceLevel": "A1_BOUNDED",
                        "engine": "local",
                        "mode": "BOUNDED",
                        "assumptionHash": "5" * 64,
                        "tcbHash": "6" * 64,
                        "bound": {"steps": 1},
                    }
                ],
            },
        )
        self.assertEqual(
            normalized["output"]["manifest"]["assumptionDigest"], exact_digest("5")
        )
        self.assertEqual(
            normalized["output"]["manifest"]["tcbDigest"], exact_digest("6")
        )

    def test_proof_carrying_rejects_forged_or_missing_local_cas_references(self) -> None:
        artifact = self.runtime.artifact_store.put(
            "tenant-a",
            b"proof certificate bytes",
            media_type="application/octet-stream",
            retention_class="AUDIT",
        )
        forged = dict(artifact)
        forged["uri"] = (
            "cas://" + "0" * 64 + "/" + str(artifact["sha256"])
        )
        missing = dict(artifact)
        missing_digest = exact_digest("f")
        missing["sha256"] = missing_digest
        missing["uri"] = str(artifact["uri"]).rsplit("/", 1)[0] + "/" + missing_digest
        for index, reference in enumerate((forged, missing)):
            with self.subTest(reference=index), self.assertRaises(HandlerError):
                self.dispatch(
                    "elmos-proof-carrying-conversion",
                    f"proof-package-invalid-{index}",
                    {
                        "artifacts": [
                            {**reference, "path": "certificates/proof.bin"}
                        ]
                    },
                )

    def test_verified_core_binds_generator_contract_and_encrypted_artifacts(self) -> None:
        result = self.dispatch(
            "elmos-verified-core-generator",
            "verified-core-a",
            {
                "functionName": "identity",
                "parameters": ["value"],
                "expression": "value",
                "formula": "value = value",
                "contract": {
                    "preconditions": [],
                    "postconditions": ["result == value"],
                    "invariants": [],
                },
                "adapterMappings": [
                    {
                        "sourceField": "value",
                        "targetField": "value",
                        "mappingKind": "identity",
                        "evidenceStatus": "TESTED",
                        "evidenceDigest": exact_digest("d"),
                    }
                ],
            },
        )
        output = result["output"]
        self.assertTrue(output["verifiedCoreTestedShellBoundaryExplicit"])
        self.assertFalse(output["contractsRemoved"])
        self.assertTrue(output["generatorDigest"].startswith("sha256:"))
        self.assertEqual(
            output["proofVerificationRequest"]["verification_status"],
            "NATIVE_VERIFICATION_NOT_RUN",
        )
        self.assertTrue(all(item["encrypted"] for item in output["artifactRefs"]))

    def test_verified_core_rejects_unsafe_identifiers_and_unbound_proof_claims(self) -> None:
        for subject, payload in (
            (
                "verified-core-keyword-function",
                {
                    "functionName": "class",
                    "parameters": ["value"],
                    "expression": "value",
                },
            ),
            (
                "verified-core-keyword-parameter",
                {
                    "functionName": "identity",
                    "parameters": ["for"],
                    "expression": "for",
                },
            ),
            (
                "verified-core-unbound-proof",
                {
                    "functionName": "identity",
                    "parameters": ["value"],
                    "expression": "value",
                    "adapterMappings": [
                        {
                            "sourceField": "value",
                            "targetField": "value",
                            "mappingKind": "identity",
                            "evidenceStatus": "PROVED",
                        }
                    ],
                },
            ),
            (
                "verified-core-unbound-test",
                {
                    "functionName": "identity",
                    "parameters": ["value"],
                    "expression": "value",
                    "adapterMappings": [
                        {
                            "sourceField": "value",
                            "targetField": "value",
                            "mappingKind": "identity",
                            "evidenceStatus": "TESTED",
                        }
                    ],
                },
            ),
        ):
            with self.subTest(subject=subject), self.assertRaises(HandlerError):
                self.dispatch("elmos-verified-core-generator", subject, payload)

        bound = self.dispatch(
            "elmos-verified-core-generator",
            "verified-core-bound-proof",
            {
                "functionName": "identity",
                "parameters": ["value"],
                "expression": "value",
                "adapterMappings": [
                    {
                        "sourceField": "value",
                        "targetField": "value",
                        "mappingKind": "identity",
                        "evidenceStatus": "PROVED",
                        "evidenceDigest": exact_digest("e"),
                    }
                ],
            },
        )
        mapping = bound["output"]["coreManifest"]["adapterMappings"][0]
        self.assertEqual(
            mapping["evidenceStatus"],
            "DECLARED_PROVED_EVIDENCE_BOUND_NOT_VERIFIED",
        )
        self.assertIn(
            "ADAPTER_MAPPING_INDEPENDENT_VERIFICATION_REQUIRED:0",
            bound["output"]["coreManifest"]["gaps"],
        )


if __name__ == "__main__":
    unittest.main()
