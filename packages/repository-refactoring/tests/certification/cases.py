"""The Golden-corpus fixture repositories.

The set is chosen to cover the behaviours that a plausible-but-wrong
implementation gets wrong: a cross-file rename that must follow importers, a
contract change whose direction depends on what it breaks, a gate with no
evidence behind it, a schema migration that must stay expand-contract, and an
undecidable input that must *not* resolve to a decision.
"""

from __future__ import annotations

from typing import Any

from .corpus import CorpusCase

_BILLING = {
    "pyproject.toml": '[project]\nname = "acme-billing"\nversion = "1.0.0"\nrequires-python = ">=3.11"\n',
    "src/acme/__init__.py": "",
    "src/acme/billing.py": (
        "from decimal import Decimal\n"
        "\n"
        "from acme.ledger import post_entry\n"
        "\n"
        "DEFAULT_CURRENCY = 'USD'\n"
        "\n"
        "\n"
        "class BillingService:\n"
        "    def __init__(self, ledger):\n"
        "        self._ledger = ledger\n"
        "\n"
        "    def charge(self, customer_id: str, amount: Decimal, *, currency: str = DEFAULT_CURRENCY) -> str:\n"
        "        entry = post_entry(customer_id, amount, currency)\n"
        "        return entry\n"
    ),
    "src/acme/ledger.py": (
        "from decimal import Decimal\n"
        "\n"
        "\n"
        "def post_entry(customer_id: str, amount: Decimal, currency: str) -> str:\n"
        "    return f'{customer_id}:{amount}:{currency}'\n"
        "\n"
        "\n"
        "def reverse_entry(entry: str) -> str:\n"
        "    return entry\n"
    ),
    "src/acme/api.py": (
        "from acme.ledger import post_entry\n"
        "\n"
        "\n"
        "def handle(customer_id, amount, currency):\n"
        "    return post_entry(customer_id, amount, currency)\n"
    ),
    "tests/test_billing.py": (
        "from acme.ledger import post_entry\n"
        "\n"
        "\n"
        "def test_post_entry():\n"
        "    assert post_entry('c1', 1, 'USD') == 'c1:1:USD'\n"
    ),
    "contracts/billing.proto": (
        'syntax = "proto3";\n'
        "package acme.billing.v1;\n"
        "\n"
        "message ChargeCreated {\n"
        "  string id = 1;\n"
        "  string currency = 2;\n"
        "}\n"
    ),
    "db/migrations/001_init.sql": (
        "CREATE TABLE public.users (\n"
        "    id bigint NOT NULL,\n"
        "    legacy_name character varying(255) NOT NULL,\n"
        "    created_at timestamp with time zone\n"
        ");\n"
    ),
    "CODEOWNERS": "*  @acme/platform\n/src/acme/  @acme/payments\n",
}

_RENAME_REQUEST = {
    "apiVersion": "elmos.dev/v1",
    "kind": "RefactorRequest",
    "metadata": {"tenantId": "acme", "projectId": "billing-platform"},
    "spec": {
        "repositories": [
            {"uri": "git@example.com/acme/billing.git", "revision": "c0de" * 10, "role": "primary"}
        ],
        "intent": {
            "type": "structural-refactor",
            "goals": ["rename post_entry to record_entry"],
            "nonGoals": ["do not change the public REST contract"],
            "acceptanceCriteria": ["all existing tests pass"],
        },
        "constraints": {
            "behaviorCompatibility": "strict",
            "publicApiCompatibility": "backward-compatible",
            "maximumChangedFiles": 200,
        },
        "execution": {"mode": "supervised", "createPullRequest": True, "maxParallelShards": 4},
    },
}

_SERVICES = {
    "services/billing/client.py": (
        "import requests\n"
        "\n"
        "\n"
        "def charge(customer_id):\n"
        "    return requests.post('http://ledger/charge', json={'id': customer_id})\n"
        "\n"
        "\n"
        "def publish(event):\n"
        "    kafka.publish('charge.created', event)\n"
        "\n"
        "\n"
        "def read():\n"
        "    return db.execute('SELECT * FROM public.ledger_entries')\n"
    ),
    "services/ledger/handler.py": (
        "@KafkaListener\n"
        "def on_message(message):\n"
        "    consume('charge.created')\n"
        "\n"
        "\n"
        "def write(entry):\n"
        "    db.execute('INSERT INTO public.ledger_entries VALUES (1)')\n"
    ),
}

_CLIENT = {
    "src/Cart.tsx": (
        "import React, {useState} from 'react';\n"
        "export function Cart() {\n"
        "  const [n, setN] = useState(0);\n"
        "  localStorage.setItem('cart', String(n));\n"
        "  document.getElementById('total');\n"
        "  track('cart_viewed', {n});\n"
        "  return <div><img src='a.png'/></div>;\n"
        "}\n"
    ),
    "src/routes.ts": "export const routes = [{path: '/cart'}, {path: '/checkout/:id'}];\n",
}

