---
name: enterprise-canonical-master-data-and-business-object-model
description: Define cross-suite enterprise business objects, field semantics, identities, relationships, and data authority across SAP, Oracle, Dynamics, Salesforce, and external platforms. Use when creating canonical master, reference, transaction, balance, document, event, configuration, or history contracts.
---

# Enterprise Business Object Model

## Model

1. Separate suite-native objects from enterprise business concepts.
2. Classify each object as master, reference, transaction, balance, document, event, configuration, or history.
3. Record enterprise ID, native ID, legacy ID, external ID, partner or country identity, role, and validity.
4. Define every field's business meaning, owner, type, unit, currency, timezone, code set, classification, validity, and source of truth.
5. Declare source, shared, target, reference-only, archived, or unknown authority.
6. Version relationships and identity Crosswalks.

## Guardrails

- Never merge objects solely because names match.
- Distinguish billing account, selling relationship, entitled organization, and other contextual roles.
- Preserve semantic conflicts and unknown authority as explicit blockers.
- Publish approved object semantics into data and integration contracts.

## Output

Produce enterprise-object definitions, identity roles, relationship graph, authority map, and schema references.
