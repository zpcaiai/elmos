CREATE OR REPLACE VIEW billing.v_wallet_reconciliation AS
WITH ledger_agg AS (
    SELECT wallet_id,
           SUM(CASE
                 WHEN entry_type IN ('TOPUP','REFUND','BONUS','RELEASE') THEN amount
                 WHEN entry_type = 'USAGE' THEN -ABS(amount)
                 ELSE 0
               END) AS posted_effect
    FROM billing.ledger_entries
    GROUP BY wallet_id
),
reservation_agg AS (
    SELECT wallet_id,
           SUM(reserved_amount - consumed_amount)
             FILTER (WHERE status = 'ACTIVE') AS active_reserved
    FROM billing.credit_reservations
    GROUP BY wallet_id
)
SELECT
    w.id AS wallet_id,
    wb.available_balance,
    wb.reserved_balance,
    COALESCE(la.posted_effect, 0) AS posted_effect,
    COALESCE(ra.active_reserved, 0) AS active_reserved
FROM billing.wallets w
JOIN billing.wallet_balances wb ON wb.wallet_id = w.id
LEFT JOIN ledger_agg la ON la.wallet_id = w.id
LEFT JOIN reservation_agg ra ON ra.wallet_id = w.id;

CREATE OR REPLACE VIEW billing.v_model_margin AS
SELECT
    tue.model_call_id,
    tue.provider,
    tue.model,
    tue.provider_total_cost,
    tue.customer_credit_cost,
    tue.customer_credit_cost - tue.provider_total_cost AS nominal_margin_value
FROM billing.token_usage_events tue;
