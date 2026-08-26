"""Batch-4 acceptance: Skills 08, 09, 10, 16, 18, 19, 21 and 22.

Each test here asserts a behaviour the honest version of the Skill must have
and a plausible-but-wrong implementation would not.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from elmos_repository_refactoring import (
    apicompat,
    client,
    contractsmig,
    distributed,
    performance,
    program,
    registry,
    security,
    sqlops,
)
from elmos_repository_refactoring.buildgraph import build_graph
from elmos_repository_refactoring.contracts import ContractError, RecipeStatus, RiskClass
from elmos_repository_refactoring.discovery import discover
from elmos_repository_refactoring.index import build_index
from elmos_repository_refactoring.patch import diff_snapshots
from elmos_repository_refactoring.runtime import dispatch
from elmos_repository_refactoring.sandbox import ExecutionStatus
from elmos_repository_refactoring.synthesis import BUILTIN_RECIPES
from elmos_repository_refactoring.workspace import WorkspaceSnapshot

from .fixtures import PROTO, request_payload, workspace_payload


def _snapshot(files: dict[str, str]) -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_payload(
        {
            "source": "inline",
            "repository_id": "acme",
            "revision": "a" * 40,
            "files": [{"path": key, "content": value} for key, value in sorted(files.items())],
        }
    )


@pytest.fixture()
def fixture_snapshot() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_payload(workspace_payload())


# ---------------------------------------------------------------------------
# Skill 08 — cross-language contract evolution
# ---------------------------------------------------------------------------


class TestContractMigration:
    def test_wire_break_puts_consumers_first(self) -> None:
        before = apicompat.extract_wire_surface({"c.proto": PROTO})
        after = apicompat.extract_wire_surface(
            {"c.proto": PROTO.replace("string currency = 2;", "string currency = 4;")}
        )
        order, reason = contractsmig.choose_order(apicompat.diff_surfaces(before, after))
        assert order is contractsmig.MigrationOrder.CONSUMER_FIRST
        assert "absorbed by consumers" in reason

    def test_source_break_puts_provider_first(self) -> None:
        diff = apicompat.ApiDiff(
            changes=(
                apicompat.ApiChange(
                    identity="m.f",
                    change="removed",
                    impact=apicompat.CompatibilityImpact.SOURCE_BREAK,
                    detail="",
                ),
            )
        )
        order, _ = contractsmig.choose_order(diff)
        assert order is contractsmig.MigrationOrder.PROVIDER_FIRST

    def test_additive_change_needs_no_ordering(self) -> None:
        diff = apicompat.ApiDiff(
            changes=(
                apicompat.ApiChange(
                    identity="m.g",
                    change="added",
                    impact=apicompat.CompatibilityImpact.ADDITIVE,
                    detail="",
                ),
            )
        )
        order, _ = contractsmig.choose_order(diff)
        assert order is contractsmig.MigrationOrder.SIMULTANEOUS

    def test_contract_with_no_visible_consumer_raises_risk(
        self, fixture_snapshot: WorkspaceSnapshot
    ) -> None:
        inventory = discover(fixture_snapshot)
        index = build_index(fixture_snapshot, inventory, build_graph(fixture_snapshot, inventory))
        sources = contractsmig.find_sources(fixture_snapshot)
        consumers = contractsmig.find_consumers(index, fixture_snapshot, sources)
        invisible = [item for item in consumers if not item.visible]
        assert invisible, "a contract nothing in-repository consumes must be reported, not ignored"
        assert all(item.role == "external" for item in invisible)

    def test_cleanup_wave_is_gated_on_zero_old_path_usage(
        self, fixture_snapshot: WorkspaceSnapshot
    ) -> None:
        inventory = discover(fixture_snapshot)
        index = build_index(fixture_snapshot, inventory, build_graph(fixture_snapshot, inventory))
        before = apicompat.extract_wire_surface(
            {record.path: record.text or "" for record in fixture_snapshot}
        )
        after = apicompat.extract_wire_surface({"contracts/billing.proto": PROTO.replace("= 2;", "= 4;")})
        plan = contractsmig.plan_contract_migration(
            fixture_snapshot, index, apicompat.diff_surfaces(before, after)
        )
        cleanup = [wave for wave in plan.waves if wave.wave_id.endswith("cleanup")]
        assert cleanup and cleanup[0].gate == "old-path-usage-zero"


# ---------------------------------------------------------------------------
# Skill 09 — data schema refactor
# ---------------------------------------------------------------------------


SCHEMA = """
CREATE TABLE public.users (
    id bigint NOT NULL,
    legacy_name character varying(255) NOT NULL,
    created_at timestamp with time zone
);
"""


class TestSchemaRefactor:
    def test_rename_is_expand_backfill_contract(self) -> None:
        table = sqlops.parse_schema(SCHEMA)[0]
        plan = sqlops.plan_column_rename(
            table, old_column="legacy_name", new_column="display_name"
        )
        assert plan.phases == ("expand", "expand", "backfill", "contract")
        assert sqlops.check_phase_order(plan.files).ordered
        destructive = [item for item in plan.files if item.destructive]
        assert [item.phase for item in destructive] == ["contract"]

    def test_not_null_is_parsed_not_swallowed_by_the_type(self) -> None:
        table = sqlops.parse_schema(SCHEMA)[0]
        assert table.column("legacy_name") is not None
        assert table.column("legacy_name").nullable is False
        assert table.column("created_at").nullable is True

    def test_identifier_injection_is_refused(self) -> None:
        table = sqlops.parse_schema(SCHEMA)[0]
        with pytest.raises(ContractError) as error:
            sqlops.plan_column_rename(
                table, old_column="legacy_name", new_column="x; DROP TABLE users; --"
            )
        assert error.value.code == "invalid_sql_identifier"

    def test_missing_column_blocks_rather_than_generating_sql(self) -> None:
        table = sqlops.parse_schema(SCHEMA)[0]
        plan = sqlops.plan_column_rename(table, old_column="nope", new_column="display_name")
        assert not plan.executable
        assert plan.files == ()

    def test_dispatcher_refuses_to_infer_the_migration(self) -> None:
        result = dispatch(
            "data-schema-refactor",
            {"workspace": workspace_payload(), "request": request_payload()},
        )
        assert result["status"] == "blocked"
        assert "required" in result["reasons"][0]


# ---------------------------------------------------------------------------
# Skill 10 — distributed system refactor
# ---------------------------------------------------------------------------


DISTRIBUTED_FILES = {
    "services/billing/client.py": (
        "import requests\n"
        "def charge(cid):\n"
        "    return requests.post('http://ledger/charge', json={'id': cid})\n"
        "\n"
        "def notify(cid):\n"
        "    for _ in range(3):\n"
        "        retry = True\n"
        "        requests.post('http://ledger/notify', timeout=2)\n"
        "\n"
        "def publish(event):\n"
        "    kafka.publish('charge.created', event)\n"
        "\n"
        "def read():\n"
        "    return db.execute('SELECT * FROM public.ledger_entries')\n"
    ),
    "services/ledger/handler.py": (
        "@KafkaListener\n"
        "def on_message(message):\n"
        "    consume('charge.created')\n"
        "def write(entry):\n"
        "    db.execute('INSERT INTO public.ledger_entries VALUES (1)')\n"
    ),
}


class TestDistributed:
    def test_shared_table_is_coupling_even_when_undeclared(self) -> None:
        snapshot = _snapshot(DISTRIBUTED_FILES)
        services = distributed.discover_services(snapshot)
        shared = distributed.shared_datastores(snapshot, services)
        assert [item["table"] for item in shared] == ["public.ledger_entries"]

    def test_shared_data_forbids_a_distributed_transaction(self) -> None:
        snapshot = _snapshot(DISTRIBUTED_FILES)
        services = distributed.discover_services(snapshot)
        edges = distributed.build_service_graph(snapshot, services)
        shared = distributed.shared_datastores(snapshot, services)
        pattern, reason = distributed.choose_write_pattern(edges, shared)
        assert pattern is distributed.WritePattern.LOCAL_TRANSACTION
        assert "resolved before any distributed pattern" in reason

    def test_retry_findings_do_not_leak_from_the_next_function(self) -> None:
        """The window is the enclosing block, not a fixed line count."""

        findings = distributed.audit_call_policies(_snapshot(DISTRIBUTED_FILES))
        by_line = {(item.line, item.control) for item in findings}
        #: line 3 has no retry at all: only the missing timeout is reported.
        assert (3, "timeout") in by_line
        assert (3, "retry-bound") not in by_line
        #: line 8 has a bounded loop and a timeout, so only backoff and
        #: idempotency are missing.
        assert (8, "retry-bound") not in by_line
        assert (8, "retry-backoff") in by_line
        assert (8, "retry-idempotency") in by_line

    def test_hot_path_is_unknown_without_traces(self) -> None:
        snapshot = _snapshot(DISTRIBUTED_FILES)
        services = distributed.discover_services(snapshot)
        edges = distributed.build_service_graph(snapshot, services)
        assert edges
        assert all(edge.observed_calls is None for edge in edges)
        payload = edges[0].to_payload()
        assert payload["hot"] is None

    def test_async_edges_get_duplicate_and_replay_tests(self) -> None:
        snapshot = _snapshot(DISTRIBUTED_FILES)
        services = distributed.discover_services(snapshot)
        edges = distributed.build_service_graph(snapshot, services)
        names = {item.name.split(":", 1)[0] for item in distributed.resilience_matrix(edges)}
        assert {"duplicate", "reorder", "replay"} <= names
        assert all(
            item.decidable_offline is False for item in distributed.resilience_matrix(edges)
        )

    def test_undeclared_services_are_flagged_as_a_guess(self) -> None:
        snapshot = _snapshot(DISTRIBUTED_FILES)
        index = build_index(snapshot, discover(snapshot), build_graph(snapshot, discover(snapshot)))
        plan = distributed.plan_distributed_refactor(snapshot, index, target="ledger")
        assert any("inferred from directory layout" in reason for reason in plan.reasons)
        assert any("no runtime traces" in reason for reason in plan.reasons)


# ---------------------------------------------------------------------------
# Skill 16 — Recipe registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def _registry(self) -> tuple[registry.RecipeRegistry, str]:
        store = registry.RecipeRegistry()
        recipe = next(iter(BUILTIN_RECIPES.values()))
        entry = store.register(recipe, owners=("@acme/platform",))
        return store, entry.digest

    def test_one_success_does_not_certify(self) -> None:
        store, digest = self._registry()
        store.record_evaluation(
            digest,
            registry.EvaluationReport(
                recipe_reference="r",
                recipe_digest=digest,
                corpus_digest="sha256:" + "0" * 64,
                true_positives=50,
                false_positives=0,
                false_negatives=0,
                escape_defects=0,
                idempotent=True,
                repositories=("only-one",),
                adversarial_fixtures=3,
            ),
        )
        store.sign(digest, subject="alice", role="owner")
        store.promote(digest, RecipeStatus.QUARANTINED)
        decision = store.promote(digest, RecipeStatus.VERIFIED)
        assert not decision.granted
        assert any("distinct repository" in item for item in decision.unmet)

    def test_one_escape_defect_blocks_regardless_of_precision(self) -> None:
        store, digest = self._registry()
        store.record_evaluation(
            digest,
            registry.EvaluationReport(
                recipe_reference="r",
                recipe_digest=digest,
                corpus_digest="sha256:" + "0" * 64,
                true_positives=10_000,
                false_positives=0,
                false_negatives=0,
                escape_defects=1,
                idempotent=True,
                repositories=("a", "b", "c", "d"),
                adversarial_fixtures=9,
            ),
        )
        store.sign(digest, subject="alice", role="owner")
        #: An escape defect blocks the *first* rung, not just the last one:
        #: a Recipe that edits outside its declared scope is not merely
        #: imprecise, and no success rate compensates for it.
        decision = store.promote(digest, RecipeStatus.QUARANTINED)
        assert not decision.granted
        assert any("escape defect" in item for item in decision.unmet)
        #: And because promotion was refused, the ladder cannot be skipped.
        skipped = store.promote(digest, RecipeStatus.VERIFIED)
        assert not skipped.granted
        assert any("not a legal transition" in item for item in skipped.unmet)

    def test_precision_is_undefined_not_perfect_when_nothing_fired(self) -> None:
        report = registry.EvaluationReport(
            recipe_reference="r",
            recipe_digest="sha256:" + "0" * 64,
            corpus_digest="sha256:" + "0" * 64,
            true_positives=0,
            false_positives=0,
            false_negatives=0,
            escape_defects=0,
            idempotent=True,
            repositories=(),
            adversarial_fixtures=0,
        )
        assert report.precision is None
        assert report.recall is None

    def test_editing_a_recipe_needs_a_new_version(self) -> None:
        store, _ = self._registry()
        recipe = next(iter(BUILTIN_RECIPES.values()))
        with pytest.raises(ContractError) as error:
            store.register(recipe)
        assert error.value.code == "recipe_already_registered"

    def test_revocation_names_the_runs_that_already_applied_it(self) -> None:
        store, digest = self._registry()
        store.record_application(digest, "run-1")
        store.record_application(digest, "run-2")
        store.revoke(digest, reason="escapes scope", severity=RiskClass.R4, reported_by="bob")
        with pytest.raises(ContractError) as error:
            store.check_executable(digest)
        assert error.value.code == "recipe_revoked"
        assert error.value.details["affectedRuns"] == ["run-1", "run-2"]

    def test_customer_fixture_needs_a_sharing_grant(self) -> None:
        fixture = registry.Fixture(
            fixture_id="f1",
            kind=registry.FixtureKind.POSITIVE,
            language="python",
            provenance=registry.Provenance.CUSTOMER,
            repository_id="customer-9",
            before="a",
            expected_after="b",
        )
        with pytest.raises(ContractError) as error:
            registry.admit_fixture(fixture)
        assert error.value.code == "fixture_not_shareable"


# ---------------------------------------------------------------------------
# Skill 18 — performance preservation
# ---------------------------------------------------------------------------


ENVIRONMENT = performance.Environment("m7i", 8, 16384, "sha256:image", "ds-1", 3, 16)
OTHER_ENVIRONMENT = performance.Environment("m7i", 4, 16384, "sha256:image", "ds-1", 3, 16)


def _samples(
    metric: str,
    values: list[int],
    environment: performance.Environment = ENVIRONMENT,
) -> performance.Samples:
    return performance.Samples(
        metric=metric,
        workload=performance.WorkloadClass.COMPONENT,
        values=tuple(Decimal(item) for item in values),
        unit="ms",
        environment=environment,
    )


class TestPerformance:
    def test_the_same_delta_is_noise_or_regression_depending_on_spread(self) -> None:
        rail = performance.Guardrail("latency_ms", Decimal("0.05"))
        quiet = performance.compare_metric(
            _samples("latency_ms", [100, 101, 99, 100, 102, 98, 101]),
            _samples("latency_ms", [112, 113, 111, 112, 114, 110, 113]),
            rail,
        )
        noisy = performance.compare_metric(
            _samples("noisy_ms", [100, 140, 60, 120, 80, 130, 70]),
            _samples("noisy_ms", [112, 150, 66, 128, 88, 140, 74]),
            performance.Guardrail("noisy_ms", Decimal("0.05")),
        )
        assert quiet.verdict is performance.Verdict.REGRESSED
        assert noisy.verdict is performance.Verdict.UNCHANGED

    def test_environment_mismatch_is_not_comparable(self) -> None:
        result = performance.compare_metric(
            _samples("latency_ms", [100] * 7),
            _samples("latency_ms", [100] * 7, OTHER_ENVIRONMENT),
            None,
        )
        assert result.verdict is performance.Verdict.NOT_COMPARABLE
        assert result.blocks

    def test_too_few_samples_is_undecided_and_blocks(self) -> None:
        result = performance.compare_metric(
            _samples("latency_ms", [100, 101, 99]),
            _samples("latency_ms", [100, 101, 99]),
            None,
        )
        assert result.verdict is performance.Verdict.UNDECIDED
        assert result.blocks

    def test_an_unmeasured_guardrail_blocks(self) -> None:
        report = performance.evaluate([], [], [performance.Guardrail("cost", Decimal("0.02"))])
        assert not report.allowed
        assert report.comparisons[0].verdict is performance.Verdict.NOT_RUN

    def test_higher_is_better_metrics_are_inverted(self) -> None:
        result = performance.compare_metric(
            _samples("throughput", [1000, 1001, 999, 1000, 1002, 998, 1001]),
            _samples("throughput", [800, 801, 799, 800, 802, 798, 801]),
            performance.Guardrail("throughput", Decimal("0.05")),
        )
        assert result.verdict is performance.Verdict.REGRESSED

    def test_suspects_separate_touched_symbols_from_untouched_ones(self) -> None:
        delta = performance.diff_profiles({"a.slow": 5}, {"a.slow": 30, "b.other": 7})
        suspects = performance.locate_suspects(delta, ["a.slow"])
        by_symbol = {item["symbol"]: item["changedByThisPatch"] for item in suspects}
        assert by_symbol == {"a.slow": True, "b.other": False}


# ---------------------------------------------------------------------------
# Skill 19 — security preservation
# ---------------------------------------------------------------------------


SECURE_BEFORE = {
    "app/views.py": (
        "@requires_role('admin')\n"
        "def delete_user(request, uid):\n"
        "    if request.tenant_id == user.tenant_id:\n"
        "        validate(request.data)\n"
        "        return do_delete(uid)\n"
    ),
    "app/legacy.py": "import hashlib\ndef h(x):\n    return hashlib.md5(x)\n",
}


class TestSecurity:
    def _analyse(self, after_files: dict[str, str]) -> security.SecurityReport:
        before = _snapshot(SECURE_BEFORE)
        after = _snapshot(after_files)
        return security.analyse(before, after, diff_snapshots(before, after))

    def test_removed_authorisation_is_reported(self) -> None:
        after = dict(SECURE_BEFORE)
        after["app/views.py"] = "def delete_user(request, uid):\n    return do_delete(uid)\n"
        report = self._analyse(after)
        rules = {item.rule_id for item in report.findings}
        assert "control-removed:authorization" in rules
        assert "control-removed:tenant-boundary" in rules
        assert not report.allowed

    def test_pre_existing_weakness_is_not_blamed_on_this_change(self) -> None:
        after = dict(SECURE_BEFORE)
        after["app/views.py"] = SECURE_BEFORE["app/views.py"] + "# a comment\n"
        report = self._analyse(after)
        assert not any(item.rule_id == "weak-hash" for item in report.findings)

    def test_secret_value_never_appears_in_the_finding(self) -> None:
        secret = "sk-live-9f2b7c41ee8842a0"
        findings = security.find_secrets("c.py", f"API_TOKEN = '{secret}'\n")
        assert len(findings) == 1
        assert secret not in findings[0].message
        assert findings[0].severity is security.Severity.CRITICAL

    def test_placeholders_are_not_secrets(self) -> None:
        assert security.find_secrets("c.py", "password = '${VAULT_PASSWORD}'\n") == ()
        assert security.find_secrets("c.py", "api_key = 'changeme'\n") == ()

    def test_suppression_without_approval_blocks(self) -> None:
        after = dict(SECURE_BEFORE)
        after["app/views.py"] = SECURE_BEFORE["app/views.py"] + "x = 1  # noqa: S105\n"
        report = self._analyse(after)
        assert report.unapproved_suppressions
        assert not report.allowed

    def test_suppression_with_owner_and_expiry_is_acceptable(self) -> None:
        found = security.find_suppressions(
            "c.py", "x = 1  # noqa: S105 approved-by=@acme/sec expires=2026-12-31\n"
        )
        assert len(found) == 1
        assert found[0].acceptable

    def test_dependency_downgrade_is_a_finding(self) -> None:
        delta = security.sbom_delta(
            {"pypi": {"cryptography": "42.0.5"}}, {"pypi": {"cryptography": "41.0.0"}}
        )
        assert delta[0].downgraded is True

    def test_unrunnable_scan_is_not_a_pass(self) -> None:
        report = self._analyse(dict(SECURE_BEFORE))
        assert report.scan_status == ExecutionStatus.NOT_RUN.value
        assert not report.allowed


# ---------------------------------------------------------------------------
# Skill 21 — multi-repository program
# ---------------------------------------------------------------------------


PORTFOLIO = [
    {"repositoryId": "billing-api", "role": "provider", "owners": ["@acme/payments"]},
    {"repositoryId": "web", "role": "consumer", "dependsOn": ["billing-api"]},
    {"repositoryId": "partner", "role": "consumer", "external": True, "dependsOn": ["billing-api"]},
]


class TestProgram:
    def _program(self) -> program.Program:
        portfolio = program.portfolio_from_payload(PORTFOLIO)
        return program.Program(program.plan_program("p1", portfolio, consumer_first=True))

    def test_a_repository_in_two_waves_has_two_states(self) -> None:
        active = self._program()
        active.advance(
            "billing-api", program.RepositoryState.ADOPTED, wave_id="wave-0-compatibility"
        )
        assert active.wave_complete("wave-0-compatibility")
        assert not active.wave_complete("wave-2-providers")

    def test_cleanup_blocks_while_a_consumer_has_not_adopted(self) -> None:
        active = self._program()
        active.advance(
            "billing-api", program.RepositoryState.ADOPTED, wave_id="wave-0-compatibility"
        )
        active.advance("web", program.RepositoryState.ADOPTED, wave_id="wave-1-consumers")
        active.advance("billing-api", program.RepositoryState.ADOPTED, wave_id="wave-2-providers")
        may, blockers = active.may_start("wave-3-cleanup")
        assert not may
        assert any("partner" in item for item in blockers)

    def test_pausing_one_repository_keeps_the_rest_of_the_program(self) -> None:
        active = self._program()
        active.advance("web", program.RepositoryState.MERGED, wave_id="wave-1-consumers")
        before = {key: run.state for key, run in active.runs.items()}
        active.pause("partner", reason="external team unreachable", wave_id="wave-1-consumers")
        active.resume("partner", wave_id="wave-1-consumers")
        assert {key: run.state for key, run in active.runs.items()} == before

    def test_a_cycle_is_reported_concretely(self) -> None:
        portfolio = program.portfolio_from_payload(
            [
                {"repositoryId": "a", "role": "provider", "dependsOn": ["b"]},
                {"repositoryId": "b", "role": "consumer", "dependsOn": ["a"]},
            ]
        )
        plan = program.plan_program("p2", portfolio, consumer_first=False)
        assert not plan.executable
        assert any("cycle" in item for item in plan.ordering_violations)

    def test_dependency_outside_the_portfolio_is_refused(self) -> None:
        with pytest.raises(ContractError) as error:
            program.portfolio_from_payload(
                [{"repositoryId": "a", "role": "consumer", "dependsOn": ["ghost"]}]
            )
        assert error.value.code == "unknown_dependency"


# ---------------------------------------------------------------------------
# Skill 22 — UI and client
# ---------------------------------------------------------------------------


CLIENT_FILES = {
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


class TestClient:
    def _report(self, targets: list[client.Platform]) -> client.ClientReport:
        before = _snapshot(CLIENT_FILES)
        after_files = dict(CLIENT_FILES)
        after_files["src/Cart.tsx"] = CLIENT_FILES["src/Cart.tsx"].replace(
            "cart_viewed", "cart_opened"
        )
        after = _snapshot(after_files)
        return client.analyse(after, diff_snapshots(before, after), targets=targets)

    def test_dom_use_is_a_gap_on_a_miniprogram_target(self) -> None:
        report = self._report([client.Platform.WECHAT_MINIPROGRAM])
        gaps = {(item.capability, item.platform) for item in report.gaps}
        assert (client.Capability.DOM, client.Platform.WECHAT_MINIPROGRAM) in gaps
        assert not report.allowed

    def test_the_same_component_has_no_gap_on_web(self) -> None:
        assert self._report([client.Platform.WEB]).gaps == ()

    def test_changed_analytics_line_needs_its_own_verification(self) -> None:
        report = self._report([client.Platform.WEB])
        assert any(item.rule_id == "sensitive-surface:analytics" for item in report.sensitive)

    def test_visual_result_is_not_run_without_a_renderer(self) -> None:
        report = self._report([client.Platform.WEB])
        assert report.visual
        assert all(item.status == "not-run" for item in report.visual)
        assert report.undecided_visual

    def test_missing_alt_text_is_reported(self) -> None:
        report = self._report([client.Platform.WEB])
        assert any(
            item.rule_id == "image-without-text-alternative" for item in report.accessibility
        )


# ---------------------------------------------------------------------------
# Coverage of the catalog itself
# ---------------------------------------------------------------------------


class TestBatchFourDispatch:
    @pytest.mark.parametrize(
        "skill",
        [
            "cross-language-contract-refactor",
            "data-schema-refactor",
            "distributed-system-refactor",
            "recipe-learning-registry",
            "performance-preservation",
            "security-preservation",
            "multi-repository-refactor-program",
            "ui-and-client-refactor",
        ],
    )
    def test_every_batch_four_skill_dispatches_without_a_stub(self, skill: str) -> None:
        result = dispatch(skill, {})
        assert result["status"] in ("succeeded", "blocked", "rejected", "failed")
        assert result["output"].get("code") != "handler_not_implemented"
