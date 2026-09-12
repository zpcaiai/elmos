"""Unit tests for the Enterprise Polyglot Transpiler and Hazard Lowering Engine."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engines" / "polyglot-route-engine" / "src"))

from elmos_polyglot_route.enterprise_transpiler import (
    SUPPORTED_ENTERPRISE_LANGUAGES,
    EnterpriseEmitter,
    EnterpriseSemanticParser,
    transpile_enterprise_code,
)
from elmos_polyglot_route.semantic_hazard_guard import (
    HAZARD_ASYNC_CONCURRENCY,
    HAZARD_CATEGORIES,
    HAZARD_COMPLEX_FRAMEWORK_AND_UI,
    HAZARD_EXCEPTION_UNWINDING,
    HAZARD_OBJECT_GRAPH_LIFECYCLE,
    PROFILE_ENTERPRISE_PRODUCTION,
    PROFILE_TYPED_PURE_FUNCTION,
    SemanticHazardGuard,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "engines" / "polyglot-route-engine" / "fixtures" / "enterprise"


class TestEnterpriseTranspiler(unittest.TestCase):
    def test_parse_and_emit_java_to_csharp(self):
        java_code = (FIXTURES_DIR / "EnterpriseAssetService.java").read_text(encoding="utf-8")
        csharp_code = transpile_enterprise_code(java_code, "java", "csharp")

        # Verify Object Graph Lifecycle
        self.assertIn("public class Asset", csharp_code)
        self.assertIn("public string Serial", csharp_code)
        
        # Verify Complex Framework & Routing
        self.assertIn("[ApiController]", csharp_code)
        self.assertIn('[Route("api/v1/assets")]', csharp_code)
        
        # Verify Async & Concurrency
        self.assertIn("async Task<ActionResult<Asset>>", csharp_code)
        
        # Verify Exception Unwinding
        self.assertIn("try", csharp_code)
        self.assertIn("catch (Exception ex)", csharp_code)

    def test_parse_and_emit_csharp_to_python(self):
        csharp_code = (FIXTURES_DIR / "EnterpriseAssetService.cs").read_text(encoding="utf-8")
        python_code = transpile_enterprise_code(csharp_code, "csharp", "python")

        # Verify Object Graph Lifecycle
        self.assertIn("@dataclass", python_code)
        self.assertIn("class Asset:", python_code)
        
        # Verify Complex Framework & Routing
        self.assertIn('router = APIRouter(prefix="/api/v1/assets"', python_code)
        
        # Verify Async & Concurrency
        self.assertIn("async def get_asset_by_serial", python_code)
        
        # Verify Exception Unwinding
        self.assertIn("try:", python_code)
        self.assertIn("except Exception as ex:", python_code)
        self.assertIn("raise HTTPException", python_code)

    def test_parse_and_emit_python_to_typescript(self):
        python_code = (FIXTURES_DIR / "enterprise_asset_service.py").read_text(encoding="utf-8")
        ts_code = transpile_enterprise_code(python_code, "python", "typescript")

        # Verify Object Graph Lifecycle
        self.assertIn("export class Asset", ts_code)
        
        # Verify Complex Framework & Routing
        self.assertIn("@Controller('api/v1/assets')", ts_code)
        
        # Verify Async & Concurrency
        self.assertIn("async getAssetBySerial", ts_code)
        self.assertIn("Promise<Asset>", ts_code)
        
        # Verify Exception Unwinding
        self.assertIn("try {", ts_code)
        self.assertIn("catch (error: any)", ts_code)
        self.assertIn("throw new HttpException", ts_code)

    def test_parse_and_emit_all_8_languages(self):
        java_code = (FIXTURES_DIR / "EnterpriseAssetService.java").read_text(encoding="utf-8")
        for target_lang in SUPPORTED_ENTERPRISE_LANGUAGES:
            emitted = transpile_enterprise_code(java_code, "java", target_lang)
            self.assertTrue(len(emitted) > 50, f"Failed emitting to {target_lang}")
            self.assertIn("Asset", emitted)

    def test_semantic_hazard_guard_enterprise_audit(self):
        java_code = (FIXTURES_DIR / "EnterpriseAssetService.java").read_text(encoding="utf-8")
        audit = SemanticHazardGuard.audit_enterprise_semantics(java_code, "java")
        self.assertTrue(audit["all_hazards_closed"])
        self.assertEqual(audit["profile"], PROFILE_ENTERPRISE_PRODUCTION)
        for domain in HAZARD_CATEGORIES:
            self.assertIn(domain, audit["domains"])
            self.assertEqual(audit["domains"][domain]["closure_status"], "CLOSED_ENTERPRISE_LOWERING")

    def test_semantic_hazard_guard_assert_under_enterprise_profile(self):
        java_code = (FIXTURES_DIR / "EnterpriseAssetService.java").read_text(encoding="utf-8")
        
        # Under enterprise-production-v1, this should NOT raise an error
        SemanticHazardGuard.assert_no_hazards(java_code, "java", profile=PROFILE_ENTERPRISE_PRODUCTION)

        # Under pure-function profile, it strictly raises RouteError
        from elmos_polyglot_route.models import RouteError
        with self.assertRaises(RouteError):
            SemanticHazardGuard.assert_no_hazards(java_code, "java", profile=PROFILE_TYPED_PURE_FUNCTION)


if __name__ == "__main__":
    unittest.main()
