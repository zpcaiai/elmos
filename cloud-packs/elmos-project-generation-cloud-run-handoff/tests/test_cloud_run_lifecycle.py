from __future__ import annotations

from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import sys
import unittest


PACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK_ROOT / "controller"))

import cloud_run_lifecycle as lifecycle  # noqa: E402


def request_fixture() -> dict[str, object]:
    return {
        "schema_version": lifecycle.SCHEMA,
        "pack_key": lifecycle.PACK_KEY,
        "project_id": "approved-project-1",
        "region": lifecycle.REGION,
        "service_name": "generated-api",
        "release_id": "release-01",
        "candidate_revision": "generated-api-release-01",
        "previous_revision": "generated-api-release-00",
        "image": (
            "asia-east1-docker.pkg.dev/approved-project-1/generated/api@sha256:"
            + "2" * 64
        ),
        "runtime_service_account": (
            "elmos-runner@approved-project-1.iam.gserviceaccount.com"
        ),
        "config_digest": "sha256:" + "3" * 64,
        "cpu": "2",
        "memory": "1Gi",
        "concurrency": 20,
        "min_instances": 0,
        "max_instances": 3,
        "timeout_seconds": 300,
        "budget": {
            "currency": "USD",
            "monthly_limit": 50,
            "test_limit": 5,
        },
        "owner": "team:cloud-platform",
        "ttl_expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat(),
    }


def authorization(action: str, index: int) -> dict[str, str]:
    return {
        "action": action,
        "digest": "sha256:" + f"{index:064x}",
        "approver": "user:release-approver",
    }


def evidence_fixture(request: dict[str, object]) -> dict[str, object]:
    actions: dict[str, object] = {
        "plan": {
            "status": "PASSED",
            "no_unapproved_replacement_or_deletion": True,
        },
        "canary": {
            "status": "PASSED",
            "revision": request["candidate_revision"],
            "image": request["image"],
            "traffic_percent": 0,
            "private_ingress": True,
            "authenticated_health": "PASSED",
            "authorization": authorization("canary", 1),
        },
        "promote": {
            "status": "PASSED",
            "revision": request["candidate_revision"],
            "traffic_percent": 100,
            "private_health": "PASSED",
            "authorization": authorization("promote", 2),
        },
        "abort": {
            "status": "PASSED",
            "traffic_percent": 0,
            "previous_revision_traffic_unchanged": True,
            "candidate_disposition": "DELETED",
            "authorization": authorization("abort", 3),
        },
        "rollback": {
            "status": "PASSED",
            "revision": request["previous_revision"],
            "traffic_percent": 100,
            "private_health": "PASSED",
            "authorization": authorization("rollback", 4),
        },
        "destroy": {
            "status": "PASSED",
            "service_absent": True,
            "owned_inventory_bound": True,
            "authorization": authorization("destroy", 5),
        },
        "orphan": {
            "status": "PASSED",
            "unknown_resources": 0,
            "orphaned_resources": 0,
            "billable_orphans": 0,
        },
        "drift": {
            "status": "PASSED",
            "config_digest": request["config_digest"],
            "unknown_drift": 0,
            "protected_replacements": 0,
            "protected_deletions": 0,
        },
        "cost": {
            "status": "PASSED",
            "currency": "USD",
            "monthly_forecast": 40,
            "test_spend": 4,
            "included_categories": sorted(lifecycle.COST_CATEGORIES),
        },
    }
    artifacts = [
        {
            "role": role,
            "sha256": "sha256:" + f"{index:064x}",
            "byte_size": index,
        }
        for index, role in enumerate(
            (
                "provider-plan",
                "canary-describe",
                "canary-health",
                "promotion-traffic",
                "abort-drill",
                "rollback-drill",
                "destroy-observation",
                "orphan-inventory",
                "drift-inventory",
                "cost-observation",
            ),
            start=101,
        )
    ]
    return {
        "schema_version": lifecycle.EVIDENCE_SCHEMA,
        "pack_key": lifecycle.PACK_KEY,
        "request_digest": lifecycle._digest(request),
        "synthetic": True,
        "evidence_class": "LOCAL_CONTRACT_TEST",
        "external_execution": "NOT_RUN",
        "executor": "workload:local-contract-test",
        "independent_verifier": "user:independent-reviewer",
        "certification": "NOT_CERTIFIED",
        "actions": actions,
        "artifacts": artifacts,
    }


