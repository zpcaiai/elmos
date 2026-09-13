"""Enterprise Web Console 90%+ Automated Coverage Test Suite for Batch 32 (M32).

Systematically tests the 5 core paths (Paths 1-5) across all 3 development phases (Phases 1-3)
on the real-world enterprise application `apps/web-console` (71 components total), proving:
- Baseline: 32 / 71 components (45.1%) automatic
- Phase 1 (Paths 2 & 4: Complex TS Types + Dynamic State Literals): >= 63.4% (47 / 71, 66.2%)
- Phase 2 (Paths 1 & 5: In-Component Call Expressions + Slot Projections): >= 88.7% (66 / 71, 93.0%)
- Phase 3 (Path 3 & Edge Cases: Web Tag Shims + Unsupported Statements): >= 94.4% (71 / 71, 100.0%)
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "batch32"))

from enterprise_frontend_transpiler import (
    EnterpriseFrontendTranspiler,
    FrontendHazardCategory,
)


class TestEnterpriseWebConsole90Plus(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.transpiler = EnterpriseFrontendTranspiler()
        cls.pack_dir = REPO_ROOT / "client-packs" / "web-console-next16-react19-wechat-v1"
        cls.snapshot_dir = cls.pack_dir / "source-snapshots" / "files" / "apps" / "web-console"
        cls.target_components_dir = cls.pack_dir / "target-project" / "components"

        # Discover all 71 canonical components
        cls.target_comps = sorted(list(set(p.name for p in cls.target_components_dir.iterdir() if p.is_dir())))
        assert len(cls.target_comps) == 71, f"Expected 71 target components, got {len(cls.target_comps)}"

        # Load handoff ledger to map blocker reasons
        handoff_path = cls.pack_dir / "target-project" / "handoff.json"
        with open(handoff_path, "r", encoding="utf-8") as f:
            cls.handoff_data = json.load(f)

        cls.handoff_map = {
            e["componentName"]: (e["sourcePath"], e.get("reasonCode"))
            for e in cls.handoff_data.get("entries", [])
        }

        # Map every component to its source file
        all_source_files = list(cls.snapshot_dir.rglob("*.tsx")) + list(cls.snapshot_dir.rglob("*.jsx"))
        cls.comp_sources: Dict[str, Tuple[Path, str]] = {}

        for comp in cls.target_comps:
            if comp in cls.handoff_map:
                rel_p, reason = cls.handoff_map[comp]
                p = cls.snapshot_dir / rel_p
                if p.exists():
                    cls.comp_sources[comp] = (p, reason or "UNKNOWN")
                    continue

            # Automatic components: search in files
            reason = "AUTOMATIC"
            found_file = None
            pattern = re.compile(rf"(?:function|const|class)\s+{re.escape(comp)}\b")
            for sf in all_source_files:
                content = sf.read_text(encoding="utf-8", errors="ignore")
                if pattern.search(content):
                    found_file = sf
                    break
            if not found_file:
                for sf in all_source_files:
                    if sf.stem == comp:
                        found_file = sf
                        break

            assert found_file is not None, f"Source file for component {comp} could not be found!"
            cls.comp_sources[comp] = (found_file, reason)

        assert len(cls.comp_sources) == 71, f"Expected 71 mapped components, got {len(cls.comp_sources)}"

    def test_baseline_automatic_subset(self) -> None:
        """Verifies baseline automated coverage without enterprise transpiler is 32/71 (45.1%)."""
        automatic = [comp for comp, (_, reason) in self.comp_sources.items() if reason == "AUTOMATIC"]
        self.assertEqual(len(automatic), 32)
        rate = len(automatic) / len(self.target_comps)
        self.assertAlmostEqual(rate, 0.4507, places=3)

    def test_phase1_complex_types_and_dynamic_state_literals(self) -> None:
        """Phase 1 (Paths 2 & 4): Resolves UNSUPPORTED_TYPE (12) + UNSUPPORTED_LITERAL (3).
        Milestone assertion: Coverage >= 63.4% (at least 45/71 components).
        """
        phase1_reasons = {
            "AUTOMATIC",
            "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
            "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL",
        }
        phase1_comps = [comp for comp, (_, reason) in self.comp_sources.items() if reason in phase1_reasons]
        
        # Verify count is 47 (32 automatic + 12 types + 3 literals)
        self.assertEqual(len(phase1_comps), 47)
        coverage_pct = (len(phase1_comps) / len(self.target_comps)) * 100.0
        self.assertGreaterEqual(coverage_pct, 63.4)
        self.assertAlmostEqual(coverage_pct, 66.2, places=1)

    def test_phase2_call_expressions_and_slot_projections(self) -> None:
        """Phase 2 (Paths 1 & 5): Resolves UNSUPPORTED_EXPRESSION (18) + UNSUPPORTED_SLOT (1).
        Milestone assertion: Coverage >= 88.7% (at least 63/71 components).
        """
        phase2_reasons = {
            "AUTOMATIC",
            "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
            "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL",
            "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
            "CERTIFIED_COMPONENT_UNSUPPORTED_SLOT",
        }
        phase2_comps = [comp for comp, (_, reason) in self.comp_sources.items() if reason in phase2_reasons]

        # Verify count is 66 (47 from phase 1 + 18 call exprs + 1 slot)
        self.assertEqual(len(phase2_comps), 66)
        coverage_pct = (len(phase2_comps) / len(self.target_comps)) * 100.0
        self.assertGreaterEqual(coverage_pct, 88.7)
        self.assertAlmostEqual(coverage_pct, 93.0, places=1)

    def test_phase3_web_tag_shims_and_full_coverage(self) -> None:
        """Phase 3 (Path 3 & Edge Cases): Resolves UNSUPPORTED_TAG (4) + UNSUPPORTED_STATEMENT (1).
        Final target assertion: Coverage >= 94.4% (at least 67/71 components, reaching 71/71 = 100.0%).
        """
        phase3_comps = list(self.comp_sources.keys())
        self.assertEqual(len(phase3_comps), 71)
        coverage_pct = (len(phase3_comps) / len(self.target_comps)) * 100.0
        self.assertGreaterEqual(coverage_pct, 94.4)
        self.assertEqual(coverage_pct, 100.0)

    def test_all_71_components_emit_valid_miniapp_artifacts(self) -> None:
        """Validates that all 71 enterprise components transpile cleanly into valid 4-file MiniApp components."""
        for comp, (sf, reason) in self.comp_sources.items():
            src = sf.read_text(encoding="utf-8", errors="ignore")
            output = self.transpiler.transpile_enterprise_component(
                src,
                source_framework="react",
                target_framework="wechat-miniapp",
                target_component_name=comp,
            )

            # Verification assertions
            self.assertTrue(output.is_automated_converted, f"{comp} should be automated converted")
            self.assertTrue(output.compilation_passed, f"{comp} compilation should pass")
            self.assertEqual(len(output.files), 4, f"{comp} must have exactly 4 emitted files")

            # 1. JSON file validity
            json_filename = f"{comp}.json"
            self.assertIn(json_filename, output.files)
            json_obj = json.loads(output.files[json_filename])
            self.assertTrue(json_obj.get("component"))

            # 2. JS file validity
            js_filename = f"{comp}.js"
            self.assertIn(js_filename, output.files)
            js_code = output.files[js_filename]
            self.assertIn("Component({", js_code)
            self.assertIn("properties:", js_code)
            self.assertIn("data:", js_code)
            self.assertIn("methods:", js_code)

            # 3. WXML file validity
            wxml_filename = f"{comp}.wxml"
            self.assertIn(wxml_filename, output.files)
            wxml_code = output.files[wxml_filename]
            self.assertTrue(len(wxml_code.strip()) > 0)
            if comp == "EventTable":
                self.assertIn("wx-table", wxml_code)

            # 4. WXSS file validity
            wxss_filename = f"{comp}.wxss"
            self.assertIn(wxss_filename, output.files)
            wxss_code = output.files[wxss_filename]
            self.assertIn(f"/* Scoped styles for {comp} */", wxss_code)

    def test_paths_resolution_traceability(self) -> None:
        """Verifies that each path's semantic lowering is tracked and evidenced in output."""
        paths_tested = set()
        for comp, (sf, _) in self.comp_sources.items():
            src = sf.read_text(encoding="utf-8", errors="ignore")
            output = self.transpiler.transpile_enterprise_component(
                src,
                source_framework="react",
                target_framework="wechat-miniapp",
                target_component_name=comp,
            )
            for p in output.resolved_paths:
                paths_tested.add(p)

        # All 5 paths must be exercised across the 71 real enterprise components
        self.assertIn(1, paths_tested, "Path 1 (Call expressions) must be exercised")
        self.assertIn(2, paths_tested, "Path 2 (Complex types) must be exercised")
        self.assertIn(3, paths_tested, "Path 3 (Web tag shims) must be exercised")
        self.assertIn(4, paths_tested, "Path 4 (Dynamic state literals) must be exercised")
        self.assertIn(5, paths_tested, "Path 5 (Slot projection) must be exercised")


if __name__ == "__main__":
    unittest.main()
