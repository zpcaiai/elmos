# Project Synthesis P0 launch runbook

## Frozen v1 scope

`p0-launch-scope-v1.json` is the only P0 scope authority. It freezes API
starter generation for Java, Python, C#, TypeScript, Go, Kotlin, PHP, and Rust;
the exact native toolchains listed in that file; disposable PostgreSQL 17.5;
and JWT HS256 or OIDC RSA/RS256 authentication. A different database version,
JWK type, signature algorithm, target version, project kind, or deployment
topology is a new qualification scope, not an implicit extension of v1.

Validate the immutable contract locally:

```bash
python3 scripts/operations/validate_project_synthesis_p0_scope.py
make project-synthesis-p0-contract
```

This is repository-owned engineering evidence only. It performs no provider
call, production deployment, approval, external assessment, or certification.

## Local current-SHA qualification

Run the complete local engine and exact-toolchain paths first:

```bash
make project-synthesis
make project-synthesis-toolchains
```

For a clean committed checkout, collect a replay bundle outside the repository:

```bash
evidence_dir="$(mktemp -d)/project-synthesis-p0"
python3 scripts/operations/generate_project_synthesis_p0_evidence.py \
  --repository . \
  --output "$evidence_dir" \
  --auth-profile jwt
```

The collector runs the full engine tests, Ruff, mypy, all-toolchain acceptance,
the 16-profile production matrix, P0/Runner/Vercel contract tests, the Batch 33
Cloud gate, a frozen offline web-console install, and the web-console check. It
binds the commit and tree both before and after execution. Its ceiling is
`READY_FOR_TRUSTED_SIGNING`; it cannot sign, deploy, approve, or certify.

## Ten production evidence gates

`p0-launch-gate-contract.json` defines the only aggregate production decision.
All ten gates must pass for the current clean commit and tree:

1. current-SHA release bundle and SCM attestation;
2. Linux systemd/rootless production Runner execution;
3. managed PostgreSQL migration, write/read, isolation, and rollback;
4. managed RSA/RS256 IdP discovery and positive/negative token tests;
5. Cloud Run plan, apply, runtime probe, rollback, destroy, and IAM review;
6. SBOM, artifact integrity, provenance, signature, and vulnerability evidence;
7. independent representative-workload UAT;
8. independent security assessment with no open critical or high finding;
9. governed release approval with separation of duties and rollback owner;
10. external production-certification decision over the complete gate result.

Every referenced evidence file is a content-addressed JSON envelope:

```json
{
  "schema_version": "1.0.0",
  "kind": "elmos.project-synthesis.evidence-reference",
  "role": "<exact role from the gate contract>",
  "status": "PASSED",
  "scope_id": "project-synthesis-api-v1",
  "source_revision": {
    "commit_sha": "<current commit>",
    "tree_sha": "<current tree>"
  },
  "producer": {
    "id": "<accountable producer>",
    "role": "<producer role>"
  },
  "observed_at": "<timezone-aware timestamp>",
  "details": {}
}
```

The release-bundle SCM attestation additionally identifies the exact
`zpcaiai/elmos` repository, commit, tree, protected-branch result, required
checks result, and deployment SHA. Each gate artifact and detached signature
must match the contract and an active, role-specific Ed25519 trust key. A
public-key fingerprint cannot be reused across independent roles.

Evaluate repository state and the external evidence directory with:

```bash
PROJECT_SYNTHESIS_P0_EVIDENCE_DIR=/outside/immutable-evidence \
PROJECT_SYNTHESIS_P0_GATE_OUTPUT=/outside/p0-launch-result.json \
make project-synthesis-p0-production-gate
```

The evidence directory and output must stay outside the source repository.
The evaluator reobserves Git after all evidence checks to reject a revision
change during evaluation.

## Current production blockers

The repository intentionally has no production trust keys configured. The
latest operator observation reports PostgreSQL 17.11 and an OKP/EdDSA IdP key,
which cannot satisfy the frozen PostgreSQL 17.5 and RSA/RS256 profile. Real
managed database execution, IdP validation, production Runner deployment,
Cloud Run lifecycle, trusted signing, independent UAT/security assessment,
governed release approval, and external certification remain `NOT_RUN` or
`NOT_CERTIFIED` until their accountable owners execute them and supply the
contracted evidence.

Even after all ten production gates pass, the repository evaluator reports
`production_ready=true` but keeps `certified=false`: it verifies an external
certification artifact and never manufactures or self-issues certification.
