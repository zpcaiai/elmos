# BUILD_CACHE_HANDOFF.md

> Read this before touching `engines/build-cache-engine/`.
> Companions: `BUILD_CACHE_TASK.md`, `BUILD_CACHE_IMPLEMENTATION_STATUS.md`,
> `BUILD_CACHE_TEST_RESULTS.md`, `BUILD_CACHE_EVIDENCE.md`.

- **Last updated:** 2026-08-19 (pass 2)
- **Written by:** Claude (Cowork cloud session)
- **Overall status:** `CERTIFIED_IN_SANDBOX` — 24/24 skills implemented,
  **555 tests (550 pass, 5 skip)**, 4 skills `PARTIAL` for reasons that are
  environmental, not architectural, and named below.

## 0. What landed in pass 2

Pass 1 is already committed. This is a **second, additive** change; nothing
from pass 1 was deleted, and nothing outside these two paths was touched.

```text
engines/build-cache-engine/          37 modules, 17 891 lines · 30 test files, 8 047 lines
.ai/BUILD_CACHE_*.md                 this evidence set
```

New files:

| Path | What it is |
| --- | --- |
| `src/elmos_build_cache/treesitter_hash.py` | Exact public-interface extraction for twelve languages via `tree-sitter` |
| `migrations/sqlite/0002_saved_compiler_ms.sql` | `action_cache_entries.saved_compiler_ms` |
| `migrations/postgres/0003_column_types.sql` | Column types the implementation actually stores (ids as text, epoch seconds as `double precision`) |
| `migrations/postgres/0004_saved_compiler_ms.sql` | Same column on the production dialect |
| `tests/test_treesitter_hash.py` | 103 tests, thirteen languages |
| `tests/test_native_toolchains.py` | 12 tests driving real Gradle / dotnet / cargo / ccache / tsc / pip / go |
| `tests/test_e2e_real_stages.py` | E2E-001 with a real `javac` stage and a real translator |
| `tests/test_metadata_store_contract.py` | 23 contract tests × {SQLite, PostgreSQL 16} |
| `tests/test_remote_s3.py` | 12 tests against a live HTTP S3 endpoint |
| `tests/test_chaos_process.py` | Real `SIGKILL` and real tmpfs exhaustion |
| `tests/test_provenance_crypto.py` | Ed25519 + AES-256-GCM |

Changed behaviour worth knowing about:

- **`security.py` was rewritten.** `Ed25519ProvenanceSigner` is the default;
  `HmacProvenanceSigner` remains for offline development and is *refused* by
  `require_asymmetric` when `SecurityConfig.require_asymmetric_provenance` is
  set (it defaults to `True`). `EnvelopeCipher` is AES-256-GCM with the tenant
  identity as AAD. **Existing HMAC-signed provenance will not verify.**
- **`interface_hash.extract_interface` now tries tree-sitter first** and falls
  back to the line scanner if no grammar is available. `ModuleInterface` gained
  an `extractor` field that is part of `semantic_digest`, so **every
  `source_semantic_digest` changes with this commit** — expect one cold pass.
- **`saved_compiler_ms` is new** on `ActionCacheRecord` and the accounting.
  Before this, a restored compile node reported zero saved compiler time.
- **SQLite now keeps a migration ledger** (`schema_migrations`). An existing
  database converges: `0001` is `IF NOT EXISTS` throughout and is recorded on
  first open, then `0002` adds its column once.
- `LANGUAGE_ADAPTERS["go"]` is `go-build`, a new ninth adapter.

## 1. Commit — do this yourself

The cloud session's bridge to the Mac **cannot delete files**, so any `git`
command that needs a lock leaves undeletable debris. No `git` command was run.

```bash
cd ~/DevProjects/AIProjects/elmos
git add engines/build-cache-engine .ai/BUILD_CACHE_*.md
git commit -m "feat(build-cache): certify the cache subsystem against real services and toolchains"
```

## 2. Reproduce the gates

```bash
cd engines/build-cache-engine
python3.12 -m venv .venv
.venv/bin/pip install -e '.[postgres,s3]' ruff==0.12.5 mypy==1.17.0 pytest==8.4.1 'moto[s3,server]>=5.0'

.venv/bin/ruff check src tests
.venv/bin/mypy
.venv/bin/pytest tests                        # PostgreSQL rows skip without the DSN
ELMOS_TEST_POSTGRES_DSN=postgresql://user:pw@127.0.0.1:5432/elmos_cache .venv/bin/pytest tests
.venv/bin/pytest tests -m "not toolchain"     # skip the real build tools

cd ../../agent-skills/packages/elmos-build-cache-staging-recovery && ./validate.sh
```

**The Mac's system Python is 3.10 and cannot run this engine.** Use 3.12.
Toolchain tests skip cleanly when a tool is absent; they never pass silently.
`tree-sitter` and `tree-sitter-language-pack` are now **required** dependencies
(both pinned exactly — see §4).

