-- Compiler time saved by a cache hit.
--
-- The reference schema accounts for CPU, wall time and model tokens, but not
-- for compiler time -- which for a *build* cache is the headline number: a
-- restored compile node reported ``saved.compiler_ms = 0`` no matter how long
-- the original build took. The column is additive and defaulted, so an
-- existing database picks it up without rewriting any row.
ALTER TABLE action_cache_entries ADD COLUMN saved_compiler_ms INTEGER NOT NULL DEFAULT 0;
