from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch29"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from route_sets import (  # noqa: E402
    COMPLETE_ROUTE_KEYS,
    COMPLETION_ROUTE_KEYS,
    CORE_ROUTE_KEYS,
    EXACT_ROUTE_SETS,
    MODULE_EQUIVALENCE_ROUTE_KEYS,
    NINE_LANGUAGE_COMPLETE_ROUTE_KEYS,
    NODEJS_EXACT_ROUTE_KEYS,
    NODEJS_NEGATIVE_COMMON_CASE_IDS,
    SPECIALIZED_ROUTE_KEYS,
    SUPPORTED_ROUTE_LANGUAGES,
    nodejs_negative_case_ids,
    provenance_route_set,
)


def load_runner():
    path = SCRIPTS / "run_polyglot_routes.py"
    spec = importlib.util.spec_from_file_location("batch29_nodejs_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def not_run_module_evidence(
    route_key: str,
    source: str,
    target: str,
    input_domain: str,
    out_of_domain: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "kind": "typed-pure-module-equivalence",
        "profile": "typed-pure-module-v1",
        "status": "NOT_RUN",
        "local_verification_status": "NOT_RUN",
        "route": {
            "route_key": route_key,
            "source_language": source,
            "target_language": target,
        },
        "module_input_sha256": None,
        "module_contract": {
            "source_profile_symbols": [],
            "target_profile_symbols": [],
            "target_helper_symbols": [],
            "verified_language_prelude": {"status": "NOT_RUN"},
            "verified_language_wrapper": {"status": "NOT_RUN"},
            "manifest_symbols": [],
            "exact_profile_symbol_set": False,
            "exact_generated_helper_symbol_set": False,
            "exact_profile_signature_set": False,
            "whole_file_closure_sha256": None,
            "independence": {"status": "NOT_RUN"},
        },
        "functions": [],
        "composition": {
            "rule": "per-function-denotation-plus-module-composition",
            "input_domain": input_domain,
            "out_of_domain_arithmetic_behavior": out_of_domain,
            "function_count": 0,
            "passed_function_count": 0,
            "status": "NOT_RUN",
            "proof_strength": "NONE",
            "original_source_bytes_theorem": False,
            "source_compiler_runtime_soundness": "NOT_RUN",
            "target_compiler_runtime_soundness": "NOT_RUN",
            "analyzer_and_emitter_soundness": "NOT_RUN",
            "source_user_call_graph": "NOT_RUN",
            "target_call_graph": "NOT_RUN",
            "target_profile_to_emitted_call_graph_status": "NOT_RUN",
            "target_profile_to_emitted_call_graph_scope": "NOT_RUN",
        },
        "artifact_refs": [],
        "certification_status": "NOT_CERTIFIED",
        "external_verification_status": "NOT_RUN",
        "limitations": ["Native execution has not run."],
    }


