---
name: b37-extension-eol-data-portability-exit
description: Implement extension deprecation end-of-life customer migration data portability configuration export uninstall archival retention and final publisher exit.
---

# Skill B37-X15: b37-extension-eol-data-portability-exit

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- EOL never strands customer-owned data or silently removes critical workflows.
- Security-compromised releases may skip ordinary timelines but still require safe export and notification where possible.
- Final payout and archival follow unresolved dispute and legal-hold rules.

## Workflow

1. Define deprecation announcement, support end, security-only period, installation stop, execution stop, EOL, and archive dates.
2. Inventory active tenants, dependencies, configuration, state, data, workflows, licenses, support obligations, and replacement options.
3. Provide replacement guidance, configuration export, data portability, migration tooling, and tested uninstall.
4. Drain dependencies, installations, credentials, jobs, billing, payouts, support, and runtime resources.
5. Archive immutable releases, evidence, legal records, and required support artifacts while deleting data according to policy.

## Required repository outputs

- `lifecycle/eol-policy.json`
- tenant migration records, portability artifacts, uninstall evidence, archive and retention records

## Verification

- Run `validate_eol_policy.py`.
- Exercise normal EOL, publisher exit, replacement migration, portability, uninstall, and residual-dependency detection.

## Stop and escalate when

- Active critical dependency or customer workflow has no replacement or approved exception.
- Data ownership, portability, retention, or legal hold is unresolved.

## Definition of done

- All tenants exit or formally accept exceptions, residual dependencies are zero, and data/configuration remain portable and governed.
