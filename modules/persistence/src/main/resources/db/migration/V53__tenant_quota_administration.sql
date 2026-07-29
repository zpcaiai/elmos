-- Tenant quota administration.
--
-- Version note: V52 is deliberately skipped. docs/p0-implementation/sql/ holds a
-- planned V52__execution_job_queue_and_runner_fleet.sql that has not been applied
-- yet; taking V52 here would make the two collide at migrate time. Flyway tolerates
-- gaps in the version sequence, so leaving V52 free is the cheaper mistake.
--
-- An operator adjusting a tenant's allowance is a subscription lifecycle event and
-- belongs in the same append-only log as every other one, so the existing event_type
-- CHECK is widened rather than a second audit table being introduced. A second table
-- would let a reader reconstruct a subscription's history and silently miss the
-- adjustments.

ALTER TABLE subscription_events
    DROP CONSTRAINT subscription_events_self_service_type;

ALTER TABLE subscription_events
    ADD CONSTRAINT subscription_events_self_service_type CHECK (
        event_type IS NULL OR event_type IN (
            'TRIAL_GRANTED', 'CHECKOUT_COMPLETED', 'INVOICE_PAID',
            'PAYMENT_FAILED', 'CANCEL_SCHEDULED', 'CANCELLED',
            'PLAN_CHANGED', 'REFUNDED', 'EXPIRED',
            'QUOTA_ADJUSTED'
        )
    );

-- The adjustment's before/after values and the operator's reason live in the
-- event payload. payload is already NOT NULL DEFAULT '{}'::jsonb, so no column is
-- added; this constraint makes the shape mandatory for this one event type instead
-- of leaving it to caller discipline. An adjustment whose payload does not say what
-- changed is not an audit record.
ALTER TABLE subscription_events
    ADD CONSTRAINT subscription_events_quota_adjustment_payload CHECK (
        event_type IS DISTINCT FROM 'QUOTA_ADJUSTED' OR (
            payload ? 'quotaAllocationId'
            AND payload ? 'reasonCode'
            AND payload ? 'previousTokenLimit'
            AND payload ? 'previousCreditLimit'
            AND payload ? 'tokenLimit'
            AND payload ? 'creditLimit'
        )
    );

COMMENT ON CONSTRAINT subscription_events_quota_adjustment_payload ON subscription_events IS
    'A QUOTA_ADJUSTED event must carry the allocation, the operator reason code and both '
    'the previous and the new limits. Without the previous values the log records that '
    'something changed but not what it changed from, which cannot be reviewed.';
