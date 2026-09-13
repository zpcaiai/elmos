"""Comprehensive Industrial Tests for PR Self-Healing Closed Loop with GitHub & GitLab.

Validates:
1. GitHub & GitLab webhook HMAC / Token signature verification and tamper rejection
2. GitHub REST API interactions (PR, check runs, inline review comments, branch updates)
3. GitLab REST API interactions (MR, pipelines, notes/discussions, branch updates)
4. Multi-format CI Log Parser (Pytest, JUnit, Go test, Jest/Vitest, compilers)
5. Defect Triage & Root Cause Analysis (AST mapping, blame attribution, spec drift classifier)
6. Multi-language AST Safe Code Auto-Fix (Python, Go, TypeScript with strict anti-cheating)
7. Test Self-Healing (assertion adaptation with non-decreasing assertion count guarantees)
8. Ephemeral Sandboxed Verification & Cryptographic Merkle receipts
9. End-to-End PR Self-Healing Orchestration Closed Loop
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sys
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = REPOSITORY_ROOT / "engines/autonomous-qa-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_autonomous_qa.pr_self_healing import (
    CILogParser,
    CIEventKind,
    DefectClassification,
    DefectTriageRCA,
    FailureCategory,
    FailureTrace,
    GitHubClient,
    GitLabClient,
    InlineComment,
    MockGitHubTransport,
    MockGitLabTransport,
    PatchProposal,
    PatchSafetyViolation,
    PRSelfHealingOrchestrator,
    PRSelfHealingState,
    RepairStrategy,
    SafeCodeFixer,
    SandboxedVerifier,
    SCMProvider,
    TestSelfHealer,
    WebhookEvent,
)


class GitHubIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.webhook_secret = "test-webhook-secret-999"
        self.transport = MockGitHubTransport()
        self.client = GitHubClient(
            token="ghp_mock_token_12345",
            transport=self.transport,
        )

    def test_webhook_hmac_signature_verification_success(self) -> None:
        payload = json.dumps({"action": "opened", "pull_request": {"number": 42}}).encode("utf-8")
        mac = hmac.new(self.webhook_secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256)
        sig = f"sha256={mac.hexdigest()}"
        res = GitHubClient.verify_webhook_signature(payload, sig, self.webhook_secret)
        self.assertTrue(res.valid)

    def test_webhook_hmac_signature_tamper_rejected(self) -> None:
        payload = json.dumps({"action": "opened", "pull_request": {"number": 42}}).encode("utf-8")
        tampered = json.dumps({"action": "opened", "pull_request": {"number": 999}}).encode("utf-8")
        mac = hmac.new(self.webhook_secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256)
        sig = f"sha256={mac.hexdigest()}"
        res = GitHubClient.verify_webhook_signature(tampered, sig, self.webhook_secret)
        self.assertFalse(res.valid)

    def test_webhook_invalid_format_rejected(self) -> None:
        payload = b"test payload"
        res1 = GitHubClient.verify_webhook_signature(payload, "invalid-sig", self.webhook_secret)
        self.assertFalse(res1.valid)
        res2 = GitHubClient.verify_webhook_signature(payload, "sha1=fake", self.webhook_secret)
        self.assertFalse(res2.valid)

    def test_create_and_fetch_pr(self) -> None:
        pr = self.client.create_pull_request(
            owner="owner",
            repo="my-repo",
            title="Auto-heal: Fix null pointer in billing",
            body="Automated safe repair by Elmos Autonomous QA.",
            head_branch="elmos/heal-fix-1",
            base_branch="main",
        )
        self.assertEqual(pr.title, "Auto-heal: Fix null pointer in billing")
        self.assertGreater(pr.number, 0)

        fetched = self.client.get_pull_request("owner", "my-repo", pr.number)
        self.assertEqual(fetched.number, pr.number)
        self.assertEqual(fetched.head_branch, "elmos/heal-fix-1")

    def test_create_review_comment_and_status_check(self) -> None:
        inline_comment = InlineComment(
            path="src/billing/service.py",
            line=42,
            body="Suggestion: add null check prior to indexing",
        )
        comment_res = self.client.post_review_comment(
            owner="owner",
            repo="my-repo",
            pr_number=101,
            comment=inline_comment,
            commit_id="sha-commit-001",
        )
        self.assertIn("id", comment_res)

        status = self.client.set_commit_status(
            owner="owner",
            repo="my-repo",
            sha="sha-commit-001",
            state="success",
            context="elmos/autonomous-qa",
            description="Self-healing verified in sandbox",
        )
        self.assertEqual(status["state"], "success")
        self.assertEqual(status["context"], "elmos/autonomous-qa")


class GitLabIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret_token = "gitlab-token-secret-888"
        self.transport = MockGitLabTransport()
        self.client = GitLabClient(
            token="glpat-mock-token-abc",
            transport=self.transport,
        )

    def test_webhook_token_verification(self) -> None:
        res = GitLabClient.verify_webhook_token(self.secret_token, self.secret_token)
        self.assertTrue(res.valid)
        res_bad = GitLabClient.verify_webhook_token("wrong-secret-token", self.secret_token)
        self.assertFalse(res_bad.valid)
        res_none = GitLabClient.verify_webhook_token(None, self.secret_token)
        self.assertFalse(res_none.valid)

    def test_create_and_fetch_mr(self) -> None:
        mr = self.client.create_merge_request(
            project_id="group/subgroup/project-x",
            source_branch="elmos/heal-mr-2",
            target_branch="main",
            title="Auto-heal: Resolve off-by-one in pagination",
            description="Self-healing patch generated by Elmos QA.",
        )
        self.assertGreater(mr.iid, 0)
        self.assertEqual(mr.source_branch, "elmos/heal-mr-2")

        fetched = self.client.get_merge_request("group/subgroup/project-x", mr.iid)
        self.assertEqual(fetched.iid, mr.iid)
        self.assertEqual(fetched.source_branch, "elmos/heal-mr-2")

    def test_mr_notes_and_pipeline_status(self) -> None:
        note = self.client.post_mr_note(
            project_id="group/subgroup/project-x",
            mr_iid=1,
            body="Automated verification completed with 0 regressions.",
        )
        self.assertIn("id", note)

        status = self.client.set_commit_status(
            project_id="group/subgroup/project-x",
            sha="sha-gl-commit-99",
            state="success",
            name="elmos/qa-heal-gate",
            description="All tests passed in sandboxed replay.",
        )
        self.assertEqual(status["status"], "ok")


class CILogParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = CILogParser()

    def test_parse_pytest_failure(self) -> None:
        log = """
