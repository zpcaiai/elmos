# Dependabot remediation execution — 2026-08-30

This is repository engineering evidence. It is not production certification,
an independent security assessment, or a claim that accepted residual risks
were fixed.

## Executed state transition

- GitHub open-alert inventory before this follow-up: **137** (`9 high`,
  `105 medium`, `23 low`).
- Exact immutable corpus/evidence exceptions generated: **128**.
- Exceptions applied through the digest-bound governance tool: **128** alerts
  dismissed as `tolerable_risk`; each dismissal says **accepted residual risk,
  not fixed**, names controls, and expires after 90 days.
- GitHub open-alert inventory immediately after those decisions: **9**.
- Active high alert: `deepmerge-ts@7.1.5` under
  `apps/web-console/pnpm-lock.yaml`. The owning direct dependency was upgraded
  from `html-to-text@10.0.0` to `10.0.1`, which resolves
  `deepmerge-ts@8.0.2` (patched range starts at `8.0.0`). Frozen installation,
  `pnpm audit --audit-level high`, all Web Console policy tests, type checking,
  and the Next.js production build passed locally. GitHub closure remains
  dependent on the pushed default-branch manifest and its subsequent scan.
- Remaining active EOL findings: **8** alert records covering Vue 2.7.16 and
  `vue-template-compiler@2.7.16` in the Component Dialect and Frontend Client
  engines. The GitHub advisories identify no Vue 2 patch for
  `vue-template-compiler`; replacing the exact Vue 2 route with Vue 3 would be
  a breaking semantic change, not remediation.

## Vue 2 compensating controls executed

- Added one repository-owned fail-closed guard to each active engine.
- Enforced a 1 MiB UTF-8 compiler-input ceiling.
- Rejected `<script>`, `<style>`, and `<textarea>` inside analyzed templates
  before the EOL parser runs.
- Rejected adversarial runs of more than 256 consecutive `<` characters with
  a linear scan.
- Rejected compiler execution when sensitive `Object.prototype` fields are
  polluted.
- Added positive, oversized/ReDoS, and prototype-pollution tests.
- Frontend Client Engine result: **216 passed, 0 failed**.
- Component Dialect Engine initially exposed one unrelated unmapped
  `CERTIFIED_COMPONENT_USEMEMO_CALLBACK` dogfood finding; the blocker catalog
  was completed, the 24-case scan suite passed, and the final full rerun
  completed with **369 passed, 1 skipped, 0 failed** across 13 suites.
- Component npm audit and Frontend pnpm audit each retain **1 low + 1
  moderate** Vue 2 EOL vulnerability and no high finding. The offered
  automatic fixes are breaking/non-equivalent package replacements, so they
  were not applied or represented as safe remediation.

## Evidence files and replay

- `dependabot-open-alerts-2026-08-30.json` binds all 137 pre-decision alert
  identities.
- `dependabot-risk-exceptions-2026-08-30.json` binds the 128 exact decisions,
  their controls, owner, expiry, and source snapshot digest; `fixed_claims` is
  empty and certification is `NOT_CERTIFIED`.
- Governance replay:
  `python3 scripts/dependabot_governance.py --snapshot <snapshot> --registry <registry>`.
- Web Console replay: `cd apps/web-console && pnpm install --frozen-lockfile
  --ignore-scripts && pnpm audit --audit-level high && pnpm check`.
- Component replay: `cd engines/component-dialect-engine && npm ci
  --ignore-scripts && npm run check`.
- Frontend replay: `cd engines/frontend-client-engine && pnpm install
  --frozen-lockfile --ignore-scripts && pnpm check`.

## Conservative decision

The dependency campaign materially reduced open alerts and fixed the active
high dependency in source, but the eight Vue 2 EOL alert records remain active
until an authorized product/security decision removes the exact route, adopts
a maintained compatible distribution with independent evidence, or approves a
time-bound production exception. Independent security review and production
certification remain `NOT_RUN / NOT_CERTIFIED`; release status remains
`NOT_GA`.
