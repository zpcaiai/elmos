import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_modernization_proof_release_evidence as subject


class CollectModernizationProofReleaseEvidenceTest(unittest.TestCase):
    def pr(self):
        return {
            "number": 42,
            "state": "open",
            "draft": True,
            "html_url": "https://github.com/zpcaiai/elmos/pull/42",
            "user": {"login": "release-engineer"},
            "head": {"sha": "a" * 40, "ref": "codex/release"},
            "base": {"ref": "main", "repo": {"full_name": "zpcaiai/elmos"}},
        }

    def test_accepts_exact_open_draft_pr(self):
        observed = subject.validate_pr(
            self.pr(), repository="zpcaiai/elmos", expected_head_sha="a" * 40
        )
        self.assertTrue(observed["draft"])
        self.assertEqual("a" * 40, observed["head_sha"])

    def test_rejects_ready_for_review_pr(self):
        document = self.pr()
        document["draft"] = False
        with self.assertRaises(subject.EvidenceFailure):
            subject.validate_pr(
                document, repository="zpcaiai/elmos", expected_head_sha="a" * 40
            )

    def test_rejects_wrong_head_subject(self):
        with self.assertRaises(subject.EvidenceFailure):
            subject.validate_pr(
                self.pr(), repository="zpcaiai/elmos", expected_head_sha="b" * 40
            )

    def test_rejects_wrong_repository_or_base(self):
        wrong_repository = self.pr()
        wrong_repository["base"]["repo"]["full_name"] = "attacker/elmos"
        with self.assertRaises(subject.EvidenceFailure):
            subject.validate_pr(
                wrong_repository, repository="zpcaiai/elmos", expected_head_sha="a" * 40
            )
        wrong_base = self.pr()
        wrong_base["base"]["ref"] = "release"
        with self.assertRaises(subject.EvidenceFailure):
            subject.validate_pr(
                wrong_base, repository="zpcaiai/elmos", expected_head_sha="a" * 40
            )

    def test_release_blockers_keep_image_failures_and_replace_stale_pr_state(self):
        image_blockers = [
            "VULNERABILITY_SCAN_BLOCKED",
            "EXTERNAL_REGISTRY_NOT_CONFIGURED",
            "SCM_DRAFT_PULL_REQUEST_NOT_RUN",
        ]
        boundary_blockers = [
            "SCM_DRAFT_PULL_REQUEST_EXECUTED_AWAITING_INDEPENDENT_VERIFICATION"
        ]
        blockers = subject.merge_production_blockers(image_blockers, boundary_blockers)
        self.assertIn("VULNERABILITY_SCAN_BLOCKED", blockers)
        self.assertIn("EXTERNAL_REGISTRY_NOT_CONFIGURED", blockers)
        self.assertNotIn("SCM_DRAFT_PULL_REQUEST_NOT_RUN", blockers)
        self.assertIn(boundary_blockers[0], blockers)


if __name__ == "__main__":
    unittest.main()