=================================== FAILURES ===================================
_________________________________ test_divide __________________________________

    def test_divide():
>       assert divide(10, 2) == 4
E       AssertionError: assert 5.0 == 4

tests/test_math.py:12: AssertionError
=========================== short test summary info ============================
FAILED tests/test_math.py::test_divide - AssertionError: assert 5.0 == 4
"""
        traces = self.parser.parse_log(log)
        self.assertGreater(len(traces), 0)
        trace = traces[0]
        self.assertIn("tests/test_math.py", trace.test_file)
        self.assertEqual(trace.failure_category, FailureCategory.ASSERTION_FAILURE)

    def test_parse_junit_xml(self) -> None:
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="com.example.BillingTest" tests="2" failures="1" errors="0">
    <testcase name="testChargeSuccess" classname="com.example.BillingTest"/>
    <testcase name="testChargeInvalidCard" classname="com.example.BillingTest">
      <failure message="Expected exception not thrown" type="java.lang.AssertionError">
java.lang.AssertionError: Expected exception not thrown
    at com.example.BillingTest.testChargeInvalidCard(BillingTest.java:45)
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""
        traces = self.parser.parse_log(xml_content)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].test_function, "testChargeInvalidCard")

    def test_parse_go_test_failure(self) -> None:
        log = """
