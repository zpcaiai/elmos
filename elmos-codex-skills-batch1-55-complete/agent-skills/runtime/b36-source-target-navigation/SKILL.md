---
name: b36-source-target-navigation
description: "Implement precise bidirectional source-target navigation over versioned many-to-many source maps with rename merge split confidence freshness and unsupported-region handling."
---

# Skill 1294: b36-source-target-navigation

## Use this skill when

- Developers need to navigate from migrated target code back to source semantics and vice versa.
- Diagnostics, reviews, evidence, and conflicts require a shared mapping service.

## Domain-specific risks and invariants

- Line-only mappings become stale after formatting, manual edits, renames, merges, or splits.
- Incorrect navigation can cause reviewers or repair agents to modify the wrong code.

## Workflow

1. Define stable source, PSP, UIR, FCM, target, patch, and test node identities.
2. Implement versioned many-to-many mapping edges with ranges, semantic anchors, confidence, provenance, and ownership.
3. Implement incremental map updates after generation, formatting, manual edits, merges, and refactors.
4. Expose navigation through IDE, CLI, PR, API, and evidence views with freshness checks.
5. Add accuracy, ambiguity, stale-map, rename, split, merge, generated/manual, and unsupported-region corpora.

## Required repository outputs

- `navigation/map.json`, mapping service/index, generated bindings and query APIs
- Accuracy benchmark, stale-map detection evidence, source/target navigation traces
- Explicit unmapped and approximate regions with owners

## Verification

- Validate graph references, path scope, digests, document versions, and mapping confidence.
- Run a labeled benchmark and measure exact/approximate/incorrect/unmapped rates.
- Test formatting, rename, split, merge, manual edit, conflict resolution, and artifact upgrade.
- Reject navigation when freshness cannot be established.

## Stop and escalate when

- A P0 mapping points to a different semantic symbol.
- Freshness cannot be determined after a repository or artifact change.
- Approximate or unmapped regions are hidden from the user.
- Paths escape the approved workspace or tenant.

## Definition of done

- Bidirectional P0 navigation meets the approved accuracy threshold.
- Stale or ambiguous mappings fail safely.
- All edges are provenance-linked and versioned.
- Navigation behavior is consistent across IDE, CLI, PR, and evidence views.
