from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/operations/wait_for_vercel_deployment.py"
SPEC = importlib.util.spec_from_file_location("wait_for_vercel_deployment", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VercelDeploymentWaitTests(unittest.TestCase):
    def test_waits_for_exact_sha_and_returns_successful_environment(self) -> None:
        polls = iter([[], [{
            "id": 42,
            "task": "deploy",
            "creator": {"login": "vercel[bot]"},
            "created_at": "2026-09-04T07:00:00Z",
        }]])
        sleeps: list[float] = []

        def fetch(path: str) -> Any:
            if path.endswith("/statuses"):
                return [{
                    "state": "success",
                    "created_at": "2026-09-04T07:01:00Z",
                    "environment_url": "https://elmos-commit.example.vercel.app",
                }]
            self.assertIn("deployments?sha=" + "a" * 40, path)
            return next(polls)

        url = MODULE.wait_for_deployment(
            "zpcaiai/elmos",
            "a" * 40,
            fetch_json=fetch,
            timeout_seconds=60,
            poll_seconds=5,
            monotonic=lambda: 0,
            sleep=sleeps.append,
        )
        self.assertEqual(url, "https://elmos-commit.example.vercel.app")
        self.assertEqual(sleeps, [5])

    def test_reuses_successful_ancestor_only_for_identical_deployment_surface(
        self,
    ) -> None:
        current_sha = "a" * 40
        parent_sha = "b" * 40
        apps_sha = "c" * 40
        web_console_sha = "d" * 40
        ignore_sha = "e" * 40

        def root_tree() -> dict[str, Any]:
            return {
                "tree": [
                    {"path": ".vercelignore", "type": "blob", "sha": ignore_sha},
                    {"path": "apps", "type": "tree", "sha": apps_sha},
                ]
            }

        def fetch(path: str) -> Any:
            if path.endswith(f"deployments?sha={current_sha}&per_page=100"):
                return [
                    {
                        "id": 42,
                        "task": "deploy",
                        "environment": "Preview",
                        "creator": {"login": "vercel[bot]"},
                        "created_at": "2026-09-13T09:31:35Z",
                    }
                ]
            if path.endswith("/deployments/42/statuses"):
                return []
            if path.endswith(f"/commits/{current_sha}/status"):
                return {
                    "statuses": [
                        {
                            "context": "Vercel",
                            "state": "success",
                            "target_url": "https://vercel.com/team/elmos/deployment-id",
                            "updated_at": "2026-09-13T09:31:35Z",
                        }
                    ]
                }
            if path.endswith(f"/git/trees/{current_sha}") or path.endswith(
                f"/git/trees/{parent_sha}"
            ):
                return root_tree()
            if path.endswith(f"/git/trees/{apps_sha}"):
                return {
                    "tree": [
                        {
                            "path": "web-console",
                            "type": "tree",
                            "sha": web_console_sha,
                        }
                    ]
                }
            if path.endswith(f"/commits/{current_sha}"):
                return {"parents": [{"sha": parent_sha}]}
            if path.endswith(f"deployments?sha={parent_sha}&per_page=100"):
                return [
                    {
                        "id": 84,
                        "task": "deploy",
                        "environment": "Preview",
                        "creator": {"login": "vercel[bot]"},
                        "created_at": "2026-09-13T09:07:50Z",
                    }
                ]
            if path.endswith("/deployments/84/statuses"):
                return [
                    {
                        "state": "success",
                        "created_at": "2026-09-13T09:07:52Z",
                        "environment_url": "https://identical-tree.vercel.app",
                    }
                ]
            self.fail(f"unexpected GitHub API path: {path}")

        url = MODULE.wait_for_deployment(
            "zpcaiai/elmos",
            current_sha,
            fetch_json=fetch,
            timeout_seconds=60,
            poll_seconds=5,
            required_environment="Preview",
        )
        self.assertEqual(url, "https://identical-tree.vercel.app")

    def test_does_not_reuse_ancestor_with_different_deployment_surface(self) -> None:
        current_sha = "a" * 40
        parent_sha = "b" * 40
        current_apps_sha = "c" * 40
        parent_apps_sha = "d" * 40
        ignore_sha = "e" * 40

        def fetch(path: str) -> Any:
            if path.endswith(f"deployments?sha={current_sha}&per_page=100"):
                return [
                    {
                        "id": 42,
                        "task": "deploy",
                        "environment": "Preview",
                        "creator": {"login": "vercel[bot]"},
                        "created_at": "2026-09-13T09:31:35Z",
                    }
                ]
            if path.endswith("/deployments/42/statuses"):
                return []
            if path.endswith(f"/commits/{current_sha}/status"):
                return {
                    "statuses": [
                        {
                            "context": "Vercel",
                            "state": "success",
                            "target_url": "https://vercel.com/team/elmos/deployment-id",
                            "updated_at": "2026-09-13T09:31:35Z",
                        }
                    ]
                }
            if path.endswith(f"/git/trees/{current_sha}"):
                apps_sha = current_apps_sha
            elif path.endswith(f"/git/trees/{parent_sha}"):
                apps_sha = parent_apps_sha
            elif path.endswith(f"/git/trees/{current_apps_sha}"):
                return {
                    "tree": [
                        {
                            "path": "web-console",
                            "type": "tree",
                            "sha": "f" * 40,
                        }
                    ]
                }
            elif path.endswith(f"/git/trees/{parent_apps_sha}"):
                return {
                    "tree": [
                        {
                            "path": "web-console",
                            "type": "tree",
                            "sha": "1" * 40,
                        }
                    ]
                }
            else:
                apps_sha = None
            if apps_sha is not None:
                return {
                    "tree": [
                        {"path": ".vercelignore", "type": "blob", "sha": ignore_sha},
                        {"path": "apps", "type": "tree", "sha": apps_sha},
                    ]
                }
            if path.endswith(f"/commits/{current_sha}"):
                return {"parents": [{"sha": parent_sha}]}
            if path.endswith(f"/commits/{parent_sha}"):
                return {"parents": []}
            self.fail(f"unexpected GitHub API path: {path}")

        clock = iter((0.0, 1.0))
        with self.assertRaisesRegex(
            MODULE.DeploymentResolutionError,
            "VERCEL_DEPLOYMENT_TIMEOUT",
        ):
            MODULE.wait_for_deployment(
                "zpcaiai/elmos",
                current_sha,
                fetch_json=fetch,
                timeout_seconds=0.5,
                poll_seconds=5,
                required_environment="Preview",
                monotonic=lambda: next(clock),
            )

    def test_failed_deployment_fails_closed_without_using_mutable_alias(self) -> None:
        def fetch(path: str) -> Any:
            if path.endswith("/statuses"):
                return [{
                    "state": "failure",
                    "created_at": "2026-09-04T07:01:00Z",
                    "environment_url": "https://failed.vercel.app",
                    "description": "build failed",
                }]
            return [{
                "id": 42,
                "task": "deploy",
                "creator": {"login": "vercel[bot]"},
                "created_at": "2026-09-04T07:00:00Z",
            }]

        with self.assertRaisesRegex(
            MODULE.DeploymentResolutionError,
            "VERCEL_DEPLOYMENT_FAILURE:build failed",
        ):
            MODULE.wait_for_deployment(
                "zpcaiai/elmos",
                "b" * 40,
                fetch_json=fetch,
                timeout_seconds=60,
                poll_seconds=5,
            )

    def test_successful_production_deployment_uses_public_production_domain(self) -> None:
        def fetch(path: str) -> Any:
            if path.endswith("/statuses"):
                return [{
                    "state": "success",
                    "created_at": "2026-09-06T10:48:56Z",
                    "environment_url": "https://elmos-commit.vercel.app",
                }]
            return [{
                "id": 84,
                "task": "deploy",
                "environment": "Production",
                "creator": {"login": "vercel[bot]"},
                "created_at": "2026-09-06T10:48:56Z",
            }]

        url = MODULE.wait_for_deployment(
            "zpcaiai/elmos",
            "c" * 40,
            fetch_json=fetch,
            timeout_seconds=60,
            poll_seconds=5,
            production_url="https://elmos-alpha.vercel.app",
        )
        self.assertEqual(url, "https://elmos-alpha.vercel.app")

    def test_required_production_ignores_newer_successful_preview(self) -> None:
        def fetch(path: str) -> Any:
            if path.endswith("/statuses"):
                return [{
                    "state": "success",
                    "created_at": "2026-09-08T11:16:00Z",
                    "environment_url": "https://exact-sha.vercel.app",
                }]
            return [
                {
                    "id": 42,
                    "task": "deploy",
                    "environment": "Preview",
                    "creator": {"login": "vercel[bot]"},
                    "created_at": "2026-09-08T11:15:00Z",
                },
                {
                    "id": 84,
                    "task": "deploy",
                    "environment": "Production",
                    "creator": {"login": "vercel[bot]"},
                    "created_at": "2026-09-08T11:14:00Z",
                },
            ]

        url = MODULE.wait_for_deployment(
            "zpcaiai/elmos",
            "e" * 40,
            fetch_json=fetch,
            timeout_seconds=60,
            poll_seconds=5,
            production_url="https://elmos-alpha.vercel.app",
            required_environment="Production",
        )
        self.assertEqual(url, "https://elmos-alpha.vercel.app")

    def test_production_domain_is_validated_only_after_exact_deployment_succeeds(self) -> None:
        def fetch(path: str) -> Any:
            if path.endswith("/statuses"):
                return [{
                    "state": "success",
                    "created_at": "2026-09-06T10:48:56Z",
                    "environment_url": "https://elmos-commit.vercel.app",
                }]
            return [{
                "id": 84,
                "task": "deploy",
                "environment": "Production",
                "creator": {"login": "vercel[bot]"},
                "created_at": "2026-09-06T10:48:56Z",
            }]

        with self.assertRaisesRegex(
            MODULE.DeploymentResolutionError,
            "VERCEL_DEPLOYMENT_URL_UNTRUSTED",
        ):
            MODULE.wait_for_deployment(
                "zpcaiai/elmos",
                "d" * 40,
                fetch_json=fetch,
                timeout_seconds=60,
                poll_seconds=5,
                production_url="https://example.com",
            )

    def test_rejects_non_vercel_or_credentialed_urls(self) -> None:
        for url in (
            "http://elmos.vercel.app",
            "https://example.com",
            "https://user@example.vercel.app",
            "https://example.vercel.app:invalid",
            "https://example.vercel.app:8443",
            "https://example.vercel.app/not-root",
            "https://example.vercel.app?token=secret",
        ):
            with self.subTest(url=url), self.assertRaises(
                MODULE.DeploymentResolutionError
            ):
                MODULE._deployment_url(url)

    def test_workflow_resolves_deployment_before_installing_dependencies(self) -> None:
        workflow = (
            ROOT / ".github/workflows/vercel-deployment-smoke.yml"
        ).read_text(encoding="utf-8")
        resolve = workflow.index("- name: Resolve exact successful Vercel deployment")
        install = workflow.index("- name: Install locked web dependencies")
        smoke = workflow.index("- name: Run deployment surface smoke")
        self.assertLess(resolve, install)
        self.assertLess(install, smoke)
        self.assertIn("deployments: read", workflow)
        self.assertIn("statuses: read", workflow)
        self.assertIn("github.event.pull_request.head.sha || github.sha", workflow)
        self.assertEqual(1_800, MODULE.DEFAULT_TIMEOUT_SECONDS)
        self.assertIn("timeout-minutes: 45", workflow)
        self.assertIn("--timeout-seconds 1800", workflow)
        self.assertIn('--required-environment "${ELMOS_DEPLOYMENT_ENVIRONMENT}"', workflow)
        self.assertIn("github.event_name == 'pull_request' && 'Preview' || 'Production'", workflow)
        self.assertIn('--production-url "${ELMOS_PRODUCTION_SMOKE_URL}"', workflow)
        trigger_block = workflow.split("permissions:", 1)[0]
        self.assertIn("push:\n    branches: [main]", trigger_block)
        self.assertIn("pull_request:\n    branches: [main]", trigger_block)
        self.assertNotIn("paths:", trigger_block)

    def test_workflow_uses_short_lived_oidc_for_protected_preview(self) -> None:
        workflow = (
            ROOT / ".github/workflows/vercel-deployment-smoke.yml"
        ).read_text(encoding="utf-8")
        playwright_config = (
            ROOT / "apps/web-console/playwright.vercel.config.ts"
        ).read_text(encoding="utf-8")
        smoke_spec = (
            ROOT / "apps/web-console/e2e/vercel-deployment-smoke.spec.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("id-token: write", workflow)
        self.assertRegex(
            workflow,
            r"actions/github-script@[0-9a-f]{40}",
        )
        self.assertIn("await core.getIDToken()", workflow)
        self.assertIn("core.setSecret(token)", workflow)
        self.assertIn("steps.vercel-trusted-source.outputs.token", workflow)
        self.assertIn("ELMOS_VERCEL_TRUSTED_OIDC_TOKEN", workflow)
        self.assertIn("x-vercel-trusted-oidc-idp-token", smoke_spec)
        self.assertIn('trace: hasVercelTrustedOidcToken ? "off"', playwright_config)
        self.assertNotIn("x-vercel-protection-bypass", workflow + smoke_spec)


if __name__ == "__main__":
    unittest.main()
