"""Real CPython and pinned Esprima parser cases; caller code is never run."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import importlib.metadata
from pathlib import Path
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from elmos_foundry.ast_extraction_semantics import (
    ESPRIMA_VERSION,
    INPUTS,
    MAX_FILE_BYTES,
    PYTHON_GRAMMAR,
    _parser_version,
    SKILLS,
    build_ast_extraction_handlers,
)
from elmos_foundry.canonical import canonical_digest, digest_bytes
from elmos_foundry.domain import TenantScope
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.store import FoundryStore, IdempotencyConflict, StoreError, StoreSecurityError


def fixture_inputs(skill: str, scope: TenantScope) -> dict[str, Any]:
    if skill not in SKILLS:
        raise ValueError("no AST fixture for this Skill")
    files = []
    for path, language, version, mode, content in (
        (
            "example.py",
            "python",
            PYTHON_GRAMMAR,
            "module",
            "def greet(name):\n    return 'Hello ' + name\n",
        ),
        (
            "example.js",
            "javascript",
            "ECMAScript2017",
            "module",
            "export const greet = (name) => 'Hello ' + name;\n",
        ),
    ):
        files.append(
            {
                "path": path,
                "language": language,
                "language_version": version,
                "source_type": mode,
                "content": content,
                "content_digest": digest_bytes(content.encode()),
            }
        )
    return {
        "normalized repository artifact": {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "purpose": scope.purpose,
            "revision_set_id": scope.revision_set_id,
            "files": files,
            "baseline": {},
        },
        "build metadata": {
            "parser_versions": [_parser_version("javascript"), _parser_version("python")],
            "source_configuration": "NOT_EXECUTED",
        },
        "runtime trace": {"status": "NOT_RUN", "reason": "static extraction never runs source"},
        "test result": {"status": "NOT_RUN", "reason": "static extraction never runs caller tests"},
    }


class Catalog:
    content_sha256 = "0" * 64
    discovery: Mapping[str, Any] = {}
    atomic_skills: Mapping[str, Mapping[str, Any]] = {name: {} for name in SKILLS}
    meta_skills: Mapping[str, Mapping[str, Any]] = {}


class AstExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ast.sqlite3"
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id="tenant",
            project_id="project",
            actor_id="actor",
            environment_id="local-test",
            workspace_digest=canonical_digest("workspace"),
            revision_set_id=canonical_digest("revision"),
            purpose="ast-test",
            capabilities=("foundry.store.read", "foundry.store.write"),
            ttl_seconds=600,
        )
        self.store = self.open_store()
        self.skill = "multi-language-ast-extraction"
        self.handler = build_ast_extraction_handlers(Catalog(), self.store)[self.skill]
        self.inputs = fixture_inputs(self.skill, self.scope)

    def open_store(self) -> FoundryStore:
        store = FoundryStore(self.path, context_verifier=self.kernel.require_context)
        self.addCleanup(store.close)
        return store

    def execute(
        self, inputs: Mapping[str, Any] | None = None, invocation: str = "case"
    ) -> Mapping[str, Any]:
        return self.handler(
            self.skill,
            {"inputs": self.inputs if inputs is None else inputs},
            self.scope,
            invocation,
        )

    @staticmethod
    def set_source(
        inputs: dict[str, Any], language: str, content: str, mode: str | None = None
    ) -> None:
        for item in inputs["normalized repository artifact"]["files"]:
            if item["language"] == language:
                item["content"] = content
                item["content_digest"] = digest_bytes(content.encode("utf-8"))
                if mode is not None:
                    item["source_type"] = mode

    def test_two_real_parsers_emit_nodes_edges_and_bound_versions(self) -> None:
        result = self.execute()
        self.assertEqual(result["status"], "SUCCEEDED")
        outputs = result["outputs"]
        graph = outputs["semantic graph"]
        kinds = {node["kind"] for node in graph["nodes"]}
        self.assertTrue(
            {"FunctionDef", "Return", "ExportNamedDeclaration", "ArrowFunctionExpression"}.issubset(
                kinds
            )
        )
        identities = {node["node_id"] for node in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["parent_id"], identities)
            self.assertIn(edge["child_id"], identities)
        report = outputs["confidence report"]
        self.assertEqual(report["parse_coverage"], 1)
        self.assertEqual(report["symbol_resolution"], "NOT_RUN")
        self.assertEqual(report["production_gate"], "BLOCKED")
        self.assertIn(
            {"language": "javascript", "parser": "esprima-python", "version": ESPRIMA_VERSION},
            report["parser_versions"],
        )
        self.assertEqual(result["certification_status"], "NOT_CERTIFIED")

    def test_positive_python_grammar_constructs(self) -> None:
        sources = (
            "value = 2 ** 100\n",
            "async def work(value):\n    return await value\n",
            "class Item:\n    def get(self):\n        return self.value\n",
            "values = [x * x for x in range(3) if x > 0]\n",
            "try:\n    raise ValueError('no')\nexcept ValueError as error:\n    pass\n",
            "match value:\n    case {'kind': kind}:\n        result = kind\n",
            "text = f'hello {name!r}'\n",
            "raw = b'\\x00'\nnumber = 2j\n",
            "value = external()  # type: ignore[name-defined]\n",
        )
        for index, source in enumerate(sources):
            with self.subTest(source=source):
                inputs = deepcopy(self.inputs)
                self.set_source(inputs, "python", source)
                self.assertEqual(self.execute(inputs, f"py-{index}")["status"], "SUCCEEDED")

    def test_positive_ecmascript_2017_script_and_module_constructs(self) -> None:
        cases = (
            ("const value = 2 ** 3;", "script"),
            ("async function work() { return await task(); }", "script"),
            ("class Item { get value() { return 1; } }", "script"),
            ("const {value} = source; const items = [...source];", "script"),
            ("function* values(){ yield 1; }", "script"),
            ("const text = `hello ${name}`;", "script"),
            ("import {value} from './value.js'; export default value;", "module"),
            ("const matcher = /[a-z]+/gi;", "script"),
        )
        for index, (source, mode) in enumerate(cases):
            with self.subTest(source=source):
                inputs = deepcopy(self.inputs)
                self.set_source(inputs, "javascript", source, mode)
                self.assertEqual(self.execute(inputs, f"js-{index}")["status"], "SUCCEEDED")

    def test_unicode_source_ranges_are_utf8_byte_accurate(self) -> None:
        inputs = deepcopy(self.inputs)
        self.set_source(inputs, "python", "café = '😀'\r\nresult = café\r\n")
        self.set_source(inputs, "javascript", "const label = '😀';\r\nconst café = label;\r\n")
        result = self.execute(inputs)
        self.assertEqual(result["status"], "SUCCEEDED")
        files = {
            item["path"]: item["content"].encode("utf-8")
            for item in inputs["normalized repository artifact"]["files"]
        }
        checked = 0
        for node in result["outputs"]["semantic graph"]["nodes"]:
            attrs, span = node["attributes"], node["source_span"]
            if attrs.get("id") == "café" or attrs.get("name") == "café":
                self.assertEqual(
                    files[node["path"]][span["start_byte"] : span["end_byte"]].decode("utf-8"),
                    "café",
                )
                checked += 1
        self.assertGreaterEqual(checked, 3)

    def test_source_instructions_and_side_effects_are_never_executed(self) -> None:
        marker = Path(self.temporary.name) / "should-not-exist"
        inputs = deepcopy(self.inputs)
        self.set_source(
            inputs,
            "python",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
        )
        self.set_source(
            inputs,
            "javascript",
            f"require('fs').writeFileSync({str(marker)!r}, 'executed');",
            "script",
        )
        self.assertEqual(self.execute(inputs)["status"], "SUCCEEDED")
        self.assertFalse(marker.exists())

    def test_diagnostics_preserve_failed_file_denominator_and_partial_graph(self) -> None:
        self.set_source(self.inputs, "javascript", "const broken = ;")
        result = self.execute()
        self.assertEqual(result["status"], "BLOCKED")
        graph = result["outputs"]["semantic graph"]
        self.assertEqual(len(graph["files"]), 2)
        self.assertTrue(graph["diagnostics"])
        self.assertEqual(result["outputs"]["confidence report"]["parse_coverage"], 0.5)
        self.assertEqual(
            result["outputs"]["confidence report"]["source_map_complete"], "INCOMPLETE"
        )
        self.assertTrue(any(node["language"] == "python" for node in graph["nodes"]))
        self.assertEqual(self.execute(), result)

    def test_tolerant_recovery_keeps_diagnostic_and_never_passes(self) -> None:
        self.set_source(self.inputs, "javascript", '"use strict"; with (value) {}', "script")
        result = self.execute()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "RECOVERED_WITH_ERRORS",
            {item["status"] for item in result["outputs"]["semantic graph"]["files"]},
        )

    def test_modern_javascript_typescript_and_jsx_fail_closed(self) -> None:
        for index, source in enumerate(
            (
                "const value = object?.field;",
                "const value = 1n;",
                "const value: number = 1;",
                "const view = <div/>;",
                "const value = {...other};",
                "const {...rest} = other;",
                "const regex = /a/s;",
                "const regex = /(?<=a)b/;",
            )
        ):
            with self.subTest(source=source):
                inputs = deepcopy(self.inputs)
                self.set_source(inputs, "javascript", source)
                self.assertEqual(self.execute(inputs, f"unsupported-{index}")["status"], "BLOCKED")

    def test_exact_required_inputs_cannot_be_empty_missing_or_extended(self) -> None:
        replacements: tuple[Any, ...] = (None, {}, [], "")
        for name in INPUTS:
            for replacement in replacements:
                with (
                    self.subTest(name=name, replacement=replacement),
                    self.assertRaises(ValueError),
                ):
                    inputs = deepcopy(self.inputs)
                    inputs[name] = replacement
                    self.execute(inputs)
        inputs = deepcopy(self.inputs)
        inputs["command"] = "execute-anything"
        with self.assertRaises(ValueError):
            self.execute(inputs)

    def test_scope_digest_paths_versions_and_configuration_are_bound(self) -> None:
        for key, value in (
            ("tenant_id", "other"),
            ("project_id", "other"),
            ("purpose", "other"),
            ("revision_set_id", canonical_digest("other")),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                inputs = deepcopy(self.inputs)
                inputs["normalized repository artifact"][key] = value
                self.execute(inputs)
        for key, value in (
            ("path", "../escape.py"),
            ("language", "typescript"),
            ("language_version", "unknown"),
            ("source_type", "eval"),
            ("content_digest", canonical_digest("forged")),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                inputs = deepcopy(self.inputs)
                inputs["normalized repository artifact"]["files"][0][key] = value
                self.execute(inputs)
        inputs = deepcopy(self.inputs)
        inputs["build metadata"]["source_configuration"] = "EXECUTE"
        with self.assertRaises(ValueError):
            self.execute(inputs)
        for outer in ("runtime trace", "test result"):
            with self.subTest(outer=outer), self.assertRaises(ValueError):
                inputs = deepcopy(self.inputs)
                inputs[outer]["status"] = "PASS"
                self.execute(inputs)

    def test_token_depth_and_size_budgets(self) -> None:
        for index, source in enumerate(("(" * 65 + "1" + ")" * 65, "x=1;" * 1500)):
            inputs = deepcopy(self.inputs)
            self.set_source(inputs, "python", source)
            self.assertEqual(self.execute(inputs, f"budget-{index}")["status"], "BLOCKED")
        self.set_source(self.inputs, "python", "x" * (MAX_FILE_BYTES + 1))
        with self.assertRaises(ValueError):
            self.execute()

    def test_missing_and_changed_parser_dependencies_fail_before_execution(self) -> None:
        with patch(
            "elmos_foundry.ast_extraction_semantics.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError,
        ):
            with self.assertRaisesRegex(ValueError, "required"):
                self.execute()
        with patch(
            "elmos_foundry.ast_extraction_semantics.importlib.metadata.version",
            return_value="4.0.2",
        ):
            with self.assertRaisesRegex(ValueError, "version"):
                self.execute()
        inputs = deepcopy(self.inputs)
        inputs["build metadata"]["parser_versions"][0]["version"] = "4.0.2"
        with self.assertRaises(ValueError):
            self.execute(inputs)

    def test_builder_and_fixture_do_not_import_optional_parser(self) -> None:
        with patch(
            "elmos_foundry.ast_extraction_semantics._esprima",
            side_effect=AssertionError("eager parser"),
        ):
            self.assertEqual(set(build_ast_extraction_handlers(Catalog(), self.store)), set(SKILLS))
            self.assertEqual(set(fixture_inputs(self.skill, self.scope)), set(INPUTS))

    def test_restart_replays_without_reparsing_and_changed_request_conflicts(self) -> None:
        result = self.execute()
        self.store.close()
        self.store = self.open_store()
        self.handler = build_ast_extraction_handlers(Catalog(), self.store)[self.skill]
        with patch(
            "elmos_foundry.ast_extraction_semantics._python_tree",
            side_effect=AssertionError("reparse"),
        ):
            self.assertEqual(self.execute(), result)
        self.set_source(self.inputs, "python", "changed = 42\n")
        with self.assertRaises(IdempotencyConflict):
            self.execute()

    def test_pending_run_recovers_from_immutable_input_checkpoint(self) -> None:
        with patch.object(self.store, "transition_run", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.execute()
        result = self.execute()
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(
            result["outputs"]["confidence report"]["checkpoint_status"],
            "LOCAL_IMMUTABLE_RUN_BASELINE",
        )

    def test_unauthenticated_context_missing_store_and_identity_fail_closed(self) -> None:
        unbound = TenantScope(
            self.scope.tenant_id,
            self.scope.project_id,
            purpose=self.scope.purpose,
            revision_set_id=self.scope.revision_set_id,
        )
        with self.assertRaises(StoreSecurityError):
            self.handler(self.skill, {"inputs": self.inputs}, unbound, "forged")
        without_store = build_ast_extraction_handlers(Catalog(), None)[self.skill]
        with self.assertRaises(StoreError):
            without_store(self.skill, {"inputs": self.inputs}, self.scope, "no-store")
        with self.assertRaises(ValueError):
            self.handler("different-skill", {"inputs": self.inputs}, self.scope, "wrong")

    def test_empty_file_and_content_only_baseline_diff_remain_explicit(self) -> None:
        self.set_source(self.inputs, "python", "")
        artifact = self.inputs["normalized repository artifact"]
        artifact["baseline"] = {"example.py": digest_bytes(b""), "removed.py": digest_bytes(b"old")}
        result = self.execute()
        self.assertEqual(result["status"], "SUCCEEDED")
        changes = {
            item["path"]: item["change"] for item in result["outputs"]["semantic diff"]["changes"]
        }
        self.assertEqual(
            changes, {"example.py": "UNCHANGED", "example.js": "ADDED", "removed.py": "REMOVED"}
        )
        self.assertEqual(artifact["files"][0]["language_version"], PYTHON_GRAMMAR)


if __name__ == "__main__":
    unittest.main()
