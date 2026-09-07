---
name: customization-extension-clean-core-and-technical-debt-classifier
description: Classify enterprise suite customizations and extensions by business value, observed use, support boundary, upgrade stability, coupling, ownership, and Clean Core status. Use for SAP Clean Core, extension placement, technical-debt decisions, and governed retirement candidates.
---

# Customization and Clean Core Classification

## Classify

1. Identify core modifications, in-app, side-by-side, low-code, integration, reporting, data, temporary compatibility, and unsupported customizations.
2. Evaluate business value separately from technical risk: differentiation, regulation, industry, localization, operational need, duplicate standard, obsolete, or unknown.
3. Score the five Clean Core dimensions: business process, extensibility, data, integration, and operations.
4. Record whether the dependency uses a public API, released extension point, supported metadata, internal API, direct database, screen automation, or unknown boundary.
5. Select `KEEP`, standard reconfiguration, supported in-app rebuild, side-by-side, domain service, integration layer, standard replacement, retirement, or manual review.

## Guardrails

- Never equate Clean Core with zero extensions.
- Treat unused assets as candidates until seasonal use and ownership are resolved.
- Require owner, value approval, test, target placement, due date, and removal or exception expiry.
- Escalate direct database and internal API coupling as upgrade risk.

## Output

Produce versioned classification, debt, placement, owner, evidence, and exit-plan records.
