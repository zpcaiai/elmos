# Implementation Guide — Fine-Tuning and Adapter Training Pipeline Generator

## Purpose

Generate governed SFT, preference, distillation and PEFT/LoRA pipelines with data lineage, evaluation, safety, reproducibility and promotion gates.

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

1. compile dataset, split and consent contracts
2. generate reproducible training and checkpoint pipeline
3. track base model, adapter and tokenizer lineage
4. run capability, safety and regression evaluation
5. promote via registry, canary and rollback

## Native acceptance corpus

- `ELMOS_FINE_TUNING_ADAPTER_TRAINING_PIPELINE_GENERATOR-01` — native scenario: compile dataset, split and consent contracts
- `ELMOS_FINE_TUNING_ADAPTER_TRAINING_PIPELINE_GENERATOR-02` — native scenario: generate reproducible training and checkpoint pipeline
- `ELMOS_FINE_TUNING_ADAPTER_TRAINING_PIPELINE_GENERATOR-03` — native scenario: track base model, adapter and tokenizer lineage
- `ELMOS_FINE_TUNING_ADAPTER_TRAINING_PIPELINE_GENERATOR-04` — native scenario: run capability, safety and regression evaluation
- `ELMOS_FINE_TUNING_ADAPTER_TRAINING_PIPELINE_GENERATOR-05` — native scenario: promote via registry, canary and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
