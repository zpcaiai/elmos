import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "verification-packs" / "elmos-three-line-workflow-protocol"


class WorkflowProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads((PACK / "models" / "model.json").read_text())
        cls.protocol = json.loads(
            (PACK / "state-machines" / "workflow-protocol.json").read_text()
        )
        cls.transitions = {
            (source, command["command"]): command["to"]
            for command in cls.model["commands"]
            for source in command["from"]
        }

    def execute(self, trace):
        state = trace["initial"]
        for event in trace["events"]:
            target = self.transitions.get((state, event))
            if target is None:
                return state, event
            state = target
        return state, None

    def test_development_traces_reach_declared_terminal_states(self):
        corpus = json.loads(
            (PACK / "corpus" / "development" / "traces.json").read_text()
        )
        for trace in corpus["traces"]:
            with self.subTest(trace=trace["id"]):
                state, rejection = self.execute(trace)
                self.assertIsNone(rejection)
                self.assertEqual(trace["expected"], state)

    def test_negative_corpus_detects_each_seeded_forbidden_transition(self):
        corpus = json.loads(
            (PACK / "corpus" / "negative" / "traces.json").read_text()
        )
        detected = set()
        for trace in corpus["traces"]:
            with self.subTest(trace=trace["id"]):
                state, rejection = self.execute(trace)
                self.assertEqual(trace["expected_rejection"]["state"], state)
                self.assertEqual(trace["expected_rejection"]["event"], rejection)
                detected.add(trace["id"])
        self.assertEqual(
            {
                "neg-push-dirty",
                "neg-pr-before-push",
                "neg-start-without-lease",
                "neg-complete-after-block",
            },
            detected,
        )

    def test_no_command_can_merge_deploy_or_force_push(self):
        effects = {
            effect
            for command in self.model["commands"]
            for effect in command.get("effects", [])
        }
        forbidden = set(self.protocol["forbidden_external_effects"])
        self.assertTrue(forbidden.isdisjoint(effects))
        self.assertEqual(
            {"publish-non-force-branch", "publish-pr"},
            set(self.protocol["repository_external_effects"]),
        )

    def test_terminal_states_cannot_publish_after_loss_or_cancellation(self):
        for state in ("blocked", "cancelled", "succeeded", "partial"):
            with self.subTest(state=state):
                self.assertNotIn((state, "complete"), self.transitions)
                self.assertNotIn((state, "start"), self.transitions)
                self.assertNotIn((state, "acquire-lease"), self.transitions)

    def test_holdout_and_representative_execution_remain_not_run(self):
        for relative in (
            "corpus/holdout/traces.json",
            "corpus/representative-workloads/traces.json",
        ):
            with self.subTest(corpus=relative):
                value = json.loads((PACK / relative).read_text())
                self.assertEqual("NOT_RUN", value["execution_status"])


if __name__ == "__main__":
    unittest.main()
