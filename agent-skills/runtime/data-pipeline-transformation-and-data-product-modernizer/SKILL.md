---
name: data-pipeline-transformation-and-data-product-modernizer
description: Modernize stored-procedure ETL, SSIS, ODI, Informatica, Python, Spark, Flink, Airflow, cron, SQL, dbt, and BI extracts into versioned transformations and owned data products. Use for pipeline graphs, batch/stream semantics, backfill, schema evolution, and OpenLineage-compatible evidence.
---

# Data Transformation Modernization

## Inventory the graph

- Model source, ingest, stage, clean, conform, transform, aggregate, serve, and publish nodes with explicit inputs and outputs.
- Choose keep-and-upgrade, SQL transformation, dbt, Spark batch, Flink stream, CDC materialization, data-product extraction, or manual redesign per pipeline.
- Preserve credentials, schedules, retry, checkpoints, resource budgets, and failure behavior.

## Define data products

- Assign owner, domain, inputs, outputs, schema, SLA, freshness, quality, access, retention, cost, consumers, and documentation.
- Declare BATCH_ONLY, STREAM_ONLY, LAMBDA_DUAL, STREAMING_PRIMARY_BATCH_REPAIR, or UNIFIED_TABLE semantics.
- Distinguish an exactly-once processing claim from exactly-once effect and at-least-once with idempotency.

## Govern evolution

- Version backfills, make them restartable, scope time windows, checkpoint progress, reconcile output, and isolate current incremental processing.
- Control add, rename, type, nullability, delete, default, nested, and partition evolution.
- Export job, run, and dataset lineage events with organization, snapshot, code version, and data contract references.
- Block on missing owners, non-replayable critical backfills, or unverifiable delivery semantics.
