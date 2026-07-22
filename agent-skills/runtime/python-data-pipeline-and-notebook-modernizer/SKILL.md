---
name: python-data-pipeline-and-notebook-modernizer
description: Modernize Python scripts, notebooks, Airflow, Celery, Spark, cron, and batch pipelines into reproducible, testable, observable workflows with explicit data and scheduling contracts. Use for notebook hidden state, pipeline DAGs, side effects, retries, backfills, or data-contract migration.
---

# Python Data Pipeline and Notebook Modernizer

## Reconstruct the workflow

Inventory cron/shell/scripts, notebooks, Airflow, Celery, Spark, Dask/Luigi/Prefect/Dagster, database procedures, watchers, functions, and manual steps. Build source/extract/transform/validate/model/load/publish/notify nodes with data, schedule, control, retry, and side-effect edges.

Define input/output schema, key, ordering, null, timezone, encoding, partition, freshness, volume, and quality rules for each stage. Identify database/file/object/message/API/SFTP/warehouse dependencies.

## Eliminate hidden state deliberately

Restart the Notebook kernel and run all cells from a clean state. Track definitions, reads, files, imports, side effects, outputs, execution order, widgets, hard-coded paths, manual steps, and inline secrets. Mark `NOTEBOOK_HIDDEN_STATE` on failure. Choose keep-as-report, package, pipeline, testable functions, or scheduled job; never delete notebooks automatically.

Compare Airflow IDs/schedule/catchup/retry/pools/XCom/backfill/datasets, Celery queue/ack/retry/serialization/idempotency/beat, and Spark schema/UDF/Arrow/partition/shuffle/checkpoint behavior.

Run baselines with shadow endpoints, stubs, test databases, transactions, or dry-run for writes, deletes, notifications, messages, uploads, billing, and external APIs. Accept only after schedule, dependency, schema, counts/hashes, ordering, retry, idempotency, backfill, partial failure, delivery semantics, runtime, and resources are evidenced.

