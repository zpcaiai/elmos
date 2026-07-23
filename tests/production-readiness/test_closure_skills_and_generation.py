from __future__ import annotations

import unittest
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SKILLS = (
    "elmos-business-line-closure-audit",
    "elmos-generation-journey-closure",
    "elmos-cross-service-operability-closure",
)


class ClosureSkillsAndGenerationTests(unittest.TestCase):
    def test_ci_covers_every_polyglot_engine_business_line(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        self.assertTrue(
            {
                "java",
                "dotnet-engine",
                "python-engine",
                "frontend-client-engine",
                "project-synthesis",
                "web-console",
            }.issubset(jobs)
        )
        rendered = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("dotnet restore engines/dotnet-engine/Elmos.Dotnet.slnx --locked-mode", rendered)
        self.assertIn("uv --directory engines/python-engine run --locked pytest", rendered)
        self.assertIn("pnpm --dir engines/frontend-client-engine install --frozen-lockfile", rendered)

    def test_skill_inventory_ui_matches_callable_repository_directories(self) -> None:
        catalog = (
            ROOT / "apps" / "web-console" / "app" / "lib" / "catalog.ts"
        ).read_text(encoding="utf-8")
        codex = re.search(r"codexSkillCount:\s*(\d+)", catalog)
        runtime = re.search(r"runtimeSkillCount:\s*(\d+)", catalog)
        self.assertIsNotNone(codex)
        self.assertIsNotNone(runtime)

        def skill_count(relative: str) -> int:
            return sum(
                1
                for directory in (ROOT / relative).iterdir()
                if directory.is_dir() and (directory / "SKILL.md").is_file()
            )

        self.assertEqual(skill_count(".agents/skills"), int(codex.group(1)))
        self.assertEqual(skill_count("agent-skills/runtime"), int(runtime.group(1)))

    def test_closure_skills_have_complete_discoverable_interfaces(self) -> None:
        for name in SKILLS:
            directory = ROOT / "agent-skills" / "runtime" / name
            skill_text = (directory / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("[TODO", skill_text, name)
            self.assertTrue(skill_text.startswith("---\n"), name)
            _, frontmatter, body = skill_text.split("---", 2)
            metadata = yaml.safe_load(frontmatter)
            self.assertEqual(name, metadata["name"])
            self.assertGreater(len(metadata["description"]), 100)
            self.assertIn("## Completion", body)

            interface = yaml.safe_load(
                (directory / "agents" / "openai.yaml").read_text(encoding="utf-8")
            )["interface"]
            self.assertIn(f"${name}", interface["default_prompt"])
            self.assertTrue(interface["display_name"].startswith("ELMOS"))
            self.assertGreaterEqual(len(interface["short_description"]), 25)

    def test_generation_ui_exposes_the_exact_governed_cli_sequence(self) -> None:
        source = (
            ROOT
            / "apps"
            / "web-console"
            / "app"
            / "generation"
            / "ProjectGenerationStudio.tsx"
        ).read_text(encoding="utf-8")
        commands = (
            "uv run elmos-project-synthesis draft",
            "uv run elmos-project-synthesis approve",
            "uv run elmos-project-synthesis generate",
            "uv run elmos-project-synthesis verify",
        )
        positions = [source.index(command) for command in commands]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("synthesis-request.json", source)
        self.assertIn("approved-request.json", source)
        self.assertIn("verification.json", source)
        self.assertIn("disabled={!draft}", source)

    def test_generation_capability_route_preserves_evidence_boundaries(self) -> None:
        route = (
            ROOT
            / "apps"
            / "web-console"
            / "app"
            / "api"
            / "capabilities"
            / "generation"
            / "route.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('source: "REPOSITORY_CONTRACT"', route)
        self.assertEqual(3, route.count(': "NOT_RUN"'))
        self.assertIn('certificationStatus: "NOT_CERTIFIED"', route)
        self.assertNotIn("child_process", route)
        self.assertNotIn("exec(", route)

    def test_migration_drafts_close_the_local_create_read_delete_loop(self) -> None:
        source = (
            ROOT
            / "apps"
            / "web-console"
            / "app"
            / "migration"
            / "MigrationStudio.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("window.localStorage.getItem(DRAFT_STORAGE_KEY)", source)
        self.assertIn("window.localStorage.setItem(DRAFT_STORAGE_KEY", source)
        self.assertIn("function removeDraft", source)
        self.assertIn('scope: String(form.get("scope")', source)
        self.assertIn("capabilityId: draftCapability", source)


if __name__ == "__main__":
    unittest.main()
