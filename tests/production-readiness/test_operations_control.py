from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class OperationsControlReadinessTests(unittest.TestCase):
    def test_all_control_plane_route_groups_have_server_audit_classification(self) -> None:
        registry = (
            ROOT
            / "apps/control-plane/src/main/java/io/elmos/controlplane"
            / "OperationsBusinessLineRegistry.java"
        ).read_text(encoding="utf-8")
        interceptor = (
            ROOT
            / "apps/control-plane/src/main/java/io/elmos/controlplane"
            / "ServerOperationAuditInterceptor.java"
        ).read_text(encoding="utf-8")
        controller_sources = (
            ROOT / "apps/control-plane/src/main/java/io/elmos/controlplane"
        ).glob("*Controller.java")
        route_groups: set[str] = set()
        for source_path in controller_sources:
            source = source_path.read_text(encoding="utf-8")
            route_groups.update(re.findall(r'@RequestMapping\("([^"]+)"\)', source))
        excluded = {"/api/v1/operations-observability"}
        registered_prefixes = set(
            re.findall(r'ROUTES\.put\("([^"]+)"', registry)
        )
        missing = sorted(
            route
            for route in route_groups - excluded
            if not any(route.startswith(prefix) for prefix in registered_prefixes)
        )
        self.assertEqual([], missing)
        for required in (
            "SERVER_ATTEMPT",
            "SERVER_OPERATION",
            "BEST_MATCHING_PATTERN_ATTRIBUTE",
            "activity.append",
        ):
            # The implementation uses store.append; accept the exact durable call.
            if required == "activity.append":
                self.assertIn("store.append", interceptor)
            else:
                self.assertIn(required, interceptor)

    def test_web_proxy_audits_every_api_before_execution_and_fails_closed(self) -> None:
        source = (ROOT / "apps/web-console/proxy.ts").read_text(encoding="utf-8")
        for token in (
            '"/api/:path*"',
            "auditApiAttempt",
            "/api/v1/operations-observability/audit-events",
            "SERVER_OPERATION_AUDIT_NOT_CONFIGURED",
            "SERVER_OPERATION_AUDIT_UNAVAILABLE",
            "X-ELMOS-Operations-Key",
            "normalizedRoute",
        ):
            self.assertIn(token, source)
        self.assertIn('path === "/api/telemetry/events"', source)
        self.assertIn('path === "/api/health"', source)
        self.assertNotIn("request.nextUrl.search", source.split("auditApiAttempt", 1)[1].split("export async", 1)[0])

    def test_operations_schema_is_rls_scoped_and_retention_never_deletes_audit(self) -> None:
        migration = (
            ROOT
            / "modules/persistence/src/main/resources/db/migration"
            / "V51__production_operations_control.sql"
        ).read_text(encoding="utf-8")
        for table in (
            "product_telemetry_events",
            "operations_slo_policies",
            "operations_alerts",
            "operations_incidents",
            "operations_remediation_proposals",
            "operations_workflow_events",
            "operations_notification_outbox",
            "operations_retention_runs",
        ):
            self.assertIn(f"CREATE TABLE {table}", migration)
        self.assertIn("FORCE ROW LEVEL SECURITY", migration)
        self.assertIn("operations_workflow_events_append_only", migration)
        self.assertIn("operations_retention_runs_append_only", migration)

        store = (
            ROOT
            / "modules/persistence/src/main/java/io/elmos/persistence"
            / "JdbcOperationsManagementStore.java"
        ).read_text(encoding="utf-8")
        self.assertIn("delete from product_telemetry_events", store.lower())
        self.assertNotIn("delete from audit_events", store.lower())
        self.assertIn("auditEventsDeleted\", false", store)

    def test_quick_fix_is_automatic_but_cannot_self_mutate_or_self_approve(self) -> None:
        profile = json.loads((ROOT / "quick-fix/profile.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "quick-fix/registry.json").read_text(encoding="utf-8"))
        self.assertEqual("DETECT_DIAGNOSE_PROPOSE_AUTOMATIC", profile["mode"])
        self.assertEqual("APPROVAL_AND_EXTERNAL_SCM_REQUIRED", profile["sourceMutation"])
        self.assertEqual("FAIL_CLOSED", profile["stalePolicy"])
        self.assertEqual(
            {"STABLE_ERROR_DIAGNOSTIC_V1", "LATENCY_BUDGET_DIAGNOSTIC_V1"},
            {recipe["recipeId"] for recipe in registry["recipes"]},
        )
        self.assertTrue(all(recipe["approvalRequired"] for recipe in registry["recipes"]))
        self.assertTrue(all("TARGETED_REGRESSION" in recipe["requiredTests"] for recipe in registry["recipes"]))

    def test_admin_exposes_complete_governed_workflow(self) -> None:
        api = (
            ROOT / "apps/web-console/app/api/admin/operations/route.ts"
        ).read_text(encoding="utf-8")
        ui = (
            ROOT / "apps/web-console/app/admin/OperationsAdmin.tsx"
        ).read_text(encoding="utf-8")
        for action in (
            "EVALUATE",
            "ACKNOWLEDGE_ALERT",
            "ASSIGN_INCIDENT",
            "RESOLVE_INCIDENT",
            "APPROVE_REMEDIATION",
            "REJECT_REMEDIATION",
            "PREPARE_SCM",
            "ENFORCE_RETENTION",
        ):
            self.assertIn(action, api)
            self.assertIn(action, ui)
        proxy = (
            ROOT / "apps/web-console/app/lib/server/operationsProxy.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('permission: Record<AdminRole, AccountPermission>', proxy)
        self.assertIn("ACCOUNT_SESSION_REQUIRED", proxy)
        self.assertIn("ELMOS_ADMIN_ALLOW_TOKEN_FALLBACK", proxy)


if __name__ == "__main__":
    unittest.main()