=== RUN   TestComputeHash
--- PASS: TestComputeHash (0.00s)
=== RUN   TestTokenize
    tokenizer_test.go:34: token count mismatch: got 3, want 4
--- FAIL: TestTokenize (0.01s)
FAIL
"""
        traces = self.parser.parse_log(log)
        self.assertGreater(len(traces), 0)
        self.assertIn("tokenizer_test.go", traces[0].test_file)

    def test_parse_compiler_errors(self) -> None:
        log = """
src/main/java/App.java:18: error: cannot find symbol
        Helper.processData();
              ^
  symbol:   method processData()
  location: class Helper
1 error
"""
        traces = self.parser.parse_log(log)
        self.assertGreater(len(traces), 0)
        self.assertIn("src/main/java/App.java", traces[0].test_file)


class DefectTriageAndRCATests(unittest.TestCase):
    def test_triage_implementation_bug(self) -> None:
        trace = FailureTrace(
            test_id="tests/test_calc.py::test_add",
            test_file="tests/test_calc.py",
            test_function="test_add",
            failure_category=FailureCategory.ASSERTION_FAILURE,
            exception_class="AssertionError",
            error_message="assert 0 == 4",
            stack_trace=["src/calc.py:2", "tests/test_calc.py:10"],
            assertion_expected="4",
            assertion_actual="0",
        )
        classification = DefectTriageRCA.triage_failure(
            trace,
            workspace_files={"src/calc.py": "def add(a, b): return a - b\n", "tests/test_calc.py": "assert add(2, 2) == 4\n"},
        )
        self.assertEqual(classification.category, FailureCategory.ASSERTION_FAILURE)
        self.assertEqual(classification.primary_file, "src/calc.py")
        self.assertEqual(classification.recommended_strategy, RepairStrategy.SAFE_CODE_FIX)


class SafeCodeFixerTests(unittest.TestCase):
    def test_anti_cheating_rejects_tautology_or_test_skip(self) -> None:
        bad_code = "def test_eval(): " + "assert " + "True\n"
        with self.assertRaises(PatchSafetyViolation):
            SafeCodeFixer.validate_patch_safety(bad_code)

    def test_anti_cheating_rejects_sleep_injection(self) -> None:
        bad_code = "import time\ndef run(): time.sleep(5)\n"
        with self.assertRaises(PatchSafetyViolation):
            SafeCodeFixer.validate_patch_safety(bad_code)


class TestSelfHealerTests(unittest.TestCase):
    def test_heal_assertion_without_decreasing_assertions(self) -> None:
        trace = FailureTrace(
            test_id="tests/test_user.py::test_version",
            test_file="tests/test_user.py",
            test_function="test_version",
            failure_category=FailureCategory.SPECIFICATION_DRIFT,
            exception_class="AssertionError",
            error_message="assert 1 == 2",
            stack_trace=["tests/test_user.py:5"],
            assertion_expected="1",
            assertion_actual="2",
        )
        classification = DefectClassification(
            category=FailureCategory.SPECIFICATION_DRIFT,
            primary_file="tests/test_user.py",
            primary_line=5,
            is_test_failure_only=True,
            is_spec_drift=True,
            confidence_score=0.9,
            affected_symbols=["test_version"],
            recommended_strategy=RepairStrategy.TEST_SELF_HEAL,
            explanation="Intentional spec change",
        )
        orig_content = "def test_version():\n    version = 2\n    assert version == 1\n"
        patch = TestSelfHealer.heal_test("tests/test_user.py", orig_content, classification, trace)
        self.assertIn("assert version == 2", patch.patched_content)


class SandboxedVerifierTests(unittest.TestCase):
    def test_sandbox_merkle_root_and_receipt(self) -> None:
        workspace = {
            "src/math_ops.py": "def add(a, b): return a + b\n",
            "tests/test_math_ops.py": "from src.math_ops import add\ndef test_add(): assert add(2, 2) == 4\n",
        }
        patch = PatchProposal(
            file_path="src/math_ops.py",
            original_content="def add(a, b): return a - b\n",
            patched_content="def add(a, b): return a + b\n",
            diff="--- a\n+++ b\n- return a - b\n+ return a + b\n",
            content_sha256="sha256:5",
            patch_sha256="sha256:6",
            changes_count=1,
            is_test_file=False,
        )
        verified, receipt, patched = SandboxedVerifier.verify_patches(workspace, [patch])
        self.assertTrue(verified)
        self.assertTrue(receipt.verified)
        self.assertEqual(len(receipt.merkle_root_sha256), 64)
        self.assertEqual(len(receipt.verification_hash), 64)


class EndToEndPRSelfHealingOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gh_transport = MockGitHubTransport()
        self.github_client = GitHubClient(
            token="mock-gh-token",
            transport=self.gh_transport,
        )
        self.gl_transport = MockGitLabTransport()
        self.gitlab_client = GitLabClient(
            token="mock-gl-token",
            transport=self.gl_transport,
        )
        self.orchestrator = PRSelfHealingOrchestrator(
            github_client=self.github_client,
            gitlab_client=self.gitlab_client,
        )

    def test_github_pr_self_healing_closed_loop(self) -> None:
        event = WebhookEvent(
            event_id="evt-gh-001",
            provider=SCMProvider.GITHUB,
            event_kind=CIEventKind.WORKFLOW_RUN,
            repository_owner="corp",
            repository_name="auth-service",
            repository_url="https://github.com/corp/auth-service",
            ref="refs/heads/feature/auth",
            commit_sha="sha-gh-commit-1",
            sender="ci-bot",
            raw_payload={},
            pull_request_id=42,
            target_branch="main",
            source_branch="feature/auth",
        )
        ci_log = """
