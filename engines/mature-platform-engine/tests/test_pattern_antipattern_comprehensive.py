import unittest
from datetime import datetime
from elmos_mature_platform.types import (
    PatternType,
    PatternConfidence,
    PatternRecord,
    PatternMatch,
    PatternRule
)
from elmos_mature_platform.pattern_antipattern_engine import PatternAntipatternEngine

class TestPatternAntipatternEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PatternAntipatternEngine()

    def test_register_pattern_success(self):
        pattern = PatternRecord(
            pattern_id="p1",
            name="Singleton",
            pattern_type=PatternType.DESIGN,
            description="A design pattern."
        )
        pid = self.engine.register_pattern(pattern)
        self.assertEqual(pid, "p1")
        self.assertEqual(len(self.engine._patterns), 1)

    def test_register_antipattern_success(self):
        pattern = PatternRecord(
            pattern_id="a1",
            name="God Class",
            pattern_type=PatternType.DESIGN,
            description="An antipattern.",
            is_antipattern=True,
            fix_suggestion="Split into smaller classes."
        )
        pid = self.engine.register_pattern(pattern)
        self.assertEqual(pid, "a1")

    def test_register_antipattern_fails_without_fix(self):
        pattern = PatternRecord(
            pattern_id="a2",
            name="Spaghetti Code",
            pattern_type=PatternType.CODE,
            description="Bad code.",
            is_antipattern=True
        )
        with self.assertRaises(ValueError):
            self.engine.register_pattern(pattern)

    def test_record_match_success(self):
        pattern = PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...")
        self.engine.register_pattern(pattern)
        match = PatternMatch(match_id="m1", pattern_id="p1", file_path="main.py")
        self.engine.record_match(match)
        self.assertEqual(self.engine._patterns["p1"].occurrences, 1)

    def test_record_match_invalid_pattern(self):
        match = PatternMatch(match_id="m1", pattern_id="p1", file_path="main.py")
        with self.assertRaises(ValueError):
            self.engine.record_match(match)

    def test_record_match_first_seen_updated(self):
        pattern = PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...")
        self.engine.register_pattern(pattern)
        match = PatternMatch(match_id="m1", pattern_id="p1", file_path="main.py")
        self.engine.record_match(match)
        self.assertTrue(self.engine._patterns["p1"].first_seen != "")
        self.assertEqual(self.engine._patterns["p1"].first_seen, self.engine._patterns["p1"].last_seen)

    def test_add_rule_success(self):
        pattern = PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...")
        self.engine.register_pattern(pattern)
        rule = PatternRule(rule_id="r1", pattern_id="p1")
        self.engine.add_rule(rule)
        self.assertEqual(len(self.engine._rules), 1)

    def test_add_rule_invalid_pattern(self):
        rule = PatternRule(rule_id="r1", pattern_id="p1")
        with self.assertRaises(ValueError):
            self.engine.add_rule(rule)

    def test_search_patterns_by_type(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="..."))
        self.engine.register_pattern(PatternRecord(pattern_id="p2", name="P2", pattern_type=PatternType.DESIGN, description="..."))
        results = self.engine.search_patterns(pattern_type=PatternType.CODE)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pattern_id, "p1")

    def test_search_patterns_by_is_antipattern(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="..."))
        self.engine.register_pattern(PatternRecord(pattern_id="p2", name="P2", pattern_type=PatternType.CODE, description="...", is_antipattern=True, fix_suggestion="fix"))
        results = self.engine.search_patterns(is_antipattern=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pattern_id, "p2")

    def test_search_patterns_by_language(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...", languages=["python"]))
        self.engine.register_pattern(PatternRecord(pattern_id="p2", name="P2", pattern_type=PatternType.CODE, description="...", languages=["java"]))
        results = self.engine.search_patterns(language="python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pattern_id, "p1")

    def test_search_patterns_combined_filters(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...", is_antipattern=True, fix_suggestion="x", languages=["python"]))
        self.engine.register_pattern(PatternRecord(pattern_id="p2", name="P2", pattern_type=PatternType.CODE, description="...", is_antipattern=True, fix_suggestion="x", languages=["java"]))
        results = self.engine.search_patterns(pattern_type=PatternType.CODE, is_antipattern=True, language="python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pattern_id, "p1")

    def test_get_matches_success(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="..."))
        self.engine.record_match(PatternMatch(match_id="m1", pattern_id="p1", file_path="f1.py"))
        matches = self.engine.get_matches("p1")
        self.assertEqual(len(matches), 1)

    def test_get_matches_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_matches("p1")

    def test_get_top_patterns(self):
        for i in range(3):
            p = PatternRecord(pattern_id=f"p{i}", name=f"P{i}", pattern_type=PatternType.CODE, description="...")
            self.engine.register_pattern(p)
            for _ in range(i):
                self.engine.record_match(PatternMatch(match_id=f"m_{i}_{_}", pattern_id=f"p{i}", file_path="f"))
        top = self.engine.get_top_patterns(2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0].pattern_id, "p2")
        self.assertEqual(top[1].pattern_id, "p1")

    def test_get_top_antipatterns(self):
        for i in range(3):
            p = PatternRecord(pattern_id=f"a{i}", name=f"A{i}", pattern_type=PatternType.CODE, description="...", is_antipattern=True, fix_suggestion="x")
            self.engine.register_pattern(p)
            for _ in range(i):
                self.engine.record_match(PatternMatch(match_id=f"m_{i}_{_}", pattern_id=f"a{i}", file_path="f"))
        top = self.engine.get_top_antipatterns(2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0].pattern_id, "a2")
        self.assertEqual(top[1].pattern_id, "a1")

    def test_promote_pattern_to_medium(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...", confidence=PatternConfidence.LOW))
        for _ in range(5):
            self.engine.record_match(PatternMatch(match_id=f"m{_}", pattern_id="p1", file_path="f"))
        p = self.engine.promote_pattern("p1")
        self.assertEqual(p.confidence, PatternConfidence.MEDIUM)

    def test_promote_pattern_to_high(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...", confidence=PatternConfidence.LOW))
        for _ in range(20):
            self.engine.record_match(PatternMatch(match_id=f"m{_}", pattern_id="p1", file_path="f"))
        p = self.engine.promote_pattern("p1")
        self.assertEqual(p.confidence, PatternConfidence.HIGH)

    def test_promote_pattern_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.promote_pattern("p1")

    def test_deprecate_pattern(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="..."))
        p = self.engine.deprecate_pattern("p1")
        self.assertEqual(p.confidence, PatternConfidence.EXPERIMENTAL)

    def test_deprecate_pattern_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.deprecate_pattern("p1")

    def test_get_pattern_trends(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="..."))
        for _ in range(5):
            self.engine.record_match(PatternMatch(match_id=f"m{_}", pattern_id="p1", file_path="f"))
        self.engine.register_pattern(PatternRecord(pattern_id="p2", name="P2", pattern_type=PatternType.DESIGN, description="..."))
        self.engine.record_match(PatternMatch(match_id="m_2", pattern_id="p2", file_path="f"))
        
        trends = self.engine.get_pattern_trends()
        self.assertEqual(trends["by_type"][PatternType.CODE.value], 1)
        self.assertEqual(trends["by_type"][PatternType.DESIGN.value], 1)
        self.assertIn("p1", trends["growing"])
        self.assertIn("p2", trends["new"])

    def test_get_pattern_report(self):
        self.engine.register_pattern(PatternRecord(pattern_id="p1", name="P1", pattern_type=PatternType.CODE, description="...", languages=["python"]))
        self.engine.register_pattern(PatternRecord(pattern_id="a1", name="A1", pattern_type=PatternType.DESIGN, description="...", is_antipattern=True, fix_suggestion="x", languages=["java"]))
        
        report = self.engine.get_pattern_report()
        self.assertEqual(report["total_patterns"], 2)
        self.assertEqual(report["by_type"][PatternType.CODE.value], 1)
        self.assertEqual(report["coverage_by_language"]["python"], 1)
        self.assertIn("p1", report["top_patterns"])
        self.assertIn("a1", report["top_antipatterns"])

    def test_empty_search(self):
        results = self.engine.search_patterns()
        self.assertEqual(len(results), 0)

    def test_empty_top_patterns(self):
        self.assertEqual(len(self.engine.get_top_patterns()), 0)

    def test_empty_top_antipatterns(self):
        self.assertEqual(len(self.engine.get_top_antipatterns()), 0)

    def test_top_patterns_limit(self):
        for i in range(15):
            self.engine.register_pattern(PatternRecord(pattern_id=f"p{i}", name=f"P{i}", pattern_type=PatternType.CODE, description="..."))
        self.assertEqual(len(self.engine.get_top_patterns(10)), 10)

    def test_top_antipatterns_limit(self):
        for i in range(15):
            self.engine.register_pattern(PatternRecord(pattern_id=f"a{i}", name=f"A{i}", pattern_type=PatternType.CODE, description="...", is_antipattern=True, fix_suggestion="x"))
        self.assertEqual(len(self.engine.get_top_antipatterns(10)), 10)

if __name__ == '__main__':
    unittest.main()
