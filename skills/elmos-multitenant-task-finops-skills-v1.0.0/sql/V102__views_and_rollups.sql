-- Rebuildable financial and operational projections.
SET search_path = elmos, public;

CREATE OR REPLACE VIEW task_usage_cost_v AS
SELECT
  u.tenant_id,
  u.account_id,
  u.project_id,
  u.task_id,
  u.task_run_id,
  u.base_currency AS reporting_currency,
  max(u.ingested_at) AS as_of,
  sum(u.base_cost) FILTER (WHERE u.cost_status IN ('POSTED','FINAL','CORRECTION')) AS posted_actual_cost,
  sum(u.base_cost) FILTER (WHERE u.cost_status = 'FINAL') AS final_usage_cost,
  sum(u.base_cost) FILTER (WHERE u.usage_type LIKE 'MODEL_%') AS model_cost,
  sum(u.base_cost) FILTER (WHERE u.usage_type LIKE 'COMPUTE_%' OR u.usage_type LIKE 'MEMORY_%' OR u.usage_type LIKE 'GPU_%') AS compute_cost,
  sum(u.base_cost) FILTER (WHERE u.usage_type LIKE 'STORAGE_%' OR u.usage_type LIKE 'EGRESS_%') AS storage_network_cost,
  sum(u.base_cost) FILTER (WHERE u.usage_type LIKE 'RETRY_%') AS retry_cost,
  sum(u.base_cost) FILTER (WHERE u.usage_type LIKE 'RECOVERY_%') AS recovery_cost,
  count(*) AS usage_event_count
FROM usage_event u
GROUP BY u.tenant_id, u.account_id, u.project_id, u.task_id, u.task_run_id, u.base_currency;

CREATE OR REPLACE VIEW task_revenue_v AS
SELECT
  a.tenant_id,
  a.task_id,
  r.base_currency AS reporting_currency,
  max(GREATEST(r.posted_at, a.created_at)) AS as_of,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'CHARGE') AS charged,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'CREDIT') AS credits,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'REFUND') AS refunds,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'RECOGNITION') AS recognized_revenue,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'COLLECTION') AS collected_cash,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'PAYMENT_FEE') AS payment_fees,
  sum(a.allocated_amount * r.fx_rate) FILTER (WHERE r.kind = 'TAX') AS taxes,
  count(*) AS allocation_count
FROM revenue_allocation a
JOIN revenue_entry r
  ON r.id = a.source_revenue_entry_id
 AND r.tenant_id = a.tenant_id
GROUP BY a.tenant_id, a.task_id, r.base_currency;

CREATE OR REPLACE VIEW task_profitability_v AS
SELECT
  t.tenant_id,
  t.account_id,
  t.project_id,
  t.id AS task_id,
  t.task_type,
  t.state,
  COALESCE(c.reporting_currency, r.reporting_currency) AS reporting_currency,
  GREATEST(COALESCE(c.as_of, '-infinity'::timestamptz), COALESCE(r.as_of, '-infinity'::timestamptz)) AS as_of,
  COALESCE(c.posted_actual_cost, 0) AS posted_actual_cost,
  COALESCE(r.recognized_revenue, 0) AS recognized_revenue,
  COALESCE(r.collected_cash, 0) AS collected_cash,
  COALESCE(r.charged, 0) - COALESCE(r.credits, 0) - COALESCE(r.refunds, 0) AS net_billed_revenue,
  COALESCE(r.recognized_revenue, 0) - COALESCE(c.posted_actual_cost, 0) AS gross_profit,
  CASE
    WHEN COALESCE(r.recognized_revenue, 0) = 0 THEN NULL
    ELSE (COALESCE(r.recognized_revenue, 0) - COALESCE(c.posted_actual_cost, 0))
         / r.recognized_revenue
  END AS gross_margin
FROM task t
LEFT JOIN (
  SELECT tenant_id, task_id, reporting_currency, max(as_of) AS as_of,
         sum(posted_actual_cost) AS posted_actual_cost
  FROM task_usage_cost_v
  GROUP BY tenant_id, task_id, reporting_currency
) c
  ON c.tenant_id = t.tenant_id AND c.task_id = t.id
LEFT JOIN task_revenue_v r
  ON r.tenant_id = t.tenant_id AND r.task_id = t.id
 AND (c.reporting_currency IS NULL OR r.reporting_currency = c.reporting_currency);

CREATE OR REPLACE VIEW account_concurrency_v AS
SELECT
  s.account_id,
  count(*) FILTER (WHERE s.task_id IS NOT NULL) AS active_slots,
  3::integer AS maximum_slots,
  jsonb_agg(
    jsonb_build_object(
      'slot_no', s.slot_no,
      'tenant_id', s.tenant_id,
      'task_id', s.task_id,
      'lease_generation', s.lease_generation,
      'lease_expires_at', s.lease_expires_at
    )
    ORDER BY s.slot_no
  ) FILTER (WHERE s.task_id IS NOT NULL) AS occupied
FROM account_task_slot s
GROUP BY s.account_id;

-- Refresh/rebuild task cost projection from immutable usage ledger.
CREATE OR REPLACE FUNCTION rebuild_task_cost_summary(
  p_tenant_id uuid,
  p_task_id uuid,
  p_reporting_currency char(3)
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_posted numeric(30,12);
  v_final numeric(30,12);
  v_as_of timestamptz;
BEGIN
  SELECT
    COALESCE(sum(base_cost) FILTER (WHERE cost_status IN ('POSTED','FINAL','CORRECTION')), 0),
    CASE
      WHEN bool_and(cost_status IN ('FINAL','CORRECTION')) THEN COALESCE(sum(base_cost), 0)
      ELSE NULL
    END,
    max(ingested_at)
  INTO v_posted, v_final, v_as_of
  FROM usage_event
  WHERE tenant_id = p_tenant_id
    AND task_id = p_task_id
    AND base_currency = p_reporting_currency;

  INSERT INTO task_cost_summary (
    task_id, tenant_id, posted_actual_cost, final_actual_cost,
    reporting_currency, status, usage_event_watermark, as_of,
    reconciliation_status, updated_at
  )
  VALUES (
    p_task_id, p_tenant_id, v_posted, v_final,
    p_reporting_currency,
    CASE WHEN v_final IS NULL THEN 'POSTING'::financial_status ELSE 'FINAL'::financial_status END,
    v_as_of, COALESCE(v_as_of, clock_timestamp()),
    CASE WHEN v_final IS NULL THEN 'UNRECONCILED' ELSE 'COMPLETE' END,
    clock_timestamp()
  )
  ON CONFLICT (task_id) DO UPDATE
  SET posted_actual_cost = EXCLUDED.posted_actual_cost,
      final_actual_cost = EXCLUDED.final_actual_cost,
      reporting_currency = EXCLUDED.reporting_currency,
      status = EXCLUDED.status,
      usage_event_watermark = EXCLUDED.usage_event_watermark,
      as_of = EXCLUDED.as_of,
      reconciliation_status = EXCLUDED.reconciliation_status,
      updated_at = clock_timestamp();
END;
$$;
