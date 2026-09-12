"""Comprehensive test suite for EnterpriseSupportSlaEngine (B39 - Skill 1360)."""

from datetime import datetime, timedelta, timezone
import unittest

from elmos_mature_platform.enterprise_support_sla_engine import (
    EnterpriseSupportSlaEngine,
)
from elmos_mature_platform.types import (
    SupportSlaTarget,
    SupportTicket,
    SupportTierLevel,
    TicketPriority,
    TicketStatus,
)


class TestEnterpriseSupportSlaComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = EnterpriseSupportSlaEngine()

    def test_default_seeded_sla_targets(self):
        # Check Mission Critical P1: 15 min response, 120 min resolution
        target = self.engine.get_sla_target(SupportTierLevel.MISSION_CRITICAL, TicketPriority.P1_CRITICAL)
        self.assertIsNotNone(target)
        self.assertEqual(target.response_time_minutes, 15)
        self.assertEqual(target.resolution_time_minutes, 120)
        self.assertTrue(target.dedicated_tam)

        # Check Premier P1: 30 min response
        target_premier = self.engine.get_sla_target(SupportTierLevel.PREMIER, TicketPriority.P1_CRITICAL)
        self.assertIsNotNone(target_premier)
        self.assertEqual(target_premier.response_time_minutes, 30)

    def test_create_and_record_compliant_response(self):
        created = datetime.now(timezone.utc)
        ticket = SupportTicket(
            ticket_id="tkt-mc-001",
            customer_id="cust-enterprise-alpha",
            support_tier=SupportTierLevel.MISSION_CRITICAL,
            priority=TicketPriority.P1_CRITICAL,
            created_at=created.isoformat(),
            summary="Production outage in database",
        )
        self.engine.create_ticket(ticket)

        # Responded in 10 minutes (target is 15 min -> OK)
        resp_time = (created + timedelta(minutes=10)).isoformat()
        updated = self.engine.record_response("tkt-mc-001", "lead-sre@example.com", resp_time)

        self.assertEqual(updated.status, TicketStatus.IN_PROGRESS)
        self.assertFalse(updated.response_breached)
        self.assertFalse(updated.service_credit_eligible)

    def test_record_response_breach_and_service_credit_eligibility(self):
        created = datetime.now(timezone.utc)
        ticket = SupportTicket(
            ticket_id="tkt-mc-002",
            customer_id="cust-enterprise-beta",
            support_tier=SupportTierLevel.MISSION_CRITICAL,
            priority=TicketPriority.P1_CRITICAL,
            created_at=created.isoformat(),
            summary="API gateway downtime",
        )
        self.engine.create_ticket(ticket)

        # Responded in 25 minutes (target is 15 min -> BREACH)
        resp_time = (created + timedelta(minutes=25)).isoformat()
        updated = self.engine.record_response("tkt-mc-002", "oncall@example.com", resp_time)

        self.assertTrue(updated.response_breached)
        self.assertTrue(updated.service_credit_eligible)

    def test_record_resolution_breach(self):
        created = datetime.now(timezone.utc)
        ticket = SupportTicket(
            ticket_id="tkt-res-001",
            customer_id="cust-gamma",
            support_tier=SupportTierLevel.PREMIER,
            priority=TicketPriority.P1_CRITICAL,
            created_at=created.isoformat(),
            summary="Critical batch failure",
        )
        self.engine.create_ticket(ticket)

        # Responded in 20 min (compliant, < 30)
        self.engine.record_response("tkt-res-001", "eng@example.com", (created + timedelta(minutes=20)).isoformat())

        # Resolved in 300 minutes (Premier P1 target is 240 min -> RESOLUTION BREACH)
        resolved_time = (created + timedelta(minutes=300)).isoformat()
        updated = self.engine.record_resolution("tkt-res-001", resolved_time)

        self.assertEqual(updated.status, TicketStatus.RESOLVED)
        self.assertTrue(updated.resolution_breached)
        self.assertTrue(updated.service_credit_eligible)

    def test_calculate_sla_compliance_statistics(self):
        created = datetime.now(timezone.utc)
        # Ticket 1: Compliant
        t1 = SupportTicket(
            ticket_id="t1",
            customer_id="cust-1",
            support_tier=SupportTierLevel.STANDARD,
            priority=TicketPriority.P2_HIGH,
            created_at=created.isoformat(),
        )
        self.engine.create_ticket(t1)
        self.engine.record_response("t1", "e1", (created + timedelta(minutes=60)).isoformat())
        self.engine.record_resolution("t1", (created + timedelta(minutes=200)).isoformat())

        # Ticket 2: Breached response
        t2 = SupportTicket(
            ticket_id="t2",
            customer_id="cust-1",
            support_tier=SupportTierLevel.STANDARD,
            priority=TicketPriority.P2_HIGH,
            created_at=created.isoformat(),
        )
        self.engine.create_ticket(t2)
        # Standard P2 response SLA is 480 min; respond at 600 min
        self.engine.record_response("t2", "e2", (created + timedelta(minutes=600)).isoformat())
        self.engine.record_resolution("t2", (created + timedelta(minutes=1000)).isoformat())

        stats = self.engine.calculate_sla_compliance(customer_id="cust-1")
        self.assertEqual(stats["total_tickets"], 2)
        self.assertEqual(stats["response_compliance_pct"], 50.0)
        self.assertEqual(stats["resolution_compliance_pct"], 100.0)

    def test_get_eligible_service_credits(self):
        created = datetime.now(timezone.utc)
        t = SupportTicket(
            ticket_id="t-credit",
            customer_id="cust-vip",
            support_tier=SupportTierLevel.MISSION_CRITICAL,
            priority=TicketPriority.P1_CRITICAL,
            created_at=created.isoformat(),
        )
        self.engine.create_ticket(t)
        # Breach response: 40 min
        self.engine.record_response("t-credit", "sre", (created + timedelta(minutes=40)).isoformat())

        credits = self.engine.get_eligible_service_credits("cust-vip")
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0].ticket_id, "t-credit")

    def test_get_tier_features(self):
        mc_feat = self.engine.get_tier_features(SupportTierLevel.MISSION_CRITICAL)
        self.assertTrue(mc_feat["tam"])
        self.assertEqual(mc_feat["p1_response_min"], 15)
        self.assertEqual(mc_feat["service_credit_pct"], 10.0)

        comm_feat = self.engine.get_tier_features(SupportTierLevel.COMMUNITY)
        self.assertFalse(comm_feat["tam"])
        self.assertEqual(comm_feat["service_credit_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
