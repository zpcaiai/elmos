from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMPORTER = ROOT / "tooling" / "import_product_closure_convergence.py"
CLOSURE_GATE = ROOT / "scripts" / "product-closure-batch56a" / "run_product_closure_gate.py"
CONVERGENCE_GATE = ROOT / "scripts" / "product-convergence" / "run_repository_convergence_gate.py"
CONVERGENCE_VALIDATOR = (
    ROOT / "scripts" / "product-convergence" / "validate_repository_convergence_bundle.py"
)
CONVERGENCE_CRITERIA = (
    "unified_core",
    "private_runner",
    "reference_engine",
    "reference_route",
    "validation_lab",
    "maintainability",
    "customer_handoff",
    "unit_economics",
)
CONVERGENCE_SKILLS = [f"CONV-{number:03d}" for number in range(1, 33)]


def write_evidence(root: Path, name: str, content: str) -> dict[str, object]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    data = path.read_bytes()
    return {
        "path": name,
        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def record(root: Path, name: str, executor: str, verifier: str, **extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "executor_id": executor,
        "verifier_id": verifier,
        "authorization_ref": "AUTH-REAL-001",
        "independent": True,
        "accepted": True,
        "authorized_real_execution": True,
        "evidence_file": write_evidence(root, f"evidence/{name}.json", json.dumps({"run": name})),
    }
    value.update(extra)
    return value


def prepare_convergence_bundle(root: Path, bundle: Path) -> None:
    plan = json.loads((bundle / "convergence-plan.json").read_text(encoding="utf-8"))
    plan["status"] = "approved"
    plan["owners"] = {skill_id: f"owner-{skill_id.lower()}" for skill_id in CONVERGENCE_SKILLS}
    plan["milestones"] = [{"milestone_id": "reference-route", "status": "completed"}]
    plan["blocking_items"] = []
    (bundle / "convergence-plan.json").write_text(json.dumps(plan), encoding="utf-8")

    capability_evidence: dict[str, dict[str, object]] = {}
    capabilities = []
    evidence_nodes = []
    for criterion in CONVERGENCE_CRITERIA:
        descriptor = write_evidence(
            root,
            f"evidence/capability-{criterion}.json",
            json.dumps({"criterion": criterion, "status": "passed", "execution_mode": "real"}),
        )
        capability_evidence[criterion] = descriptor
        capabilities.append(
            {
                "capability_id": criterion,
                "type": "convergence-readiness",
                "version": "1.0.0",
                "status": "supported",
                "owner": f"owner-{criterion}",
                "evidence": [descriptor],
                "constraints": [],
            }
        )
        evidence_nodes.append(
            {
                "id": f"evidence-{criterion}",
                "type": "criterion-result",
                "digest": hashlib.sha256(criterion.encode()).hexdigest(),
                "tenant_id": "elmos-internal",
                "producer": f"executor-{criterion}",
            }
        )
    (bundle / "capability-registry.json").write_text(
        json.dumps({"capabilities": capabilities}), encoding="utf-8"
    )
    (bundle / "dependency-graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": criterion, "kind": "readiness-capability"}
                    for criterion in CONVERGENCE_CRITERIA
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    (bundle / "evidence-graph.json").write_text(
        json.dumps({"nodes": evidence_nodes, "edges": []}), encoding="utf-8"
    )
    corpora = {
        "corpora": [
            {
                "corpus_id": "internal-holdout-v1",
                "class": "internal-holdout",
                "version": "1.0.0",
                "owner": "validation-owner",
                "license": "internal-approved",
                "allowed_uses": ["qualification"],
                "tenant_id": "elmos-internal",
                "content_digest": hashlib.sha256(b"internal-holdout").hexdigest(),
            },
            *[
                {
                    "corpus_id": f"customer-{organization}-v1",
                    "class": "customer-private",
                    "version": "1.0.0",
                    "owner": organization,
                    "license": "customer-authorized",
                    "allowed_uses": ["acceptance"],
                    "tenant_id": organization,
                    "content_digest": hashlib.sha256(organization.encode()).hexdigest(),
                }
                for organization in ("org-a", "org-b")
            ],
        ]
    }
    (bundle / "benchmark-corpus.json").write_text(json.dumps(corpora), encoding="utf-8")

    route = json.loads((bundle / "reference-route-plan.json").read_text(encoding="utf-8"))
    route["source"]["framework_versions"] = ["Spring Boot 3.5.3"]
    route["target"]["language_versions"] = ["C# 13"]
    route["target"]["framework_versions"] = ["ASP.NET Core 9.0", "EF Core 9.0"]
    route["status"] = "accepted"
    route["evidence"] = [
        write_evidence(
            root,
            "evidence/reference-route.json",
            json.dumps({"status": "passed", "execution_mode": "real", "route_id": route["route_id"]}),
        )
    ]
    (bundle / "reference-route-plan.json").write_text(json.dumps(route), encoding="utf-8")

    handoff = json.loads((bundle / "handoff-package.json").read_text(encoding="utf-8"))
    for exercise in handoff["exercises"]:
        exercise["status"] = "passed"
    handoff["customer_approvals"] = [
        {"organization_id": "org-a", "accepted": True},
        {"organization_id": "org-b", "accepted": True},
    ]
    (bundle / "handoff-package.json").write_text(json.dumps(handoff), encoding="utf-8")

    request = json.loads((bundle / "readiness-gate.json").read_text(encoding="utf-8"))
    request["status"] = "passed"
    request["criteria"] = {criterion: True for criterion in CONVERGENCE_CRITERIA}
    request["criterion_evidence"] = capability_evidence
    request["repository_evidence"] = {
        "artifact_manifest": write_evidence(
            root,
            "artifact.json",
            json.dumps(
                {
                    "source_commit": "1" * 40,
                    "target_commit": "2" * 40,
                    "artifacts": [{"name": "reference-route", "digest": "sha256:" + "a" * 64}],
                }
            ),
        ),
        "environment_manifest": write_evidence(
            root,
            "environment.json",
            json.dumps(
                {
                    "environment_id": "isolated-reference-lab",
                    "execution_mode": "real",
                    "tool_versions": {"java": "21.0.7", "dotnet": "9.0.7"},
                    "authorization_ref": "AUTH-REAL-001",
                }
            ),
        ),
    }
    request["artifact_sha256"] = request["repository_evidence"]["artifact_manifest"]["sha256"].removeprefix(
        "sha256:"
    )
    request["environment_sha256"] = request["repository_evidence"]["environment_manifest"][
        "sha256"
    ].removeprefix("sha256:")
    request["design_partner_evidence"] = [
        record(root, "partner-a", "partner-a-executor", "partner-a-verifier", organization_id="org-a"),
        record(root, "partner-b", "partner-b-executor", "partner-b-verifier", organization_id="org-b"),
    ]
    request["independent_review_evidence"] = [
        record(root, "review", "review-executor", "independent-reviewer")
    ]
    request["zero_tolerance_findings"] = []
    (bundle / "readiness-gate.json").write_text(json.dumps(request), encoding="utf-8")


class ProductClosureConvergenceIntegrationTest(unittest.TestCase):
    def run_gate(self, script: Path, target: Path, evidence_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), str(target), "--evidence-root", str(evidence_root)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_importer_verifies_exact_installation(self) -> None:
        result = subprocess.run(
            [sys.executable, str(IMPORTER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(16, report["batch56a_runtime_skills"])
        self.assertEqual(32, report["convergence_agent_skills"])
        self.assertEqual(48, report["skill_creator_compatible_validation"])
        self.assertEqual("NOT_RUN", report["external_evidence"])

    def test_batch56_normalizes_provenance_without_invalid_frontmatter(self) -> None:
        manifest = json.loads(
            (ROOT / "docs" / "product-closure-convergence" / "installed-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(16, len(manifest["batch56a"]["skills"]))
        self.assertEqual(32, len(manifest["convergence"]["skills"]))
        for item in manifest["batch56a"]["skills"]:
            text = (ROOT / item["installed_path"]).read_text(encoding="utf-8")
            header = text.split("---", 2)[1]
            self.assertNotIn("\nid:", "\n" + header)
            self.assertNotIn("\nbatch:", "\n" + header)
            self.assertNotIn("\nmaturity:", "\n" + header)
            self.assertIn("source_sha256:", header)

    def test_default_closure_request_fails_closed(self) -> None:
        target = ROOT / "templates" / "product-closure-batch56a" / "product-closure-gate.example.json"
        result = self.run_gate(CLOSURE_GATE, target, ROOT)
        self.assertEqual(2, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("BLOCKED", report["decision"])
        self.assertFalse(report["gaApproved"])
        self.assertEqual("NOT_RUN", report["externalEvidence"])

    def test_closure_gate_rejects_fake_digest_and_self_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = {
                "schemaVersion": "1.0",
                "artifactDigest": "sha256:" + "a" * 64,
                "programs": {name: "COMPLETED" for name in ("canonicalKernel", "goldenJourneys", "providers")},
                "p0Failures": [],
                "decision": "GA",
                "repositoryEvidence": {
                    "artifactManifest": {"path": "missing.json", "sha256": "sha256:" + "a" * 64, "bytes": 1},
                    "environmentManifest": {"path": "missing-env.json", "sha256": "sha256:" + "b" * 64, "bytes": 1},
                    "programEvidence": [
                        record(root, name, "same-person", "same-person", program=name)
                        for name in ("canonicalKernel", "goldenJourneys", "providers")
                    ],
                },
            }
            path = root / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            result = self.run_gate(CLOSURE_GATE, path, root)
            self.assertEqual(2, result.returncode)
            self.assertEqual("BLOCKED", json.loads(result.stdout)["decision"])

    def test_closure_gate_can_only_prepare_external_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository_evidence = {
                "artifactManifest": write_evidence(root, "artifact.json", "artifact-v1"),
                "environmentManifest": write_evidence(root, "environment.json", "environment-v1"),
                "programEvidence": [
                    record(root, name, f"executor-{name}", f"verifier-{name}", program=name)
                    for name in ("canonicalKernel", "goldenJourneys", "providers")
                ],
            }
            request = {
                "schemaVersion": "1.0",
                "artifactDigest": repository_evidence["artifactManifest"]["sha256"],
                "programs": {name: "COMPLETED" for name in ("canonicalKernel", "goldenJourneys", "providers")},
                "p0Failures": [],
                "decision": "GA",
                "repositoryEvidence": repository_evidence,
            }
            path = root / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            result = self.run_gate(CLOSURE_GATE, path, root)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual("READY_FOR_EXTERNAL_GATE", report["decision"])
            self.assertFalse(report["gaApproved"])
            self.assertFalse(report["productionCertified"])

    def test_default_convergence_request_fails_closed(self) -> None:
        result = self.run_gate(CONVERGENCE_GATE, ROOT / "product-convergence", ROOT)
        self.assertEqual(2, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("BLOCKED", report["decision"])
        self.assertEqual("NOT_RUN", report["external_evidence"])
        self.assertFalse(report["certified"])
        self.assertFalse(report["production_certified"])
        self.assertFalse(report["approves_deployment"])

    def test_repository_convergence_schema_bundle(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CONVERGENCE_VALIDATOR), str(ROOT / "product-convergence")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(12, report["schemas"])
        self.assertEqual(11, report["schema_bound_instances"])
        self.assertEqual("not-run", report["readiness"])

    def test_convergence_gate_rejects_fake_digest_and_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "product-convergence"
            shutil.copytree(ROOT / "product-convergence", bundle)
            request = json.loads((bundle / "readiness-gate.json").read_text(encoding="utf-8"))
            request["status"] = "passed"
            request["criteria"] = {key: True for key in request["criteria"]}
            request["repository_evidence"] = {
                "artifact_manifest": {"path": "missing", "sha256": "sha256:" + "a" * 64, "bytes": 1},
                "environment_manifest": {"path": "missing", "sha256": "sha256:" + "b" * 64, "bytes": 1},
            }
            request["design_partner_evidence"] = [
                record(root, "partner-a", "same", "same", organization_id="org-a"),
                record(root, "partner-b", "same", "same", organization_id="org-b"),
            ]
            request["independent_review_evidence"] = [record(root, "review", "same", "same")]
            (bundle / "readiness-gate.json").write_text(json.dumps(request), encoding="utf-8")
            result = self.run_gate(CONVERGENCE_GATE, bundle, root)
            self.assertEqual(2, result.returncode)
            self.assertEqual("BLOCKED", json.loads(result.stdout)["decision"])

    def test_convergence_gate_can_only_prepare_external_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "product-convergence"
            shutil.copytree(ROOT / "product-convergence", bundle)
            prepare_convergence_bundle(root, bundle)
            result = self.run_gate(CONVERGENCE_GATE, bundle, root)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual("READY_FOR_EXTERNAL_GATE", report["decision"])
            self.assertEqual("READY_FOR_EXTERNAL_GATE", report["maximum_decision"])
            self.assertFalse(report["certified"])
            self.assertFalse(report["production_certified"])
            self.assertFalse(report["approves_deployment"])
            self.assertFalse(report["approves_customer_acceptance"])

    def test_convergence_gate_rejects_fuzzy_route_after_other_facts_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "product-convergence"
            shutil.copytree(ROOT / "product-convergence", bundle)
            prepare_convergence_bundle(root, bundle)
            route = json.loads((bundle / "reference-route-plan.json").read_text(encoding="utf-8"))
            route["target"]["language_versions"] = ["C# current LTS"]
            (bundle / "reference-route-plan.json").write_text(json.dumps(route), encoding="utf-8")
            result = self.run_gate(CONVERGENCE_GATE, bundle, root)
            self.assertEqual(2, result.returncode)
            self.assertIn("reference route versions must be exact", result.stdout)

    def test_convergence_gate_rejects_missing_criterion_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "product-convergence"
            shutil.copytree(ROOT / "product-convergence", bundle)
            prepare_convergence_bundle(root, bundle)
            request = json.loads((bundle / "readiness-gate.json").read_text(encoding="utf-8"))
            request["criterion_evidence"].pop("unit_economics")
            (bundle / "readiness-gate.json").write_text(json.dumps(request), encoding="utf-8")
            result = self.run_gate(CONVERGENCE_GATE, bundle, root)
            self.assertEqual(2, result.returncode)
            self.assertIn("criterion_evidence must bind all eight exact readiness criteria", result.stdout)


if __name__ == "__main__":
    unittest.main()
