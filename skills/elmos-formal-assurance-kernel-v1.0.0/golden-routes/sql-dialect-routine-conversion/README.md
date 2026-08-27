# SQL Dialect and Routine Conversion Formal Golden Route

This Golden Route defines the minimum repeatable path for commercial certification of `sql-conversion`.

## Critical properties

- query equivalence mode and bounds are explicit
- schema mapping is lossless or approved one-way refinement
- type precision, collation, time and NULL semantics are preserved
- routine/trigger effects, exceptions and transactions refine source
- dynamic SQL unsupported boundaries are monitored

## Certification conditions

- five SQL dialect pairs
- query corpus with NULL/bag/window cases
- routine/trigger corpus
- production-size differential replay
- E1-E5 complete

A successful package validation is not an E5 certification. E5 requires real repositories/environments, exact toolchain pins, failure injection and signed evidence.