#: An intentionally *undecidable* repository: the only source file cannot be
#: decoded, so nothing about it may be reported as safe.
_UNREADABLE = {
    "README.md": "# corpus\n",
}

CASES: tuple[CorpusCase, ...] = (
    CorpusCase(
        case_id="01-discovery-billing",
        skill="repository-discovery",
        description="Language, build, ownership and sensitive-area inventory of a small polyglot repo.",
        files=_BILLING,
        projections=(
            "output.language_inventory.languages",
            "output.repository_inventory.coverage",
            "output.repository_inventory.buildSystems",
            "output.repository_inventory.testPaths",
            "output.repository_inventory.ownership",
        ),
    ),
    CorpusCase(
        case_id="02-semantic-index-billing",
        skill="semantic-index",
        description="Exact Python extraction plus contract entities; coverage must account for what was not read.",
        files=_BILLING,
        projections=(
            "output.coverage_metrics",
            "output.unknown_region_report",
            "output.semantic_index_snapshot.snapshotId",
            "output.semantic_index_snapshot.coverage",
        ),
    ),
    CorpusCase(
        case_id="03-impact-of-rename",
        skill="change-impact-analysis",
        description="Closure of a cross-file rename, including the importer and the test.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "output.risk_assessment.riskClass",
            "output.risk_assessment.unknownPenalty",
            "output.wave_plan",
            "output.test_selection_plan",
        ),
    ),
    CorpusCase(
        case_id="04-transform-cross-file-rename",
        skill="deterministic-transform-executor",
        description="The proof case: a scope-correct rename that follows importers and is idempotent.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.transformEvidence.idempotent",
            "output.transformEvidence.changedPaths",
            "output.transformEvidence.scopeExpansions",
            "output.transformEvidence.roundTripFailures",
            "output.patchSet.changedFiles",
            "output.patchSet.changedLines",
            "output.changedSymbolSet",
            "output.unifiedDiff",
        ),
    ),
    CorpusCase(
        case_id="05-verification-without-executor",
        skill="test-and-verification",
        description="Every executed gate must be undecided-and-failing when no executor supplied evidence.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.validation_report.passed",
            "output.validation_report.undecidedBlockingGates",
            "output.validation_report.blockingFailures",
            "output.validation_report.gateDecisions",
        ),
    ),
    CorpusCase(
        case_id="06-schema-expand-contract",
        skill="data-schema-refactor",
        description="An online column rename must stay expand / index / backfill / contract.",
        files=_BILLING,
        payload_extra={
            "request": _RENAME_REQUEST,
            "table": "public.users",
            "old_column": "legacy_name",
            "new_column": "display_name",
        },
        projections=(
            "output.phases",
            "output.phaseOrder",
            "output.executable",
            "output.files[3].destructive",
            "output.backfill.resumable",
        ),
    ),
    CorpusCase(
        case_id="07-contract-wire-break",
        skill="cross-language-contract-refactor",
        description=(
            "A renumbered proto field is a wire break: consumers first, and blocked "
            "under a backward-compatible policy."
        ),
        files=_BILLING,
        payload_extra={
            "request": _RENAME_REQUEST,
            "candidate_workspace": {
                "source": "inline",
                "repository_id": "corpus",
                "revision": "c0de" * 10,
                "files": [
                    {"path": path, "content": content if path != "contracts/billing.proto"
                     else content.replace("string currency = 2;", "string currency = 4;")}
                    for path, content in sorted(_BILLING.items())
                ],
            },
        },
        projections=(
            "status",
            "output.contractMigrationPlan.order",
            "output.contractMigrationPlan.riskClass",
            "output.contractMigrationPlan.blockedReason",
            "output.contractDiff.counts",
        ),
    ),
    CorpusCase(
        case_id="08-distributed-shared-datastore",
        skill="distributed-system-refactor",
        description="Two services reaching the same table is coupling, and it forbids a distributed transaction.",
        files=_SERVICES,
        payload_extra={"request": _RENAME_REQUEST, "target_service": "ledger"},
        projections=(
            "status",
            "output.writePattern",
            "output.sharedDatastores",
            "output.hotPathKnowledge",
            "output.callPolicyFindings",
        ),
    ),
    CorpusCase(
        case_id="09-client-platform-gap",
        skill="ui-and-client-refactor",
        description="DOM use is a hard gap on a miniprogram target, and a visual result with no renderer is not-run.",
        files=_CLIENT,
        payload_extra={
            "request": _RENAME_REQUEST,
            "target_platforms": ["web", "wechat-miniprogram"],
        },
        projections=(
            "status",
            "output.platformCompatibilityMatrix",
            "output.visualDiff",
            "output.sensitiveSurfaces",
        ),
    ),
    CorpusCase(
        case_id="10-empty-repository-is-undecided",
        skill="semantic-index",
        description="A repository with no code must report low coverage, not a confident empty index.",
        files=_UNREADABLE,
        projections=(
            "output.coverage_metrics",
            "output.unknown_region_report",
        ),
    ),
)


