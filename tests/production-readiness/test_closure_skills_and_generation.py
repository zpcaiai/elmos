from __future__ import annotations

import json
import re
import unittest
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
        self.assertIn("make product-closure-convergence-skills", rendered)

    def test_production_readiness_covers_all_current_skill_distributions_portably(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        target = re.search(r"production-readiness-check:([^\n]+)", makefile)
        self.assertIsNotNone(target)
        prerequisites = set(target.group(1).split())
        self.assertTrue(
            {"batch45-check", "project-synthesis", "batch97-104-skills", "product-closure-convergence-skills", "web"}
            .issubset(prerequisites)
        )
        self.assertIn("UV ?= uv", makefile)
        self.assertNotIn("/opt/homebrew/bin/uv", makefile)

    def test_vercel_deploys_the_nested_nextjs_console_instead_of_an_empty_root(self) -> None:
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual("nextjs", config["framework"])
        self.assertEqual("apps/web-console/.next", config["outputDirectory"])
        self.assertEqual(
            "npx --yes pnpm@10.12.4 --dir apps/web-console build",
            config["buildCommand"],
        )
        self.assertEqual(
            "npx --yes pnpm@10.12.4 --dir apps/web-console install --frozen-lockfile",
            config["installCommand"],
        )

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

    def test_generation_drafts_close_local_create_restore_delete_loop(self) -> None:
        source = (
            ROOT
            / "apps"
            / "web-console"
            / "app"
            / "generation"
            / "ProjectGenerationStudio.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn('DRAFT_STORAGE_KEY = "elmos.project-generation-drafts.v1"', source)
        self.assertIn("window.localStorage.getItem(DRAFT_STORAGE_KEY)", source)
        self.assertIn("window.localStorage.setItem(DRAFT_STORAGE_KEY", source)
        self.assertIn("function restoreDraft", source)
        self.assertIn("function removeDraft", source)
        self.assertIn("createdAt: new Date().toISOString()", source)
        self.assertIn(".slice(0, 50)", source)
        self.assertIn("isStoredGenerationDraft", source)

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
