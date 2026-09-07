# Product B39 complete Skill pack

This directory records the integration contract for the submitted Product B39
finance Skill pack. It contains 48 implementation Skills in three independent
but connected domains:

- B39A financial, billing and commercial operations: 16 Skills;
- B39B payment, treasury and financial-risk operations: 16 Skills;
- B39C finance analytics, planning and unit economics: 16 Skills.

The normalized source package remains under
`elmos-codex-skills-batch39-complete`. Its Skills are installed into
`agent-skills/runtime`. Batch 39 adds 48 names without superseding an earlier
Product Skill, taking the canonical Product inventory to 339 and the complete
Runtime Skill catalog to 879.

Product B39 Finance is a different namespace from Migration Pack M39 Global
SRE. Product Skills remain under `agent-skills/runtime`; Migration Pack Skills
remain under `.agents/skills` and retain their independent gates.

## Name normalization

The submitted pack contained 34 names longer than Codex's 64-character Skill
limit. Those names use the deterministic alias:

```text
source_name[:55].rstrip("-") + "-" + sha256(source_name)[:8]
```

`manifest.json` and the ELMOS source manifest preserve every original
`source_name`. All 48 source and installed Skills have an `agents/openai.yaml`
interface whose default prompt invokes the normalized `$skill-name`.

## Commands

```text
./elmos-codex-skills-batch39-complete/validate.sh
python3 tooling/integrate_product_batch39_complete_skill_pack.py
python3 tooling/validate_product_batch33_39_integration.py
python3 tooling/ensure_runtime_skill_interfaces.py --check
make product-batch35-39
make backend
```

The integrator is idempotent. The central validator checks official Skill
validity, package and Skill digests, exact B39A/B/C inventories, deterministic
aliases, interface metadata, namespace separation and the `NOT_RUN` external
evidence boundary. The legacy B33-B38 synchronizer reapplies both the complete
B34-B38 overlay and the B39 overlay so a full resync cannot silently remove or
replace the submitted contracts.

## Evidence boundary

Passing static package, Skill, architecture and local Maven tests does not
certify tax treatment, accounting conclusions, payment providers, bank rails,
cash positions, financial close, management reporting or production use.
Those outcomes remain `NOT_RUN` until executed against the exact provider,
jurisdiction, legal entity and accounting-policy tuple by authorized producers
and independent verifiers with immutable evidence.
