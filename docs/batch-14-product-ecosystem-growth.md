# Batch 14 product growth, content, developer ecosystem, Marketplace and regional replication

Repository scope was reconciled to the complete authoritative Batch 14 specification on 2026-07-21. This is the cross-language roadmap's growth Batch 14 and is distinct from the older Java-engine Batch 14 frontend/client engine.

Local tests establish deterministic control behavior, contracts, tenant isolation and append-only evidence handling only. They do not establish a real signup, message, publication, Marketplace action, payment, moderation decision, translation approval, legal decision, partner authorization, regional launch, customer value result or production outcome.

## Product and Ecosystem Growth Model

`modules/ecosystem-growth` implements the Product and Ecosystem Growth Model (PEGM). It admits an immutable, signed Batch 13 B13-G artifact, a versioned customer-value North Star, all seven PEGM domains and all five measured flywheels.

The seven PEGM domains are:

1. Acquisition
2. Activation
3. Adoption
4. Retention
5. Expansion
6. Advocacy
7. Ecosystem

The recommended North Star is `Monthly Verified Migration Value`: migration work units that passed static, build, test, behavioral or production-cutover verification during the month. Registration, generated lines, model tokens and agent calls are explicitly excluded as standalone success measures.

The five measured flywheels are product, content, community, Marketplace and regional growth. Each profile must link to customer value, define quality guardrails and close a feedback loop. Growth cannot compensate for security, privacy, tenant, technical-quality, license, support, retention or margin failure.

## Evidence-only control plane

The module exposes seven read-only authority ports:

1. `ProductActivationAuthority`
2. `ContentDeveloperAuthority`
3. `CommunitySafetyAuthority`
4. `MarketplaceGrowthAuthority`
5. `InternationalizationAuthority`
6. `RegionalChannelAuthority`
7. `GrowthConformanceAuthority`

Each G14-A through G14-F envelope is bound to the same assessment run and platform-business version. It carries coverage, exact controls, tenant/privacy/guardrail results, preserved negative evidence, critical and cross-tenant counters, metrics, source authority, observation time and immutable evidence references.

The evaluator rejects or blocks missing, future-dated, wrong-run, wrong-version, wrong-area, stale, conflicting, unconsented, cross-tenant, fabricated or externally executed results. Authority exception messages are reduced to exception class so provider text cannot leak.

## Non-compensating G14 gates

| Gate | Authoritative requirement |
| --- | --- |
| G14-A | Self-service signup, repository connection, Assessment activation, measurable time to value, controlled Trial cost and security guardrails |
| G14-B | Complete technical content review, core documentation journeys, tested SDK journeys, building samples and available developer portal |
| G14-C | Isolated community identity, moderation SLA, malicious-content controls, verified knowledge workflow and zero private customer leakage |
| G14-D | Verified publishers, complete executable-asset security and License gates, install rollback, fake-review controls and zero critical asset incidents |
| G14-E | Passed I18n architecture, critical UI localization, 100% human review for Security/Billing, regional formats and regional compliance |
| G14-F | Complete market-entry assessment, approved Launch Playbook, ready local support, enforced partner quality gates and available regional metrics |
| G14-G | G14-A through G14-F all pass, channel CAC and contribution margin are visible, all evidence is traceable and critical open growth risks equal zero |

Only G14-G may produce:

```json
{
  "growth_platform_version": "growth-ecosystem-v1",
  "gate": "G14-G",
  "status": "scalable-growth-ready",
  "supported_motions": [
    "product-led-growth",
    "content-led-growth",
    "developer-led-growth",
    "community-led-growth",
    "marketplace-led-growth",
    "partner-led-regional-expansion"
  ],
  "open_non_blocking_items": []
}
```

## Skills 401–460

The repository contains exactly 60 Skill Creator packages under `agent-skills/ecosystem-growth`. Each package uses the exact authoritative name, detailed description, domain-specific structures, hard rules and acceptance criteria supplied for its Skill number.

The capability ranges are:

- 401–415: growth system, North Star, journey, acquisition, PLG, self-service, activation, TTV, Trial, lifecycle, referral, experiments, analytics and attribution;
- 416–422: content strategy, production, SEO, comparison, customer proof, events and research;
- 423–429: developer portal, documentation, API/CLI/SDK, starters, sandbox, DevRel and champion programs;
- 430–435: community identity, knowledge, moderation, reputation, events and support-to-community loop;
- 436–443: Marketplace orchestration, publishers, certification, discovery, install, pricing, reviews and network effects;
- 444–449: I18n, localization workflow, terminology, regional UX, compliance and regional pricing/tax;
- 450–456: market entry, Launch Playbook, local programs, partners, cloud alliances, support and regional dashboard;
- 457–459: growth economics, brand/risk governance and learning playbooks;
- 460: G14-A through G14-G conformance.

Every Skill records operational field acceptance as `PASSED`, `FAILED`, `NOT_RUN` or `INCONCLUSIVE`. Repository tests never close an external field criterion.

## Artifacts and reports

`EcosystemGrowthArtifactWriter` writes the exact `growth-platform/` hierarchy outside the platform repository. The eleven top-level areas are:

- `growth-core`
- `product-growth`
- `content`
- `developer-ecosystem`
- `community`
- `marketplace`
- `internationalization`
- `regional-growth`
- `economics`
- `governance`
- `reports`

It writes 25 immutable artifacts: manifest, PEGM control model, gate result, compressed growth-domain profiles, compressed flywheel profiles, six gate-evidence envelopes, G14-G conformance evidence, evidence pack and the twelve specified reports:

1. `product-growth-report.json`
2. `activation-retention-report.json`
3. `channel-attribution-report.json`
4. `content-performance-report.json`
5. `developer-ecosystem-report.json`
6. `community-health-report.json`
7. `marketplace-growth-report.json`
8. `localization-quality-report.json`
9. `regional-launch-report.json`
10. `channel-economics-report.json`
11. `growth-risk-report.json`
12. `batch-14-conformance-report.json`

Writes are atomic and append-only. Existing targets, symbolic-link workspaces, symbolic-link parents and direct or resolved paths inside the repository are rejected.

## Contracts and storage

Eighteen strict Draft 2020-12 schemas under `contracts/ecosystem-growth-schema` cover growth program, Monthly Verified Migration Value, event/identity/funnel/experiment/content, developer extension, community, Marketplace, locale, regional pack, six-area gate evidence, evidence pack and final conformance. The final schema independently enforces the G14-G readiness invariant.

V22 creates the exact 69 Batch 14 core tables proposed by the specification. Every table records organization ownership plus tenant scope, region, locale, persona, channel, campaign, source, consent, schema/policy version, observation time, evidence, content hash and `external_operation_executed=false`. All 69 tables use forced row-level security; 18 event, decision, review, certification, payout, translation, requirement, learning and economics streams are append-only.

V10 remains authoritative for Marketplace/commercial execution, V20 remains authoritative for the Batch 13 business loop, and the pre-existing V21 remains the enterprise integration/middleware migration.

## External acceptance boundary

The 87 completion questions and every row in `docs/batch-14-growth-acceptance-checklist.md` remain field-evidence questions. Local repository verification cannot establish actual activation, conversion, retention, attribution, SDK adoption, community safety, Marketplace network effects, localization approval, regional support, CAC, payback, margin or global readiness.

Repository verification results are recorded separately in `docs/batch-14-growth-verification.md`.
