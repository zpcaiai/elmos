# Evaluation and Continuous Certification

## Data plane

Datasets carry source, consent, privacy class, lineage, deduplication, difficulty, human labels, holdout status, contamination result, version, expiry and revocation. Production traces are not automatically training or evaluation data.

## Judge plane

LLM judges are non-authoritative unless paired with an independent oracle and explicit bounded policy. Calibration measures false pass, false fail, agreement, confidence intervals, ordering/style bias and self-preference.

## Drift plane

Provider fingerprints cover resolved model, region, tool behavior, structured output, safety/refusal, latency, token accounting and cache behavior. Critical drift invalidates dependent evidence and triggers shadow evaluation, re-certification or rollback.
