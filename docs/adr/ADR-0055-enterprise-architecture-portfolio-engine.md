# ADR-0055: Evidence graph for enterprise architecture and portfolio decisions

## Status

Accepted on 2026-07-22.

## Decision

Implement Batch 26 as an evidence graph and option-evaluation engine, not a drawing repository or automatic investment board. Source authority, confidence, timestamps and conflicts remain explicit. The engine can prepare an ADR, roadmap or investment decision but only an authorized human can approve it. Store projections in `enterprise_architecture`.

## Consequences

External frameworks and technology radars remain reference adapters. They cannot overwrite observed topology, declare benefits, approve exceptions, fund initiatives or retire applications.
