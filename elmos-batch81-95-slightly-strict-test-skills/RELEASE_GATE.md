# Release Gate

Batch 81–95 is certified only when:

- Critical pass rate = 100%.
- High pass rate >= 98%.
- Overall pass rate >= 95%.
- Batch execution coverage = 100%.
- Direct source Skill coverage = 100%.
- Critical/High evidence completeness = 100%.
- Overall evidence completeness >= 98%.
- Flaky rate <= 1%.
- Quarantine rate <= 0.5%.
- No zero-tolerance finding remains.

Critical failures are non-compensating: success in other batches cannot offset them.
