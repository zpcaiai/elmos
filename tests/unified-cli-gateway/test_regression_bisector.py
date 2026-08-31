"""Unit tests for ELMOS Semantic Regression Bisector."""

import io
import json
import sys
import unittest

from elmos_cli.dispatcher import main
from elmos_polyglot_compiler.regression_bisector import (
    SemanticRegressionBisector,
    run_semantic_bisect,
)


class SemanticRegressionBisectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bisector = SemanticRegressionBisector()

    def test_bisect_empty_history(self) -> None:
        res = self.bisector.bisect_revisions([])
        self.assertEqual(res.status, "EMPTY_HISTORY")
        self.assertIsNone(res.first_bad_revision)

    def test_bisect_find_first_culprit(self) -> None:
        revisions = [
            {"id": "r1", "is_valid": True, "message": "commit 1"},
            {"id": "r2", "is_valid": True, "message": "commit 2"},
            {"id": "r3", "is_valid": False, "message": "commit 3 - break invariant"},
            {"id": "r4", "is_valid": False, "message": "commit 4"},
            {"id": "r5", "is_valid": False, "message": "commit 5"},
        ]
        res = self.bisector.bisect_revisions(revisions)
        self.assertEqual(res.status, "FOUND_CULPRIT")
        self.assertEqual(res.first_bad_revision, "r3")
        self.assertIn("break invariant", res.culprit_message)
        self.assertLessEqual(res.total_steps, 3)

    def test_bisect_all_passing(self) -> None:
        revisions = [
            {"id": "r1", "is_valid": True, "message": "ok 1"},
            {"id": "r2", "is_valid": True, "message": "ok 2"},
        ]
        res = self.bisector.bisect_revisions(revisions)
        self.assertEqual(res.status, "ALL_PASSING")
        self.assertIsNone(res.first_bad_revision)

    def test_cli_polyglot_bisect(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["polyglot", "bisect", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "NOT_RUN")
            self.assertIn("revision", data["culprit_message"].lower())
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
