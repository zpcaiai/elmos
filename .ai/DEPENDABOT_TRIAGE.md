# Dependabot triage — 20 open branches against `main` @ `5b9e33ab7`

GitHub reports 222 alerts on the default branch (57 high / 142 moderate / 23 low).
There are 23 remote branches not contained in `main`: 20 dependabot, 2 `codex/*`,
and the `perf/*` branch itself.

**None of the 20 bumps is already applied on `main`** — every target version was
checked against main's current value. Each branch is 1 commit touching 1–3 files.

The classification below is by *coupling*, not by size. This repository pins
exact toolchain versions and validates them (`scripts/batch29/route_runtime_metadata.py`,
`engines/polyglot-route-engine/src/elmos_polyglot_route/toolchains.py`,
`routes/inventory.json`, and the per-route packs), so a one-line version bump is
not always a one-line change.

---

## A. Free — no pin coupling anywhere outside the manifest (11)

Merge as-is. Each was checked for the old version string across `scripts/`,
`engines/`, `apps/web-console/app/` and found nowhere else.

| branch | change | files |
|---|---|---|
| `github_actions/actions/checkout-7.0.1` | v5 → v7.0.1 | 3 workflows |
| `github_actions/actions/setup-go-7.0.0` | 5.5.0 → 7.0.0 | `ci.yml` |
| `github_actions/actions/setup-node-7.0.0` | v5 → v7.0.0 | `ci.yml` |
| `github_actions/actions/setup-python-7.0.0` | v6 → v7.0.0 | 2 workflows |
| `github_actions/gradle/actions/setup-gradle-6.2.0` | v4 → v6.2.0 | `ci.yml` |
| `maven/org.apache.maven.plugins-maven-jar-plugin-3.5.0` | 3.4.1 → 3.5.0 | `apps/elmosctl/pom.xml` |
| `maven/org.xerial-sqlite-jdbc-3.53.2.1` | 3.50.3.0 → 3.53.2.1 | `pom.xml` |
| `maven/docker-java.version-3.7.1` | 3.4.2 → 3.7.1 | `pom.xml` |
| `maven/com.github.luben-zstd-jni-1.5.7-11` | 1.5.7-3 → 1.5.7-11 | 3 poms |
| `npm_and_yarn/apps/web-console/jose-6.2.8` | 6.1.2 → 6.2.8 | `package.json` + lock |
| `npm_and_yarn/apps/web-console/mammoth-1.12.1` | 1.12.0 → 1.12.1 | `package.json` + lock |

Two notes:

* **`setup-go`**: dependabot bumped the SHA but left the trailing comment as
  `# v5` while actually moving to v7.0.0. Fix the comment when merging or the
  pin will read as v5 forever.
* **`zstd-jni`**: the root pom property was `1.5.7-3` while
  `modules/commercial-loop` and `modules/ecosystem-growth` hardcoded `1.5.7-4`.
  This branch unifies all three on `1.5.7-11`, so it also removes a real
  inconsistency.

```
for b in \
  dependabot/github_actions/actions/checkout-7.0.1 \
  dependabot/github_actions/actions/setup-go-7.0.0 \
  dependabot/github_actions/actions/setup-node-7.0.0 \
  dependabot/github_actions/actions/setup-python-7.0.0 \
  dependabot/github_actions/gradle/actions/setup-gradle-6.2.0 \
  dependabot/maven/org.apache.maven.plugins-maven-jar-plugin-3.5.0 \
  dependabot/maven/org.xerial-sqlite-jdbc-3.53.2.1 \
  dependabot/maven/docker-java.version-3.7.1 \
  dependabot/maven/com.github.luben-zstd-jni-1.5.7-11 \
  dependabot/npm_and_yarn/apps/web-console/jose-6.2.8 \
  dependabot/npm_and_yarn/apps/web-console/mammoth-1.12.1 ; do
  git merge --no-edit "origin/$b" || break
done
```

After the two npm ones, regenerate the lock in one step rather than trusting two
separate dependabot locks:
`cd apps/web-console && pnpm install --lockfile-only`.

---

## B. Collides with the exact-toolchain contract — NOT a dependency bump (2)

