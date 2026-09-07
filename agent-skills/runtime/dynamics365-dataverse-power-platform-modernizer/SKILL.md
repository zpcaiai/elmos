---
name: dynamics365-dataverse-power-platform-modernizer
description: Modernize Dynamics 365, Dataverse, and Power Platform environments, Solutions, layers, tables, forms, apps, plugins, custom APIs, Power Automate flows, security roles, variables, and connection references. Use for source-driven ALM, managed Solution promotion, layer conflict analysis, and low-code governance.
---

# Dynamics and Power Platform Modernization

## Execute

1. Inventory environment, Solution, publisher, layers, table, column, relationship, form, view, app, flow, rule, plugin, custom API, connector, role, environment variable, and connection reference.
2. Establish source control plus versioned Solution artifact plus environment deployment as the target truth.
3. Distinguish unmanaged, managed, patch, upgrade, hotfix, and legacy default layers.
4. Resolve base, managed, unmanaged, active, override, dependency, and conflict layers before claiming deployment success.
5. Require owner, purpose, trigger, data classification, connection, environment, criticality, DLP, tests, and deployment path for every low-code app or flow.
6. Validate Dataverse row ownership, business units, alternate keys, audit, security, and plugin side effects.

## Guardrails

Do not overwrite a production-only baseline, put secrets in connection references, assume a managed upgrade defeated an active unmanaged layer, or treat low code as low risk.
