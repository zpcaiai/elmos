"""End-to-end tests: compile and run the Java, run the translation, compare.

These are the tests that can fail for a reason nobody anticipated.  Everything
else in this suite asserts something a human decided ought to be true; these
compare against javac and the JVM, which do not care what anyone decided.

They require a JDK.  If ``javac`` is missing the tests **fail** rather than skip:
a suite that quietly skips its only behavioural evidence and still reports green
is exactly the kind of result this project exists to stop producing.
"""

import json
import os
import shutil
import unittest
from pathlib import Path

from j2p.diff.harness import (
    BOUNDARY_INTS,
    DifferentialHarness,
    default_arg_vectors,
)

CORPUS = Path(__file__).resolve().parents[1] / "corpus"

#: Argument vectors per corpus program.  Two-argument programs get the full
#: boundary cross product; the values are the ones where Java and Python
#: disagree (overflow, negative division, negative remainder, MIN_VALUE).
CORPUS_PLAN = {
    "Arith.java": default_arg_vectors(2),
    "Control.java": default_arg_vectors(2),
    "Failure.java": default_arg_vectors(2),
    "Lambdas.java": [[v] for v in BOUNDARY_INTS],
    "Library.java": [
        [v, w]
        for v in ["0", "7", "-7", "2147483647"]
        for w in ["abc", "a", "", "A b"]
    ],
    "Mixed.java": [[v] for v in BOUNDARY_INTS],
    "Resources.java": [[v] for v in BOUNDARY_INTS],
    "Objects.java": [[v] for v in BOUNDARY_INTS],
    "Records.java": [[v] for v in BOUNDARY_INTS],
    "Records2.java": [[v] for v in BOUNDARY_INTS],
    "Times.java": [
        [v] for v in ["0", "1", "-1", "86400", "-90061", "1700000000", "2147483647"]
    ],
    "Strings.java": [
        [v, s]
        for v in ["0", "7", "-7", "2147483647", "-2147483648"]
        for s in ["abc", "a", "xyz", "A b"]
    ],
}


def _thin(vectors: list[list[str]], keep: int) -> list[list[str]]:
    """Sample argument vectors for the fast profile.

    The mutation harness runs this suite once per mutant, and a JVM start per
    input vector makes the full sweep too slow to run often.  The sample keeps
    the *boundary* vectors (they are ordered first in BOUNDARY_INTS) rather than
    a random subset, because those are the ones that separate a correct
    translation from a plausible one.
    """

    if len(vectors) <= keep:
        return vectors
    step = max(1, len(vectors) // keep)
    return vectors[::step][:keep]


if os.environ.get("J2P_FAST") == "1":
    CORPUS_PLAN = {name: _thin(v, 6) for name, v in CORPUS_PLAN.items()}


class ToolchainTest(unittest.TestCase):
    def test_jdk_is_available(self):
        self.assertIsNotNone(
            shutil.which("javac"),
            "javac is required: without it there is no behavioural evidence, "
            "and a green suite would be misleading",
        )
        self.assertIsNotNone(shutil.which("java"))


class CorpusDifferentialTest(unittest.TestCase):
    """One test method per corpus program, generated below."""

    harness = None

    @classmethod
    def setUpClass(cls):
        cls.harness = DifferentialHarness()

    def _check(self, name: str):
        report = self.harness.run(CORPUS / name, CORPUS_PLAN[name])
        self.assertEqual(
            report.outcome,
            "PASS",
            f"{name}: {report.outcome}: {report.detail}",
        )
        self.assertGreater(report.matched, 0, f"{name} ran no comparisons")
        self.assertEqual(report.mismatched, 0)


def _attach(name: str) -> None:
    def test(self, _name=name):
        self._check(_name)

    test.__name__ = f"test_{name[:-5].lower()}_matches_java"
    setattr(CorpusDifferentialTest, test.__name__, test)


for _name in sorted(CORPUS_PLAN):
    _attach(_name)


class HarnessHonestyTest(unittest.TestCase):
    """The harness must not report success for work it did not do."""

    @classmethod
    def setUpClass(cls):
        cls.harness = DifferentialHarness()

    def test_unbuildable_java_is_reported_as_build_failed_not_pass(self):
        broken = CORPUS / "_broken_for_test.java"
        broken.write_text(
            "public class _broken_for_test { public static void main(String[] a)"
            " { int x = ; } }",
            encoding="utf-8",
        )
        try:
            report = self.harness.run(broken, [[]])
            self.assertIn(report.outcome, ("BUILD_FAILED", "TRANSLATION_REFUSED"))
            self.assertNotEqual(report.outcome, "PASS")
        finally:
            broken.unlink(missing_ok=True)

    def test_refused_translation_is_not_reported_as_pass(self):
        refused = CORPUS / "_refused_for_test.java"
        refused.write_text(
            "public class _refused_for_test { public static void main(String[] a)"
            " { outer: while (true) { break outer; } } }",
            encoding="utf-8",
        )
        try:
            report = self.harness.run(refused, [[]])
            self.assertEqual(report.outcome, "TRANSLATION_REFUSED")
            self.assertEqual(report.matched, 0)
        finally:
            refused.unlink(missing_ok=True)

    def test_report_serializes_to_json(self):
        report = self.harness.run(CORPUS / "Objects.java", [["1"]])
        payload = json.loads(report.to_json())
        self.assertEqual(payload["outcome"], "PASS")
        self.assertEqual(payload["matched"], 1)
        self.assertTrue(payload["uir_digest"].startswith("sha256:"))

    def test_uir_digest_is_reproducible_across_runs(self):
        first = self.harness.run(CORPUS / "Objects.java", [["1"]])
        second = self.harness.run(CORPUS / "Objects.java", [["1"]])
        self.assertEqual(first.uir_digest, second.uir_digest)

    def test_generated_python_is_reproducible_across_runs(self):
        first = self.harness.run(CORPUS / "Arith.java", [["1", "1"]])
        second = self.harness.run(CORPUS / "Arith.java", [["1", "1"]])
        self.assertEqual(first.generated_python, second.generated_python)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
