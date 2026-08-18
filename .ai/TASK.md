# TASK.md — elmos active task of record

> Maintained by AI agents (Codex / Claude Code). Source of truth for *what is being
> worked on*. Implementation truth lives in git; completion truth lives in
> `TEST_RESULTS.md` + `EVIDENCE.md`. Nothing here is a certification claim.

> ### Route-count provenance — read before quoting any denominator (K6)
>
> Verified 2026-08-18, after `a2f6f6577 feat(route-engine): add php as the
> eleventh language` landed. `routes/inventory.json` is the only authority.
>
> **Current surface: 110 directed routes across 11 languages** (11 × 10, no
> self-routes), committed and matching the working tree.
>
> `/72` and `/90` are both dead as denominators. They survive only as retained
> provenance sets — `nine-language-complete-72`, `ten-language-complete-90` —
> so historical evidence stays attributable, and neither describes the current
> surface. The 182-node figure is the *pipeline test suite*; it is not a route
> count and must never be added to or compared against one.

- **Repository:** `/Users/stephen/DevProjects/AIProjects/elmos`
- **Remote:** `https://github.com/zpcaiai/elmos.git`
- **Branch:** `feat/batch38-45-certification-toolchain`
- **HEAD at handoff:** `f8c25fae` — *feat(frontend): harden pairwise formal equivalence evidence*
- **Handoff created:** 2026-08-12 (Claude Code, taking over from Codex)

---

## 1. Project goal (recovered from Codex thread history)

Original user requirement, verbatim:

> 所有语言之间的互转，都要能够做到中小型仓库级别的代码互转
> ("Conversion between all languages must work at small/medium **repository** scale.")

Follow-up:

> 目前每两种语言之间的互转，转换完成后，行为完全等价成功率多大
> ("For each language pair, what is the fully behaviour-equivalent success rate?")

## 2. Current task

Verbatim instruction that defines the active work:

> 请提升这些的转换成功率，尽可能用 sota 方法进行提升：
> - **端到端 workload 成功率：136/144 = 94.44%**
> - **要求每条路线的 SMALL、MEDIUM 都成功：64/72 = 88.89%**
> - 历史上 8 条 Java 源路线各为 1/2；其余 64 条有向路线为 2/2。
> - Java、Swift 相关问题已有定向修复，但最新 146 项冻结全矩阵尚未完整重跑，
>   因此暂不能把路线成功率上调到 100%。
> - 独立客户仓库验证与正式认证仍是 **0/72**。

**In plain terms:** raise repository-level cross-language conversion to 100 %
behaviour-equivalent on every directed route (SMALL *and* MEDIUM), re-run the
frozen full matrix to prove it, and move independent client-repository
verification / formal certification off `0/72`.

### 2.1 Scope expansion discovered during handoff

While that task was running, a parallel workstream expanded the route matrix
from **9 languages / 72 directed routes** to **10 languages / 90 directed
routes** by adding **JavaScript (Node.js 26, ESM + strict JSDoc)** as a language
identity distinct from TypeScript (`NODEJS_DIRECTED_PAIRS`, 18 new directions).

Consequence for the numbers above: the `x/72` denominators in the user's message
predate the expansion. The matrix under test is now **90 routes**, and the
frozen suite is **182 pytest nodes**. Any future report must state which
denominator it is using.

## 3. Current batch context

Concurrent Codex threads were coordinating under an explicit freeze protocol:

| Thread | Scope |
| --- | --- |
| `019fe3cf-d456-7291-be3e-db63ff75503b` | polyglot route engine core; JavaScript/Node 26 tenth language; the 182-node matrix |
| `019fe3c7-c08c-7992-9260-38bfab959a0c` | `frontend-client-engine`, frontend toolchain runner, Batch 32 / 35 frontend packs and gates |

Frozen paths (backend-owned, frontend must not write):
`engines/polyglot-route-engine/{native.py, engine.py, toolchains.py, native/**}`,
`tests/test_*swift*`, `tests/test_repository_pipeline_language_matrix.py`,
Batch 29 route replay / toolkit, Swift and native builds.

## 4. Requirement sources (in precedence order)

1. `AGENTS.md` (repo root, ~37 KB) — batch-scoped agent instructions, Batch 29→46.
2. `.agents/skills/b2x-*/SKILL.md`, `.agents/skills/b3x-*/SKILL.md` — repository-scoped skills.
3. `engines/polyglot-route-engine/README.md` — canonical type/operator semantics,
   supported profile (`typed-pure-function-v1`, `typed-pure-module-v1`), fail-closed policy.
4. `routes/inventory.json` — the declared route surface (90) and its provenance route sets.

`SKILL.md` presence is a **requirement** statement, never evidence of implementation.

## 5. Hard constraints carried over from Codex

- **Fail-closed everywhere.** Unsupported semantics must surface as an explicit
  error code, never be widened, coerced, or silently permitted.
- **Only the batch gate scripts may declare certification readiness**
  (`scripts/batch32/run_client_gate.py`, `scripts/batch33/run_cloud_gate.py`,
  `scripts/batch34/run_portfolio_gate.py`, and the Batch 29 route certification gate).
- **No weakening to make a gate pass**: no skipped/deleted tests, no relaxed
  assertions, no `any`, no updated visual baselines, no broadened permissions,
  no mocked-away real behaviour.
- **Corpora stay independent**: development, negative, holdout and
  representative workloads must not cross-contaminate.
- **Freeze discipline**: a source change invalidates the current freeze window
  (R*n*) and a new window must be rebuilt from T0 before matrix evidence counts.
- **Interrupted runs are void.** A partial matrix log with no pytest summary
  may never be spliced into an evidence set.

## 6. Definition of Done for the current task

| # | Criterion | How it is proven |
| --- | --- | --- |
| D1 | Static gates green | engine Ruff, changed-set Ruff, strict mypy (22 files), `py_compile`, `node --check` on JS/TS |
| D2 | Suite shape confirmed | `pytest --collect-only` reports exactly **182** nodes |
| D3 | Freeze window valid | T0/T30/T60 triple hash identical across source / external / frontend domains; read-only snapshot byte-closed against live |
| D4 | Full matrix run to completion | one serial pytest process, **no `-x`**, terminates with a real summary line — not SIGTERM |
| D5 | Route success | every directed route passes both SMALL and MEDIUM |
| D6 | Independent verification | client-repository verification recorded per route (currently `0/72`) |
| D7 | Certification | only via the batch gate script; until then status stays `NOT_CERTIFIED` |

**Current DoD status: D1 ✅ / D2 ✅ / D3 ⛔ invalidated / D4 ⛔ NOT_RUN / D5 ⛔ / D6 ⛔ 0 / D7 ⛔**
(see `IMPLEMENTATION_STATUS.md` for the evidence behind each mark)
