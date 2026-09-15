"""Implementation of B04 Golden Route: spring-modernization and Spring Requirement Oracles."""

from __future__ import annotations

from typing import Any

from .contracts import GateDecision


class SpringEndpointService:
    """Mock service demonstrating Spring Controller / Security / Transaction semantics."""

    def __init__(self) -> None:
        self.session_store: dict[str, dict[str, Any]] = {}
        self.db_records: dict[str, str] = {}
        self.tx_active: bool = False

    def handle_request(
        self,
        *,
        path: str,
        method: str,
        roles: list[str],
        session_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        # Role check: /admin requires ADMIN role
        if path.startswith("/admin") and "ROLE_ADMIN" not in roles:
            return {"status_code": 403, "error": "ACCESS_DENIED"}

        # Session returnUrl tracking
        session = self.session_store.setdefault(session_id, {})
        if "returnUrl" in data:
            session["returnUrl"] = data["returnUrl"]

        return {
            "status_code": 200,
            "path": path,
            "session": dict(session),
            "payload": data,
        }

    def transactional_method_via_proxy(self, record_id: str, value: str, fail: bool = False) -> None:
        """Simulates Spring AOP proxy interception creating a transaction."""
        self.tx_active = True
        backup = dict(self.db_records)
        try:
            self.db_records[record_id] = value
            if fail:
                raise RuntimeError("DB_FAILURE_IN_TX")
        except Exception:
            # Proxy rolls back
            self.db_records = backup
            raise
        finally:
            self.tx_active = False

    def self_invocation_bypassing_proxy(self, record_id: str, value: str, fail: bool = False) -> None:
        """Simulates self-invocation (this.method()) bypassing the Spring AOP proxy (No rollback)."""
        # AOP proxy is bypassed -> NO transaction wrapper created
        self.db_records[record_id] = value
        if fail:
            # No rollback happens because proxy was bypassed!
            raise RuntimeError("DB_FAILURE_WITHOUT_TX_ROLLBACK")


class SpringRequirementOracle:
    """Independent oracle enforcing Spring modernization invariants."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules = rules or {}

    def evaluate_spring_migration(
        self,
        *,
        source_security: dict[str, list[str]],
        target_security: dict[str, list[str]],
        proxy_mode: str,
        session_preserved: bool,
        behavioral_tests_passed: bool,
        target_build_passed: bool,
    ) -> tuple[GateDecision, str]:
        # Rule 1: Security non-loosening (target cannot grant broader access than source)
        for path, src_roles in source_security.items():
            tgt_roles = target_security.get(path, [])
            if "ROLE_ANONYMOUS" in tgt_roles and "ROLE_ANONYMOUS" not in src_roles:
                return GateDecision.FAIL, f"SECURITY_LOOSENED: Anonymous access granted on {path}"

        # Rule 2: Transaction proxy mode must not allow silent self-invocation bypass
        if proxy_mode == "RAW_THIS_INVOCATION":
            return GateDecision.FAIL, "TRANSACTION_BYPASS_SELF_INVOCATION"

        # Rule 3: Session state preservation
        if not session_preserved:
            return GateDecision.FAIL, "SESSION_RETURN_URL_LOST"

        # Rule 4: Target build alone does not imply behavioral certification (Acceptance A03)
        if target_build_passed and not behavioral_tests_passed:
            return GateDecision.FAIL, "TARGET_BUILD_PASSED_BUT_BEHAVIOR_NOT_CERTIFIED"

        return GateDecision.PASS, "SPRING_MODERNIZATION_VERIFIED"


class SpringModernizationRouteRunner:
    """Executes B04 Spring Modernization Golden Route scenarios SPR-001 through SPR-006."""

    @classmethod
    def run_all(cls) -> dict[str, Any]:
        results = {
            "SPR-001": cls._run_spr_001(),
            "SPR-002": cls._run_spr_002(),
            "SPR-003": cls._run_spr_003(),
            "SPR-004": cls._run_spr_004(),
            "SPR-005": cls._run_spr_005(),
            "SPR-006": cls._run_spr_006(),
        }
        all_passed = all(r["decision"] == GateDecision.PASS for r in results.values())
        return {
            "domain": "spring-modernization",
            "golden_route": "golden-spring-modernization",
            "overall_decision": GateDecision.PASS if all_passed else GateDecision.FAIL,
            "cases": results,
        }

    @classmethod
    def _run_spr_001(cls) -> dict[str, Any]:
        # SPR-001: REST Endpoint & DTO binding equivalence
        svc = SpringEndpointService()
        resp = svc.handle_request(
            path="/api/v1/orders",
            method="POST",
            roles=["ROLE_USER"],
            session_id="sess-1",
            data={"order_id": "ord-101", "amount": 5000},
        )
        assert resp["status_code"] == 200
        assert resp["payload"]["order_id"] == "ord-101"
        return {
            "case_id": "SPR-001",
            "decision": GateDecision.PASS,
            "details": "REST endpoint mapping and JSON DTO binding verified equivalent.",
        }

    @classmethod
    def _run_spr_002(cls) -> dict[str, Any]:
        # SPR-002: Security chain & RBAC role preservation
        svc = SpringEndpointService()
        # Normal user accessing /admin should be denied 403
        resp_denied = svc.handle_request(
            path="/admin/settings",
            method="GET",
            roles=["ROLE_USER"],
            session_id="sess-2",
            data={},
        )
        assert resp_denied["status_code"] == 403

        # Admin user allowed
        resp_allowed = svc.handle_request(
            path="/admin/settings",
            method="GET",
            roles=["ROLE_ADMIN"],
            session_id="sess-3",
            data={},
        )
        assert resp_allowed["status_code"] == 200
        return {
            "case_id": "SPR-002",
            "decision": GateDecision.PASS,
            "details": "Spring Security RBAC filter chain authorization verified.",
        }

    @classmethod
    def _run_spr_003(cls) -> dict[str, Any]:
        # SPR-003 (Acceptance A01): Self invocation proxy bypass detected in DB fault test
        svc = SpringEndpointService()

        # Proxied invocation properly rolls back on error
        try:
            svc.transactional_method_via_proxy("k1", "v1", fail=True)
        except RuntimeError:
            pass
        assert "k1" not in svc.db_records  # Rolled back!

        # Self-invocation bypassing proxy fails to roll back (dirty state)
        try:
            svc.self_invocation_bypassing_proxy("k2", "v2", fail=True)
        except RuntimeError:
            pass
        assert "k2" in svc.db_records  # Dirty write occurred!

        # Oracle flags this proxy mode as a failure
        oracle = SpringRequirementOracle()
        dec, msg = oracle.evaluate_spring_migration(
            source_security={},
            target_security={},
            proxy_mode="RAW_THIS_INVOCATION",
            session_preserved=True,
            behavioral_tests_passed=True,
            target_build_passed=True,
        )
        assert dec == GateDecision.FAIL
        assert "TRANSACTION_BYPASS_SELF_INVOCATION" in msg
        return {
            "case_id": "SPR-003",
            "decision": GateDecision.PASS,
            "details": f"A01: Self-invocation transaction bypass caught and failed by Oracle: {msg}",
        }

    @classmethod
    def _run_spr_004(cls) -> dict[str, Any]:
        # SPR-004 (Acceptance A02): Session returnUrl lost across redirect detected
        oracle = SpringRequirementOracle()
        dec, msg = oracle.evaluate_spring_migration(
            source_security={},
            target_security={},
            proxy_mode="ASPECTJ_WEAVING",
            session_preserved=False,  # ReturnUrl was dropped
            behavioral_tests_passed=True,
            target_build_passed=True,
        )
        assert dec == GateDecision.FAIL
        assert "SESSION_RETURN_URL_LOST" in msg
        return {
            "case_id": "SPR-004",
            "decision": GateDecision.PASS,
            "details": f"A02: Lost session returnUrl correctly blocks behavioral equivalence: {msg}",
        }

    @classmethod
    def _run_spr_005(cls) -> dict[str, Any]:
        # SPR-005 (Acceptance A03): Target build passed alone does not grant migration certification
        oracle = SpringRequirementOracle()
        dec, msg = oracle.evaluate_spring_migration(
            source_security={},
            target_security={},
            proxy_mode="ASPECTJ_WEAVING",
            session_preserved=True,
            behavioral_tests_passed=False,  # Behavioral parity failed
            target_build_passed=True,        # Build compiled
        )
        assert dec == GateDecision.FAIL
        assert "TARGET_BUILD_PASSED_BUT_BEHAVIOR_NOT_CERTIFIED" in msg
        return {
            "case_id": "SPR-005",
            "decision": GateDecision.PASS,
            "details": f"A03: Target build alone correctly refused certification without behavioral proof: {msg}",
        }

    @classmethod
    def _run_spr_006(cls) -> dict[str, Any]:
        # SPR-006: Independent Oracle catches security loosening (e.g. anonymous access)
        oracle = SpringRequirementOracle()
        dec, msg = oracle.evaluate_spring_migration(
            source_security={"/admin": ["ROLE_ADMIN"]},
            target_security={"/admin": ["ROLE_ANONYMOUS"]},  # Bad rewrite!
            proxy_mode="ASPECTJ_WEAVING",
            session_preserved=True,
            behavioral_tests_passed=True,
            target_build_passed=True,
        )
        assert dec == GateDecision.FAIL
        assert "SECURITY_LOOSENED" in msg
        return {
            "case_id": "SPR-006",
            "decision": GateDecision.PASS,
            "details": f"Independent Oracle successfully blocked relaxed endpoint authorization: {msg}",
        }
