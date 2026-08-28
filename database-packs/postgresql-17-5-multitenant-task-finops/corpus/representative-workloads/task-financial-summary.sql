-- Representative shape only; production and provider reconciliation remain NOT_RUN.
SELECT task_id, currency, final_cost_minor, recognized_revenue_minor,
       gross_profit_minor, gross_margin_ratio, reconciliation_status, qualification
  FROM mtf_task_financial_summary;
