"""Repository-level proof that all 1,244 brokered skills have exact handlers."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOUNDRY_SRC = ROOT / "engines/knowledge-skill-model-foundry-engine/src"
if str(FOUNDRY_SRC) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_SRC))

from elmos_foundry.automated_handlers.pack_handlers import get_all_automated_handlers
from elmos_foundry.domain import TenantScope
from elmos_foundry.exact_skills.registry import EXPECTED_EXACT_SKILLS, load_exact_handlers
from elmos_foundry.native_semantics import load_native_programs


class PackExactHandlerTests(unittest.TestCase):
    def test_pack_registry_exposes_unique_exact_handlers(self) -> None:
        programs = load_native_programs()
        exact = load_exact_handlers()
        packs = get_all_automated_handlers()
        self.assertEqual(len(programs), EXPECTED_EXACT_SKILLS)
        self.assertEqual(len(exact), EXPECTED_EXACT_SKILLS)
        self.assertEqual(set(packs), set(exact))
        self.assertEqual(len({id(fn) for fn in packs.values()}), EXPECTED_EXACT_SKILLS)
        scope = TenantScope(tenant_id="tenant-pack", project_id="project-exact")
        cobol = packs["cobol-copybook-data-model-migration"](
            "cobol-copybook-data-model-migration",
            {"text": "copybook"},
            scope,
            "inv-cobol",
        )
        android = packs["android-compose-adapter"](
            "android-compose-adapter",
            {"text": "copybook"},
            scope,
            "inv-cobol",
        )
        self.assertEqual(cobol["status"], "SUCCEEDED")
        self.assertEqual(android["status"], "SUCCEEDED")
        self.assertTrue(cobol.get("exact") and android.get("exact"))
        self.assertNotEqual(cobol["output_digest"], android["output_digest"])
        self.assertNotEqual(cobol["handler_id"], android["handler_id"])


if __name__ == "__main__":
    unittest.main()
