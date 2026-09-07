# ADR-0049: Enterprise Suite Modernization Engine

## Status

Accepted for Batch 21 repository scope on 2026-07-21.

## Decision

Add `ELMOS_ENTERPRISE_SUITE` as the eleventh independent execution engine. Reuse the existing tenant, workflow, authorization, Runner, evidence, quality, audit, billing, delivery, SCM, portfolio, integration, data and cutover control planes. Do not create a parallel platform around ERP, CRM, HCM, SCM or EPM products.

Normalize configuration, customization, extensions, business capabilities and versioned processes, canonical enterprise objects, master-data crosswalks, roles and segregation-of-duties, reports, integrations, usage and history into a vendor-neutral Suite Estate. Preserve vendor-specific behavior and unresolved ownership instead of inferring a clean-core or standardization decision.

Offer Keep and Govern, Technical Upgrade, System Conversion, Greenfield, Selective Data Transition, Cloud Reimplementation, Module Replacement, Composable Suite, Dual-Suite Coexistence, Full Replacement and Retire target profiles. Oracle EBS support duration is not treated as a forced migration signal. Clean Core is evaluated across process, extensions, data, integrations and operations. Power Platform solutions and Salesforce metadata packages remain source-controlled ALM artifacts.

External SAP, Oracle EBS/Fusion, Dynamics/Dataverse, Salesforce, Process Mining, MDM and Archive adapters default to read-only and `NOT_CONFIGURED`. Require short-lived leases and exact environment scopes for all Runner activity, sandbox authorization for business-process validation, data-migration authorization for data movement, and independent production approval for production or master-data authority changes.

The Worker cannot modify production configuration, publish transports or solutions, deploy Salesforce production metadata, modify user permissions, bulk-delete business data, accept process/financial/SOD differences, switch shared-master authority, or mutate Cutover/Decommission decisions. Cutover requires current independent configuration, master data, open-transaction, financial, inventory, process, role/SOD, report, integration, batch, rollback and owner evidence. Decommission adds a separate post-cutover stability, usage, archive, credential, license and legal-hold gate.

Use Flyway V23 because the existing product-ecosystem migration owns V22. Cover all 63 requested tenant objects by creating 62 projections and extending Batch 13's existing forced-RLS `business_capabilities` authority. Add tenant policies, stable identity constraints, append-only evidence protections and cross-tenant tests; existing shared identity, workflow, evidence, data, integration and audit objects remain authoritative.

## Consequences

Repository tests can prove contract integrity, deterministic policy, tenant and idempotency boundaries, fail-closed adapters, Skill integrity, and independent Cutover/Decommission decision logic. They cannot prove a customer suite was discovered, transformed, reconciled, deployed, cut over, or retired. Those remain external evidence gates and must stay `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or `BLOCKED` until executed in approved environments.

## Official design references

- Oracle E-Business Suite support: https://www.oracle.com/apac/support/premier/software/ebs/
- SAP Clean Core dimensions: https://www.sap.com/documents/2025/12/983d8327-327f-0010-bca6-c68f7e60039b.html
- Power Platform application lifecycle management: https://learn.microsoft.com/zh-cn/power-platform/alm/overview-alm
- Salesforce metadata deploy and retrieve: https://developer.salesforce.com/docs/platform/code-builder/guide/codebuilder-deploy-retrieve.html
