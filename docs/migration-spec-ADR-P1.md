# Decision Record — P1 Convergence ADR-MIG-P1-01 … 06

The adversarial review found six capability families modelled two to five times across Batch 1–8.
Duplicate models are the most expensive defect class in this specification: each copy grows its own
schema, its own normalizers and its own copy of the invariants, and the weakest copy ends up setting the
real safety level. All six are converged here, in data, before Skill 327–764 is implemented.

## Convergence rule

For each family exactly one **implemented** Skill is the authority. It carries:

> This Skill is the sole authority for the *family* model; its schema, state machine and invariants may
> not be redefined by any other Skill.

Every other member is a **domain view**. It carries:

> This Skill is a domain view of the *family* model owned by `authority`; it may add collection points
> and domain thresholds but may not redefine that schema or relax its invariants, and the owning Skill
> must be present in the loaded capability closure whenever this one is selected.

**Why the authority is the implemented Skill, not the richest one.** The review nominated the richest
definition in each family, but four of those six live in Skill 327–764. Pointing an implemented Skill at
an unimplemented owner creates a dangling reference. Instead the authority is the implemented member and
the richer field set is **merged into it** — same outcome, no forward reference.

## The six families

| ADR | Family | Authority | Merged from | Views now | Planned views |
|---|---|---|---|---|---|
| P1-01 | messaging semantics | `B123-S11 unified-messaging-ir` | Skill 7, 520 | 4 | 16 |
| P1-02 | serialization | `B121-S02 serialization-semantic-ir` | Skill 89, 361, 629 | 2 | 15 |
| P1-03 | context propagation | `B121-S04 framework-context-propagation-ir` | Skill 452, 602, 719 | 0 | 5 |
| P1-04 | shadow side-effect isolation | `B106-S13 shadow-side-effect-firewall` | Skill 425, 586–591, 750–754 | 5 | 12 |
| P1-05 | certification evidence custody | `B108-S11 certification-evidence-vault` | Skill 178, 427, 609 | 1 | 2 |
| P1-06 | certification revocation | `B108-S12 certification-revocation-monitor` | Skill 428, 763 | 0 | 2 |

12 implemented views and 52 planned source Skills are bound to the six authorities.

## Field sets merged into the authorities

**Messaging** — message identity, key, partition, timestamp, producer and consumer identity now sit
alongside delivery, acknowledgement and ordering semantics. Inbox deduplication state and offset commit
position belong to this model, not a separate one.

**Serialization** — wire name, field presence, ordering, polymorphic discriminator, reference
preservation, compression and schema version are all part of this model. Field presence uses the
six-state absence model, never a boolean present flag.

**Context propagation** — every field declares who creates it, who propagates it, who may mutate it,
which call types it reaches, whether a background task inherits it, and when it is cleared. A background
task never inherits an end-user authority implicitly.

**Shadow isolation** — every shadow mechanism in any layer declares which of the six interception modes
it uses. Real dual-write requires separate written approval and is never a default mode.

**Evidence custody** — one content-addressed vault serves every object type; the object type is a
parameter, not a reason for a second vault. Pack versions, toolchain fingerprints and layer levels are
stored with every bundle.

**Revocation** — one engine watches the causal inputs of every certification object type and emits the
same four states. Recovery from a downgraded state requires new evidence; an approval alone never
restores it.

## Known ordering constraint

Four authorities sit in later Batches than some of their views — `unified-messaging-ir` is B123-S11 while
`message-semantics-verifier` is B105-S07. Renumbering 326 Skills to fix Batch order would be worse than
the problem. The mitigation is the closure requirement in the view clause: selecting a view **requires**
loading its authority, so the model is never absent at runtime even though it appears later in the
catalog. The capability graph enforces this; Batch order does not.

## Also converged

**Absence semantics** — `B109-S12 nullability-and-absence-ir-builder` is upgraded from four states to the
authoritative six (missing, explicit null, defaulted, empty, zero, present). Merging any two requires a
decision record and a regression test.

**Retry budget** — the authority (Skill 707) lives entirely in the unimplemented range, so it is recorded
in `convergence.py` as `RETRY_BUDGET_AUTHORITY` for the Skill 327–764 generator rather than applied now.
Gateway, mesh, driver and application retry configuration must reference one shared budget document, and
measured amplification above the declared ceiling blocks promotion.

## Enforcement

`gen/convergence.py` holds the registry; `_apply_p1_convergence()` in `gen/skills_data.py` applies it and
**fails the build** if the registry names a slug that does not exist. The generator for Skill 327–764 must
consult the same registry so the 52 planned members are emitted as views from the start.
