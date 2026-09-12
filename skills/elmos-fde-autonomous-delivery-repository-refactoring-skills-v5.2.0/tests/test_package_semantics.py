import json, unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]

class PackageSemanticsTests(unittest.TestCase):
    def test_all_component_skills_non_routable_and_e3(self):
        manifests=list((ROOT/"skills/atomic").rglob("manifest.yaml")); self.assertEqual(45,len(manifests))
        for p in manifests:
            d=yaml.safe_load(p.read_text(encoding="utf-8")); s=d["spec"]
            self.assertFalse(s["routable"]); self.assertEqual("E3",s["compatibility"]["standaloneCompletionBoundary"])
            self.assertEqual("prohibited-in-capability-package",s["authority"]["productionWrite"])

    def test_requirements_scenarios_tasks_are_nontrivial(self):
        req=json.loads((ROOT/"catalog/requirements.json").read_text(encoding="utf-8"))
        sc=json.loads((ROOT/"catalog/scenarios.json").read_text(encoding="utf-8"))
        tasks=json.loads((ROOT/"catalog/implementation-tasks.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(req["count"],250); self.assertGreaterEqual(sc["count"],250); self.assertGreaterEqual(tasks["count"],450)

    def test_issue_ontology_depth(self):
        d=yaml.safe_load((ROOT/"catalog/issue-ontology.yaml").read_text(encoding="utf-8"))
        self.assertGreaterEqual(d["metadata"]["domainCount"],20); self.assertGreaterEqual(d["metadata"]["issueTypeCount"],150)

    def test_no_completion_authority_adapter(self):
        for p in (ROOT/"adapters").glob("*/descriptor.yaml"):
            d=yaml.safe_load(p.read_text(encoding="utf-8")); self.assertFalse(d["spec"]["completionAuthority"])

if __name__=="__main__": unittest.main()
