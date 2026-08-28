# Pricing and Billing Skill Integration

This directory records the repository-owned, fail-closed integration of
`elmos-pricing-billing-skills` `1.0.0`.

## Pinned source

- Archive: `skills/subskills/elmos-pricing-billing-skills-v1.0.0.zip`
- SHA-256: `9f7440b69a82a52172a1f62da915d96cfa4e0326dc04a305603c76001c8e88bc`
- Immutable extracted tree: `skills/elmos-pricing-billing-skills-v1.0.0/`
- Inventory: `130` files and `513164` uncompressed bytes

The user-supplied pinned SHA-256 proves byte identity only; it does not establish authorship, signature, SBOM, or provenance attestation.

The importer treats the ZIP as untrusted data. It does not import or execute
the bundled shell, Python, test, CI, installer, uninstaller, validator, quote,
or SQL files.

## Installed state

- Guidance: `GUIDANCE_IMPORTED`
- Installation: `INSTALLED`
- Runtime implementation: `LOCAL_REFERENCE_BOUND`
- Runtime binding: `verification-packs/pricing-billing-local-v1/runtime-binding.json`
- Importer runtime evidence: `NOT_RUN`
- External evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`
- Maximum local claim: `BOUNDED_LOCAL_REFERENCE_IMPLEMENTATION`

All source `B00`–`B53` identifiers are qualified as
`elmos.pricing-billing.v1/Bxx`. They do not name or update any other repository
Batch, Migration Pack, Product Batch, or test-suite result.

## Installed Skills

- `$elmos-billing-orchestrator`
- `$elmos-pricing-product-model`
- `$elmos-plan-catalog-entitlements`
- `$elmos-credit-wallet-ledger`
- `$elmos-usage-metering`
- `$elmos-task-cost-estimation`
- `$elmos-quote-budget-guard`
- `$elmos-project-pricing-contracts`
- `$elmos-subscription-invoicing`
- `$elmos-payments-reconciliation`
- `$elmos-refunds-disputes`
- `$elmos-enterprise-byok`
- `$elmos-cost-margin-analytics`
- `$elmos-billing-admin-ux`
- `$elmos-security-compliance`
- `$elmos-billing-observability-ops`
- `$elmos-billing-testing-certification`
- `$elmos-rollout-migration`

Each Skill is byte-and-mode identical in `.agents/skills/` and
`agent-skills/runtime/`. Installed `SKILL.md` files retain the source body but
use repository-compatible frontmatter and an explicit provenance/evidence
boundary. `agents/openai.yaml` provides deterministic UI metadata. The shared
support material referenced by those Skills is generated at
`.elmos-billing-kit/`; bundled helper files are present as non-executable data.

Semantic overlap and precedence for Product B39 Finance, Product B44 FinOps,
Product Batch 56, and the current commercial billing implementation are
recorded in `overlap-map.json`.

## Validation

```bash
python3 tooling/integrate_pricing_billing_skills.py --check
python3 tooling/validate_pricing_billing_installed.py
python3 -m unittest discover -s tests/pricing-billing-skills -p 'test_*.py' -v
```

`--write` is conflict-safe: an absent managed tree may be created and an exact
tree is a no-op, but a differing existing tree is never overwritten.
