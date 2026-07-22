
# Batch 31 Data Safety Policy

## Default rules

- Discovery uses read-only, least-privilege credentials.
- Development and certification use disposable databases, clones, masked snapshots, or synthetic data.
- No production write, DDL, lock-heavy query, full-table scan, data export, or workload capture occurs without a separately approved operational plan.
- Credentials, secrets, raw production values, and regulated data do not enter skill files, prompts, logs, public corpora, or shared evidence.
- Query text and plans are scrubbed according to tenant policy; literals are parameterized or tokenized when practical.
- Backfill, CDC, reconciliation, and repair jobs are idempotent, checkpointed, bounded, and reversible or forward-recoverable.
- Legal hold, retention, residency, and customer data-classification policies override deletion and sampling.
- Customer-private data, SQL, routines, plans, and corpus cases remain isolated and are never promoted to public packs without authorization and sanitization.

## Prohibited certification shortcuts

- comparing only row counts;
- using aggregate equality to ignore detail differences;
- widening numeric tolerances after a failure;
- disabling constraints, triggers, row security, or tests to pass;
- converting money to floating point;
- ignoring collation or time-zone differences;
- executing replay workloads against authoritative production sinks;
- certifying from generated DDL without real target execution.
