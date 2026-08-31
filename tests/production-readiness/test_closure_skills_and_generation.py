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
    def test_ci_actions_are_digest_pinned_and_browser_evidence_is_retained(self) -> None:
        rendered = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        mutable_action = re.compile(
            r"^\s*uses:\s+[^\s#]+@(?![0-9a-f]{40}(?:\s|$))", re.MULTILINE
        )
        all_workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        )
        self.assertIsNone(mutable_action.search(all_workflows))
        service_images = re.findall(r"^\s*image:\s+(\S+)", rendered, re.MULTILINE)
        self.assertTrue(service_images)
        self.assertTrue(
            all(
                re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", image)
                for image in service_images
            )
        )
        self.assertEqual(
            3,
            rendered.count(
                "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
            ),
        )
        expected_evidence_workflows = {
            ".github/workflows/ci.yml": 3,
            ".github/workflows/repository-migration-platform-skills.yml": 1,
            ".github/workflows/vercel-deployment-smoke.yml": 1,
        }
        for workflow_path, expected_count in expected_evidence_workflows.items():
            workflow_text = (ROOT / workflow_path).read_text(encoding="utf-8")
            self.assertEqual(
                expected_count,
                workflow_text.count(
                    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
                ),
                workflow_path,
            )
        for evidence_path in (
            "apps/web-console/test-results/ci-playwright-report",
            "apps/web-console/test-results/ci-generation-browser-matrix-report",
            "apps/web-console/test-results/ci-runner-playwright-report",
        ):
            self.assertIn(evidence_path, rendered)

    def test_ci_covers_every_polyglot_engine_business_line(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        self.assertTrue(
            {
                "java",
                "dotnet-engine",
                "python-engine",
                "frontend-client-engine",
                "polyglot-routes",
                "project-synthesis",
                "project-synthesis-acceptance",
                "web-console",
                "web-console-runner-e2e",
            }.issubset(jobs)
        )
        rendered = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        polyglot_job = json.dumps(jobs["polyglot-routes"], ensure_ascii=False, sort_keys=True)
        polyglot_verify = next(
            step["run"]
            for step in jobs["polyglot-routes"]["steps"]
            if step.get("name") == "Verify compiler-backed route engine"
        )
        synthesis_evidence_job = json.dumps(
            jobs["project-synthesis-acceptance"],
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertIn("dotnet restore engines/dotnet-engine/Elmos.Dotnet.slnx --locked-mode", rendered)
        self.assertIn("uv --directory engines/python-engine run --locked pytest", rendered)
        self.assertIn("pnpm --dir engines/frontend-client-engine install --frozen-lockfile", rendered)
        self.assertIn('"java-version": "21.0.11"', polyglot_job)
        self.assertIn('"dotnet-version": "10.0.301"', polyglot_job)
        self.assertIn('"node-version": "26.0.0"', polyglot_job)
        self.assertIn('export ELMOS_JAVA21_HOME="$JAVA_HOME"', polyglot_verify)
        self.assertIn("python scripts/operations/validate_translation_route_matrix.py", rendered)
        self.assertIn('"java-version": "21.0.11"', synthesis_evidence_job)
        self.assertIn('"dotnet-version": "10.0.301"', synthesis_evidence_job)
        self.assertIn('"node-version": "26.0.0"', synthesis_evidence_job)
        self.assertIn("install_project_synthesis_ci_toolchains.sh", synthesis_evidence_job)
        self.assertIn("python scripts/run_acceptance.py --require-all-toolchains", synthesis_evidence_job)
        self.assertIn("python scripts/run_production_matrix.py", synthesis_evidence_job)
        self.assertIn("playwright install --with-deps chromium", rendered)
        self.assertIn("--project=mobile-chromium", rendered)
        self.assertIn("e2e/generation-runner.spec.ts", rendered)
        self.assertIn("e2e/spring-real-journey-ui.spec.ts", rendered)
        self.assertIn("make product-closure-convergence-skills", rendered)
        installer_path = ROOT / "scripts/toolchains/install_project_synthesis_ci_toolchains.sh"
        installer = installer_path.read_text(encoding="utf-8")
        self.assertNotEqual(installer_path.stat().st_mode & 0o111, 0)
        for exact_contract in (
            'MAVEN_VERSION="3.9.10"',
            'PHP_VERSION="8.4.12"',
            'POSTGRES_VERSION="17.5"',
            "MAVEN_SHA512=",
            "PHP_SHA256=",
            "POSTGRES_SHA256=",
        ):
            self.assertIn(exact_contract, installer)

    def test_production_readiness_covers_all_current_skill_distributions_portably(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        target = re.search(r"production-readiness-check:([^\n]+)", makefile)
        self.assertIsNotNone(target)
        prerequisites = set(target.group(1).split())
        self.assertTrue(
            {
                "batch45-check",
                "project-synthesis",
                "chinadb-commercial-migration-skills",
                "sql-transpiler",
                "batch97-104-skills",
                "product-closure-convergence-skills",
                "web",
            }
            .issubset(prerequisites)
        )
        self.assertIn("UV ?= uv", makefile)
        self.assertNotIn("/opt/homebrew/bin/uv", makefile)

    def test_vercel_deploys_the_nested_nextjs_console_instead_of_an_empty_root(self) -> None:
        app_root = ROOT / "apps" / "web-console"
        config = json.loads((app_root / "vercel.json").read_text(encoding="utf-8"))
        package = json.loads((app_root / "package.json").read_text(encoding="utf-8"))
        self.assertEqual("nextjs", config["framework"])
        self.assertEqual("@elmos/web-console", package["name"])
        self.assertEqual("pnpm@10.12.4", package["packageManager"])
        self.assertEqual("next build", package["scripts"]["build"])
        self.assertFalse((ROOT / "vercel.json").exists())

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

    def test_closure_skill_import_is_repository_self_contained(self) -> None:
        source = (
            ROOT / "tooling" / "import_product_closure_convergence.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("/Users/", source)
        self.assertNotIn(".codex/skills", source)
        self.assertIn("skill_creator_tools.validate_skill", source)

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
            "uv run elmos-project-synthesis analyze",
            "uv run elmos-project-synthesis approve",
            "uv run elmos-project-synthesis generate",
            "uv run elmos-project-synthesis verify",
            "uv run elmos-project-synthesis runtime-plan",
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

    def test_python_production_profile_has_one_postgresql_17_5_contract(self) -> None:
        contract_paths = (
            ROOT
            / "apps"
            / "web-console"
            / "app"
            / "generation"
            / "ProjectGenerationStudio.tsx",
            ROOT
            / "engines"
            / "project-synthesis-engine"
            / "src"
            / "elmos_project_synthesis"
            / "container_images.py",
            ROOT
            / "engines"
            / "project-synthesis-engine"
            / "src"
            / "elmos_project_synthesis"
            / "python_production_target.py",
            ROOT / "engines" / "project-synthesis-engine" / "README.md",
            ROOT / "scripts" / "operations" / "rootless_project_runner.py",
            ROOT / "docs" / "BUSINESS_LINE_CLOSURE_MATRIX.md",
            ROOT / "docs" / "project-synthesis" / "BUNDLED_EMITTER_SUPPORT.md",
        )
        contents = "\n".join(path.read_text(encoding="utf-8") for path in contract_paths)
        forbidden_version = ".".join(("17", "6"))
        self.assertNotIn(forbidden_version, contents)
        self.assertIn("PostgreSQL 17.5", contents)
        self.assertRegex(
            contents,
            r"postgres:17\.5-alpine@sha256:[0-9a-f]{64}",
        )

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
