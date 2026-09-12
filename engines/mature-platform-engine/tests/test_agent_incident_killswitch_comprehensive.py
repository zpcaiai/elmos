import unittest
import time
from elmos_mature_platform.types import (
    KillswitchAction,
    KillswitchTrigger,
    KillswitchRule,
    KillswitchEvent
)
from elmos_mature_platform.agent_incident_killswitch_engine import AgentIncidentKillswitchEngine

class TestAgentIncidentKillswitchEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AgentIncidentKillswitchEngine()
        
    def test_create_rule_generates_id(self):
        rule = KillswitchRule(
            rule_id="",
            agent_id="agent_1",
            trigger=KillswitchTrigger.ERROR_RATE,
            action=KillswitchAction.PAUSE,
            threshold=0.5
        )
        rule_id = self.engine.create_rule(rule)
        self.assertTrue(rule_id)
        self.assertEqual(rule_id, rule.rule_id)

    def test_create_rule_keeps_existing_id(self):
        rule = KillswitchRule(
            rule_id="r1",
            agent_id="agent_1",
            trigger=KillswitchTrigger.ERROR_RATE,
            action=KillswitchAction.PAUSE,
            threshold=0.5
        )
        rule_id = self.engine.create_rule(rule)
        self.assertEqual(rule_id, "r1")

    def test_enable_rule(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, enabled=False)
        self.engine.create_rule(rule)
        enabled_rule = self.engine.enable_rule("r1")
        self.assertTrue(enabled_rule.enabled)

    def test_enable_rule_missing(self):
        with self.assertRaises(KeyError):
            self.engine.enable_rule("missing")

    def test_disable_rule(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, enabled=True)
        self.engine.create_rule(rule)
        disabled_rule = self.engine.disable_rule("r1")
        self.assertFalse(disabled_rule.enabled)

    def test_disable_rule_missing(self):
        with self.assertRaises(KeyError):
            self.engine.disable_rule("missing")

    def test_evaluate_trigger_no_rules(self):
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.9)
        self.assertIsNone(event)

    def test_evaluate_trigger_under_threshold(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        self.engine.create_rule(rule)
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.5)
        self.assertIsNone(event)

    def test_evaluate_trigger_over_threshold(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        self.engine.create_rule(rule)
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.9)
        self.assertIsNotNone(event)
        self.assertEqual(event.rule_id, "r1")
        self.assertEqual(event.metric_value, 0.9)

    def test_evaluate_trigger_disabled_rule(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8, enabled=False)
        self.engine.create_rule(rule)
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.9)
        self.assertIsNone(event)

    def test_evaluate_trigger_updates_rule_stats(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        self.engine.create_rule(rule)
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.9)
        self.assertEqual(rule.trigger_count, 1)
        self.assertTrue(rule.last_triggered)

    def test_manual_killswitch(self):
        event = self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "Emergency stop")
        self.assertEqual(event.agent_id, "a1")
        self.assertEqual(event.action, KillswitchAction.TERMINATE)
        self.assertEqual(event.trigger, KillswitchTrigger.MANUAL)
        self.assertEqual(event.rule_id, "manual")

    def test_resolve_event(self):
        event = self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "Emergency stop")
        resolved = self.engine.resolve_event(event.event_id, "All good now")
        self.assertTrue(resolved.resolved)
        self.assertEqual(resolved.resolution_notes, "All good now")
        self.assertTrue(resolved.resolved_at)

    def test_resolve_event_missing(self):
        with self.assertRaises(KeyError):
            self.engine.resolve_event("missing", "notes")

    def test_get_active_events_empty(self):
        self.assertEqual(len(self.engine.get_active_events()), 0)

    def test_get_active_events_filtered(self):
        e1 = self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        e2 = self.engine.manual_killswitch("a2", KillswitchAction.PAUSE, "pause")
        self.engine.resolve_event(e1.event_id, "resolved")
        active = self.engine.get_active_events()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].event_id, e2.event_id)

    def test_get_agent_events(self):
        self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        self.engine.manual_killswitch("a1", KillswitchAction.PAUSE, "pause")
        self.engine.manual_killswitch("a2", KillswitchAction.PAUSE, "pause")
        events = self.engine.get_agent_events("a1")
        self.assertEqual(len(events), 2)

    def test_get_rules_for_agent(self):
        rule1 = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE)
        rule2 = KillswitchRule(rule_id="r2", agent_id="a1", trigger=KillswitchTrigger.COST_LIMIT, action=KillswitchAction.TERMINATE)
        rule3 = KillswitchRule(rule_id="r3", agent_id="a2", trigger=KillswitchTrigger.TIMEOUT, action=KillswitchAction.ISOLATE)
        self.engine.create_rule(rule1)
        self.engine.create_rule(rule2)
        self.engine.create_rule(rule3)
        rules = self.engine.get_rules_for_agent("a1")
        self.assertEqual(len(rules), 2)
        self.assertEqual(set(r.rule_id for r in rules), {"r1", "r2"})

    def test_is_agent_killed_false(self):
        self.assertFalse(self.engine.is_agent_killed("a1"))

    def test_is_agent_killed_true(self):
        self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        self.assertTrue(self.engine.is_agent_killed("a1"))

    def test_is_agent_killed_resolved(self):
        event = self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        self.engine.resolve_event(event.event_id, "fixed")
        self.assertFalse(self.engine.is_agent_killed("a1"))

    def test_is_agent_killed_wrong_action(self):
        self.engine.manual_killswitch("a1", KillswitchAction.PAUSE, "pause")
        self.assertFalse(self.engine.is_agent_killed("a1"))

    def test_get_killswitch_report_empty(self):
        report = self.engine.get_killswitch_report()
        self.assertEqual(report["total_events"], 0)

    def test_get_killswitch_report_counts(self):
        self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        self.engine.manual_killswitch("a1", KillswitchAction.PAUSE, "pause")
        
        rule = KillswitchRule(rule_id="r1", agent_id="a2", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.ROLLBACK, threshold=0.5)
        self.engine.create_rule(rule)
        self.engine.evaluate_trigger("a2", KillswitchTrigger.ERROR_RATE, 0.9)
        
        report = self.engine.get_killswitch_report()
        self.assertEqual(report["total_events"], 3)
        self.assertEqual(report["by_trigger"][KillswitchTrigger.MANUAL.value], 2)
        self.assertEqual(report["by_trigger"][KillswitchTrigger.ERROR_RATE.value], 1)
        self.assertEqual(report["by_action"][KillswitchAction.TERMINATE.value], 1)
        self.assertEqual(report["by_action"][KillswitchAction.PAUSE.value], 1)
        self.assertEqual(report["by_action"][KillswitchAction.ROLLBACK.value], 1)
        self.assertEqual(report["top_agents"]["a1"], 2)
        self.assertEqual(report["top_agents"]["a2"], 1)

    def test_get_killswitch_report_resolution_time(self):
        e1 = self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        # Just resolve immediately
        self.engine.resolve_event(e1.event_id, "done")
        report = self.engine.get_killswitch_report()
        self.assertTrue(report["avg_resolution_time_seconds"] >= 0.0)

    def test_evaluate_trigger_exact_threshold(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        self.engine.create_rule(rule)
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.8)
        self.assertIsNotNone(event)

    def test_evaluate_trigger_different_trigger_type(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        self.engine.create_rule(rule)
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.COST_LIMIT, 0.9)
        self.assertIsNone(event)

    def test_multiple_rules_same_agent(self):
        r1 = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        r2 = KillswitchRule(rule_id="r2", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.TERMINATE, threshold=0.9)
        self.engine.create_rule(r1)
        self.engine.create_rule(r2)
        
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.85)
        self.assertEqual(event.rule_id, "r1")
        self.assertEqual(event.action, KillswitchAction.PAUSE)

    def test_multiple_rules_higher_threshold(self):
        r1 = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.PAUSE, threshold=0.8)
        r2 = KillswitchRule(rule_id="r2", agent_id="a1", trigger=KillswitchTrigger.ERROR_RATE, action=KillswitchAction.TERMINATE, threshold=0.9)
        self.engine.create_rule(r1)
        self.engine.create_rule(r2)
        
        # It triggers the first one that matches
        # Note: Depending on dict ordering, it might hit r1 first even if it's over 0.9
        event = self.engine.evaluate_trigger("a1", KillswitchTrigger.ERROR_RATE, 0.95)
        self.assertIsNotNone(event)

    def test_agent_killed_multiple_events(self):
        self.engine.manual_killswitch("a1", KillswitchAction.PAUSE, "pause")
        e2 = self.engine.manual_killswitch("a1", KillswitchAction.TERMINATE, "stop")
        self.assertTrue(self.engine.is_agent_killed("a1"))
        self.engine.resolve_event(e2.event_id, "fixed")
        self.assertFalse(self.engine.is_agent_killed("a1"))

    def test_rule_defaults(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ANOMALY, action=KillswitchAction.THROTTLE)
        self.assertTrue(rule.enabled)
        self.assertEqual(rule.cooldown_seconds, 300)
        self.assertEqual(rule.trigger_count, 0)
        self.assertEqual(rule.threshold, 0.0)

    def test_rule_persistence(self):
        rule = KillswitchRule(rule_id="r1", agent_id="a1", trigger=KillswitchTrigger.ANOMALY, action=KillswitchAction.THROTTLE)
        self.engine.create_rule(rule)
        self.engine.disable_rule("r1")
        self.assertFalse(self.engine.get_rules_for_agent("a1")[0].enabled)

if __name__ == '__main__':
    unittest.main()
