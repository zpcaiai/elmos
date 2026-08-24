# Reference implementation

This standard-library Python package demonstrates core semantics:

- canonical ActionKey hashing and immutable SHA-256 CAS;
- append-only journal, generated-file staging, atomic sealing, CAS promotion, recovery, complete-tree publication;
- educational SIEVE, S3-FIFO, W-TinyLFU, size-aware W-TinyLFU, LRU, and GDSF policies;
- equal-capacity multi-policy trace replay with object, byte, avoided-compute, token, and critical-path metrics;
- deterministic workload fingerprinting and an interpretable off-path policy router;
- conversion-DAG next-use protection, prefetch ranking, and eviction ordering.

It is intentionally compact and is **not** the production ELMOS server. Merlin, S4-FIFO, 3L-Cache, distributed coordination, security, model lifecycle, and production certification remain implementation work defined by the Skills.

Run:

```bash
python3 -m unittest discover -s reference-implementation/tests -v
python3 scripts/run_cache_benchmark.py examples/cache-trace.example.jsonl --capacity-bytes 2500000
```

## v1.2.0 coding-agent cache parity components

The reference package now also contains:

- `prompt_cache.py`: canonical stable/append-only/volatile prompt compilation, provider capability and normalized usage types, and cache-affinity keys;
- `context_ledger.py`: append-only hash-linked repository context events, staleness propagation, and checkpoints;
- `environment_cache.py`: precise environment snapshot keys and restore-versus-rebuild decisions;
- `affinity.py`: compatibility-safe cache-locality scoring;
- `miss_diagnostics.py`: first-difference and identity-change reason classification;
- `parity.py`: mandatory SLO evaluation and compute-weighted reuse.

Run the illustrative gate evaluator:

```bash
python3 scripts/run_cache_parity_benchmark.py \
  examples/cache-parity-observations.example.json
```

The fixture proves the package interfaces and gate code work. It is explicitly not a production ELMOS performance result.
