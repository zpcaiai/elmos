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
        self.assertIn("github.event.pull_request.head.sha || github.sha", workflow)


if __name__ == "__main__":
    unittest.main()
