---
name: bi-semantic-layer-report-and-metric-modernizer
description: Inventory BI artifacts and centralize versioned, owned metrics and semantic models while preserving results, security, refresh, usage, and business definitions. Use for SSRS, Power BI, Tableau, Cognos, Qlik, Excel, Looker, Superset, dbt Semantic Layer, or custom-report migration.
---

# BI and Semantic Modernization

## Inventory

- Inventory reports, dashboards, datasets, extracts, workbooks, measures, calculated fields, filters, parameters, drill paths, security rules, schedules, and subscriptions.
- Record usage through views, users, exports, subscriptions, embedding, APIs, executive use, and regulatory use before retirement.
- Map refresh schedule, incremental windows, gateways, credentials, dataset sizes, failures, durations, and dependencies.

## Govern metrics

- Define metric name, domain, owner, formula, grain, filter, timezone, currency, version, and effective date in a tool-neutral contract.
- Model entities, dimensions, measures, metrics, time grains, relationships, filters, and segments.
- Mark similar names as DUPLICATE_METRIC_CANDIDATE; never merge or retire them automatically.
- Treat dbt or another semantic provider as an adapter, not the canonical identity.

## Validate independently

- Compare rows, totals, metrics, filters, dates, currency, locale, sort, drill, refresh, export, and visual behavior.
- Validate row-level security by effective user, role, tenant, region, and hierarchy as an independent critical gate.
- Require the business owner to approve metric-definition changes.
- Do not let visual similarity replace numeric and semantic equivalence.
