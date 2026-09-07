---
name: salesforce-org-metadata-and-extension-modernizer
description: Modernize Salesforce Org metadata, Apex, triggers, Flow, objects, fields, validation, Lightning, permissions, profiles, Named Credentials, packages, Platform Events, and CDC. Use for source-driven Salesforce ALM, packaging, order-of-execution analysis, event retention, and secure credential deployment.
---

# Salesforce Org Modernization

## Execute

1. Inventory Org, edition, object, field, record type, validation, formula, Apex, trigger, Flow, legacy process, Lightning, permissions, profile, Named Credential, integration, report, dashboard, and package.
2. Retrieve production metadata into a pinned baseline before restructuring packages or deploying changes.
3. Build the source-driven path: source control, scratch or sandbox validation, conflict detection, validated deployment, and production promotion.
4. Compare unpackaged metadata, unlocked, org-dependent unlocked, managed, and second-generation package boundaries; record dependency debt and reduction plan.
5. Build an order-of-execution graph across Apex, record-triggered Flow, validation, workflow, legacy Process Builder, and duplicate rules.
6. Treat Platform Event and CDC retention as a bounded replay window; reconcile data after gaps beyond it.
7. Package Named Credential metadata separately from target-environment principals and tokens.

## Guardrails

Do not make the production Org the only source, compute replay IDs, treat the event bus as permanent history, expose principals in packages, or infer business equivalence from deployment success.
