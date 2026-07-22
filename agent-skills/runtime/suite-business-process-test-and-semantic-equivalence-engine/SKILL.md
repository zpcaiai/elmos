---
name: suite-business-process-test-and-semantic-equivalence-engine
description: Validate enterprise suite configuration, extensions, APIs, workflows, data migration, end-to-end business processes, finance, inventory, security, reports, performance, batch, and Cutover semantics. Use for ERP or CRM equivalence, approved standardization differences, and independent hard-gate evidence.
---

# Suite Process and Semantic Validation

## Execute

1. Pin source and target artifacts, company, country, module, process variant, data set, users, integrations, and environment.
2. Execute only in an approved suite sandbox with synthetic company, customer, supplier, products, ledger, inventory, workflow users, and virtualized external systems.
3. Assert document, status, approval, inventory, ledger, tax, messages, audit, report, allowed action, and denied action.
4. Keep configuration, unit extension, API, workflow, integration, process, data, financial, inventory, security, report, performance, batch, and Cutover results separate.
5. Classify `EXACT`, `BUSINESS_EQUIVALENT`, `STANDARDIZED_APPROVED`, `EXPECTED_DIFFERENCE`, `REGRESSION`, or `INCONCLUSIVE`.
6. Require named Business Owner approval for every `STANDARDIZED_APPROVED` difference.
7. Build regression packs by module, country, company, process variant, and criticality.

## Hard gates

Financial, inventory, SoD, report security, and end-to-end process gates fail independently. A single-module pass or equal total does not authorize Cutover.
