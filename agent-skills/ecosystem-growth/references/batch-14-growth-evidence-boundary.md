# Batch 14 growth evidence boundary

Read this file before using any of the Skills 401–460 packages.

Batch 14 implements the Product and Ecosystem Growth Model (PEGM). Its seven growth domains are Acquisition, Activation, Adoption, Retention, Expansion, Advocacy, and Ecosystem. Its five measured flywheels are product, content, community, Marketplace, and regional growth.

## Authority and evidence

Repository code, generated artifacts, plans, drafts, simulations, dashboards, forecasts, and local tests prove only local contract behavior. They do not prove real signup, activation, content conversion, community health, Marketplace use, localization approval, regional support, revenue, retention, margin, or production readiness.

Bind every result to tenant scope, region, locale, persona, channel, campaign, source, consent, product and schema version, owner, observation time, and immutable evidence references. Preserve negative and failed results. Treat missing, stale, future-dated, conflicting, cross-tenant, unconsented, fabricated, or unverifiable evidence as NOT_RUN, INCONCLUSIVE, or blocking.

Do not execute identity, messaging, publication, moderation, Marketplace, payment, tax, legal, partner, regional-launch, or customer-production actions from the Batch 14 control plane. Record external_operation_executed=false for control-plane-only evaluations.

## Non-compensating gates

| Gate | Required outcome |
| --- | --- |
| G14-A | Self-service signup, repository connection, assessment activation, measurable time to value, controlled trial cost, and security guardrails pass |
| G14-B | Technical content review is complete; core docs, SDK journeys, samples, and developer portal are ready |
| G14-C | Community identity isolation, moderation SLA, malicious-content controls, verified knowledge, and zero private customer leakage pass |
| G14-D | Publisher verification, executable-asset security and license gates, install rollback, review abuse controls, and zero critical asset incidents pass |
| G14-E | I18n architecture, critical UI localization, human review for security and billing, regional formats, and regional compliance pass |
| G14-F | Regional assessment, approved launch playbook, local support, partner quality gates, and regional metrics are ready |
| G14-G | G14-A through G14-F all pass, channel economics and contribution margin are visible, and critical open growth risks equal zero |

A later gate cannot compensate for an earlier failure. Only Skill 460 may return scalable-growth-ready, and only when G14-G is fully evidenced.

## Shared hard rules

- Bind growth to verified customer migration value rather than traffic, accounts, generated code, tokens, calls, or other vanity measures.
- Keep metric definitions versioned and identity resolution lawful, minimal, and tenant-isolated.
- Never bypass security, privacy, consent, quality, license, localization, support, or margin guardrails for growth.
- Keep critical UI, security, billing, legal, tax, and regional compliance under qualified human or authoritative-system review.
- Separate plans and candidate recommendations from approved or executed field outcomes.
- Require an owner and stop condition for every program, channel, experiment, launch, and open risk.
- Preserve failures, limitations, uncertainty, and non-significant experiments in the learning repository.
- Do not claim global readiness from translation alone or repeatability from a single regional success.
