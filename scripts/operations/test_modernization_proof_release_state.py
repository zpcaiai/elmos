import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modernization_proof_release_state as subject


class ModernizationProofReleaseStateTest(unittest.TestCase):
    def test_initial_state_is_exact_and_not_run(self):
        states = subject.initial_external_boundaries()
        self.assertEqual(set(subject.EXTERNAL_BOUNDARIES), set(states))
        self.assertEqual({subject.NOT_RUN}, set(states.values()))

    def test_missing_extra_and_unknown_states_fail_closed(self):
        missing = subject.initial_external_boundaries()
        missing.pop("REAL_CLOUD_PROVIDER")
        with self.assertRaises(subject.ReleaseStateFailure):
            subject.validate_external_boundaries(missing)

        extra = subject.initial_external_boundaries()
        extra["UNDECLARED_PROVIDER"] = subject.NOT_RUN
        with self.assertRaises(subject.ReleaseStateFailure):
            subject.validate_external_boundaries(extra)

        unknown = subject.initial_external_boundaries()
        unknown["REAL_CLOUD_PROVIDER"] = "PASSED"
        with self.assertRaises(subject.ReleaseStateFailure):
            subject.validate_external_boundaries(unknown)

    def test_observed_pr_execution_does_not_claim_independent_verification(self):
        states = subject.record_observed_execution(
            subject.initial_external_boundaries(), boundary="SCM_DRAFT_PULL_REQUEST"
        )
        self.assertEqual(
            subject.EXECUTED_AWAITING_VERIFICATION,
            states["SCM_DRAFT_PULL_REQUEST"],
        )
        self.assertEqual(subject.NOT_RUN, states["REAL_CLOUD_PROVIDER"])

    def test_observation_cannot_edit_an_unrelated_boundary(self):
        before = subject.initial_external_boundaries()
        after = subject.record_observed_execution(
            before, boundary="SCM_DRAFT_PULL_REQUEST"
        )
        after["REAL_CLOUD_PROVIDER"] = subject.EXECUTED_AWAITING_VERIFICATION
        with self.assertRaises(subject.ReleaseStateFailure):
            subject.validate_observation_transition(
                before, after, boundary="SCM_DRAFT_PULL_REQUEST"
            )

    def test_observation_cannot_downgrade_verified_state(self):
        states = subject.initial_external_boundaries()
        states["SCM_DRAFT_PULL_REQUEST"] = subject.INDEPENDENTLY_VERIFIED
        with self.assertRaises(subject.ReleaseStateFailure):
            subject.record_observed_execution(states, boundary="SCM_DRAFT_PULL_REQUEST")


if __name__ == "__main__":
    unittest.main()
