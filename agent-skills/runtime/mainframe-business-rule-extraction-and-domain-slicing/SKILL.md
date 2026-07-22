---
name: mainframe-business-rule-extraction-and-domain-slicing
description: Extract evidence-linked mainframe business-rule candidates and capability slices from COBOL, copybooks, JCL, CICS, IMS, Db2, VSAM, screens, files, calendars, and runtime traces. Use for business-rule catalogs, domain decomposition, AI-assisted explanation, or extraction planning.
---

# Mainframe Rule Extraction and Domain Slicing

## Extract candidates

1. Capture validation, calculation, eligibility, routing, pricing, accounting, state, authorization, scheduling, transformation, and error-handling candidates.
2. Record inputs, conditions, outputs, side effects, source locations, runtime observations, tests, confidence, and owner.
3. Grade evidence as source-direct, source-inferred, runtime-observed, test-confirmed, or business-approved.
4. Keep AI and tool explanations as candidates; only `BUSINESS_APPROVED` rules are authoritative.
5. Preserve unobserved seasonal, error, regulatory, rare, and dynamic-call paths until evidence and an owner justify disposition.

## Slice capabilities

- Combine business capability, transaction boundary, data ownership, rule cohesion, call graph, team, change frequency, and runtime affinity.
- Mark cross-cutting, data-coupled, transaction-coupled, batch-coupled, unsafe, and unknown slices explicitly.
- Require owner approval before a rule catalog or slice drives transformation or retirement.