class CloudRunLifecycleTests(unittest.TestCase):
    def test_contract_lists_every_action_and_preserves_external_boundary(self) -> None:
        contract = json.loads(
            (PACK_ROOT / "controller/lifecycle-contract.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [entry["name"] for entry in contract["lifecycle"]["actions"]],
            list(lifecycle.ACTIONS),
        )
        self.assertEqual(
            set(contract["authorization"]["separate_actions"]),
            set(lifecycle.MUTATING_ACTIONS),
        )
        self.assertTrue(
            all(
                contract["current_external_status"][action] == "NOT_RUN"
                for action in lifecycle.ACTIONS
            )
        )
        self.assertEqual(
            contract["current_external_status"]["certification"],
            "NOT_CERTIFIED",
        )

    def test_plan_is_private_digest_pinned_and_zero_traffic(self) -> None:
        request = request_fixture()
        plan = lifecycle.build_plan(request)
        canary = plan["commands"]["canary"][0]
        self.assertIn(f"--image={request['image']}", canary)
        self.assertIn("--ingress=internal", canary)
        self.assertIn("--no-allow-unauthenticated", canary)
        self.assertIn("--no-traffic", canary)
        self.assertIn(
            f"--set-annotations=elmos.dev/config-digest={request['config_digest']}",
            canary,
        )
        self.assertEqual(plan["status"], "BLOCKED_PREREQUISITES")
        self.assertFalse(plan["execution_authorized"])
        self.assertEqual(
            plan["blocking_prerequisites"],
            {
                "immutable_secret_version_refs": "NOT_IMPLEMENTED",
                "vercel_to_internal_cloud_run_network_bridge": "NOT_IMPLEMENTED",
            },
        )
        self.assertEqual(
            plan["separate_authorization_required"],
            list(lifecycle.MUTATING_ACTIONS),
        )
        self.assertEqual(plan["external_execution_evidence"], "NOT_RUN")
        self.assertEqual(plan["certification"], "NOT_CERTIFIED")

    def test_request_rejects_scope_drift_tags_default_identity_and_unknowns(self) -> None:
        mutations = (
            ("region", "us-central1", "TARGET_REGION_MISMATCH"),
            ("image", "gcr.io/example/app:latest", "IMAGE_DIGEST_OR_REGISTRY_INVALID"),
            (
                "runtime_service_account",
                "default@approved-project-1.iam.gserviceaccount.com",
                "RUNTIME_SERVICE_ACCOUNT_INVALID",
            ),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                request = request_fixture()
                request[field] = value
                with self.assertRaisesRegex(lifecycle.LifecycleError, expected):
                    lifecycle.build_plan(request)
        request = request_fixture()
        request["undeclared"] = True
        with self.assertRaisesRegex(lifecycle.LifecycleError, "REQUEST_FIELDS_MISMATCH"):
            lifecycle.build_plan(request)

    def test_synthetic_evidence_is_test_only_and_external_path_rejects_it(self) -> None:
        request = request_fixture()
        evidence = evidence_fixture(request)
        self.assertEqual(
            lifecycle.validate_evidence(
                request,
                evidence,
                allow_synthetic_contract_test=True,
            ),
            "LOCAL_CONTRACT_VALID",
        )
        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "LOCAL_CONTRACT_TEST_FLAG_REQUIRED",
        ):
            lifecycle.validate_evidence(request, evidence)

        forged = evidence_fixture(request)
        forged["synthetic"] = False
        forged["evidence_class"] = "EXTERNAL_PROVIDER"
        forged["external_execution"] = "EXECUTED"
        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "EXTERNAL_EVIDENCE_REQUIRES_BATCH33_GATE",
        ):
            lifecycle.validate_evidence(
                request,
                forged,
                allow_synthetic_contract_test=True,
            )

    def test_request_ttl_must_be_future_and_no_more_than_24_hours(self) -> None:
        now = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)
        for value, expected in (
            ("2026-09-04T11:59:59Z", "TTL_EXPIRED"),
            ("2026-09-05T12:00:01Z", "TTL_EXCEEDS_24_HOURS"),
            ("2026-09-04T13:00:00", "TTL_TIMEZONE_REQUIRED"),
        ):
            request = request_fixture()
            request["ttl_expires_at"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(lifecycle.LifecycleError, expected):
                    lifecycle.validate_request(request, now=now)

    def test_canary_must_pass_and_authorization_cannot_be_reused(self) -> None:
        request = request_fixture()
        evidence = evidence_fixture(request)
        evidence["actions"]["canary"]["authenticated_health"] = "FAILED"
        with self.assertRaisesRegex(lifecycle.LifecycleError, "CANARY_CONTRACT_FAILED"):
            lifecycle.validate_evidence(
                request,
                evidence,
                allow_synthetic_contract_test=True,
            )
        evidence = evidence_fixture(request)
        evidence["actions"]["promote"]["authorization"] = deepcopy(
            evidence["actions"]["canary"]["authorization"]
        )
        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "PROMOTE_AUTHORIZATION_SCOPE_INVALID",
        ):
            lifecycle.validate_evidence(
                request,
                evidence,
                allow_synthetic_contract_test=True,
            )

    def test_orphan_drift_and_cost_unknowns_fail_closed(self) -> None:
        request = request_fixture()
        cases = (
            ("orphan", "unknown_resources", 1, "ORPHAN_OR_UNKNOWN_RESOURCE_DETECTED"),
            ("drift", "unknown_drift", 1, "DRIFT_CONTRACT_FAILED"),
            ("cost", "monthly_forecast", 51, "MONTHLY_BUDGET_EXCEEDED"),
        )
        for action, field, value, expected in cases:
            with self.subTest(action=action, field=field):
                evidence = evidence_fixture(request)
                evidence["actions"][action][field] = value
                with self.assertRaisesRegex(lifecycle.LifecycleError, expected):
                    lifecycle.validate_evidence(
                        request,
                        evidence,
                        allow_synthetic_contract_test=True,
                    )

    def test_controller_cannot_claim_certification(self) -> None:
        request = request_fixture()
        evidence = evidence_fixture(request)
        evidence["certification"] = "CERTIFIED"
        with self.assertRaisesRegex(lifecycle.LifecycleError, "CONTROLLER_CANNOT_CERTIFY"):
            lifecycle.validate_evidence(
                request,
                evidence,
                allow_synthetic_contract_test=True,
            )


if __name__ == "__main__":
    unittest.main()
