from __future__ import annotations

from contextlib import redirect_stderr
import io
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_release_contract() -> ModuleType:
    path = ROOT / "tools/release_contract.py"
    spec = importlib.util.spec_from_file_location(
        "proof_harness_release_contract_test", path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("release contract module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryAssetTests(unittest.TestCase):
    def test_composite_release_inventory_is_exact_and_fail_closed(self) -> None:
        package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(package["project"]["version"], "3.1.0")

        module = load_release_contract()
        manifest = module.build_manifest(ROOT)
        self.assertEqual(
            manifest["artifact"], "elmos-proof-driven-harness-engine@3.1.0"
        )
        self.assertEqual(manifest["counts"]["baseSchemas"], 18)
        self.assertEqual(manifest["counts"]["deltaSchemas"], 15)
        self.assertEqual(manifest["counts"]["roles"]["delta-example"], 15)
        self.assertEqual(manifest["counts"]["roles"]["delta-adapter-profile"], 5)
        self.assertEqual(manifest["counts"]["roles"]["supply-chain-boundary"], 1)
        self.assertEqual(manifest["counts"]["files"], 133)
        self.assertEqual(manifest["counts"]["roles"]["runtime-source"], 31)
        self.assertEqual(
            manifest["counts"]["roles"]["delta-acceptance-traceability"], 1
        )
        release_paths = {entry["path"] for entry in manifest["files"]}
        self.assertTrue(
            {
                "README.md",
                "deploy/README.md",
                "deploy/Dockerfile",
                "deploy/helm/proof-harness/values.yaml",
                "deploy/helm/proof-harness/values.schema.json",
                "deploy/helm/proof-harness/templates/deployment.yaml",
                "src/elmos_proof_harness/assurance_policies.py",
                "supply-chain/delta-v3.1-acceptance-bindings.json",
            }.issubset(release_paths)
        )
        self.assertEqual(
            [material["version"] for material in manifest["sourceMaterials"]],
            ["3.0.0", "3.1.0"],
        )
        packaged_assets = {
            item
            for items in package["tool"]["setuptools"]["data-files"].values()
            for item in items
        }
        expected_assets = {
            relative
            for _, relative in module.RELEASE_ENTRIES
            if not relative.startswith("src/elmos_proof_harness/")
        } | {module.MANIFEST_RELATIVE.as_posix()}
        self.assertEqual(packaged_assets, expected_assets)
        self.assertFalse(any("*" in item for item in packaged_assets))
        self.assertEqual(
            package["tool"]["setuptools"]["packages"], ["elmos_proof_harness"]
        )
        self.assertFalse(package["tool"]["setuptools"]["include-package-data"])
        self.assertNotIn("packages", package["tool"]["setuptools"].get("find", {}))
        self.assertEqual(manifest["claimBoundary"]["commercialDistribution"], "BLOCKED")
        self.assertEqual(manifest["claimBoundary"]["certification"], "NOT_CERTIFIED")
        for member in manifest["files"]:
            self.assertTrue(
                set(Path(member["path"]).parts).isdisjoint(module.EXCLUDED_NAMES),
                member["path"],
            )

    def test_json_contracts_are_closed_and_parseable(self) -> None:
        schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertEqual(len(schema_paths), 18)
        for path in schema_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                document["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
            self.assertEqual(document["type"], "object")
            self.assertFalse(document["additionalProperties"], path.name)

        delta_schema_paths = sorted((ROOT / "schemas/delta-v3.1").glob("*.schema.json"))
        self.assertEqual(len(delta_schema_paths), 15)
        for path in delta_schema_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                document["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertEqual(document["type"], "object")
            self.assertFalse(document["additionalProperties"], path.name)

        values = json.loads(
            (ROOT / "deploy/helm/proof-harness/values.schema.json").read_text(
                encoding="utf-8"
            )
        )
        digest = values["properties"]["image"]["properties"]["digest"]
        self.assertEqual(digest["pattern"], "^sha256:[0-9a-f]{64}$")
        self.assertEqual(values["properties"]["replicaCount"]["minimum"], 2)
        self.assertIn("runtimeAssurance", values["required"])
        runtime_assurance = values["properties"]["runtimeAssurance"]
        self.assertFalse(runtime_assurance["additionalProperties"])
        self.assertEqual(runtime_assurance["required"], ["factory"])
        factory = runtime_assurance["properties"]["factory"]
        self.assertGreater(factory["minLength"], 0)
        self.assertRegex("company.runtime:create_control_plane", factory["pattern"])
        for invalid in ("", "module-only", "module:factory:extra", "bad-module:f"):
            self.assertNotRegex(invalid, factory["pattern"])
        postgresql = values["properties"]["postgresql"]
        self.assertIn("authorityExistingSecret", postgresql["required"])
        self.assertIn("authorityDsnKey", postgresql["required"])
        self.assertGreater(
            postgresql["properties"]["authorityExistingSecret"]["minLength"], 0
        )

    def test_postgres_migration_is_tenant_qualified_and_fail_closed(self) -> None:
        sql = (ROOT / "migrations/V001__proof_harness_core.sql").read_text(
            encoding="utf-8"
        )
        self.assertGreaterEqual(sql.count("tenant_id uuid NOT NULL"), 20)
        self.assertGreaterEqual(sql.count("project_id uuid NOT NULL"), 20)
        self.assertGreaterEqual(sql.count("FORCE ROW LEVEL SECURITY"), 1)
        self.assertIn("proof_harness.current_tenant_id()", sql)
        self.assertIn("proof_harness.current_project_id()", sql)
        self.assertIn("tenant_project_isolation", sql)
        self.assertIn("assert_event_fence", sql)
        self.assertIn("reject_immutable_mutation", sql)
        self.assertIn("environment_authority_revocations", sql)
        self.assertIn("external_signature_revocations", sql)
        self.assertIn("attested_status", sql)
        self.assertIn("certification_authority", sql)
        self.assertIn("'AWAITING_REVIEW'", sql)
        self.assertIn("'TIMED_OUT'", sql)
        self.assertIn("baseline_digest text NOT NULL", sql)
        self.assertIn("completion_review_signature_required", sql)
        self.assertIn("effective_completion_reviews", sql)
        self.assertIn(
            "external completion decision lacks a live bound signature receipt", sql
        )
        self.assertNotRegex(
            sql, re.compile(r"REPLACE_WITH|SET_ME|TODO|FIXME", re.IGNORECASE)
        )
        self.assertNotIn("ON DELETE CASCADE", sql)

    def test_helm_defaults_require_exact_external_configuration(self) -> None:
        values = (ROOT / "deploy/helm/proof-harness/values.yaml").read_text(
            encoding="utf-8"
        )
        deployment = (
            ROOT / "deploy/helm/proof-harness/templates/deployment.yaml"
        ).read_text(encoding="utf-8")
        network = (
            ROOT / "deploy/helm/proof-harness/templates/networkpolicy.yaml"
        ).read_text(encoding="utf-8")
        dockerfile = (ROOT / "deploy/Dockerfile").read_text(encoding="utf-8")
        self.assertIn('repository: ""', values)
        self.assertIn('digest: ""', values)
        self.assertIn('existingSecret: ""', values)
        runtime_values = values.split("runtimeAssurance:\n", maxsplit=1)[1].split(
            "\ntransport:", maxsplit=1
        )[0]
        self.assertIn('  factory: ""', runtime_values)
        self.assertIn("@{{ .Values.image.digest }}", deployment)
        self.assertIn("ELMOS_RUNTIME_ASSURANCE_FACTORY", deployment)
        self.assertIn('required "runtimeAssurance.factory is required"', deployment)
        self.assertIn("ELMOS_POSTGRES_AUTHORITY_DSN", deployment)
        self.assertIn(
            'required "postgresql.authorityExistingSecret is required"',
            deployment,
        )
        self.assertIn(
            'required "postgresql.authorityDsnKey is required"', deployment
        )
        self.assertIn(
            "postgresql application and authority writer must use distinct secret keys",
            deployment,
        )
        self.assertIn("runAsNonRoot: true", deployment)
        self.assertIn("readOnlyRootFilesystem: true", deployment)
        self.assertIn("allowPrivilegeEscalation: false", deployment)
        self.assertIn("automountServiceAccountToken: false", deployment)
        self.assertIn("ingress: []", network)
        self.assertNotIn("0.0.0.0/0", network)
        self.assertIn("--check-installed", dockerfile)
        self.assertIn("pip install --no-cache-dir --no-compile", dockerfile)
        self.assertIn('ELMOS_RUNTIME_ASSURANCE_FACTORY=""', dockerfile)
        self.assertIn(
            '--expected-manifest-sha256 "${RELEASE_MANIFEST_SHA256}"',
            dockerfile,
        )

    def test_production_cli_rejects_a_missing_runtime_assurance_factory(self) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "ELMOS_PROOF_HARNESS_DB",
                "ELMOS_RUNTIME_ASSURANCE_FACTORY",
            }
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = os.fspath(ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "elmos_proof_harness",
                "serve",
                "--runtime-mode",
                "production",
                "--expected-issuer",
                "https://issuer.example",
                "--expected-audience",
                "proof-harness",
                "--transport-mode",
                "trusted-proxy",
                "--authenticator-factory",
                "company.auth:create_authenticator",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        error = json.loads(result.stderr)["error"]
        self.assertEqual(error["type"], "ValueError")
        self.assertEqual(
            error["message"],
            "missing required production serve configuration: "
            "runtime assurance factory",
        )

    def test_observability_catalog_excludes_sensitive_labels(self) -> None:
        catalog = (ROOT / "observability/metrics.yaml").read_text(encoding="utf-8")
        for forbidden in (
            "tenant_id",
            "project_id",
            "actor_id",
            "repository_url",
            "source_path",
            "evidence_id",
        ):
            self.assertIn(f"- {forbidden}", catalog)
            self.assertNotRegex(catalog, rf"labels:\s*\[[^\]]*\b{forbidden}\b")
        alerts = (ROOT / "observability/alerts.yaml").read_text(encoding="utf-8")
        self.assertIn("ProofHarnessStatusInflationAttempt", alerts)
        self.assertIn("ProofHarnessUnknownExternalOutcome", alerts)
        self.assertIn("ProofHarnessCriticalObligationBlocked", alerts)

    def test_openapi_never_grants_identity_from_transport_payload(self) -> None:
        spec = (ROOT / "openapi/proof-harness-v3.openapi.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("version: 3.1.0", spec)
        self.assertIn("request bodies cannot grant authority", spec)
        self.assertIn("Idempotency-Key", spec)
        self.assertIn("oauth2", spec)
        self.assertIn("/v3/invocations:", spec)
        self.assertIn("READY_FOR_EXTERNAL_GATE", spec)
        self.assertNotIn("CERTIFIED_COMPLETE", spec)

    def test_public_contracts_require_the_full_revision_and_release_gate_set(
        self,
    ) -> None:
        invocation = json.loads(
            (ROOT / "schemas/invocation.schema.json").read_text(encoding="utf-8")
        )
        required_revisions = set(invocation["properties"]["revisionSet"]["required"])
        self.assertEqual(
            required_revisions,
            {
                "revisionSetId",
                "source",
                "baseline",
                "requirements",
                "policy",
                "workflow",
                "modelRoute",
                "toolchain",
                "environment",
                "domainPack",
            },
        )
        revision_set = json.loads(
            (ROOT / "schemas/revision-set.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(revision_set["required"]),
            {
                "revisionSetId",
                "tenantId",
                "projectId",
                "goalId",
                "source",
                "baseline",
                "requirements",
                "policy",
                "workflow",
                "modelRoute",
                "toolchain",
                "environment",
                "domainPack",
                "createdAt",
            },
        )

        review = json.loads(
            (ROOT / "schemas/completion-review.schema.json").read_text(encoding="utf-8")
        )
        gate_results = review["properties"]["gateResults"]
        self.assertEqual(
            set(gate_results["required"]),
            {"P05", "E0", "E1", "E2", "E3", "E4", "E5"},
        )
        self.assertFalse(gate_results["additionalProperties"])
        signature = review["properties"]["externalSignature"]
        self.assertTrue(
            {
                "receiptId",
                "tenantId",
                "projectId",
                "signerIdentity",
                "providerId",
                "verificationEvidenceId",
                "issuedAt",
                "expiresAt",
                "independent",
                "certificationAuthority",
                "attestedStatus",
            }.issubset(signature["required"])
        )
        self.assertEqual(signature["properties"]["independent"], {"const": True})

        certificate = json.loads(
            (ROOT / "schemas/completion-certificate.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            certificate["$defs"]["digest"]["pattern"],
            "^sha256:[0-9a-f]{64}$",
        )
        self.assertTrue(
            {
                "productionAssessment",
                "signatureReceiptId",
                "signatureReceiptSha256",
            }.issubset(certificate["required"])
        )
        certified_rule = certificate["allOf"][1]["then"]["properties"]
        self.assertEqual(certified_rule["productionAssessment"], {"const": True})
        self.assertEqual(certified_rule["gateResults"]["minItems"], 7)
        self.assertEqual(certified_rule["gateResults"]["maxItems"], 7)
        self.assertEqual(
            len(certified_rule["gateResults"]["allOf"]),
            7,
        )
        proof_statuses = certificate["properties"]["statusCounts"]["propertyNames"][
            "enum"
        ]
        self.assertNotIn("FAIL", proof_statuses)
        self.assertIn("REFUTED_WITH_COUNTEREXAMPLE", proof_statuses)

        passing_review = review["$defs"]["allPassingProductionGates"]
        self.assertEqual(
            set(passing_review["required"]),
            {"P05", "E0", "E1", "E2", "E3", "E4", "E5"},
        )
        self.assertTrue(
            all(
                definition == {"const": "PASS"}
                for definition in passing_review["properties"].values()
            )
        )

    def test_supply_chain_records_do_not_manufacture_release_evidence(self) -> None:
        sbom = json.loads(
            (ROOT / "supply-chain/sbom.cdx.json").read_text(encoding="utf-8")
        )
        policy = json.loads(
            (ROOT / "supply-chain/release-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        source = sbom["components"][0]
        properties = {item["name"]: item["value"] for item in source["properties"]}
        self.assertEqual(properties["ai.elmos.executed"], "false")
        self.assertEqual(
            properties["ai.elmos.selective-inert-data-materialized"], "true"
        )
        self.assertEqual(
            properties["ai.elmos.executable-content-materialized"], "false"
        )
        self.assertEqual(properties["ai.elmos.approved-license"], "ABSENT")
        self.assertEqual(properties["ai.elmos.signature"], "ABSENT")
        self.assertEqual(sbom["metadata"]["component"]["version"], "3.1.0")
        self.assertEqual(len(sbom["components"]), 2)
        delta_source = sbom["components"][1]
        self.assertEqual(delta_source["version"], "3.1.0")
        self.assertEqual(
            delta_source["hashes"][0]["content"],
            "13ba6f089d3c367affe3e03999418029873d842e07a8c80cfaeeffb4308a7a37",
        )
        integrity = json.loads(
            (ROOT / "supply-chain/delta-v3.1-integrity.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            integrity["artifact"], "elmos-proof-driven-harness-engine@3.1.0"
        )
        self.assertEqual(
            [material["version"] for material in integrity["materials"]],
            ["3.0.0", "3.1.0"],
        )
        self.assertTrue(
            all(not material["executed"] for material in integrity["materials"])
        )
        self.assertEqual(integrity["commercial_distribution"], "BLOCKED")
        self.assertEqual(integrity["certification"], "NOT_CERTIFIED")
        self.assertEqual(policy["local_maximum"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(policy["artifact"], "elmos-proof-driven-harness-engine@3.1.0")
        self.assertEqual(
            policy["source_materials"],
            {
                "base": "elmos-proof-driven-agentic-harness-repository-semantic-compiler@3.0.0",
                "delta": "elmos-v3-harness-runtime-assurance-delta@3.1.0",
            },
        )
        self.assertEqual(policy["release_authority"], "EXTERNAL_REQUIRED")
        self.assertTrue(
            all(
                value == "NOT_RUN"
                for value in policy["required_before_distribution"].values()
            )
        )


class ReleaseContractSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_release_contract()

    def _materialize_release_tree(self, destination: Path) -> None:
        for _, relative in self.contract.RELEASE_ENTRIES:
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _zip(
        self, members: list[tuple[zipfile.ZipInfo | str, bytes]]
    ) -> zipfile.ZipFile:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members:
                archive.writestr(name, payload)
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def test_generator_rejects_unexpected_assets_and_intermediate_symlinks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve(strict=True)
            release_root = temporary_root / "release"
            release_root.mkdir()
            self._materialize_release_tree(release_root)
            unexpected = release_root / "schemas/unexpected.schema.json"
            unexpected.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "managed release tree is not exact",
            ):
                self.contract.build_manifest(release_root)
            unexpected.unlink()

            unexpected_runtime = (
                release_root / "src/elmos_proof_harness/unexpected_runtime.py"
            )
            unexpected_runtime.write_text("VALUE = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "managed release tree is not exact",
            ):
                self.contract.build_manifest(release_root)
            unexpected_runtime.unlink()

            unexpected_helm = (
                release_root
                / "deploy/helm/proof-harness/templates/unexpected-resource.yaml"
            )
            unexpected_helm.write_text("kind: ConfigMap\n", encoding="utf-8")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "managed release tree is not exact",
            ):
                self.contract.build_manifest(release_root)
            unexpected_helm.unlink()

            real_delta = temporary_root / "outside-delta"
            shutil.copytree(release_root / "schemas/delta-v3.1", real_delta)
            shutil.rmtree(release_root / "schemas/delta-v3.1")
            os.symlink(real_delta, release_root / "schemas/delta-v3.1")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "linked filesystem member",
            ):
                self.contract.build_manifest(release_root)

    def test_generator_never_replaces_a_manifest_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve(strict=True)
            release_root = temporary_root / "release"
            release_root.mkdir()
            self._materialize_release_tree(release_root)
            outside = temporary_root / "outside.json"
            outside.write_bytes(b"outside-is-unchanged\n")
            manifest = release_root / self.contract.MANIFEST_RELATIVE
            os.symlink(outside, manifest)
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "linked filesystem member",
            ):
                self.contract.generate(release_root)
            self.assertEqual(outside.read_bytes(), b"outside-is-unchanged\n")

    def test_anchored_directory_rejects_rename_and_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve(strict=True)
            anchored = temporary_root / "anchored"
            moved = temporary_root / "moved"
            anchored.mkdir()
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "pathname identity changed",
            ):
                with self.contract._anchored_directory(anchored):
                    anchored.rename(moved)
                    anchored.mkdir()

    def test_file_read_rejects_pathname_swap_after_descriptor_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve(strict=True)
            victim = temporary_root / "victim.txt"
            displaced = temporary_root / "displaced.txt"
            victim.write_bytes(b"stable payload")
            original_read = self.contract._read_descriptor
            swapped = False

            def swap_after_read(
                descriptor: int,
                label: str,
                *,
                limit: int,
            ) -> bytes:
                nonlocal swapped
                payload = original_read(descriptor, label, limit=limit)
                if not swapped:
                    swapped = True
                    victim.rename(displaced)
                    victim.write_bytes(payload)
                return payload

            with (
                self.contract._anchored_directory(temporary_root) as (_, root_fd),
                mock.patch.object(
                    self.contract,
                    "_read_descriptor",
                    side_effect=swap_after_read,
                ),
                self.assertRaisesRegex(
                    self.contract.ReleaseContractError,
                    "pathname identity changed",
                ),
            ):
                self.contract._read_file_at(root_fd, victim.name)

    def test_manifest_builder_rescans_after_the_second_file_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release_root = Path(temporary).resolve(strict=True) / "release"
            release_root.mkdir()
            self._materialize_release_tree(release_root)
            unexpected = release_root / "schemas/unexpected-after-snapshot.json"
            original_read = self.contract._read_file_snapshot_at
            reads = 0

            def add_after_second_snapshot(
                root_fd: int,
                relative: str,
                *,
                limit: int = self.contract.MAX_FILE_BYTES,
            ) -> object:
                nonlocal reads
                snapshot = original_read(root_fd, relative, limit=limit)
                reads += 1
                if reads == len(self.contract.RELEASE_ENTRIES) * 2:
                    unexpected.write_bytes(b"{}\n")
                return snapshot

            with (
                mock.patch.object(
                    self.contract,
                    "_read_file_snapshot_at",
                    side_effect=add_after_second_snapshot,
                ),
                self.assertRaisesRegex(
                    self.contract.ReleaseContractError,
                    "managed release tree is not exact",
                ),
            ):
                self.contract.build_manifest(release_root)

    def test_wheel_members_require_canonical_collision_free_names(self) -> None:
        cases = (
            [
                ("elmos_proof_harness/Module.py", b"a"),
                ("elmos_proof_harness/module.py", b"b"),
            ],
            [("elmos_proof_harness//module.py", b"a")],
            [("elmos_proof_harness/ｍodule.py", b"a")],
        )
        for members in cases:
            with self.subTest(member=members[-1][0]):
                archive = self._zip(members)
                with archive, self.assertRaises(self.contract.ReleaseContractError):
                    self.contract._safe_zip_members(archive)

    def test_wheel_members_reject_bombs_symlinks_and_aggregate_overflow(self) -> None:
        archive = self._zip([("bomb.bin", b"0" * (1024 * 1024))])
        with (
            archive,
            self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "compression ratio",
            ),
        ):
            self.contract._safe_zip_members(archive)

        linked = zipfile.ZipInfo("linked.py")
        linked.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self._zip([(linked, b"target.py")])
        with (
            archive,
            self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "linked or special",
            ),
        ):
            self.contract._safe_zip_members(archive)

        archive = self._zip([("one.bin", b"12345678"), ("two.bin", b"abcdefgh")])
        with (
            archive,
            mock.patch.object(
                self.contract,
                "MAX_WHEEL_UNCOMPRESSED_BYTES",
                15,
            ),
            self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "aggregate uncompressed",
            ),
        ):
            self.contract._safe_zip_members(archive)

        archive = self._zip([("one.bin", b"12345678"), ("two.bin", b"abcdefgh")])
        with (
            archive,
            mock.patch.object(
                self.contract,
                "MAX_WHEEL_COMPRESSED_BYTES",
                1,
            ),
            self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "aggregate compressed",
            ),
        ):
            self.contract._safe_zip_members(archive)

        members = [(f"members/{index:04d}.txt", b"") for index in range(513)]
        archive = self._zip(members)
        with (
            archive,
            self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "too many entries",
            ),
        ):
            self.contract._safe_zip_members(archive)

    def test_wheel_input_symlink_is_rejected_before_zip_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve(strict=True)
            target = temporary_root / "real.whl"
            target.write_bytes(b"not-a-wheel")
            linked = temporary_root / "linked.whl"
            os.symlink(target, linked)
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "input symlink is forbidden",
            ):
                with self.contract._open_wheel(linked):
                    self.fail("wheel symlink unexpectedly opened")

    def test_wheel_file_and_directory_pathnames_are_revalidated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve(strict=True)
            wheel = temporary_root / "direct.whl"
            displaced = temporary_root / "direct.displaced.whl"
            wheel.write_bytes(b"wheel payload")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "wheel (changed while reading|pathname identity changed)",
            ):
                with self.contract._open_wheel(wheel):
                    wheel.rename(displaced)
                    wheel.write_bytes(b"wheel payload")

            wheel_directory = temporary_root / "wheels"
            moved_directory = temporary_root / "wheels-moved"
            wheel_directory.mkdir()
            candidate_name = self.contract.WHEEL_DISTRIBUTION + "-py3-none-any.whl"
            candidate = wheel_directory / candidate_name
            candidate.write_bytes(b"directory wheel payload")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "wheel directory pathname identity changed",
            ):
                with self.contract._open_wheel(wheel_directory):
                    wheel_directory.rename(moved_directory)
                    wheel_directory.mkdir()
                    (wheel_directory / candidate_name).write_bytes(
                        b"directory wheel payload"
                    )

    def test_manifest_nested_shape_errors_are_controlled(self) -> None:
        manifest = self.contract.build_manifest(ROOT)
        malformed_values = []
        malformed = dict(manifest)
        malformed["counts"] = []
        malformed_values.append(malformed)
        malformed = dict(manifest)
        malformed["files"] = [dict(manifest["files"][0], path=7)] + manifest["files"][
            1:
        ]
        malformed_values.append(malformed)
        malformed = dict(manifest)
        malformed["files"] = [dict(manifest["files"][0], bytes=True)] + manifest[
            "files"
        ][1:]
        malformed_values.append(malformed)
        malformed = dict(manifest)
        malformed_counts = dict(manifest["counts"])
        malformed_roles = dict(malformed_counts["roles"])
        one_count_role = next(
            role for role, count in malformed_roles.items() if count == 1
        )
        malformed_roles[one_count_role] = True
        malformed_counts["roles"] = malformed_roles
        malformed["counts"] = malformed_counts
        malformed_values.append(malformed)
        for malformed in malformed_values:
            with self.subTest(field=type(malformed.get("counts")).__name__):
                with self.assertRaises(self.contract.ReleaseContractError):
                    self.contract._load_manifest(
                        self.contract.json_bytes(malformed),
                        "malformed-test",
                    )
        with self.assertRaises(self.contract.ReleaseContractError):
            self.contract._load_manifest(
                b'{"artifact":"first","artifact":"duplicate"}\n',
                "duplicate-key-test",
            )

    def test_installed_check_requires_pin_and_rejects_every_extra_kind(self) -> None:
        manifest = self.contract.build_manifest(ROOT)
        manifest_payload = self.contract.json_bytes(manifest)
        manifest_pin = self.contract.digest(manifest_payload)
        with tempfile.TemporaryDirectory() as temporary:
            installation = Path(temporary).resolve(strict=True)
            assets = installation / "assets"
            module = installation / "module"
            assets.mkdir()
            module.mkdir()
            runtime_prefix = "src/elmos_proof_harness/"
            for entry in manifest["files"]:
                relative = entry["path"]
                if relative.startswith(runtime_prefix):
                    target = module / relative.removeprefix(runtime_prefix)
                else:
                    target = assets / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            installed_manifest = assets / self.contract.MANIFEST_RELATIVE
            installed_manifest.parent.mkdir(parents=True, exist_ok=True)
            installed_manifest.write_bytes(manifest_payload)
            checked = self.contract.check_installed(assets, module, manifest_pin)
            self.assertEqual(checked["contractRoot"], manifest["contractRoot"])
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "requires --expected-manifest-sha256",
            ):
                self.contract.check_installed(assets, module)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = self.contract.main(
                    [
                        "--check-installed",
                        "--assets-root",
                        os.fspath(assets),
                        "--module-root",
                        os.fspath(module),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertIn("requires --expected-manifest-sha256", stderr.getvalue())

            bytecode = module / "__pycache__/module.cpython-314.pyc"
            bytecode.parent.mkdir()
            bytecode.write_bytes(b"untrusted-loadable-bytecode")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "exact manifest inventory",
            ):
                self.contract.check_installed(assets, module, manifest_pin)
            shutil.rmtree(bytecode.parent)

            loose_bytecode = module / "unmanifested.pyc"
            loose_bytecode.write_bytes(b"untrusted-loadable-bytecode")
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "exact manifest inventory",
            ):
                self.contract.check_installed(assets, module, manifest_pin)
            loose_bytecode.unlink()

            extra_regular = module / "unmanifested.txt"
            extra_regular.write_text("unexpected", encoding="utf-8")
            with self.assertRaises(self.contract.ReleaseContractError):
                self.contract.check_installed(assets, module, manifest_pin)
            extra_regular.unlink()

            native = module / "unmanifested.so"
            native.write_bytes(b"native")
            with self.assertRaises(self.contract.ReleaseContractError):
                self.contract.check_installed(assets, module, manifest_pin)
            native.unlink()

            linked = module / "unmanifested-link"
            os.symlink(module / "__init__.py", linked)
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "linked filesystem member",
            ):
                self.contract.check_installed(assets, module, manifest_pin)
            linked.unlink()

            special = module / "unmanifested-fifo"
            os.mkfifo(special)
            with self.assertRaisesRegex(
                self.contract.ReleaseContractError,
                "special filesystem member",
            ):
                self.contract.check_installed(assets, module, manifest_pin)
            special.unlink()

            moved_assets = installation / "assets-moved"
            original_revalidate = self.contract._revalidate_file_at
            swapped = False

            def swap_assets_after_final_member_check(
                root_fd: int,
                relative: str,
                expected: tuple[int, int, int, int, int],
            ) -> None:
                nonlocal swapped
                original_revalidate(root_fd, relative, expected)
                if not swapped:
                    swapped = True
                    assets.rename(moved_assets)
                    assets.mkdir()

            with (
                mock.patch.object(
                    self.contract,
                    "_revalidate_file_at",
                    side_effect=swap_assets_after_final_member_check,
                ),
                self.assertRaisesRegex(
                    self.contract.ReleaseContractError,
                    "anchored directory pathname identity changed",
                ),
            ):
                self.contract.check_installed(assets, module, manifest_pin)


if __name__ == "__main__":
    unittest.main()
