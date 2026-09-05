from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "operations" / "wait_for_vercel_deployment.py"


def load_waiter():
    spec = importlib.util.spec_from_file_location("wait_for_vercel_deployment", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VercelDeploymentWaiterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.waiter = load_waiter()
        self.sha = "a" * 40

    def deployment(self, identifier: int, created_at: str, *, sha: str | None = None):
        return {
            "id": identifier,
            "sha": sha or self.sha,
            "task": "deploy",
            "created_at": created_at,
            "creator": {"login": "vercel[bot]"},
        }

    def status(self, state: str, url: str | None = None):
        return {
            "id": 10,
            "state": state,
            "created_at": "2026-09-04T12:00:00Z",
            "environment_url": url,
            "creator": {"login": "vercel[bot]"},
        }

    def test_newest_pending_never_falls_back_to_older_success(self) -> None:
        deployments = [
            self.deployment(1, "2026-09-04T10:00:00Z"),
            self.deployment(2, "2026-09-04T11:00:00Z"),
        ]
        status_calls = 0
        clock = iter((0.0, 0.0, 0.1))

        def fetch(path: str):
            nonlocal status_calls
            if "statuses" not in path:
                return deployments
            self.assertIn("/deployments/2/statuses", path)
            status_calls += 1
            return [
                self.status("pending")
                if status_calls == 1
                else self.status("success", "https://elmos-new-a1b2.vercel.app")
            ]

        resolved = self.waiter.wait_for_deployment(
            "owner/repository",
            self.sha,
            fetch_json=fetch,
            timeout_seconds=10,
            poll_seconds=0.01,
            monotonic=lambda: next(clock),
            sleep=lambda _seconds: None,
        )
        self.assertEqual(resolved, "https://elmos-new-a1b2.vercel.app")
        self.assertEqual(status_calls, 2)

    def test_newest_terminal_failure_is_not_hidden_by_older_success(self) -> None:
        deployments = [
            self.deployment(1, "2026-09-04T10:00:00Z"),
            self.deployment(2, "2026-09-04T11:00:00Z"),
        ]

        def fetch(path: str):
            if "statuses" not in path:
                return deployments
            self.assertIn("/deployments/2/statuses", path)
            return [self.status("failure", "https://elmos-old.vercel.app")]

        with self.assertRaisesRegex(
            self.waiter.DeploymentResolutionError,
            "VERCEL_DEPLOYMENT_FAILURE",
        ):
            self.waiter.wait_for_deployment(
                "owner/repository",
                self.sha,
                fetch_json=fetch,
                timeout_seconds=10,
                poll_seconds=1,
            )

    def test_mismatched_sha_and_non_vercel_creator_do_not_resolve(self) -> None:
        records = [
            self.deployment(1, "2026-09-04T10:00:00Z", sha="b" * 40),
            {
                **self.deployment(2, "2026-09-04T11:00:00Z"),
                "creator": {"login": "attacker"},
            },
        ]
        clock = iter((0.0, 1.0))
        with self.assertRaisesRegex(
            self.waiter.DeploymentResolutionError,
            "VERCEL_DEPLOYMENT_TIMEOUT",
        ):
            self.waiter.wait_for_deployment(
                "owner/repository",
                self.sha,
                fetch_json=lambda _path: records,
                timeout_seconds=0.5,
                poll_seconds=0.01,
                monotonic=lambda: next(clock),
                sleep=lambda _seconds: None,
            )

    def test_deployment_url_is_exact_https_vercel_host(self) -> None:
        for value in (
            "http://preview.vercel.app",
            "https://preview.vercel.app.evil.example",
            "https://user@preview.vercel.app",
            "https://preview.vercel.app/path",
            "https://preview.vercel.app?token=secret",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                self.waiter.DeploymentResolutionError,
                "VERCEL_DEPLOYMENT_URL_UNTRUSTED",
            ):
                self.waiter._deployment_url(value)

    def test_non_vercel_status_cannot_authorize_url(self) -> None:
        deployment = self.deployment(1, "2026-09-04T10:00:00Z")
        status = self.status("success", "https://attacker.vercel.app")
        status["creator"] = {"login": "attacker"}
        clock = iter((0.0, 1.0))
        with self.assertRaisesRegex(
            self.waiter.DeploymentResolutionError,
            "VERCEL_DEPLOYMENT_TIMEOUT",
        ):
            self.waiter.wait_for_deployment(
                "owner/repository",
                self.sha,
                fetch_json=lambda path: [status] if "statuses" in path else [deployment],
                timeout_seconds=0.5,
                poll_seconds=0.01,
                monotonic=lambda: next(clock),
                sleep=lambda _seconds: None,
            )

    def test_github_environment_append_requires_safe_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "github-env"
            output.write_text("", encoding="utf-8")
            self.waiter._append_github_environment(
                output,
                "https://preview-a1b2.vercel.app",
            )
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "ELMOS_E2E_BASE_URL=https://preview-a1b2.vercel.app\n",
            )
            link = root / "github-env-link"
            link.symlink_to(output)
            with self.assertRaisesRegex(
                self.waiter.DeploymentResolutionError,
                "GITHUB_ENV_FILE_UNSAFE",
            ):
                self.waiter._append_github_environment(
                    link,
                    "https://preview-a1b2.vercel.app",
                )

    def test_workflow_binds_checkout_probe_and_paths_to_exact_sha(self) -> None:
        workflow = (ROOT / ".github/workflows/vercel-deployment-smoke.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("deployments: read", workflow)
        self.assertIn("wait_for_vercel_deployment.py", workflow)
        self.assertIn("ELMOS_DEPLOYMENT_SHA", workflow)
        self.assertIn("ELMOS_VERCEL_EXPECTED_COMMIT_SHA", workflow)
        self.assertIn('ref: "${{ env.ELMOS_DEPLOYMENT_SHA }}"', workflow)
        self.assertIn('".vercelignore"', workflow)
        self.assertNotIn("deployment_url:", workflow)
        self.assertNotIn("ELMOS_VERCEL_SMOKE_URL", workflow)


if __name__ == "__main__":
    unittest.main()
