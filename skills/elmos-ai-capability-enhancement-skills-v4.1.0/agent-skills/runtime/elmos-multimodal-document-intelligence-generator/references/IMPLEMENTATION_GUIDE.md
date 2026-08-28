# Implementation Guide — Multimodal Document Intelligence Generator

## Purpose

Generate document ingestion systems for text, layout, tables, figures, scans, audio and video with typed provenance and quality-aware retrieval artifacts.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Parser/OCR/model capability routing
2. Layout/table/figure semantic graph
3. Page/time-range source mapping
4. Quality confidence and human review
5. Multimodal embedding and citation

## Native acceptance corpus

- `ELMOS_MULTIMODAL_DOCUMENT_INTELLIGENCE_GENERATOR-01` — born-digital PDF
- `ELMOS_MULTIMODAL_DOCUMENT_INTELLIGENCE_GENERATOR-02` — scanned table
- `ELMOS_MULTIMODAL_DOCUMENT_INTELLIGENCE_GENERATOR-03` — figure/caption relation
- `ELMOS_MULTIMODAL_DOCUMENT_INTELLIGENCE_GENERATOR-04` — audio transcript timing
- `ELMOS_MULTIMODAL_DOCUMENT_INTELLIGENCE_GENERATOR-05` — low-confidence review
- `ELMOS_MULTIMODAL_DOCUMENT_INTELLIGENCE_GENERATOR-06` — citation source-map

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
