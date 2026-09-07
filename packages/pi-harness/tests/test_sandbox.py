from __future__ import annotations

import tempfile
import unittest

from elmos_pi_harness.sandbox import SandboxNotEnforced, SandboxProfile, SandboxRunner


class SandboxTests(unittest.TestCase):
    def test_default_deny_and_allowlisted_absolute_executable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-sandbox-") as root:
            runner = SandboxRunner()
            profile = SandboxProfile("test", ("/bin/echo",), (root,), network_policy="disabled")
            with self.assertRaises(SandboxNotEnforced):
                runner.run(("/bin/echo", "blocked"), cwd=root, profile=profile, timeout_seconds=1)
            profile = SandboxProfile("test", ("/bin/echo",), (root,), network_policy="disabled", network_isolated=True)
            result = runner.run(("/bin/echo", "ok"), cwd=root, profile=profile, timeout_seconds=1)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, b"ok"))
            self.assertFalse(result.enforcement["shell"])


if __name__ == "__main__":
    unittest.main()
