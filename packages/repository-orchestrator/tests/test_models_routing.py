from __future__ import annotations

import unittest
from datetime import datetime, timezone

from elmos_repository_orchestrator.catalog import MODEL_ALIASES
from elmos_repository_orchestrator.contracts import ContractError, FailureClass, SelectionSource, Status
from elmos_repository_orchestrator.dispatcher import DispatchContext, RuntimeDispatcher
from elmos_repository_orchestrator.execution import decide_retry
from elmos_repository_orchestrator.models import RegistrySnapshot, RoutingTaskProfile, resolve_model_selection
from elmos_repository_orchestrator.routing import route_model

from fixtures import NOW, registry_payload, selection_payload, task_profile


AS_OF = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


class SelectionContractTests(unittest.TestCase):
    def test_manual_and_smart_null_rules_and_server_field_forgery(self) -> None:
        with self.assertRaisesRegex(ContractError, "manual mode requires"):
            resolve_model_selection({"mode": "manual", "selected_model": None}, source="api", now=AS_OF)
        with self.assertRaisesRegex(ContractError, "selected_model to be null"):
            resolve_model_selection({"mode": "smart", "selected_model": MODEL_ALIASES[0]}, source="api", now=AS_OF)
        with self.assertRaisesRegex(ContractError, "server-derived"):
            resolve_model_selection({"mode": "smart", "locked_by_user": False}, source="api", now=AS_OF)

    def test_naive_time_is_rejected_and_resolved_selection_is_registry_bound(self) -> None:
        with self.assertRaisesRegex(ContractError, "timezone-aware"):
            resolve_model_selection({"mode": "smart"}, source="api", now=datetime(2026, 8, 24, 12, 0))
        request = resolve_model_selection({"mode": "smart"}, source=SelectionSource.API, now=AS_OF)
        with self.assertRaisesRegex(ContractError, "requires a trusted registry"):
            request.to_payload()
        bound = request.bind_registry("sha256:" + "a" * 64).to_payload()
        self.assertEqual(bound["registry_digest"], "sha256:" + "a" * 64)
        self.assertEqual(bound["selection_source"], "api")

    def test_smart_controller_without_trusted_registry_is_not_configured(self) -> None:
        result = RuntimeDispatcher().execute(
            "elmos-model-selection-controller",
            {"as_of": NOW, "model_selection": selection_payload()},
        )
        self.assertEqual(result.status, Status.NOT_CONFIGURED)
        self.assertIsNone(result.output["resolved_selection"])
        self.assertIn("trusted_registry_not_configured", result.reasons)

    def test_registry_cannot_be_injected_through_task_payload(self) -> None:
        result = RuntimeDispatcher().execute(
            "elmos-cost-performance-router",
            {
                "as_of": NOW,
                "model_selection": selection_payload(),
                "registry": registry_payload(),
                "task_profile": task_profile(),
                "currency": "USD",
            },
        )
        self.assertEqual(result.status, Status.BLOCKED)
        self.assertTrue(any(reason.startswith("trusted_registry_forgery:") for reason in result.reasons))

    def test_resolved_controller_shape_contains_digest_and_provenance(self) -> None:
        registry = RegistrySnapshot.from_payload(registry_payload())
        result = RuntimeDispatcher().execute(
            "elmos-model-selection-controller",
            {"as_of": NOW, "model_selection": selection_payload()},
            context=DispatchContext(trusted_registry=registry),
        )
        self.assertEqual(result.status, Status.READY)
        resolved = result.output["resolved_selection"]
        self.assertEqual(resolved["registry_digest"], registry.digest)
        self.assertEqual(result.output["registry_authorization_id"], "AUTH-REGISTRY-001")
        self.assertNotIn("selection_source", result.output["validated_request"])