def _recorded_successes(case: CorpusCase) -> list[dict[str, Any]]:
    """Recordings for every command this case's run would actually issue.

    Derived from the case rather than hand-written: a hard-coded list would
    drift the moment a gate's command changed, and the corpus would then be
    recording the behaviour of a run whose evidence no longer matched.
    """

    from elmos_repository_refactoring.buildgraph import baseline_requests, build_graph
    from elmos_repository_refactoring.discovery import discover
    from elmos_repository_refactoring.verification import EXECUTED_GATES, plan_executions
    from elmos_repository_refactoring.workspace import WorkspaceSnapshot

    snapshot = WorkspaceSnapshot.from_payload(case.workspace)
    inventory = discover(snapshot)
    graph = build_graph(snapshot, inventory)
    languages = [item.language for item in inventory.languages if item.language != "unknown"][:6]
    requests = [*plan_executions(list(EXECUTED_GATES), languages), *baseline_requests(graph)]
    #: Content-addressed: two gates that issue the same command share one
    #: recording, and supplying it twice would be a duplicate the executor
    #: rejects.
    unique: dict[str, str] = {}
    for request in requests:
        unique.setdefault(request.digest, request.request_id)
    return [
        {
            "requestId": request_id,
            "requestDigest": digest,
            "status": "completed",
            "exitCode": 0,
            "durationMs": 10,
        }
        for digest, request_id in sorted(unique.items())
    ]


_PORTFOLIO = [
    {"repositoryId": "billing-api", "role": "provider", "owners": ["@acme/payments"]},
    {"repositoryId": "web", "role": "consumer", "owners": ["@acme/web"], "dependsOn": ["billing-api"]},
    {
        "repositoryId": "billing-sdk-go",
        "role": "generated-client",
        "dependsOn": ["billing-api"],
    },
    {
        "repositoryId": "partner-portal",
        "role": "consumer",
        "external": True,
        "dependsOn": ["billing-api"],
    },
]

_ENVIRONMENT = {
    "cpuModel": "m7i.2xlarge",
    "cpuCount": 8,
    "memoryMb": 16384,
    "containerImage": "sha256:" + "b" * 64,
    "datasetId": "corpus-ds-1",
    "warmupIterations": 3,
    "concurrency": 16,
}


def _samples(metric: str, values: list[int]) -> dict[str, Any]:
    return {
        "metric": metric,
        "workload": "component",
        "unit": "ms",
        "values": values,
        "environment": _ENVIRONMENT,
    }


