---
name: enterprise-suite-elmos-unified-evidence-integration
description: Map Enterprise Suite Estate, configuration, customization, Clean Core, process, master data, migration, roles, SoD, finance, inventory, ALM, Cutover, archive, and Decommission into ELMOS Evidence, Risk, Audit, Portfolio, Billing, and offline Evidence Packs. Use when integrating suite results with other ELMOS engines and control planes.
---

# Enterprise Suite Unified Evidence

## Integrate

1. Set scope `ENTERPRISE_SUITE`, engine `ELMOS_ENTERPRISE_SUITE`, schema version, exact artifact reference, tenant, environment, suite release, and observation window.
2. Link Suite Estate, configuration, customization, process graph, Clean Core, business objects, master quality, target plan, vendor modernization, data migration, integration, role, process validation, parallel run, Cutover, and Decommission evidence.
3. Map core modifications to upgrade risk, unknown customizations to governance risk, master conflicts to business-data risk, SoD conflicts to access-control risk, financial failures to critical financial-integrity risk, and unknown report consumers to Decommission risk.
4. Link application, database/data, integration, infrastructure, security, test-quality, and delivery evidence through Portfolio dependency edges.
5. Preserve separate checks for estate, process, Clean Core, master data, migration, integration, role/SoD, finance, equivalence, and Cutover.
6. Audit configuration classification, extension deployment, master merges, roles, SoD exceptions, data migration, accepted financial differences, user Cutover, legacy read-only, archive, and Decommission.

## Guardrails

Keep the business-process gate above individual technical artifacts. Never convert `NOT_RUN`, missing, stale, unknown, or inconclusive evidence into pass. Produce an offline-verifiable Evidence Pack with hashes and provenance.
