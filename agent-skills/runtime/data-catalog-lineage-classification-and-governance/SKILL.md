---
name: data-catalog-lineage-classification-and-governance
description: Catalog database, lakehouse, pipeline, report, metric, model, and data-product assets with ownership, lineage, classification, access, masking, retention, residency, and deletion policy. Use for data governance baselines, migration gates, sensitive-data propagation, and decommission readiness.
---

# Data Governance

## Build the catalog

- Catalog databases, schemas, tables, columns, views, files, lakehouse tables, topics, pipelines, models, reports, metrics, and data products.
- Record technical owner, business owner, steward, security owner, platform owner, domain, description, schema, location, quality, SLA, consumers, retention, and access.
- Capture system, database, table, column, job, query, report, metric, and model-feature lineage.
- Label lineage source and confidence as authoritative, verified, inferred, observed, or unknown.

## Propagate policy

- Classify public, internal, confidential, restricted, personal, financial, health, authentication, and secret data.
- Apply read, write, export, share, mask, tokenize, retain, delete, legal-hold, region, and model-use policies.
- Verify masks and row/column access in databases, lakehouse copies, BI, exports, and caches.
- Propagate deletion through transactions, replicas, lakehouse, extracts, report cache, feature store, training data, and backup policy, subject to legal hold.

## Gate cutover

- Require ownership, classification, access mapping, retention, deletion path, sufficient lineage, and permitted region.
- Block production cutover on missing critical ownership, masking loss, unauthorized region, broken delete propagation, or governance-policy regression.
