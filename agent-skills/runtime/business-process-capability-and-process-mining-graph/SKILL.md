---
name: business-process-capability-and-process-mining-graph
description: Build business capability and actual process graphs from suite configuration, workflow, transaction and event logs, integrations, interviews, and manual work. Use for process mining, variant analysis, shadow-process discovery, control mapping, and business-owner baselining.
---

# Business Process Graph

## Model

1. Separate value stream, business capability, end-to-end process, process variant, step, system transaction, and business object.
2. Keep vendor-standard, configured-standard, customized, manual-augmented, shadow, and unknown paths distinct.
3. Fuse suite models, workflow metadata, runtime logs, status history, audit, integrations, user interviews, and documented manual procedures.
4. Quantify variants, rework, loops, delays, bottlenecks, exceptions, and compliance deviations.
5. Represent Excel, email, chat, desktop scripts, Access databases, and manual repair as in-scope steps.
6. Attach approvals, four-eyes controls, limits, segregation, reconciliation, and exception controls to steps.

## Evidence

Progress evidence from `DECLARED` through `CONFIGURED`, `RUNTIME_OBSERVED`, `USER_CONFIRMED`, and `BUSINESS_APPROVED`. Do not treat technical configuration as the only business truth.

## Gate

Require Business Owner approval for the target process and every accepted standardization difference.
