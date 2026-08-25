-- Compiler time saved by a cache hit. See migrations/sqlite/0002 for why.
ALTER TABLE action_cache_entries ADD COLUMN IF NOT EXISTS saved_compiler_ms bigint NOT NULL DEFAULT 0;
