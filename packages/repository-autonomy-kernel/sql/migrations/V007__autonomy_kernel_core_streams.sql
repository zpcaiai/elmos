-- Capability-core stream storage. Apply after V001-V006.
--
-- Five tables, one per port the capability core speaks to. The invariants its
-- Python adapters enforce are ALSO enforced here as constraints, because an
-- adapter is one process among many and a database that only trusts its clients
-- has no invariants at all.
--
-- Why these are additive rather than folded into the control-plane tables:
-- autonomy_events is a uuid FK to autonomy_runs with no hash column, while this
-- log is chain-verified and keyed by an arbitrary stream id. Expressing one in
-- the other would mean changing released schema and the tests pinned to it, so
-- the two coexist and docs/MERGE_DECISIONS.md records the consolidation debt.
--
-- The autonomy_kernel_ prefix is deliberate: the control plane already owns
-- autonomy_events, autonomy_artifacts and autonomy_leases, and a schema
-- carrying both autonomy_event and autonomy_events is a wrong-table bug waiting
-- for a tired reader.
--
-- Targets PostgreSQL 14+ (developed against 16; the package's stated production
-- floor is 17 and nothing here uses a feature newer than 14).

create table if not exists autonomy_kernel_event (
  stream_id       text        not null,
  sequence        bigint      not null,
  event_id        text        not null,
  payload         jsonb       not null,
  hash_chain      text        not null,
  idempotency_key text,
  fencing_token   bigint,
  recorded_at     timestamptz not null default now(),
  primary key (stream_id, sequence),
  -- Sequences start at 1 and the adapter derives each from the previous head,
  -- so a gap or a zero means someone wrote around the adapter.
  constraint autonomy_kernel_event_sequence_positive check (sequence >= 1),
  constraint autonomy_kernel_event_id_unique unique (event_id),
  constraint autonomy_kernel_event_chain_shape check (hash_chain like 'sha256:%')
);

-- One event per (stream, idempotency key). This is the constraint that makes a
-- duplicate delivery return the original event instead of applying a side effect
-- twice; enforcing it only in Python would leave two concurrent workers free to
-- both "win".
create unique index if not exists autonomy_kernel_event_idempotency
  on autonomy_kernel_event (stream_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists autonomy_kernel_event_recorded_at
  on autonomy_kernel_event (stream_id, recorded_at);

create table if not exists autonomy_kernel_kv (
  key        text        not null primary key,
  value      jsonb       not null,
  version    bigint      not null,
  updated_at timestamptz not null default now(),
  constraint autonomy_kernel_kv_version_positive check (version >= 1)
);

create table if not exists autonomy_kernel_artifact (
  digest     text        not null primary key,
  media_type text        not null,
  byte_count bigint      not null,
  body       bytea       not null,
  stored_at  timestamptz not null default now(),
  -- The primary key IS the content address: 'sha256:' plus 64 hex characters.
  -- A row whose key does not have that shape was not written by this adapter.
  constraint autonomy_kernel_artifact_digest_shape
    check (digest ~ '^sha256:[0-9a-f]{64}$'),
  constraint autonomy_kernel_artifact_length_agrees check (byte_count = length(body))
);

create table if not exists autonomy_kernel_lease (
  resource_id   text        not null primary key,
  owner_id      text        not null,
  fencing_token bigint      not null,
  expires_at    timestamptz not null,
  acquired_at   timestamptz not null default now(),
  constraint autonomy_kernel_lease_token_positive check (fencing_token >= 1)
);

-- Tokens must be monotonic per resource FOREVER, including across a release and
-- a re-acquire, so the high-water mark outlives the lease row itself. Deleting
-- the lease on release and re-deriving the token from the (now absent) row would
-- hand a new owner a token a stale worker still holds - the exact failure
-- fencing exists to prevent.
create table if not exists autonomy_kernel_lease_watermark (
  resource_id  text   not null primary key,
  issued_token bigint not null,
  constraint autonomy_kernel_lease_watermark_positive check (issued_token >= 1)
);
