# ADR-0052: AI platform with independent evaluation and risk authority

## Status

Accepted on 2026-07-22.

## Decision

Implement Batch 23 as one AI control domain for predictive ML, LLM applications, RAG and Agents while keeping data, reproducibility, evaluation, safety, Responsible AI and cost as non-compensating gates. A Worker may train or deploy only through scoped Runners; it cannot judge its own release. Store projections in `ai_platform`.

## Consequences

Model, Prompt, index and Agent-tool versions travel in one release bundle. Human oversight and risk acceptance remain outside the Worker. Missing GPU, provider, Dataset or review evidence cannot become a simulated pass.