| branch | change |
|---|---|
| `npm_and_yarn/apps/web-console/typescript-7.0.2` | 5.9.2 → **7.0.2** |
| `npm_and_yarn/apps/web-console/multi-3146d5559c` | react 19.2.7 → 19.2.8, @types/react 19.1.10 → 19.2.18 |

`5.9.2` is pinned in **`toolchains.py`, `react_analyzer.py`, `react_repository.py`,
`native.py`**, in `routes/inventory.json`
(`typescript.exact_versions == ["TypeScript 5.9.2", "Node.js 26.0.0"]`,
`react.exact_versions` names it too), and in **339 files under `routes/`**.
`toolchains._react` additionally carries a sha256 over the React dependency
profile, including the literals `react=19.2.7`, `@types/react=19.1.10`,
`@types/react-dom=19.1.7`.

Merging either branch turns `make business-line-contracts` red immediately —
`LANGUAGE_EXACT_VERSION_DRIFT` / `ROUTE_SOURCE_VERSION_DRIFT` — and breaks the
TypeScript and React exact-toolchain closures. TypeScript 5 → 7 is also a major
version.

Doing this properly is a project, not a merge:
1. decide the new pinned versions,
2. update `route_runtime_metadata.VERSIONS` / `SHORT_VERSIONS`,
3. re-derive `routes/inventory.json` and the affected route packs from that
   authority (the same mechanical sweep as the 199-file refresh in
   `MERGE_PERF_VERIFICATION.md`),
4. recompute the `_typescript` / `_react` closures and their digests,
5. re-run `make business-line-contracts` and the polyglot engine suite.

**Recommendation: close these two branches** and open a tracked task instead.
Leaving them open makes the alert count look actionable when it is not.

---

## C. Needs a repository-wide decision first — do not merge one branch (7)

### 5 × `pip/engines/project-synthesis-engine/*`

`hatchling 1.27.0→1.31.0`, `mypy 1.17.0→2.3.0`, `pytest 8.4.1→9.1.1`,
`pyyaml 6.0.2→6.0.3`, `ruff 0.12.5→0.15.22`.

The same three tools are pinned independently in **six** engines, and they have
**already drifted**:

| package | mypy | pytest | ruff |
|---|---|---|---|
| `engines/database-data-engine/sql-transpiler` | 2.3.0 | 8.4.2 | 0.16.0 |
| `polyglot-route`, `project-synthesis`, `sql-dialect`, `build-cache`, … | 1.17.0 | 8.4.1 | 0.12.5 |

Merging only the `project-synthesis-engine` branch creates a **third** set.
`ruff 0.12.5 → 0.15.22` and `mypy 1.17 → 2.3` are both large jumps that will
surface new diagnostics. Do one repo-wide sweep that lands every engine on the
same triple, and budget for the lint/type fallout.

### `npm_and_yarn/apps/web-console/types/node-26.2.0` (24.3.0 → 26.2.0)

`Node.js 26.0.0` is the pinned runtime in `route_runtime_metadata.py` and
`run_polyglot_routes.py`. `@types/node` at 24 against a pinned Node 26 runtime is
already mismatched, so this bump is probably *correct* — but move the types and
the declared runtime together and re-check the TypeScript closure, rather than
merging the types bump alone.

### `maven/spring-boot.version-4.1.0` (3.5.3 → 4.1.0)

This is the **repository's own build** version. `3.5.3` is simultaneously the
Spring migration line's `default_target` in
`scripts/operations/validate_spring_route_contract.py` — it is the target of the
one route that has a pack binding (`boot-2.7-maven-to-boot-3.5.3-java-21`).
`4.1.0` is currently an `inventory_only_target` (declared, no pack).

Raising the build to 4.1.0 while the certified default target stays 3.5.3 puts
the build baseline ahead of the evidence. Decide the ordering first: either
promote 4.1.0 to a bound route with evidence, or keep the build on 3.5.3.

---

## Not dependabot, still unmerged

| branch | commits ahead | files |
|---|---|---|
| `codex/multitenant-task-finops-runtime` | 2 | 264 |
| `codex/multitenant-task-finops-skills` | 1 | 181 |

