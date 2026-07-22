#!/usr/bin/env python3
"""Generate the generic Batch 38-45 repository Skill packages.

Batches 35, 36, and 37 are managed by richer standalone packages and must not
be overwritten by this compatibility generator.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ChatGPT-跨语言迁移月报 (1).md"
SKILL_ROOT = ROOT / ".agents" / "skills"
INIT_SKILL = Path("/Users/stephen/.codex/skills/.system/skill-creator/scripts/init_skill.py")

BATCHES = {
    38: {
        "title": "Enterprise deployment matrix and upgrade lifecycle",
        "objective": "Support SaaS, dedicated, customer VPC, self-hosted, sovereign, air-gapped, edge, and multi-region editions.",
        "first": 1325,
        "metrics": {"editionConformanceRate": ("min", 1.0), "upgradeRollbackPassRate": ("min", 1.0), "recoveryPassRate": ("min", 1.0)},
        "slugs": [
            "enterprise-deployment-upgrade-factory", "edition-responsibility-matrix", "portable-control-plane",
            "multitenant-saas-edition", "dedicated-saas-edition", "customer-vpc-edition", "self-hosted-edition",
            "private-sovereign-cloud-edition", "air-gapped-edition", "edge-plant-restricted-edition",
            "multiregion-active-active-edition", "plane-topology-governance", "tenant-edition-migration",
            "platform-version-compatibility", "runner-version-compatibility", "workflow-version-long-run-recovery",
            "database-expand-contract-upgrade", "recipe-pack-extension-upgrade", "offline-signed-update-bundle",
            "zero-downtime-upgrade", "upgrade-rollback-disaster-recovery", "deployment-upgrade-gate",
        ],
    },
    39: {
        "title": "Global SRE and platform operations",
        "objective": "Operate the migration platform to enterprise-critical reliability and support standards.",
        "first": 1347,
        "metrics": {"sloPassRate": ("min", 1.0), "restorePassRate": ("min", 1.0), "incidentExercisePassRate": ("min", 1.0)},
        "slugs": [
            "global-sre-operations-factory", "service-catalog-sli-slo", "error-budget-governance",
            "global-observability-telemetry", "tenant-project-migration-health", "job-fairness-tenant-isolation",
            "autoscaling-capacity-control", "multiregion-failover", "backup-restore-recovery", "incident-command",
            "problem-root-cause-loop", "oncall-follow-the-sun", "customer-status-communication",
            "enterprise-support-sla", "change-management-freeze", "platform-cost-anomaly-monitoring",
            "chaos-resilience-fault-injection", "production-readiness-review", "sla-service-credit-governance",
            "scheduled-restore-dr-exercise", "operations-evidence-reporting", "global-operations-gate",
        ],
    },
    40: {
        "title": "Secure supply chain and compliance certification",
        "objective": "Give every generated repository, Runner, Recipe, model, artifact, and release a trustworthy supply chain.",
        "first": 1369,
        "metrics": {"supplyChainCoverageRate": ("min", 0.95), "signaturePassRate": ("min", 1.0), "criticalVulnerabilityCount": ("max", 0.0)},
        "slugs": [
            "supply-chain-compliance-factory", "secure-sdlc-ssdf", "threat-modeling", "security-architecture-review",
            "secure-code-review-approval", "sast-integration", "dast-iast-integration", "dependency-sca-governance",
            "secret-credential-scanning", "container-kubernetes-iac-scanning", "sbom-component-identity",
            "vex-applicability", "license-ip-provenance", "artifact-container-signing", "slsa-provenance",
            "isolated-trusted-builder", "runner-update-supply-chain", "ai-model-supply-chain",
            "vulnerability-patch-sla", "psirt-security-incident", "compliance-control-crosswalk",
            "customer-audit-evidence", "independent-security-assessment", "security-supply-chain-gate",
        ],
    },
    41: {
        "title": "Migration knowledge graph and intelligence flywheel",
        "objective": "Turn project outcomes, rules, tests, failures, and customer acceptance into governed reusable knowledge.",
        "first": 1393,
        "metrics": {"knowledgeProvenanceCoverageRate": ("min", 0.95), "privacyIsolationPassRate": ("min", 1.0), "predictionCalibrationPassRate": ("min", 1.0)},
        "slugs": [
            "migration-knowledge-factory", "knowledge-graph-ontology", "migration-entity-relations",
            "migration-run-ingestion", "pattern-antipattern-extraction", "recipe-mapping-recommendation",
            "similar-project-retrieval", "migration-risk-prediction", "automation-buildgreen-prediction",
            "effort-duration-cost-prediction", "target-stack-recommendation", "diagnostic-root-cause-recommendation",
            "knowledge-confidence-provenance", "knowledge-freshness-versioning", "knowledge-isolation",
            "privacy-preserving-learning", "holdout-feedback-calibration", "human-curation-governance",
            "knowledge-marketplace-sharing", "knowledge-flywheel-gate",
        ],
    },
    42: {
        "title": "Mature governed Agent migration factory",
        "objective": "Build a governed, evaluated, degradable, and human-controllable multi-Agent migration factory.",
        "first": 1413,
        "metrics": {"agentEvalPassRate": ("min", 1.0), "policyViolationCount": ("max", 0.0), "killSwitchPassRate": ("min", 1.0)},
        "slugs": [
            "agent-migration-factory", "agent-team-topology", "migration-planner-agent",
            "deterministic-execution-agent", "language-framework-specialist-agent", "verification-agent",
            "policy-enforcement-agent", "supervisor-coordination-agent", "human-approval-takeover",
            "agent-tool-permissions", "minimal-context-evidence", "agent-memory-state-governance",
            "model-routing-provider-failover", "agent-budget-resource-limits", "agent-eval-benchmark",
            "agent-shadow-canary", "agent-red-team", "agent-incident-killswitch-rollback",
            "recipe-candidate-agent", "agent-autonomy-levels", "multiagent-consensus-arbitration", "agent-factory-gate",
        ],
    },
    43: {
        "title": "Product version compatibility and LTS lifecycle",
        "objective": "Let enterprise customers remain on stable supported versions without following every latest release.",
        "first": 1435,
        "metrics": {"compatibilityMatrixPassRate": ("min", 1.0), "upgradePassRate": ("min", 1.0), "unsupportedBreakingChangeCount": ("max", 0.0)},
        "slugs": [
            "product-lifecycle-factory", "version-specification", "public-api-compatibility",
            "event-schema-compatibility", "sdk-compatibility", "runner-protocol-compatibility",
            "psp-uir-schema-compatibility", "recipe-pack-extension-compatibility", "database-migration-compatibility",
            "release-channel-governance", "support-eol-policy", "deprecation-removal", "customer-upgrade-readiness",
            "automated-upgrade-tooling", "feature-flag-progressive-enable", "rolling-mixed-version-upgrade",
            "security-fix-backport", "compatibility-test-matrix", "release-documentation", "product-lifecycle-gate",
        ],
    },
    44: {
        "title": "FinOps and migration economics optimization",
        "objective": "Measure, price, optimize, reconcile, and sustain profitable verified migration delivery.",
        "first": 1455,
        "metrics": {"meteringReconciliationRate": ("min", 1.0), "budgetGuardrailPassRate": ("min", 1.0), "grossMarginEvidenceCoverageRate": ("min", 0.95)},
        "slugs": [
            "migration-finops-factory", "cost-taxonomy-economic-model", "resource-metering",
            "showback-chargeback", "verified-workload-unit-cost", "runner-fleet-economics", "model-agent-economics",
            "artifact-retention-egress-economics", "human-expert-cost", "support-hypercare-operations-cost",
            "packaging-pricing-model", "assessment-poc-project-quote", "customer-route-edition-margin",
            "budget-quota-cost-guardrail", "cache-incremental-cost-optimization", "provider-resource-routing",
            "cost-scenario-forecast", "customer-roi-tco-value", "usage-billing-reconciliation", "economics-maturity-gate",
        ],
    },
    45: {
        "title": "Mature product comprehensive certification",
        "objective": "Decide whether the platform meets mature enterprise standards across depth, breadth, correctness, scale, security, reliability, maintainability, experience, deployment, ecosystem, economics, and customer outcomes.",
        "first": 1475,
        "metrics": {"maturityDimensionPassRate": ("min", 1.0), "independentReviewPassRate": ("min", 1.0), "unresolvedCriticalRiskCount": ("max", 0.0)},
        "slugs": [
            "mature-product-certification", "maturity-model-editions", "functional-depth-certification",
            "route-breadth-certification", "semantic-behavior-certification", "scale-performance-certification",
            "security-data-certification", "sre-reliability-dr-certification", "target-maintainability-certification",
            "developer-experience-certification", "deployment-matrix-certification", "ecosystem-certification",
            "economics-profitability-certification", "customer-value-certification", "design-partner-reference-validation",
            "independent-expert-validation", "mature-release-readiness", "product-governance-accountability",
            "residual-risk-register", "mature-product-evidence-pack", "edition-route-vertical-certification",
            "mature-product-final-gate",
        ],
    },
}


def authority_section(source: str, batch: int) -> str:
    match = re.search(
        rf"(?ms)^# Batch {batch}：.*?(?=^---\n\n# (?:Batch {batch + 1}：|总体分层关系))",
        source,
    )
    if not match:
        raise ValueError(f"Batch {batch} authority section not found")
    return match.group(0).rstrip() + "\n"


def skill_titles(section: str) -> list[tuple[int, str]]:
    return [(int(skill_id), title.strip()) for skill_id, title in re.findall(r"^Skill (\d+)\s+(.+)$", section, re.MULTILINE)]


def metric_schema(metrics: dict[str, tuple[str, float]]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(metrics),
        "properties": {name: {"type": "number", "minimum": 0} for name in metrics},
    }


def schemas(batch: int, spec: dict) -> dict[str, dict]:
    base = f"https://schemas.elmos.dev/mature-product/batch{batch}"
    program = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{base}/program.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["batch", "packKey", "owner", "scope", "skillIds", "status", "evidenceRefs", "externalOperationExecuted"],
        "properties": {
            "batch": {"const": batch},
            "packKey": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,62}$"},
            "owner": {"type": "string", "minLength": 1},
            "scope": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": True},
            "skillIds": {"type": "array", "items": {"type": "integer", "minimum": spec["first"], "maximum": spec["first"] + len(spec["slugs"]) - 1}, "minItems": 1, "uniqueItems": True},
            "status": {"enum": ["NOT_RUN", "IN_PROGRESS", "BLOCKED", "COMPLETE"]},
            "evidenceRefs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
            "externalOperationExecuted": {"const": False},
        },
    }
    claim = {
        "type": "object",
        "additionalProperties": False,
        "required": ["claimId", "status", "evidenceRefs", "provenanceRefs", "externalOperationExecuted", "authorizationRefs"],
        "properties": {
            "claimId": {"type": "string", "minLength": 1},
            "status": {"enum": ["NOT_RUN", "PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"]},
            "evidenceRefs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
            "provenanceRefs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
            "externalOperationExecuted": {"type": "boolean"},
            "authorizationRefs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
        },
        "allOf": [{"if": {"properties": {"externalOperationExecuted": {"const": True}}}, "then": {"properties": {"authorizationRefs": {"minItems": 1}}}}],
    }
    evidence = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{base}/evidence.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["batch", "packKey", "claims"],
        "properties": {"batch": {"const": batch}, "packKey": {"type": "string", "minLength": 1}, "claims": {"type": "array", "items": claim}},
    }
    certification = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{base}/certification.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["batch", "packKey", "status", "evidenceRefs", "holdoutPassRate", "representativePassRate", "criticalFindings", "metrics"],
        "properties": {
            "batch": {"const": batch}, "packKey": {"type": "string", "minLength": 1},
            "status": {"enum": ["NOT_RUN", "LIMITED", "CERTIFIED", "BLOCKED"]},
            "evidenceRefs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
            "holdoutPassRate": {"type": "number", "minimum": 0, "maximum": 1},
            "representativePassRate": {"type": "number", "minimum": 0, "maximum": 1},
            "criticalFindings": {"type": "integer", "minimum": 0},
            "metrics": metric_schema(spec["metrics"]),
        },
        "allOf": [{"if": {"properties": {"status": {"const": "CERTIFIED"}}}, "then": {"properties": {"evidenceRefs": {"minItems": 1}, "holdoutPassRate": {"const": 1}, "representativePassRate": {"const": 1}, "criticalFindings": {"const": 0}}}}],
    }
    gate = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{base}/gate-result.schema.json",
        "type": "object", "additionalProperties": False,
        "required": ["batch", "packKey", "eligible", "status", "failures", "evidenceRefs", "externalOperationExecuted"],
        "properties": {
            "batch": {"const": batch}, "packKey": {"type": "string", "minLength": 1}, "eligible": {"type": "boolean"},
            "status": {"enum": ["NOT_RUN", "CERTIFIED", "BLOCKED"]},
            "failures": {"type": "array", "items": {"type": "string"}},
            "evidenceRefs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
            "externalOperationExecuted": {"const": False},
        },
    }
    return {"program": program, "evidence": evidence, "certification": certification, "gate-result": gate}


def templates(batch: int, spec: dict) -> dict[str, dict]:
    ids = list(range(spec["first"], spec["first"] + len(spec["slugs"])))
    metrics = {name: 0 for name in spec["metrics"]}
    return {
        "program": {"batch": batch, "packKey": "template-pack", "owner": "template-owner", "scope": ["replace-with-approved-scope"], "skillIds": ids, "status": "NOT_RUN", "evidenceRefs": [], "externalOperationExecuted": False},
        "evidence": {"batch": batch, "packKey": "template-pack", "claims": []},
        "certification": {"batch": batch, "packKey": "template-pack", "status": "NOT_RUN", "evidenceRefs": [], "holdoutPassRate": 0, "representativePassRate": 0, "criticalFindings": 0, "metrics": metrics},
        "gate-result": {"batch": batch, "packKey": "template-pack", "eligible": False, "status": "NOT_RUN", "failures": ["field evidence has not run"], "evidenceRefs": [], "externalOperationExecuted": False},
    }


def skill_text(batch: int, skill_id: int, name: str, title: str, spec: dict) -> str:
    description = (
        f"Implement and verify Batch {batch} Skill {skill_id} for {name.removeprefix(f'b{batch}-').replace('-', ' ')}. "
        f"Use when work requires {title}, typed evidence, negative and holdout validation, and a fail-closed certification decision."
    )
    return f'''---
name: {name}
description: {json.dumps(description)}
---

# {title}

## Operating mode

Work directly in the repository and preserve existing customer, tenant, security, and evidence boundaries. Read the shared Batch {batch} contracts before changing code:

- `../../../docs/batch{batch}/AUTHORITY.md`
- `../../../docs/batch{batch}/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch{batch}/QUALITY_GATES.md`
- `../../../docs/batch{batch}/EVIDENCE_BOUNDARY.md`

Use `python scripts/mature_product_toolkit.py validate --batch {batch}` for structural checks. Use the scaffold and gate commands only against an explicit pack key and approved scope.

## Global constraints

- Bind every conclusion to an exact versioned scope, owner, evidence reference, and provenance reference.
- Keep development, negative, holdout, and representative workloads independent; never tune from holdout outcomes.
- Preserve unknown, unsupported, inaccessible, failed, and over-budget items in denominators and reports.
- Require explicit authorization before any external mutation, deployment, publication, merge, production access, or customer communication.
- Prefer deterministic typed contracts and bounded execution; prohibit unbounded fan-out, silent retries, fabricated evidence, and status-only certification.
- Keep the executor separate from the final certification authority and preserve human ownership of material risk acceptance.
- Stop on critical security, privacy, integrity, tenant-isolation, safety, legal, or evidence-provenance failures.
- Never weaken tests, policies, permissions, baselines, thresholds, or data boundaries merely to make a gate pass.

## Skill {skill_id}: {title}

Implement this capability as part of **{spec['title']}**. The Batch objective is: {spec['objective']}

## Workflow

1. Inspect the current implementation, runtime facts, policies, incidents, decisions, and prior evidence relevant to `{name}`.
2. Freeze an exact scope and identify accountable product, engineering, security, operations, finance, legal, or customer owners as applicable.
3. Create or update the typed program, evidence, and certification artifacts; record known unknowns before implementation.
4. Implement the smallest production-shaped capability that exercises `{title}` without bypassing existing control planes.
5. Run deterministic validation, negative cases, failure injection where safe, and independent holdout or representative workloads.
6. Record outputs, provenance, residual risks, authorization references, costs, and rollback or recovery evidence.
7. Run the Batch {batch} conservative gate and accept only the strongest status supported by actual evidence.

## Required repository outputs

- `mature-product-packs/batch{batch}/<pack-key>/program.json`
- `mature-product-packs/batch{batch}/<pack-key>/evidence.json`
- `mature-product-packs/batch{batch}/<pack-key>/certification.json`
- Capability-specific implementation, tests, run logs, evidence references, and residual-risk records for `{name}`
- `mature-product-packs/batch{batch}/<pack-key>/gate-result.json` and `gate-report.md`

## Verification

- Validate all Batch {batch} Skills, Schemas, templates, and local references.
- Reproduce the claimed capability from immutable inputs and compare outputs and side effects.
- Exercise rejected, unauthorized, degraded, rollback, and recovery paths in addition to the happy path.
- Confirm holdout and representative evidence was not used to tune the implementation or thresholds.
- Confirm every material claim links to raw evidence and an accountable owner.

## Stop and escalate when

- Scope, authority, provenance, required owners, safe test environments, or representative workloads are missing.
- The only available proof is a template, plan, mock, self-attestation, status field, or synthetic happy path.
- A critical regression, policy violation, privacy breach, tenant leak, unsafe external effect, or unrecoverable operation is observed.
- Certification would require hiding failures, excluding difficult scope, broadening permissions, or weakening acceptance criteria.

## Definition of done

The capability has typed artifacts, executable implementation or an explicit `BLOCKED` boundary, deterministic and negative tests, independent evidence, residual-risk ownership, and a conservative Batch {batch} gate result. Unexecuted field evidence remains `NOT_RUN`; no package-level test may be represented as production certification.
'''


def test_text(batch: int, spec: dict) -> str:
    metrics = {name: threshold for name, (_, threshold) in spec["metrics"].items()}
    return f'''from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "mature_product_toolkit.py"
BATCH = {batch}
METRICS = {metrics!r}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=ROOT, text=True, capture_output=True)


class Batch{batch}ToolkitTest(unittest.TestCase):
    def scaffold(self, root: Path) -> Path:
        result = run("scaffold", "--batch", str(BATCH), "--key", "acceptance-pack", "--owner", "test-owner", "--output-root", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return root / f"batch{{BATCH}}" / "acceptance-pack"

    def test_bundle(self) -> None:
        result = run("validate", "--batch", str(BATCH))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            self.assertTrue((pack / "program.json").is_file())
            self.assertEqual("NOT_RUN", json.loads((pack / "certification.json").read_text())["status"])

    def test_fake_certification_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            certification = json.loads((pack / "certification.json").read_text())
            certification["status"] = "CERTIFIED"
            (pack / "certification.json").write_text(json.dumps(certification))
            result = run("gate", "--batch", str(BATCH), str(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("BLOCKED", result.stdout)

    def test_unauthorized_external_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            certification = json.loads((pack / "certification.json").read_text())
            certification.update({{"status": "CERTIFIED", "evidenceRefs": ["evidence://test"], "holdoutPassRate": 1, "representativePassRate": 1, "criticalFindings": 0, "metrics": METRICS}})
            (pack / "certification.json").write_text(json.dumps(certification))
            evidence = {{"batch": BATCH, "packKey": "acceptance-pack", "claims": [{{"claimId": "external", "status": "PASS", "evidenceRefs": ["evidence://external"], "provenanceRefs": ["run://1"], "externalOperationExecuted": True, "authorizationRefs": []}}]}}
            (pack / "evidence.json").write_text(json.dumps(evidence))
            result = run("gate", "--batch", str(BATCH), str(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("authorizationRefs", result.stdout)


if __name__ == "__main__":
    unittest.main()
'''


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    created = 0
    for batch, spec in BATCHES.items():
        section = authority_section(source, batch)
        titles = skill_titles(section)
        if len(titles) != len(spec["slugs"]):
            raise ValueError(f"Batch {batch}: {len(titles)} titles but {len(spec['slugs'])} slugs")
        expected_ids = list(range(spec["first"], spec["first"] + len(spec["slugs"])))
        if [skill_id for skill_id, _ in titles] != expected_ids:
            raise ValueError(f"Batch {batch}: non-contiguous authority IDs")

        docs = ROOT / "docs" / f"batch{batch}"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "AUTHORITY.md").write_text(section, encoding="utf-8")
        (docs / "IMPLEMENTATION_CONTRACT.md").write_text(
            f"# Batch {batch} implementation contract\n\n## Objective\n\n{spec['objective']}\n\n"
            "## Required artifacts\n\nKeep one exact owner, scope, versioned program, evidence manifest, certification record, holdout corpus, representative workload, residual-risk register, and gate result per pack.\n\n"
            "## Execution discipline\n\nUse typed bounded work, immutable inputs, idempotency or compensation, explicit authorization for external effects, and replayable evidence. Keep execution and certification authority separate.\n",
            encoding="utf-8",
        )
        metric_lines = "\n".join(f"- `{name}` must satisfy `{op} {value}`." for name, (op, value) in spec["metrics"].items())
        (docs / "QUALITY_GATES.md").write_text(
            f"# Batch {batch} quality gates\n\nCertification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:\n\n{metric_lines}\n\nStatus-only certification and unauthorized external evidence must be rejected.\n",
            encoding="utf-8",
        )
        (docs / "EVIDENCE_BOUNDARY.md").write_text(
            f"# Batch {batch} evidence boundary\n\nPackage structure, Schemas, templates, unit tests, or generated reports do not prove field operation. Keep field claims `NOT_RUN` until raw evidence, provenance, exact environment, owner, authorization, holdout, representative workload, rollback or recovery, and the Batch {batch} gate support them.\n",
            encoding="utf-8",
        )

        for name, schema in schemas(batch, spec).items():
            write_json(ROOT / "schemas" / f"batch{batch}" / f"{name}.schema.json", schema)
        for name, template in templates(batch, spec).items():
            write_json(ROOT / "templates" / f"batch{batch}" / f"{name}.json", template)

        tests = ROOT / "tests" / f"batch{batch}"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "test_toolkit.py").write_text(test_text(batch, spec), encoding="utf-8")
        (ROOT / f"Makefile.batch{batch}").write_text(
            f"BATCH{batch}_PYTHON ?= /opt/homebrew/bin/uv run --quiet --with jsonschema --with pyyaml python\n\n"
            f".PHONY: batch{batch}-check batch{batch}-scaffold batch{batch}-gate\n\n"
            f"batch{batch}-check:\n\t$(BATCH{batch}_PYTHON) scripts/mature_product_toolkit.py validate --batch {batch}\n\t$(BATCH{batch}_PYTHON) -m unittest discover -s tests/batch{batch} -p 'test_*.py'\n\n"
            f"batch{batch}-scaffold:\n\t@test -n \"$(PACK)\" || (echo \"PACK=<pack-key> required\" && exit 2)\n\t@test -n \"$(OWNER)\" || (echo \"OWNER=<owner> required\" && exit 2)\n\t$(BATCH{batch}_PYTHON) scripts/mature_product_toolkit.py scaffold --batch {batch} --key $(PACK) --owner $(OWNER)\n\n"
            f"batch{batch}-gate:\n\t@test -n \"$(PACK)\" || (echo \"PACK=<pack-key> required\" && exit 2)\n\t$(BATCH{batch}_PYTHON) scripts/mature_product_toolkit.py gate --batch {batch} mature-product-packs/batch{batch}/$(PACK)\n",
            encoding="utf-8",
        )

        for (skill_id, title), slug in zip(titles, spec["slugs"], strict=True):
            name = f"b{batch}-{slug}"
            directory = SKILL_ROOT / name
            if not directory.exists():
                display = f"Batch {batch}: {slug.replace('-', ' ').title()}"
                short = f"Run evidence-bound Batch {batch} {slug.replace('-', ' ')} work"
                if len(short) > 64:
                    short = short[:64].rstrip()
                subprocess.run(
                    [
                        sys.executable, str(INIT_SKILL), name, "--path", str(SKILL_ROOT),
                        "--interface", f"display_name={display}",
                        "--interface", f"short_description={short}",
                        "--interface", f"default_prompt=Use ${name} to implement and verify this capability with fail-closed evidence.",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                created += 1
            (directory / "SKILL.md").write_text(skill_text(batch, skill_id, name, title, spec), encoding="utf-8")
    print(f"generated_batches={len(BATCHES)} initialized_skills={created} total_skills={sum(len(spec['slugs']) for spec in BATCHES.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
