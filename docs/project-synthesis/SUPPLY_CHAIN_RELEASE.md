# Project Synthesis supply-chain and release contract

The P0 source of truth is `p0-launch-scope-v1.json`. It freezes only the API
project kind, eight request-runtime selectors plus their exact qualification
toolchain tuples, disposable local PostgreSQL 17.5, and JWT HS256 or OIDC
RS256. The PostgreSQL version is a
local-container contract, not a managed-provider alias. Managed provider
versions require separate exact observations; provider migrations, production
delivery, independent verification, and certification remain `NOT_RUN` or
`NOT_CERTIFIED` in this repository-owned flow.

The separate `provider-observation-2026-09-04.json` is explicitly an
operator-reported, read-only observation with no raw provider receipt. It says
the managed Neon server reported 17.11 and the configured Better Auth JWKS
reported one `OKP`/`EdDSA` key. That key cannot satisfy the frozen
`RSA`/`RS256` OIDC profile, so the managed OIDC gate is
`ALGORITHM_MISMATCH` / `BLOCKED`. JWT HS256 remains an independent local
profile; none of these observations prove a migration write or production
qualification.

## Dependency evidence

Generation writes `requirements/dependency-sbom.cdx.json` and binds its exact
file digest from `.elmos/generation-manifest.json`. The SBOM is CycloneDX 1.6
and records separate transitive-inventory, artifact-integrity, and dependency-
graph statuses per selected target. It reports `INCOMPLETE` until the relevant
native evidence exists:

| Target | Inventory and integrity evidence |
|---|---|
| Java | `.elmos/dependencies/java-dependency-tree.json` plus SHA-256 of each resolved cache artifact |
| Python | `python/uv.lock`, with a valid SHA-256 for every registry package |
| C# | every generated `packages.lock.json`, with valid NuGet `contentHash` values |
| TypeScript | `typescript/pnpm-lock.yaml`, with valid package integrity values |
| Go | `go.mod` plus `go.sum` (or a dependency-free module) |
| Kotlin | `kotlin/gradle.lockfile` plus SHA-256 of each resolved cache artifact |
| PHP | `composer.lock`, or a platform-only `composer.json` with no package dependencies |
| Rust | `rust/Cargo.lock` |

Declared POM, `package.json`, `pyproject.toml`, or central package versions are
still included for review, but they never count as transitive inventory.
Placeholder integrity such as `sha512-example`, missing uv hashes, and invalid
native hash encodings remain `INCOMPLETE`. The relationship data currently
flattens each target to its component inventory, so
`dependency_graph_status=INCOMPLETE_FLATTENED` and CycloneDX composition stays
`incomplete`; the implementation never calls this a complete dependency graph.

The first `elmos-project-synthesis verify` pass builds every selected target.
For Java it also invokes the pinned Maven Dependency Plugin 3.8.1 during the
build, then replays that exact plugin offline to materialize
`.elmos/dependencies/java-dependency-tree.json`. The offline replay must parse
as a dependency tree before Java verification can pass.

After the first native build has populated its exact local caches, run
`elmos-project-synthesis collect-native-artifact-hashes --workspace ...`.
This provider-free collector reads actual Maven/Gradle cache files, computes
their SHA-256 values, and writes the request-bound
`.elmos/dependencies/artifact-hashes.json`. Missing artifacts, ambiguous cache
contents, unsafe paths, unknown components, and malformed evidence fail closed.
It is local self-attested engineering evidence, not registry or independent
attestation.

Run `elmos-project-synthesis verify` a second time after collecting the hashes.
The release flow is therefore deliberately two-pass: native verification,
native artifact-hash collection, native verification again, then
`elmos-project-synthesis supply-chain`. This prevents the signed inputs from
describing a dependency state that was not replayed by the verifier.

## Generation and Release Manifests

Generation Manifest schema 1.2 adds:

- the P0 scope ID and canonical SHA-256;
- whether the approved request is exactly in scope;
- the managed CycloneDX SBOM path, byte digest, inventory, integrity, and
  flattened-graph status;
