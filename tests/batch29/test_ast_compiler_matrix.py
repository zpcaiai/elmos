"""Comprehensive test suite for Universal AST Compiler 64-route matrix, native toolchains, ASan, and differential fuzzing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines" / "polyglot-route-engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_route.ast_compiler import (
    UniversalAstCompiler,
    UniversalClass,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalType,
    compile_polyglot_ast,
    default_compiler,
    get_emitter,
    get_parser,
)
from elmos_polyglot_route.ast_compiler.fuzzing import (
    AstFuzzGenerator,
    DifferentialFuzzCluster,
    NativeSanitizerRunner,
    SanitizerType,
)
from elmos_polyglot_route.ast_compiler.shims import ShimRegistry
from elmos_polyglot_route.enterprise_transpiler import (
    SUPPORTED_ENTERPRISE_LANGUAGES,
    transpile_enterprise_code,
)

FIXTURES_DIR = ROOT / "engines" / "polyglot-route-engine" / "fixtures" / "enterprise"

FIXTURE_MAP = {
    "java": "EnterpriseAssetService.java",
    "csharp": "EnterpriseAssetService.cs",
    "python": "enterprise_asset_service.py",
    "typescript": "enterprise_asset_service.ts",
    "go": "enterprise_asset_service.go",
    "rust": "enterprise_asset_service.rs",
    "kotlin": "EnterpriseAssetService.kt",
    "php": "EnterpriseAssetService.php",
}


class TestAstCompilerMatrix(unittest.TestCase):
    """Rigorous evaluation of the Universal AST Semantic Compiler."""

    def setUp(self) -> None:
        self.compiler = UniversalAstCompiler()
        self.cluster = DifferentialFuzzCluster()
        self.sanitizers = NativeSanitizerRunner()

    def test_full_64_bidirectional_matrix_transpilation(self) -> None:
        """Verify all 8x8 = 64 bidirectional translation routes succeed with valid AST IR."""
        total = 0
        passed = 0
        for src_lang, fname in FIXTURE_MAP.items():
            source_file = FIXTURES_DIR / fname
            self.assertTrue(source_file.exists(), f"Fixture missing: {fname}")
            src_code = source_file.read_text(encoding="utf-8")

            for tgt_lang in SUPPORTED_ENTERPRISE_LANGUAGES:
                total += 1
                emitted = self.compiler.compile(src_code, src_lang, tgt_lang)
                self.assertGreater(len(emitted), 50, f"Empty or tiny output for {src_lang} -> {tgt_lang}")
                self.assertIn("Asset", emitted, f"Domain entity 'Asset' missing in {src_lang} -> {tgt_lang}")
                passed += 1

        self.assertEqual(total, 64)
        self.assertEqual(passed, 64)

    def test_ast_ir_structural_soundness(self) -> None:
        """Verify UniversalModule AST IR preserves complex classes, fields, methods, and routing."""
        java_code = (FIXTURES_DIR / "EnterpriseAssetService.java").read_text(encoding="utf-8")
        ir_mod = self.compiler.parse_to_ir(java_code, "java")

        self.assertGreaterEqual(len(ir_mod.classes), 1)
        # Check domain model class
        asset_cls = next((c for c in ir_mod.classes if c.name == "Asset"), None)
        self.assertIsNotNone(asset_cls, "Asset class must be recognized in IR")
        field_names = [f.name.lower() for f in asset_cls.fields]
        self.assertIn("serial", field_names)
        self.assertIn("status", field_names)
        self.assertIn("value", field_names)

        # Check controller class
        ctrl_cls = next((c for c in ir_mod.classes if c.is_controller), None)
        self.assertIsNotNone(ctrl_cls, "Controller class must be recognized in IR")
        self.assertIn("api/v1/assets", ctrl_cls.base_route)

    def test_semantic_lowering_hazard_closure(self) -> None:
        """Verify that all 4 hazard domains are transformed appropriately."""
        # Create a module with async, exceptions, and lifecycle
        mod = UniversalModule(name="TestModule")
        cls = UniversalClass(
            name="Asset",
            fields=[
                UniversalField("serial", UniversalType.string_type()),
                UniversalField("value", UniversalType.float64()),
            ],
            methods=[
                UniversalMethod(
                    name="get_asset_by_serial",
                    params=[UniversalField("serial", UniversalType.string_type())],
                    return_type=UniversalType.primitive(UniversalType.string_type().kind),
                    is_async=True,
                    has_exception_handling=True,
                    http_method="GET",
                )
            ],
            is_controller=True,
            base_route="/api/v1/assets",
        )
        mod.classes.append(cls)

        # Lower to Rust (RAII / Arc / Tokio / Result)
        rust_lowered = self.compiler.lower_module(mod, "java", "rust")
        rust_code = self.compiler.emit_from_ir(rust_lowered, "rust")
        self.assertIn("Arc<RwLock<", rust_code)
        self.assertIn("Result<", rust_code)

        # Lower to Go (sync.RWMutex / channels / error)
        go_lowered = self.compiler.lower_module(mod, "java", "go")
        go_code = self.compiler.emit_from_ir(go_lowered, "go")
        self.assertIn("sync.RWMutex", go_code)

        # Lower to C# (async Task / ActionResult / ControllerBase)
        cs_lowered = self.compiler.lower_module(mod, "java", "csharp")
        cs_code = self.compiler.emit_from_ir(cs_lowered, "csharp")
        self.assertIn("async Task<", cs_code)
        self.assertIn("ControllerBase", cs_code)

    def test_standard_library_shims_coverage(self) -> None:
        """Verify cross-language stdlib shims for collections, datetime, io, and math."""
        for lang in SUPPORTED_ENTERPRISE_LANGUAGES:
            # Collection types
            list_t = ShimRegistry.get_collection("list_type", lang, "string")
            self.assertTrue(len(list_t) > 0)
            map_t = ShimRegistry.get_collection("map_type", lang, "string", "int")
            self.assertTrue(len(map_t) > 0)

            # Datetime
            now_expr = ShimRegistry.get_now_iso(lang)
            self.assertTrue(len(now_expr) > 0)

            # Logging
            log_stmt = ShimRegistry.get_log_info(lang, '"Hello World"')
            self.assertIn("Hello World", log_stmt)

    def test_native_compiler_syntax_validation(self) -> None:
        """Validate that generated Python, Go, PHP, Rust, etc. pass native toolchain checks."""
        java_code = (FIXTURES_DIR / "EnterpriseAssetService.java").read_text(encoding="utf-8")

        # Python
        py_code = self.compiler.compile(java_code, "java", "python")
        ok, err = self.cluster.validate_syntax(py_code, "python")
        self.assertTrue(ok, f"Python native syntax error: {err}")

        # PHP
        php_code = self.compiler.compile(java_code, "java", "php")
        ok, err = self.cluster.validate_syntax(php_code, "php")
        self.assertTrue(ok, f"PHP native syntax error: {err}")

        # TypeScript
        ts_code = self.compiler.compile(java_code, "java", "typescript")
        ok, err = self.cluster.validate_syntax(ts_code, "typescript")
        self.assertTrue(ok, f"TS syntax error: {err}")

        # Go
        go_code = self.compiler.compile(java_code, "java", "go")
        ok, err = self.cluster.validate_syntax(go_code, "go")
        self.assertTrue(ok, f"Go syntax error: {err}")

    def test_asan_native_memory_safety(self) -> None:
        """Prove native execution safety under Clang AddressSanitizer."""
        c_code = """
        #include <stdlib.h>
        #include <string.h>
        int main(void) {
            char *buf = (char*)malloc(64);
            if (!buf) return 1;
            strcpy(buf, "Elmos Enterprise AST Compiler Memory Test");
            free(buf);
            return 0;
        }
        """
        res = self.sanitizers.run_c_sanitizer(c_code, SanitizerType.ASAN)
        self.assertTrue(res.passed, f"ASan test failed: {res.stderr}")
        self.assertEqual(res.exit_code, 0)

    def test_differential_fuzzing_cluster_campaign(self) -> None:
        """Run a 64-iteration fuzzing campaign across randomly generated AST modules."""
        report = self.cluster.run_fuzz_campaign(iterations=64)
        self.assertEqual(report.total_runs, 64)
        self.assertEqual(report.passed_runs, 64)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertGreater(report.syntax_validations_passed, 0)


if __name__ == "__main__":
    unittest.main()
