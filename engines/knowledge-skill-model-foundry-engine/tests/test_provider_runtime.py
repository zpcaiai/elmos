"""Exact production host Provider manifest compilation."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

from elmos_foundry.external_bindings import exact_external_binding
from elmos_foundry.native_semantics import load_native_programs
from elmos_foundry.pipelines import exact_pipeline_binding
from elmos_foundry.provider_runtime import (
    MANIFEST_SCHEMA_VERSION,
    ProviderRuntimeManifestError,
    load_provider_runtime_manifest,
)
from elmos_foundry.skills import load_compiled_catalog


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ProviderRuntimeManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_compiled_catalog()
        cls.programs = load_native_programs()
        cls.executable = Path(sys.executable).resolve()
        cls.executable_digest = file_digest(cls.executable)

    def route(self, skill_name: str) -> dict[str, object]:
        binding, route = exact_external_binding(
            skill_name, self.catalog.atomic_skills[skill_name]
        )
        return {
            "skill_name": skill_name,
            "adapter_id": binding.adapter_id,
            "adapter_version": binding.version,
            "adapter_digest": binding.digest,
            "route_id": route.route_id,
            "route_version": route.version,
            "route_digest": route.digest,
            "operation": route.operation,
            "semantic_program_digest": "sha256:" + self.programs[skill_name].digest,
            "provider_id": "provider-host-test",
            "provider_version": "1.0.0",
            "executable": str(self.executable),
            "executable_digest": self.executable_digest,
            "arguments": ["--provider-mode", "strict"],
            "inherited_environment": ["ELMOS_PROVIDER_ENDPOINT"],
            "timeout_seconds": 30,
            "max_output_bytes": 1024 * 1024,
        }

    def manifest(self, routes: list[dict[str, object]]) -> dict[str, object]:
        digest = self.catalog.content_sha256
        if not digest.startswith("sha256:"):
            digest = "sha256:" + digest
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "broker_id": "broker-host-test",
            "broker_version": "1.0.0",
            "catalog_digest": digest,
            "skill_routes": routes,
            "pipeline_routes": [],
        }

    def pipeline_route(self, pipeline_name: str) -> dict[str, object]:
        binding, route = exact_pipeline_binding(
            pipeline_name, self.catalog.pipelines[pipeline_name]
        )
        return {
            "pipeline_name": pipeline_name,
            "adapter_id": binding.adapter_id,
            "adapter_version": binding.version,
            "adapter_digest": binding.digest,
            "route_id": route.route_id,
            "route_version": route.version,
            "route_digest": route.digest,
            "operation": route.operation,
            "provider_id": "provider-host-test",
            "provider_version": "1.0.0",
            "executable": str(self.executable),
            "executable_digest": self.executable_digest,
            "arguments": ["--pipeline-mode", "strict"],
            "inherited_environment": ["ELMOS_PROVIDER_ENDPOINT"],
            "timeout_seconds": 30,
            "max_output_bytes": 1024 * 1024,
        }

    def encoded(self, document: dict[str, object]) -> bytes:
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()

    def test_partial_manifest_is_explicit_and_cannot_claim_complete_coverage(self) -> None:
        name = "a2a-agent-discovery-messaging"
        document = self.manifest([self.route(name)])
        document["pipeline_routes"] = [self.pipeline_route("knowledge-to-skill")]
        partial = load_provider_runtime_manifest(
            self.encoded(document), catalog=self.catalog, require_complete=False
        )
        self.assertFalse(partial.complete_catalog)
        self.assertEqual(partial.configured_skills, (name,))
        self.assertEqual(partial.configured_pipelines, ("knowledge-to-skill",))
        validation = partial.validate_installed_executables()
        self.assertEqual(validation["status"], "HOST_PROVIDER_RUNTIME_VALIDATED")
        self.assertEqual(validation["configured_routes"], 2)
        self.assertEqual(validation["external_evidence_status"], "NOT_RUN")
        self.assertEqual(validation["certification_status"], "NOT_CERTIFIED")
        broker = partial.build_broker(receipt_verifier=lambda *_args: False)
        self.assertEqual(broker.broker_id, "broker-host-test")
        with self.assertRaisesRegex(
            ProviderRuntimeManifestError, "missing Skills=1243, pipelines=13"
        ):
            load_provider_runtime_manifest(self.encoded(document), catalog=self.catalog)

    def test_binding_digest_or_catalog_drift_fails_closed(self) -> None:
        name = "a2a-agent-discovery-messaging"
        document = self.manifest([self.route(name)])
        drifted_route = deepcopy(document)
        drifted_route["skill_routes"][0]["route_digest"] = "0" * 64  # type: ignore[index]
        with self.assertRaisesRegex(ProviderRuntimeManifestError, "drifted"):
            load_provider_runtime_manifest(
                self.encoded(drifted_route), catalog=self.catalog, require_complete=False
            )
        drifted_catalog = deepcopy(document)
        drifted_catalog["catalog_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ProviderRuntimeManifestError, "different catalog"):
            load_provider_runtime_manifest(
                self.encoded(drifted_catalog), catalog=self.catalog, require_complete=False
            )
        boolean_timeout = deepcopy(document)
        boolean_timeout["skill_routes"][0]["timeout_seconds"] = True  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            load_provider_runtime_manifest(
                self.encoded(boolean_timeout), catalog=self.catalog, require_complete=False
            )

    def test_complete_manifest_binds_every_native_skill_and_pipeline(self) -> None:
        document = self.manifest(
            [self.route(name) for name in sorted(self.programs)]
        )
        document["pipeline_routes"] = [
            self.pipeline_route(name) for name in sorted(self.catalog.pipelines)
        ]
        runtime = load_provider_runtime_manifest(
            self.encoded(document), catalog=self.catalog
        )
        self.assertTrue(runtime.complete_catalog)
        self.assertEqual(len(runtime.configured_skills), 1_244)
        self.assertEqual(len(runtime.configured_pipelines), 14)
        self.assertEqual(len(runtime.routes), 1_258)
        validation = runtime.validate_installed_executables()
        self.assertEqual(validation["configured_routes"], 1_258)
        self.assertEqual(validation["unique_executables"], 1)
        self.assertEqual(validation["execution_status"], "NOT_RUN")
        self.assertEqual(validation["certification_status"], "NOT_CERTIFIED")

if __name__ == "__main__":
    unittest.main()
