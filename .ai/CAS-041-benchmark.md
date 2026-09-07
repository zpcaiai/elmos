# ELMOS-CAS-041 action cache benchmark

Synthetic workload: 200 modules x 25 files, 200 actions per round.

| scenario | hit rate | hits | misses | expectation |
|---|---:|---:|---:|---|
| `unchanged-rerun` | 1.0000 | 200 | 0 | = 1.0000 (goal >= 0.95) |
| `one-file-changed` | 0.9950 | 199 | 1 | exactly one module misses |
| `toolchain-changed` | 0.0000 | 0 | 200 | = 0.0000, every entry invalidated |
| `permission-downgraded` | 0.0000 | 0 | 200 | = 0.0000, every read denied |

- bytes avoided: 1995000000
- compute avoided (ms): 16758000
- wall-clock avoided (ms): 24339000
- benchmark wall-clock (ms): 649

## Outcome reasons

- `ACTION/HIT/EXACT`: 399
- `ACTION/MISS/NO_ENTRY`: 201
- `ACTION/DENIED/PERMISSION_DOWNGRADE`: 200

> Simulated execution on a synthetic tree. This measures action-key and
> invalidation behaviour, not build times on a real repository.