- explicit `NOT_CREATED` / `NOT_RUN` Release Manifest, signature, and trust-root states.

After native verification, run `elmos-project-synthesis supply-chain`. The
Release Manifest binds the exact Generation Manifest, release-eligible
inventory/integrity SBOM, native
verification receipt, source commit, source tree, and clean-worktree claim. It
is emitted unsigned and therefore remains either `BLOCKED` or
`AWAITING_TRUSTED_SIGNATURE`. An unsigned manifest is never release authority.
The CLI does not accept commit, tree, or clean-state overrides: it observes
`HEAD`, `HEAD^{tree}`, and porcelain status from the exact
`--source-repository`. A dirty repository cannot reach the signing boundary.

The verification receipt must be schema 1.2 from `verify_workspace`, bind the
exact workspace, request, approval, Generation Manifest, and rebuilt SBOM, and
contain the exact-toolchain observations plus every required build/test,
startup, and PostgreSQL integration result for every selected target. Empty or
hand-written summary-only `results`, a `PARTIAL` status, missing target checks,
or a mismatched binding fails closed. This remains self-attested local evidence
until a separate trusted signer and external verifier act.

## Signature and trust root

Only detached Ed25519 signatures over canonical JSON are accepted. A signature
envelope has this exact shape:

```json
{
  "algorithm": "ed25519",
  "key_id": "release-2026",
  "kind": "elmos.project-synthesis.release-signature",
  "payload_format": "canonical-json",
  "payload_sha256": "<64 lowercase hex>",
  "schema_version": "1.0.0",
  "signature_base64": "<base64 Ed25519 signature>",
  "signed_at": "2026-09-04T01:00:00Z"
}
```

The separately supplied trust root must itself be `ACTIVE` and contain exactly
one matching active key. Each key binds `public_key_path`,
`public_key_sha256`, `valid_from`, and `valid_until`. Unknown, duplicate,
revoked, expired, future-dated, digest-mismatched, symlinked, or unsupported
keys fail closed. The verifier uses local OpenSSL Ed25519 verification; missing
OpenSSL is `BLOCKED`, never a skip or pass.

A successful signature check returns at most `READY_FOR_EXTERNAL_GATE`.
`production_ready=false`, `certified=false`, production delivery remains
`NOT_RUN`, and certification remains `NOT_CERTIFIED` until the separately
authorized external process produces its own evidence.

Signature verification must be bound to the live inputs, not only to detached
JSON files. The verifier therefore requires the workspace, SBOM, verification
receipt, and exact source repository in addition to the manifest, signature,
and trust root:

```bash
elmos-project-synthesis verify-release-signature \
  --manifest /outside/release-manifest.json \
  --signature /outside/release-manifest.sig.json \
  --trust-root /outside/release-trust-root.json \
  --workspace /exact/generated/workspace \
  --sbom /exact/generated/workspace/requirements/dependency-sbom.cdx.json \
  --verification /exact/generated/workspace/.elmos/verification-receipt.json \
  --source-repository /exact/clean/elmos-checkout
```

The source repository must be the exact `zpcaiai/elmos` origin, contain the
tracked P0 markers, and remain at the same clean commit and tree before and
after verification. A symlink, dirty worktree, origin mismatch, untracked
contract, or time-of-check/time-of-use change fails closed.

## Current-SHA replay bundle

`scripts/operations/generate_project_synthesis_p0_evidence.py` accepts only a
clean repository root and an output directory outside that repository. It
binds `HEAD`, `HEAD^{tree}`, the exact scope digest, the engine's complete
transitive inventory and artifact-integrity `uv.lock` SBOM, its explicitly
flattened graph status, allowlisted offline check commands, and raw log
digests. It never accepts arbitrary commands and never signs. With all local
checks green, `--auth-profile jwt` can reach the
`READY_FOR_TRUSTED_SIGNING` ceiling. `oidc` or `all` remains `BLOCKED` for the
current EdDSA/RS256 mismatch. Skipped checks, a dirty tree, a timeout, or any
failure also stays `BLOCKED`.
