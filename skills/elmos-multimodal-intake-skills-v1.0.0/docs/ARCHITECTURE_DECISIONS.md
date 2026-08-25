# Architecture Decisions

This file records package-level decisions. Implementation-specific choices should be copied into individual ADR files using `templates/ADR.md`.

## ADR-001 — Unified multimodal Content IR

**Status:** Accepted

Provider-specific output is normalized into versioned ContentBlock and SourceAnchor objects. Downstream agents do not independently parse every file type.

**Consequences:** stable downstream interface and provenance; requires normalization/eval investment.

## ADR-002 — Immutable originals and versioned derivatives

**Status:** Accepted

Raw asset bytes, package manifests, package versions, corrections, requirements and checkpoints are immutable versions.

**Consequences:** reliable recovery/audit/diff; requires retention and storage lifecycle.

## ADR-003 — Raw corpus is outside model context

**Status:** Accepted

Corpus storage/index size is separate from active model context. A model request contains a selected evidence bundle.

**Consequences:** can handle very large projects; retrieval and integrity become mandatory.

## ADR-004 — Dynamic model capability registry

**Status:** Accepted

Context/output/multimodal/tool limits come from versioned capability snapshots. Dated Codex parity values are fixtures, not scattered constants.

**Consequences:** safe model changes and historical reproducibility; needs source freshness and conservative fallback.

## ADR-005 — No silent truncation

**Status:** Accepted

Overflow causes explicit ranking, compression, partition, reroute or failure. It never silently drops input.

**Consequences:** transparent but more complex state management.

## ADR-006 — Structured compaction

**Status:** Accepted

Compaction produces typed task state with sources and retrieval keys, not a free-form summary.

**Consequences:** reliable long tasks; schema and integrity testing required.

## ADR-007 — Durable server-side task state

**Status:** Accepted

Client connections are subscriptions. Workflow state, checkpoints and progress persist server-side.

**Consequences:** disconnect/restart resilience; requires idempotency and outbox.

## ADR-008 — Side-effect and usage ledgers

**Status:** Accepted

External actions and provider usage have idempotent ledgers/receipts.

**Consequences:** prevents duplicate effects/costs; requires reconciliation paths.

## ADR-009 — Ingestion and code execution are separate trust zones

**Status:** Accepted

File/document/archive parsing never executes project code. Build/test runs in a distinct controlled sandbox.

**Consequences:** substantially lower attack surface; some project detection must use static methods.

## ADR-010 — Archive extraction is streamed and handle-relative

**Status:** Accepted

Archive safety is enforced before and during writes with cumulative limits and safe root-relative operations.

**Consequences:** secure against common traversal/bomb patterns; implementation is platform-specific and needs fuzzing.

## ADR-011 — Ignore creates analysis views

**Status:** Accepted

Ignore/generated/vendored decisions do not delete entries from the canonical manifest.

**Consequences:** transparent and reversible; more metadata.

## ADR-012 — Tasks pin package versions

**Status:** Accepted

A running task uses a fixed project package version. Rebase is explicit.

**Consequences:** reproducibility; concurrent updates require user-visible version choices.

## ADR-013 — Source anchors are required evidence

**Status:** Accepted

Key requirements, decisions, defects and conclusions must link to original evidence.

**Consequences:** trustworthy output and review; parser anchors need quality monitoring.

## ADR-014 — Security policy outranks content and ignore rules

**Status:** Accepted

Documents, prompts and ignore files cannot relax quarantine, tool permissions, egress or secret handling.

**Consequences:** secure default; requires privileged, audited exception flow.

## ADR-015 — ETA is machine wall-clock runtime

**Status:** Accepted

User-facing task estimates describe Elmos autonomous processing time. Human implementation effort is a separate planning concept.

**Consequences:** requires historical telemetry and calibration.

## ADR-016 — Provider abstraction with privacy-aware routing

**Status:** Accepted

OCR/ASR/vision/LLM providers are replaceable and selected by modality, privacy, quality, cost, latency and region.

**Consequences:** reduces lock-in; provider eval and normalization are required.

## Open implementation decisions

The implementing team must create ADRs for:

- workflow engine and queue;
- database/RLS strategy;
- object storage and encryption;
- parser sandbox technology;
- full-text/vector/graph technologies;
- model capability source synchronization;
- code execution sandbox;
- tenant quota/pricing model;
- backup/DR;
- deployment topology.