## 3. Ordered next steps

| # | Work | Why it matters | Closes |
| --- | --- | --- | --- |
| 1 | **Register ELMOS's real conversion stages against `stage_contract.default_pipeline()`.** The 13 contracts, their schemas and their fingerprint dimensions are declared; `tests/test_e2e_real_stages.py` shows exactly what a real stage has to return (`StageResult` with `StageOutput`s, metrics, evidence, validation level). | This is the last architectural gap: the model-driven stage is the one thing this repository cannot exercise. | E2E-001 residue, gate 10 |
| 2 | **Calibrate `observability.DEFAULT_SLOS`.** Run the ten `BENCHMARK_SCENARIOS` against a real ELMOS project and replace the estimates (95 % no-change, 70 % small-change). | PERF-001/002 measure a harness plus a small real build, not a workload. | gate 9 |
| 3 | **Cross-platform snapshot fixtures.** Golden root digests on macOS and Windows asserted equal to Linux; APFS case-insensitivity is the interesting one. | SNAP-001 is Linux-only. | gate 1 |
| 4 | **A dedicated test file for `overlay.py`,** with overlayfs (Linux) and APFS `clonefile` (macOS) isolation and documented fallbacks. | The only `PARTIAL` skill with no test file of its own. | — |
| 5 | **Certify the three remaining native adapters** — Xcode/Swift and Flutter/pub on a machine that has them, and the Maven half of `gradle-maven` where Maven Central is reachable. `tests/test_native_toolchains.py` has a slot for each; replace the skip with the same cold/warm/import/clean-room shape the other seven use. | 3 of 10 toolchains uncertified. | — |
| 6 | **Key management.** `Ed25519ProvenanceSigner` holds raw key bytes. Production should back it with a KMS/HSM: the interface (`ProvenanceSigner.sign`/`verify`/`active_key_id`) is designed for that substitution, and `public_keyset()` already exposes only verification material. | Signing is asymmetric now, but the private key still lives in the process. | — |
| 7 | **AWS-specific S3 behaviour.** The endpoint tested here is a local S3 service. Regional consistency, IAM denial paths and lifecycle rules are untested. | REMOTE rows are certified against S3 *semantics*, not against AWS. | — |

## 4. Design decisions worth knowing before you change things

- **The grammar bundle is pinned exactly** (`tree-sitter==0.26.0`,
  `tree-sitter-language-pack==1.14.3`) and its version is written into
  `ModuleInterface.extractor`, which is part of `semantic_digest`. A grammar
  upgrade therefore *invalidates the cache on purpose* rather than letting two
  differently-provisioned workers quietly disagree about what a public
  interface is. Bump it deliberately.
- **The signed payload contains the algorithm and the key id.** That is what
  makes an algorithm downgrade and a key substitution forgeries rather than
  policy questions. Do not move them outside `signing_payload`.
- **Function bodies are never walked for symbols.** The tree-sitter walker
  descends into type declarations only; walking a body would turn locals into
  public API. This is the single most important line in `treesitter_hash._Walker`.
- **Signature text is masked, body text is not.** A string literal inside an
  annotation (a route, a topic, a column name) is *surface*, tracked by
  `surface_digest`; leaving it in the signature would report every route rename
  as an API break. Literals inside bodies stay, because they are behaviour.
- **`ABORTED → RESERVED` is the only backwards edge** in the staged-file state
  machine, so a producer can retry its own failed write for the same logical
  path without a second row. Do not add other backwards edges.
- **Two operations deliberately commit before raising**: nondeterminism
  quarantine (`action_cache`) and staged-file abort (`staging`).
- **`cas.materialize` never hardlinks by default.** `share="auto"` reflinks or
  copies; `share="link"` is opt-in.
- **Restore is a full lifecycle** — `pipeline._restore` claims a lease and
  re-stages every cached output through reserve → seal → promote.
- **The contract data exists twice on purpose**: `schemas/`, `openapi/`,
  `migrations/` for humans, `src/elmos_build_cache/_data/` for imports.
  `test_repository_contract_copies_match_the_packaged_ones` fails if they drift
  — including the two new migrations.

## 5. Known hazards

- `sqlite3` + `synchronous=FULL` + `journal_mode=WAL` is the local profile. Do
  not put the metadata file on NFS.
- The chaos harness mounts and unmounts a real tmpfs through `ctypes`. It needs
  `CAP_SYS_ADMIN`; without it `bounded_filesystem()` raises
  `ExhaustionUnavailable` and the test skips rather than pretending.
- `FilesystemRemoteBackend.fail` is a chaos hook, not a feature flag.
- The `elmos-cache` CLI defaults `--tenant default`; always pass `--tenant` in
  scripts.
- Toolchain tests really invoke compilers. They are marked `toolchain`; use
  `-m "not toolchain"` in an environment where that is not wanted.
