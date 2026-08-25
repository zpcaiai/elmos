import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch29"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    scripts = str(SCRIPTS)
    inserted = scripts not in sys.path
    if inserted:
        sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(name, path)
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts)


VALIDATOR = load_module("batch29_v3_direct_validator", SCRIPTS / "validate_route.py")
GATE = load_module("batch29_v3_direct_gate", SCRIPTS / "run_route_gate.py")


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def create_v3_route(root: Path, route_key: str = "java-to-kotlin") -> Path:
    from route_runtime_metadata import (
        v3_research_certification_document,
        v3_research_evidence_document,
    )

    route = root / route_key
    for relative in VALIDATOR.REQUIRED_DIRS:
        (route / relative).mkdir(parents=True, exist_ok=True)
    write_json(
        route / "route.json",
        VALIDATOR.v3_research_route_manifest_document(route_key),
    )
    write_json(
        route / "support-matrix.json",
        {
            "schema_version": 1,
            "route_key": route_key,
            "capabilities": [
                {
                    "id": "type-system",
                    "status": "experimental",
                    "strategy": "deterministic-lowering",
                    "reason": "Route-level execution evidence has not run.",
                    "evidence_refs": [],
                },
                {
                    "id": "concurrency",
                    "status": "blocked",
                    "strategy": "human-review",
                    "reason": "Requires route-specific certification.",
                    "evidence_refs": [],
                },
            ],
        },
    )
    write_json(route / "compat-runtime" / "manifest.json", {"schema_version": 1})
    write_json(
        route / "certification" / "evidence.json",
        v3_research_evidence_document(route_key),
    )
    write_json(
        route / "certification" / "certification.json",
        v3_research_certification_document(route_key),
    )
    return route


def invoke(module, route: Path) -> tuple[int, str]:
    output = io.StringIO()
    with (
        mock.patch.object(sys, "argv", [str(module.__file__), str(route)]),
        contextlib.redirect_stdout(output),
        contextlib.redirect_stderr(output),
    ):
        status = module.main()
    return status, output.getvalue()


class V3DirectRouteGateTests(unittest.TestCase):
    def test_exact_research_contract_passes_without_execution_overclaim(self):
        with tempfile.TemporaryDirectory() as temporary:
            route = create_v3_route(Path(temporary))
            validator_status, validator_output = invoke(VALIDATOR, route)
            gate_status, gate_output = invoke(GATE, route)

        self.assertEqual(validator_status, 0, validator_output)
        self.assertEqual(gate_status, 0, gate_output)
        self.assertIn("OK:", validator_output)
        self.assertIn(
            "status=research decision=NOT_CERTIFIED",
            gate_output,
        )

    def assert_contract_tamper_fails(
        self,
        relative: str,
        mutate,
        expected: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            route = create_v3_route(Path(temporary))
            path = route / relative
            document = json.loads(path.read_text(encoding="utf-8"))
            mutate(document)
            write_json(path, document)
            validator_status, validator_output = invoke(VALIDATOR, route)
            gate_status, gate_output = invoke(GATE, route)

        self.assertNotEqual(validator_status, 0, validator_output)
        self.assertNotEqual(gate_status, 0, gate_output)
        self.assertIn(expected, validator_output)
        self.assertIn(expected, gate_output)

    def test_raw_evidence_execution_overclaim_fails_both_direct_entrypoints(self):
        self.assert_contract_tamper_fails(
            "certification/evidence.json",
            lambda document: document.__setitem__(
                "execution_status", "PASSED_LOCAL"
            ),
            "raw evidence overclaims or drifts from NOT_RUN",
        )

    def test_gate_rechecks_v3_contract_after_validator_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            route = create_v3_route(Path(temporary))
            evidence_path = route / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["execution_status"] = "PASSED_LOCAL"
            write_json(evidence_path, evidence)
            with mock.patch.object(GATE, "validate_route_main", return_value=0):
                gate_status, gate_output = invoke(GATE, route)

        self.assertEqual(gate_status, 2, gate_output)
        self.assertIn(
            "GATE FAIL: V3 route raw evidence overclaims or drifts from NOT_RUN",
            gate_output,
        )

    def test_certification_gate_overclaim_fails_both_direct_entrypoints(self):
        def overclaim(document: dict[str, object]) -> None:
            gate_results = copy.deepcopy(document["gate_results"])
            assert isinstance(gate_results, dict)
            gate_results["local_execution"] = "PASSED"
            document["gate_results"] = gate_results

        self.assert_contract_tamper_fails(
            "certification/certification.json",
            overclaim,
            "certification overclaims or drifts from NOT_CERTIFIED",
        )

    def test_empty_support_capabilities_fail_both_direct_entrypoints(self):
        self.assert_contract_tamper_fails(
            "support-matrix.json",
            lambda document: document.__setitem__("capabilities", []),
            "support matrix capabilities are empty",
        )

    def test_supported_capability_overclaim_fails_both_direct_entrypoints(self):
        def overclaim(document: dict[str, object]) -> None:
            capabilities = document["capabilities"]
            assert isinstance(capabilities, list)
            assert isinstance(capabilities[0], dict)
            capabilities[0]["status"] = "supported"

        self.assert_contract_tamper_fails(
            "support-matrix.json",
            overclaim,
            "overclaims research capability support",
        )

    def test_route_profile_overclaim_fails_both_direct_entrypoints(self):
        def overclaim(document: dict[str, object]) -> None:
            profiles = document["profiles"]
            assert isinstance(profiles, dict)
            profiles["semantic_profile"] = "typed-pure-function-v1"

        self.assert_contract_tamper_fails(
            "route.json",
            overclaim,
            "manifest is not the exact research contract",
        )

    def test_support_shape_and_duplicate_ids_fail_closed(self):
        def duplicate_and_expand(document: dict[str, object]) -> None:
            capabilities = document["capabilities"]
            assert isinstance(capabilities, list)
            capabilities.append(copy.deepcopy(capabilities[0]))
            document["unexpected"] = True

        self.assert_contract_tamper_fails(
            "support-matrix.json",
            duplicate_and_expand,
            "support matrix top-level keys are not exact",
        )


if __name__ == "__main__":
    unittest.main()
