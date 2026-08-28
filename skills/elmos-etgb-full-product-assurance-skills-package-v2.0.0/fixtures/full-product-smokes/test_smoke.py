from __future__ import annotations

import unittest
from decimal import Decimal

from smoke_system import (
    AuthorizationError,
    Chunk,
    ControlPlaneRun,
    DebugSession,
    EvidenceFact,
    PaymentOrder,
    Principal,
    StaleFenceError,
    UsageLedger,
    Wallet,
    authorize,
    grounded_answer,
    route_model,
)


class FullProductSmokeTests(unittest.TestCase):
    def test_identity(self) -> None:
        self.assertTrue(authorize(Principal("tenant-a", "developer"), "tenant-a", "execute"))
        with self.assertRaises(AuthorizationError):
            authorize(Principal("tenant-a", "owner"), "tenant-b", "read")
        with self.assertRaises(AuthorizationError):
            authorize(Principal("tenant-a", "viewer"), "tenant-a", "admin")

    def test_control_plane(self) -> None:
        run = ControlPlaneRun()
        run.transition("PREPARING", 0)
        run.transition("RUNNING", 1)
        run.complete("receipt-1", 2)
        run.complete("receipt-1", 3)  # idempotent replay
        self.assertEqual(run.state, "COMPLETED")
        self.assertEqual(run.revision, 3)
        with self.assertRaises(RuntimeError):
            run.transition("RUNNING", 3)

    def test_model_router(self) -> None:
        ledger = UsageLedger()
        def primary() -> str:
            raise TimeoutError("provider timeout")
        def fallback() -> str:
            return "ok"
        provider, output = route_model([("primary", primary), ("fallback", fallback)], ledger, "req-1")
        self.assertEqual((provider, output), ("fallback", "ok"))
        self.assertEqual(ledger.total, Decimal("1"))
        # Retry with same request and provider usage identity cannot double charge.
        route_model([("fallback", fallback)], ledger, "req-1")
        self.assertEqual(ledger.total, Decimal("1"))

    def test_rag(self) -> None:
        result = grounded_answer("What owns durable truth?", [Chunk("c1", "PostgreSQL owns durable truth", 0.95)])
        self.assertEqual(result["status"], "grounded")
        self.assertEqual(len(result["citations"]), 1)
        no_answer = grounded_answer("Unknown?", [Chunk("c2", "unrelated", 0.2)])
        self.assertEqual(no_answer, {"answer": None, "status": "insufficient-evidence", "citations": []})

    def test_project_intelligence(self) -> None:
        EvidenceFact("Route is protected", "confirmed", "src/security.py", 10, 14).validate()
        with self.assertRaises(ValueError):
            EvidenceFact("Unsupported inferred claim", "confirmed").validate()

    def test_billing(self) -> None:
        wallet = Wallet(Decimal("100"))
        self.assertTrue(wallet.reserve("r1", Decimal("30")))
        self.assertFalse(wallet.reserve("r1", Decimal("30")))
        self.assertTrue(wallet.consume("r1", "u1", Decimal("20")))
        self.assertFalse(wallet.consume("r1", "u1", Decimal("20")))
        self.assertEqual(wallet.balance, Decimal("80"))
        with self.assertRaises(ValueError):
            wallet.reserve("r2", Decimal("90"))

    def test_payment(self) -> None:
        order = PaymentOrder("order-1")
        self.assertTrue(order.apply_webhook("event-paid", "PAYMENT_CONFIRMED", Decimal("25")))
        self.assertFalse(order.apply_webhook("event-paid", "PAYMENT_CONFIRMED", Decimal("25")))
        order.apply_webhook("event-old", "PAYMENT_PENDING", Decimal("25"))
        self.assertEqual(order.state, "PAID")
        self.assertEqual(order.credited, Decimal("25"))

    def test_debug_replay(self) -> None:
        session = DebugSession(fencing_token=7)
        digest = session.checkpoint("cp1", {"counter": 2, "status": "paused"}, 7)
        self.assertEqual(session.replay("cp1", 7), {"counter": 2, "status": "paused"})
        self.assertEqual(digest, session.checkpoints["cp1"]["digest"])
        with self.assertRaises(StaleFenceError):
            session.replay("cp1", 6)


if __name__ == "__main__":
    unittest.main()
