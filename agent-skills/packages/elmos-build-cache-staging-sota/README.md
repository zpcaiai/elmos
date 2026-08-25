# ELMOS Build Cache, File Staging, and SOTA Adaptive Cache Skills

Version **1.1.0** (2026-08-19).

This package extends the deterministic build cache, generated-file staging, intermediate-state persistence, checkpoint recovery, and atomic publication package with seven implementation skills for modern adaptive cache optimization. It uses a policy portfolio, workload replay, cost-aware admission, DAG-aware future reuse, an off-hot-path adaptive selector, learning-augmented parameter control, and production certification.

The package contains **31 executable skills**. Run:

```bash
./validate.sh
./install.sh --all
```

The key safety rule is unchanged: policy and learning affect only admission, placement, prefetch, retention, or eviction. Exact ActionKeys, CAS integrity, validation level, provenance, tenancy, and atomic publication remain authoritative for reuse correctness.

See `README.zh-CN.md`, `docs/source-packages/elmos-sota-cache-optimization-spec.md`, and `docs/research/sota-cache-algorithm-matrix.md` for the full design.
