---
name: numerical-data-behavior-validator
description: Independently compare migrated Python datasets and numerical outputs across schema, dtype, nulls, ordering, floating tolerances, randomness, distributions, and business invariants. Use for NumPy, pandas, SciPy, pipeline, feature, or scientific behavior validation.
---

# Numerical and Data Behavior Validator

## Define the comparison before running it

Snapshot schema, columns/dtypes/nulls, shape/count/key/order, ranges/quantiles/categories, timezone/encoding, samples/full hashes, partitions, and metadata. Do not treat a changed file hash as automatic failure or a successful process as numerical success.

Select per-metric `EXACT`, absolute, relative, ULP, statistical distribution, business invariant, or ranking equivalence. Record `atol`, `rtol`, NaN policy, dtype, precision, and ordering policy. Never use one broad global tolerance.

Seed Python, NumPy, framework RNGs, data loaders, splits, workers, and `PYTHONHASHSEED`. Record nondeterminism and hardware separately.

Add focused checks for NumPy dtype promotion, scalars, overflow, shapes, and C ABI; and pandas string/null/copy/index/group/merge/sort/category/timezone/CSV/Parquet behavior. Statistical similarity does not replace invariants such as conservation, uniqueness, nonnegative inventory, monotonic time, or no new nulls.

Return `NUMERICALLY_EQUIVALENT`, `WITHIN_APPROVED_TOLERANCE`, `STATISTICALLY_EQUIVALENT`, `BUSINESS_EQUIVALENT`, `REGRESSION`, or `INCONCLUSIVE`. Never map `INCONCLUSIVE` to pass. Accept only with visible dtype/order/seed/tolerance/invariant evidence.

