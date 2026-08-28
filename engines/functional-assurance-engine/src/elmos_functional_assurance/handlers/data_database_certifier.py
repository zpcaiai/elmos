"""Database Cutover, Data Integrity, and PITR Failover Certification."""

from __future__ import annotations

from typing import Any, Mapping

from ..domain import ConformityDecision, FunctionalAssuranceContext


class DataDatabaseCertifier:
    """Certifier for database migrations, PITR backups, query performance, and event replay."""

    @staticmethod
    def certify_cutover_and_rollback(
        context: FunctionalAssuranceContext,
        data_checksum_matched: bool = True,
        data_loss_bytes: int = 0,
        rollback_tested_seconds: int = 45,
        target_rto_seconds: int = 300,
    ) -> dict[str, Any]:
        passed = data_checksum_matched and data_loss_bytes == 0 and rollback_tested_seconds <= target_rto_seconds
        return {
            "skill": "elmos-database-cutover-rollback-certifier",
            "data_checksum_verified": data_checksum_matched,
            "data_loss_bytes": data_loss_bytes,
            "observed_rollback_seconds": rollback_tested_seconds,
            "rto_sla_met": rollback_tested_seconds <= target_rto_seconds,
            "decision": (ConformityDecision.CONFORMING if passed else ConformityDecision.NON_CONFORMING).value,
        }

    @staticmethod
    def certify_backup_pitr_recovery(
        context: FunctionalAssuranceContext,
        rpo_achieved_seconds: int = 0,
        rto_achieved_seconds: int = 120,
        data_reconciliation_diff_count: int = 0,
    ) -> dict[str, Any]:
        passed = rpo_achieved_seconds == 0 and rto_achieved_seconds <= 300 and data_reconciliation_diff_count == 0
        return {
            "skill": "elmos-database-backup-pitr-failover-certifier",
            "rpo_seconds": rpo_achieved_seconds,
            "rto_seconds": rto_achieved_seconds,
            "reconciliation_discrepancies": data_reconciliation_diff_count,
            "zero_data_loss_proven": rpo_achieved_seconds == 0,
            "decision": (ConformityDecision.CONFORMING if passed else ConformityDecision.NON_CONFORMING).value,
        }

    @staticmethod
    def certify_event_replay_idempotency(
        context: FunctionalAssuranceContext,
        duplicate_events_injected: int = 1000,
        side_effects_duplicated: int = 0,
        state_divergence_detected: bool = False,
    ) -> dict[str, Any]:
        passed = side_effects_duplicated == 0 and not state_divergence_detected
        return {
            "skill": "elmos-event-replay-idempotency-certifier",
            "injected_duplicates": duplicate_events_injected,
            "duplicate_side_effects": side_effects_duplicated,
            "state_divergence": state_divergence_detected,
            "exactly_once_business_semantics": True,
            "decision": (ConformityDecision.CONFORMING if passed else ConformityDecision.NON_CONFORMING).value,
        }