REMAINING_CASES: tuple[CorpusCase, ...] = (
    CorpusCase(
        case_id="11-orchestrator-plan",
        skill="repository-refactor-orchestrator",
        description="Phase DAG synthesis, approval gates derived from policy, and an ETA distribution.",
        files={},
        include_workspace=False,
        payload_extra={"request": _RENAME_REQUEST, "run_id": "run-corpus-1", "action": "plan"},
        projections=(
            "status",
            "output.plan.steps",
            "output.plan.approvalGates",
            "output.plan.estimated",
            "output.plan.riskSummary",
            "output.criticalPath",
        ),
    ),
    CorpusCase(
        case_id="12-build-graph-no-executor",
        skill="build-graph-and-environment",
        description="Toolchain lock and sandbox spec; the baseline is not-run and therefore untrustworthy.",
        files=_BILLING,
        projections=(
            "status",
            "output.baseline_report.status",
            "output.baseline_report.trustworthy",
            "output.baseline_report.buildOk",
            "output.toolchain_lock.reproducible",
            "output.toolchain_lock.unpinned",
            "output.sandbox_image_spec.network",
        ),
    ),
    CorpusCase(
        case_id="13-intent-compiler",
        skill="refactor-intent-compiler",
        description="Goal classification, acceptance predicates, and the minimal conflict set.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.compiled_intent",
        ),
    ),
    CorpusCase(
        case_id="14-recipe-synthesis",
        skill="recipe-synthesis",
        description="Recipe selection by language and measured adapter level, with a recipes.lock.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.recipeSet",
            "output.recipeLock.recipes",
            "output.conflicts",
            "output.unmatchedOperations",
            "output.recipeTestReport",
        ),
    ),
    CorpusCase(
        case_id="15-api-compatibility-removal",
        skill="api-compatibility",
        description="Removing a public function is a break, and no in-repository silence makes it safe.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.compatibilityDecision",
            "output.apiDiff.counts",
            "output.deprecationPlan",
        ),
    ),
    CorpusCase(
        case_id="16-auto-repair-nothing-to-repair",
        skill="bounded-auto-repair",
        description="With no failure signature there is nothing to repair; it must not invent work.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.repairAttemptRecords",
            "output.unresolvedFailureReport",
        ),
    ),
    CorpusCase(
        case_id="17-approval-gate-unapproved",
        skill="human-approval-gate",
        description="Zero approvers is a refusal, and the request binds four digests.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.approval_decision",
            "output.approval_request.requiredRoles",
            "output.approval_request.minimumApprovers",
            "output.approval_request.forbidSelfApproval",
            "output.approval_request.boundDigests",
        ),
    ),
    CorpusCase(
        case_id="18-canary-without-rollback-proof",
        skill="canary-rollout",
        description="A canary that cannot be reversed is a deployment; it must block.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.rolloutPlan.startable",
            "output.rolloutPlan.blockedReason",
            "output.rolloutPlan.rollbackVerified",
            "output.rolloutPlan.stages",
            "output.changesets",
        ),
    ),
    CorpusCase(
        case_id="19-rollback-plan",
        skill="rollback-and-recovery",
        description="Source rolls back by inverted patch; external effects compensate in reverse order.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.incidentReport.rollbackPlan",
            "output.incidentReport.failureBoundary",
            "output.incidentReport.preservedEvidence",
            "output.rollbackExecution",
        ),
    ),
    CorpusCase(
        case_id="20-evidence-bundle-failed-run",
        skill="evidence-and-audit",
        description="A bundle for a run that did not pass must say so, not present itself as a pass.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=(
            "status",
            "output.evidence_bundle.incompleteReasons",
            "output.evidence_bundle.gateDecisions",
            "output.signed_manifest.signed",
            "output.signed_manifest.verification",
        ),
    ),
    CorpusCase(
        case_id="21-registry-promotion-refused",
        skill="recipe-learning-registry",
        description="One evaluation on one repository does not promote; every unmet condition is reported.",
        files={},
        include_workspace=False,
        payload_extra={"query": {"language": "python"}},
        projections=("status", "output.recipes", "output.revocationList", "output.promotionDecisions"),
    ),
    CorpusCase(
        case_id="22-performance-guardrail-regression",
        skill="performance-preservation",
        description="A quiet metric regresses; a noisy one with the same delta does not.",
        files={},
        include_workspace=False,
        payload_extra={
            "baseline_samples": [
                _samples("latency_ms", [100, 101, 99, 100, 102, 98, 101]),
                _samples("noisy_ms", [100, 140, 60, 120, 80, 130, 70]),
            ],
            "candidate_samples": [
                _samples("latency_ms", [112, 113, 111, 112, 114, 110, 113]),
                _samples("noisy_ms", [112, 150, 66, 128, 88, 140, 74]),
            ],
            "guardrails": [
                {"metric": "latency_ms", "maxRegression": "0.05"},
                {"metric": "noisy_ms", "maxRegression": "0.05"},
            ],
            "profile_before": {"acme.ledger.post_entry": 5},
            "profile_after": {"acme.ledger.post_entry": 30, "acme.api.handle": 7},
        },
        projections=("status", "output.performanceDiff", "output.guardrailDecision", "output.regressionSuspects"),
    ),
    CorpusCase(
        case_id="23-security-scan-not-run",
        skill="security-preservation",
        description="An unexecuted scan is undecided, and this gate treats undecided as failing.",
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        projections=("status", "output.scanStatus", "output.allowed", "output.securityDiff"),
    ),
    CorpusCase(
        case_id="24-program-cleanup-blocked",
        skill="multi-repository-refactor-program",
        description="The cleanup wave blocks while an external consumer has not adopted.",
        files={},
        include_workspace=False,
        payload_extra={
            "program_id": "prog-corpus-1",
            "portfolio": _PORTFOLIO,
            "consumer_first": True,
            "start_wave": "wave-3-cleanup",
        },
        projections=("status", "output.startGate", "output.adoption.stuckConsumers", "output.plan.waves"),
    ),
    CorpusCase(
        case_id="25-verification-with-recorded-evidence",
        skill="test-and-verification",
        description=(
            "The other half of case 05: with real recorded evidence the mechanical gates pass, "
            "and only genuinely undecided ones remain."
        ),
        files=_BILLING,
        payload_extra={"request": _RENAME_REQUEST},
        executions=_recorded_successes,
        projections=(
            "status",
            "output.validation_report.passed",
            "output.validation_report.undecidedBlockingGates",
            "output.validation_report.blockingFailures",
            "output.validation_report.gateDecisions",
        ),
    ),
)

CASES = (*CASES, *REMAINING_CASES)