class NodeJsRouteMatrixTests(unittest.TestCase):
    def test_old_sets_are_unchanged_and_node_closes_exact_ten_language_matrix(self) -> None:
        self.assertEqual(len(CORE_ROUTE_KEYS), 30)
        self.assertEqual(len(SPECIALIZED_ROUTE_KEYS), 8)
        self.assertEqual(len(COMPLETION_ROUTE_KEYS), 34)
        self.assertEqual(len(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS), 72)
        self.assertEqual(len(NODEJS_EXACT_ROUTE_KEYS), 18)
        self.assertEqual(len(COMPLETE_ROUTE_KEYS), 90)
        self.assertEqual(len(SUPPORTED_ROUTE_LANGUAGES), 10)
        self.assertEqual(
            set(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS) | set(NODEJS_EXACT_ROUTE_KEYS),
            set(COMPLETE_ROUTE_KEYS),
        )
        self.assertFalse(
            set(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS) & set(NODEJS_EXACT_ROUTE_KEYS)
        )
        self.assertTrue(
            all(
                (key.startswith("javascript-to-") or key.endswith("-to-javascript"))
                and not key.startswith("javascript-to-javascript")
                for key in NODEJS_EXACT_ROUTE_KEYS
            )
        )
        self.assertEqual(
            set(MODULE_EQUIVALENCE_ROUTE_KEYS),
            set(SPECIALIZED_ROUTE_KEYS) | set(NODEJS_EXACT_ROUTE_KEYS),
        )
        self.assertEqual(
            EXACT_ROUTE_SETS["javascript-node26-completion-18"],
            NODEJS_EXACT_ROUTE_KEYS,
        )
        self.assertEqual(
            EXACT_ROUTE_SETS["ten-language-complete-90"], COMPLETE_ROUTE_KEYS
        )
        self.assertTrue(
            all(
                provenance_route_set(key) == "javascript-node26-completion-18"
                for key in NODEJS_EXACT_ROUTE_KEYS
            )
        )

    def test_node_case_schema_accepts_string_subset_without_widening_exact_eight(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "batch29" / "module-case-manifest.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        fixtures = ROOT / "engines" / "polyglot-route-engine" / "fixtures" / "module"
        for name in ("cases.json", "nodejs-cases.json", "nodejs-typescript-cases.json"):
            validator.validate(json.loads((fixtures / name).read_text()))

        node_typescript = json.loads(
            (fixtures / "nodejs-typescript-cases.json").read_text()
        )
        impersonated_exact = copy.deepcopy(node_typescript)
        impersonated_exact["composition"] = {
            "call_graph": [],
            "global_state": "none",
            "effects": "none",
            "exceptions": "canonical-arithmetic-errors-only",
            "input_domain": "canonical-finite-no-error-input-domain",
        }
        with self.assertRaises(ValidationError):
            validator.validate(impersonated_exact)

    def test_module_evidence_schema_rejects_node_and_exact_domain_impersonation(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "schemas"
                / "batch29"
                / "module-equivalence-evidence.schema.json"
            ).read_text()
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        node = not_run_module_evidence(
            "javascript-to-java",
            "javascript",
            "java",
            "nodejs-es2022-esm-safe-integer-finite-v1",
            "BLOCKED_OUTSIDE_NODEJS_ES2022_ESM_SAFE_INTEGER_FINITE_V1",
        )
        exact = not_run_module_evidence(
            "cpp-to-java",
            "cpp",
            "java",
            "canonical-finite-no-error-input-domain",
            "BLOCKED_NOT_EQUIVALENTLY_MODELED",
        )
        validator.validate(node)
        validator.validate(exact)

        node_as_exact = copy.deepcopy(node)
        node_as_exact["composition"]["input_domain"] = (
            "canonical-finite-no-error-input-domain"
        )
        node_as_exact["composition"]["out_of_domain_arithmetic_behavior"] = (
            "BLOCKED_NOT_EQUIVALENTLY_MODELED"
        )
        with self.assertRaises(ValidationError):
            validator.validate(node_as_exact)

        exact_as_node = copy.deepcopy(exact)
        exact_as_node["composition"]["input_domain"] = (
            "nodejs-es2022-esm-safe-integer-finite-v1"
        )
        exact_as_node["composition"]["out_of_domain_arithmetic_behavior"] = (
            "BLOCKED_OUTSIDE_NODEJS_ES2022_ESM_SAFE_INTEGER_FINITE_V1"
        )
        with self.assertRaises(ValidationError):
            validator.validate(exact_as_node)

    def test_typescript_node_pair_never_claims_integer(self) -> None:
        runner = load_runner()
        self.assertEqual(
            runner.nodejs_route_types("typescript", "javascript"),
            ["number", "boolean", "string"],
        )
        self.assertEqual(
            runner.nodejs_route_types("javascript", "typescript"),
            ["number", "boolean", "string"],
        )
        self.assertEqual(
            runner.nodejs_route_types("javascript", "java"),
            ["integer", "number", "boolean"],
        )

    def test_node_routes_have_exact_directional_negative_contracts(self) -> None:
        runner = load_runner()
        javascript_java = nodejs_negative_case_ids("javascript", "java")
        javascript_typescript = nodejs_negative_case_ids(
            "javascript", "typescript"
        )
        typescript_javascript = nodejs_negative_case_ids(
            "typescript", "javascript"
        )

        self.assertEqual(len(NODEJS_NEGATIVE_COMMON_CASE_IDS), 15)
        self.assertEqual(len(javascript_java), 24)
        self.assertIn("nodejs-unsafe-integer-case-unsupported", javascript_java)
        self.assertIn(
            "nodejs-unsafe-integer-intermediate-integer-unsupported",
            javascript_java,
        )
        self.assertIn(
            "nodejs-unsafe-integer-intermediate-boolean-unsupported",
            javascript_java,
        )
        self.assertIn(
            "nodejs-unsafe-integer-intermediate-number-unsupported",
            javascript_java,
        )
        self.assertIn("nodejs-unsafe-integer-result-unsupported", javascript_java)
        self.assertIn("nodejs-division-by-zero-unsupported", javascript_java)
        self.assertIn("nodejs-modulo-by-zero-unsupported", javascript_java)
        self.assertIn("nodejs-integer-overflow-unsupported", javascript_java)
        self.assertIn("nodejs-string-semantics-unsupported", javascript_java)
        self.assertIn("nodejs-number-arithmetic-unsupported", javascript_java)
        self.assertNotIn(
            "nodejs-typescript-integer-contract-unsupported", javascript_java
        )
        for pair_cases in (javascript_typescript, typescript_javascript):
            self.assertEqual(len(pair_cases), 16)
            self.assertIn(
                "nodejs-typescript-integer-contract-unsupported", pair_cases
            )
            self.assertIn("nodejs-number-arithmetic-unsupported", pair_cases)
            self.assertNotIn("nodejs-string-semantics-unsupported", pair_cases)
            self.assertNotIn("nodejs-unsafe-integer-case-unsupported", pair_cases)
        self.assertEqual(
            set(runner.NODEJS_NEGATIVE_ANALYZE_SOURCES),
            {
                case_id
                for case_id in javascript_java
                if case_id.startswith("nodejs-")
                and case_id
                not in {
                    "nodejs-commonjs-unsupported",
                    "nodejs-division-by-zero-unsupported",
                    "nodejs-integer-overflow-unsupported",
                    "nodejs-modulo-by-zero-unsupported",
                    "nodejs-non-finite-case-unsupported",
                    "nodejs-number-arithmetic-unsupported",
                    "nodejs-string-semantics-unsupported",
                    "nodejs-unsafe-integer-case-unsupported",
                    "nodejs-unsafe-integer-intermediate-boolean-unsupported",
                    "nodejs-unsafe-integer-intermediate-integer-unsupported",
                    "nodejs-unsafe-integer-intermediate-number-unsupported",
                    "nodejs-unsafe-integer-result-unsupported",
                }
            },
        )
        self.assertEqual(
            set(runner.NODEJS_GENERATED_NEGATIVE_CASES),
            {
                "nodejs-division-by-zero-unsupported",
                "nodejs-integer-overflow-unsupported",
                "nodejs-modulo-by-zero-unsupported",
                "nodejs-number-arithmetic-unsupported",
                "nodejs-string-semantics-unsupported",
                "nodejs-unsafe-integer-intermediate-boolean-unsupported",
                "nodejs-unsafe-integer-intermediate-integer-unsupported",
                "nodejs-unsafe-integer-intermediate-number-unsupported",
            },
        )
        self.assertIn(".mjs", runner.ARTIFACT_ALLOWED_SUFFIXES)

    def test_node_analyzer_negative_sources_fail_with_declared_codes(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory(prefix="elmos-nodejs-negative-unit-") as temporary:
            root = Path(temporary)
            for case_id, specification in runner.NODEJS_NEGATIVE_ANALYZE_SOURCES.items():
                filename, function_name, content, expected_codes = specification
                source = root / filename
                source.write_text(content, encoding="utf-8")
                with self.assertRaises(runner.RouteError, msg=case_id) as raised:
                    runner.analyze(source, "javascript", function_name)
                self.assertIn(
                    runner.nodejs_route_error_code(str(raised.exception)),
                    expected_codes,
                    case_id,
                )


if __name__ == "__main__":
    unittest.main()