Both branch from `467e25551`/`5b6cb5468`, i.e. before the 40k-file `c03782bfe`.
They are substantial feature branches, not dependency bumps, and deserve the same
treatment the perf branch got: three-way analysis of the both-changed set before
any merge is attempted.

---

# Applied: class A, as one sweep rather than 11 merges

## Why not 11 merges

Simulating the eleven merges in order (three-way per file against the
accumulating state) produced **two conflicts** and, worse, a **partially bumped
`ci.yml`**. Each dependabot branch was cut from an older snapshot, so it only
rewrites the occurrences that existed then. Merging all five Actions branches
would have left:

| action | bumped | **left stale** |
|---|---|---|
| `actions/checkout` | 16 | **1** at v5 |
| `actions/setup-go` | 1 | **1** at the old SHA |
| `actions/setup-node` | 6 | **3** at v5 |
| `actions/setup-python` | 11 | **1** at v6 |
| `gradle/actions/setup-gradle` | 1 | 0 |

A merged PR that silently fixes 34 of 40 pins is worse than an open one: the
alert closes, the exposure stays. Repo-wide there are **49** old-SHA pins across
**5** workflow files, not the 8 the branches touch.

The two conflicts were pure adjacency, both resolved as unions:
`pom.xml` (`zstd-jni` next to `docker-java`) and `package.json` (`jose` next to
`mammoth`).

## What was applied

**GitHub Actions — 49 pins across all 5 workflow files**, each rewritten to the
new SHA with its version comment normalised in the same pass:

| action | new pin | count |
|---|---|---|
| `actions/checkout` | `3d3c42e5…` `# v7.0.1` | 22 |
| `actions/setup-go` | `b7ad1dad…` `# v7.0.0` | 2 |
| `actions/setup-node` | `82076278…` `# v7.0.0` | 9 |
| `actions/setup-python` | `5fda3b95…` `# v7.0.0` | 15 |
| `gradle/actions/setup-gradle` | `3f131e86…` `# v6.2.0` | 1 |

0 stale SHAs remain; all 5 files still parse as YAML. This also fixes
dependabot's own bug on `setup-go`, where it moved 5.5.0 → 7.0.0 but left the
comment reading `# v5`.

**Maven — 4 files**

* root `pom.xml`: `zstd-jni 1.5.7-3 → 1.5.7-11`, `docker-java 3.4.2 → 3.7.1`,
  `sqlite-jdbc 3.50.3.0 → 3.53.2.1`
* `modules/commercial-loop/pom.xml`, `modules/ecosystem-growth/pom.xml`:
  hardcoded `zstd-jni 1.5.7-4 → 1.5.7-11` (these were already inconsistent with
  the root property)
* `apps/elmosctl/pom.xml`: `maven-jar-plugin 3.4.1 → 3.5.0`
* `spring-boot` deliberately **left at 3.5.3** — class C

**npm — 2 files**

`jose 6.1.2 → 6.2.8`, `mammoth 1.12.0 → 1.12.1`. The lock was **regenerated**
with `pnpm install --lockfile-only` rather than text-merging two dependabot
locks; the result carries real integrity digests (32 changed lines).

**11 files total.**

## Verification

| check | result |
|---|---|
| `validate_model_catalog` / `validate_makefile_portability` / `validate_spring_route_contract` / `validate_translation_route_matrix` | **PASS** |
| YAML parse, all 5 workflows | OK |
| XML/JSON parse, all changed manifests | OK |
| `pnpm install --frozen-lockfile` | EXIT=0, `jose@6.2.8` + `mammoth@1.12.1` actually installed |
| `tsc --noEmit` against the installed bumps | **0 errors** |
| `next build` | **EXIT=0** |
| `test:upstream-policy`, `test:admin-mutation-policy`, `test:durable-lease`, `test:repository-translation` | PASS |

## The eleven branches

They can be closed once this lands — GitHub closes a dependabot PR by itself
when it sees the manifest already at the target version. Do **not** merge them
afterwards: their `ci.yml` hunks are now stale against the swept file and would
reintroduce conflicts for no gain.

Classes B and C above are untouched and still need the decisions described there.