class RoutingContractTests(unittest.TestCase):
    def _route(self, *, profile: str = "cost_performance", registry_data=None, task_data=None, mode="smart", **kwargs):
        registry = RegistrySnapshot.from_payload(registry_data or registry_payload())
        selection = resolve_model_selection(selection_payload(mode=mode, profile=profile), source="api", now=AS_OF).bind_registry(registry.digest)
        return route_model(
            RoutingTaskProfile.from_payload(task_data or task_profile()),
            selection,
            registry,
            currency="USD",
            now=AS_OF,
            **kwargs,
        )

    def test_four_profiles_are_deterministic_and_cache_affinity_affects_score(self) -> None:
        cost_performance = self._route(profile="cost_performance")
        lowest = self._route(profile="lowest_cost")
        quality = self._route(profile="max_quality")
        fastest = self._route(profile="fastest")
        self.assertEqual(cost_performance.status, Status.PLANNED)
        self.assertEqual(cost_performance.chosen_model, MODEL_ALIASES[1])
        self.assertEqual(lowest.chosen_model, MODEL_ALIASES[0])
        self.assertEqual(quality.chosen_model, MODEL_ALIASES[9])
        self.assertEqual(fastest.chosen_model, MODEL_ALIASES[9])
        candidates = {item.alias: item for item in cost_performance.candidates}
        self.assertEqual(candidates[MODEL_ALIASES[1]].cache_affinity, 1)
        self.assertGreater(candidates[MODEL_ALIASES[1]].route_score, candidates[MODEL_ALIASES[0]].route_score)

    def test_hard_filters_cover_residency_privacy_private_quota_concurrency(self) -> None:
        data = registry_payload(
            {
                MODEL_ALIASES[0]: {
                    "allowed_residencies": ["CN"],
                    "allowed_privacy_classes": ["public"],
                    "private_repository_allowed": False,
                },
                MODEL_ALIASES[1]: {"quota_remaining": 0},
                MODEL_ALIASES[2]: {"active_calls": 10},
            }
        )
        decision = self._route(registry_data=data)
        candidates = {item.alias: item for item in decision.candidates}
        self.assertIn("residency_not_allowed", candidates[MODEL_ALIASES[0]].rejection_reasons)
        self.assertIn("privacy_class_not_allowed", candidates[MODEL_ALIASES[0]].rejection_reasons)
        self.assertIn("private_repository_not_allowed", candidates[MODEL_ALIASES[0]].rejection_reasons)
        self.assertIn("quota_exhausted", candidates[MODEL_ALIASES[1]].rejection_reasons)
        self.assertIn("concurrency_capacity_exhausted", candidates[MODEL_ALIASES[2]].rejection_reasons)

    def test_budget_ceiling_rejects_before_planning(self) -> None:
        decision = self._route(task_data=task_profile(task_budget_remaining="0", run_budget_remaining="0"))
        self.assertEqual(decision.status, Status.BLOCKED)
        self.assertTrue(all("task_budget_exceeded" in item.rejection_reasons for item in decision.candidates))
        self.assertTrue(all("run_budget_exceeded" in item.rejection_reasons for item in decision.candidates))

    def test_exact_provider_deployment_revision_and_currency_are_preserved(self) -> None:
        decision = self._route(profile="lowest_cost")
        self.assertEqual(decision.chosen_provider, "provider-0")
        self.assertEqual(decision.chosen_provider_model_id, "native-0")
        self.assertEqual(decision.chosen_deployment_id, "deployment-0")
        self.assertEqual(decision.chosen_model_revision, "revision-0")
        self.assertEqual(decision.currency, "USD")
        candidate = next(item for item in decision.candidates if item.alias == MODEL_ALIASES[0])
        self.assertEqual(candidate.currency, "USD")
        self.assertIsInstance(candidate.to_dict()["expected_total_cost"], str)

    def test_manual_strict_never_silently_switches(self) -> None:
        registry = RegistrySnapshot.from_payload(registry_payload())
        selection = resolve_model_selection(selection_payload(mode="manual"), source="api", now=AS_OF).bind_registry(registry.digest)
        decision = route_model(
            RoutingTaskProfile.from_payload(task_profile()),
            selection,
            registry,
            now=AS_OF,
            fallback_from_model=MODEL_ALIASES[0],
            failure_class="semantic",
        )
        self.assertEqual(decision.status, Status.BLOCKED)
        self.assertIsNone(decision.chosen_model)
        self.assertEqual(decision.reason, "model_reselection_required")

    def test_unconfigured_placeholder_and_naive_route_time_fail_closed(self) -> None:
        data = registry_payload({MODEL_ALIASES[0]: {"provider_model_id": "SET_ME"}})
        registry = RegistrySnapshot.from_payload(data)
        selection = resolve_model_selection(selection_payload(mode="manual"), source="api", now=AS_OF).bind_registry(registry.digest)
        decision = route_model(RoutingTaskProfile.from_payload(task_profile()), selection, registry, now=AS_OF)
        self.assertEqual(decision.status, Status.NOT_CONFIGURED)
        self.assertIn("provider_model_id_unconfigured", decision.reason)
        with self.assertRaisesRegex(ContractError, "timezone-aware"):
            route_model(RoutingTaskProfile.from_payload(task_profile()), selection, registry, now=datetime(2026, 8, 24, 12, 0))


class RetryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = RegistrySnapshot.from_payload(registry_payload())
        self.task = RoutingTaskProfile.from_payload(task_profile())
        self.smart = resolve_model_selection(selection_payload(), source="api", now=AS_OF).bind_registry(self.registry.digest)

    def test_same_model_two_then_fallback_and_total_four(self) -> None:
        first = decide_retry(
            failure=FailureClass.TRANSIENT_TOOL,
            current_model=MODEL_ALIASES[0],
            attempt_models=[MODEL_ALIASES[0]],
            selection=self.smart,
            task=self.task,
            registry=self.registry,
            currency="USD",
            now=AS_OF,
        )
        self.assertEqual((first.status, first.action), (Status.PLANNED, "retry_same"))
        second = decide_retry(
            failure=FailureClass.TRANSIENT_TOOL,
            current_model=MODEL_ALIASES[0],
            attempt_models=[MODEL_ALIASES[0], MODEL_ALIASES[0]],
            selection=self.smart,
            task=self.task,
            registry=self.registry,
            currency="USD",
            now=AS_OF,
        )
        self.assertEqual((second.status, second.action), (Status.PLANNED, "fallback"))
        exhausted = decide_retry(
            failure=FailureClass.SEMANTIC,
            current_model=MODEL_ALIASES[3],
            attempt_models=list(MODEL_ALIASES[:4]),
            selection=self.smart,
            task=self.task,
            registry=self.registry,
            currency="USD",
            now=AS_OF,
        )
        self.assertEqual(exhausted.status, Status.FAILED)

    def test_terminal_failure_is_never_retried(self) -> None:
        decision = decide_retry(
            failure=FailureClass.SECURITY_POLICY_VIOLATION,
            current_model=MODEL_ALIASES[0],
            attempt_models=[MODEL_ALIASES[0]],
            selection=self.smart,
            task=self.task,
            registry=self.registry,
            currency="USD",
            now=AS_OF,
        )
        self.assertEqual((decision.status, decision.action), (Status.BLOCKED, "stop"))


if __name__ == "__main__":
    unittest.main()
