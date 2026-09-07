# Decision Record — P0 Rulings ADR-MIG-P0-01 … 04

The adversarial review of Skill 1–764 found four contradictions that make the specification
non-executable. Each is settled below. The rulings are applied **in the Skill data**, not only in prose,
so every generated Skill carries them in its Required Checks and the package validator enforces them.

---

## ADR-MIG-P0-01 — The per-language-pair ceiling summary is void

**Contradiction.** Batch 4 section 13 declared 38 entries for 36 existing language pairs. Three pairs —
`C++ <-> TypeScript`, `Python <-> Rust`, `Rust <-> TypeScript` — appeared in two mutually exclusive
groups at once ("normally targets E5-C" and "default maximum E4").

**Ruling.** The summary table is **void**. A directional path's ceiling exists in exactly one place: the
`certification_ceiling` block of its own pack. Every path Skill states this explicitly:

> This pack is the only authority for its ceiling.

**Rationale.** A ceiling is a property of a *direction*, not of an unordered pair. Batch 4's own second
principle says a language pair is not a direction; the summary table contradicted that principle by
construction, which is why it could hold two answers for one entry.

---

## ADR-MIG-P0-02 — Hard caps are derived, not tabulated

**Contradiction.** `Python <-> Swift` was never assigned a ceiling group, while Skill 165 forbids leaving
any state unknown.

**Ruling.** Hard caps follow one **graduated rule** evaluated per direction, replacing the hand-maintained
table:

| Condition | Cap |
|---|---|
| Either side retains unexplained undefined behaviour | E3 |
| Dynamic-site trace coverage is incomplete | E3 |
| Enumerated dynamic behaviour is not frozen into an explicit registry | E4 |
| Neither applies | no cap |

`DYNAMIC_RUNTIME_LANGUAGES = {Python, TypeScript, Objective-C}`
`UNDEFINED_BEHAVIOUR_LANGUAGES = {C++}`

No approval lifts either cap; only new evidence does.

**Result across all 72 directions** (programmatically verified, and symmetric — both ends of every pair
now agree):

| Cap tier | Directions |
|---|---|
| E3 and E4 | 42 |
| E3 only | 10 |
| no cap | 20 |

**Two deliberate deviations from the source text**, both in the tightening direction:

1. `Python <-> Rust` and `TypeScript <-> Rust` keep the E3 tier that Skill 190 stated, which a flat rule
   would have relaxed to E4. The graduated rule preserves the stricter reading.
2. `Objective-C <-> Swift` now carries E3/E4 caps although Skill 243 and Skill 251 declared a direct E5.
   Objective-C as a source has non-enumerable runtime dispatch, and Skill 236 already caps
   `Objective-C -> Java` at E4 for exactly that reason. The source specification was inconsistent in
   exempting the Swift direction. Tightening is the fail-closed choice.

---

## ADR-MIG-P0-03 — Seven ladders compose by the short-plank rule

**Contradiction.** E1–E5, E5-C, DR0–DR5 and four separate E2–E5 ladders (framework, dependency,
infrastructure, communication) existed with no composition rule and shared level names.

**Ruling.**

1. The four domain ladders are renamed with domain prefixes: `FW-E*`, `DEP-E*`, `INF-E*`, `COM-E*`.
2. Composition is the **minimum**:

```
composed_level = min(core, directional_path, FW-E, DEP-E, INF-E, COM-E,
                     min(DR of critical replacements))
```

3. A single layer level is **never published on its own**.
4. Any critical failure — money, permission, tenancy, transaction, idempotency, irreversible side
   effect, schema compatibility — sets the composed result to `blocked` rather than entering the minimum.

**Applied to**: `evidence-level-assessor`, `certification-ceiling-calculator`,
`certification-ceiling-evaluator`, `release-gate-evaluator`, `canary-promotion-evaluator`,
`e5-production-confidence-certification`, and each of the four framework gates.

**Rationale.** Skill 19 already forbade averaging indicators inside one gate. Averaging *across* ladders
is the same error one level up. Minimum is the only composition that cannot be gamed by strengthening an
unrelated layer.

---

## ADR-MIG-P0-04 — Cancellation follows a declared policy

**Contradiction.** Skill 706 required an already-committed payment to complete or reconcile; Skill 452 and
Skill 660 required rollback and cleanup on cancellation; Skill 744 tested cancellation racing a successful
payment. Three expectations for one state, with no decision function — so the test could not be given a
determinate assertion.

**Ruling.** Cancellation outcome is decided by an explicit policy keyed on effect reversibility, declared
per endpoint and per effect:

```yaml
cancellation_policy:
  reversible_effects: abort_and_rollback
  irreversible_effects_not_yet_started: abort_before_start
  irreversible_effects_in_flight: complete_then_reconcile
  unknown_outcome: reconcile_required
```

No layer re-interprets cancellation. Differential comparison uses the policy as the oracle.

**Applied to**: `side-effect-capture`, `side-effect-ir-builder`, `fault-injection-runner`,
`rollback-executor`, `effect-intent-recorder`, `async-ordering-verifier`.

---

## Enforcement

The rulings live in `gen/skills_data.py` under `_apply_p0_rulings()`. Verification available at any time:

- cap tier distribution and pair symmetry across all 72 directions
- presence of the composition rule in every gate and assessor Skill
- presence of the cancellation rule in every effect-handling Skill
- `./validate.sh` — full package, contract, schema and interface validation

Rulings 01 and 02 supersede Batch 4 section 13. Ruling 03 supersedes the bare level names in Batch 5, 6,
7 and 8 gates. Ruling 04 supersedes the cancellation expectations in Skill 452 and Skill 660.