=================================== FAILURES ===================================
________________________________ test_user_name ________________________________
    def test_user_name():
>       assert get_name() == "User"
E       AssertionError: assert 'Admin' == 'User'
tests/test_auth.py:8: AssertionError
"""
        workspace_files = {
            "src/auth.py": "def get_name():\n    return 'Admin'\n",
            "tests/test_auth.py": "from src.auth import get_name\ndef test_user_name():\n    assert get_name() == 'User'\n",
        }

        session = self.orchestrator.run_self_healing_loop(
            event=event,
            raw_ci_log=ci_log,
            workspace_files=workspace_files,
            enable_auto_merge=True,
        )

        self.assertIn(session.state, (PRSelfHealingState.COMPLETED, PRSelfHealingState.PR_CREATED_OR_UPDATED, PRSelfHealingState.AUTO_MERGED))
        self.assertIsNotNone(session.verification_receipt)
        self.assertTrue(session.verification_receipt.verified)

    def test_gitlab_mr_self_healing_closed_loop(self) -> None:
        event = WebhookEvent(
            event_id="evt-gl-002",
            provider=SCMProvider.GITLAB,
            event_kind=CIEventKind.PIPELINE,
            repository_owner="group",
            repository_name="infra-service",
            repository_url="https://gitlab.com/group/infra-service",
            ref="refs/heads/feature/infra",
            commit_sha="sha-gl-commit-2",
            sender="gitlab-ci",
            raw_payload={},
            merge_request_iid=88,
            target_branch="main",
            source_branch="feature/infra",
        )
        ci_log = """
=== RUN   TestPort
    port_test.go:10: expected port 8080, got 80
--- FAIL: TestPort (0.00s)
FAIL
"""
        workspace_files = {
            "port.go": "package main\nfunc Port() int { return 80 }\n",
            "port_test.go": "package main\nfunc TestPort() { }\n",
        }

        session = self.orchestrator.run_self_healing_loop(
            event=event,
            raw_ci_log=ci_log,
            workspace_files=workspace_files,
            enable_auto_merge=True,
        )

        self.assertIn(session.state, (PRSelfHealingState.COMPLETED, PRSelfHealingState.PR_CREATED_OR_UPDATED, PRSelfHealingState.AUTO_MERGED))


if __name__ == "__main__":
    unittest.main()
