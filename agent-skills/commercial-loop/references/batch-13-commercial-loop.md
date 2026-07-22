# Batch 13 commercial loop reference

## Boundary

Batch 13 is an evidence-bound control and adjudication layer over external CRM, CPQ, contract, billing, payment, accounting, identity, support, partner, and production systems. It may read signed evidence and produce draft instructions or reports. It never creates or mutates leads, opportunities, quotes, contracts, orders, invoices, tenants, entitlements, tickets, partner settlements, repositories, Runners, customer workloads, or production routes.

Admission requires one immutable, signed, version-pinned Batch 12 artifact that reached T-G. Bind every result to one assessment run, platform-business version, policy version, source-system identifiers, observed time, evidence references, and owner. An exception is recorded as its class only; never copy credentials, tokens, customer source, sensitive payloads, or raw secrets into evidence.

## Unified model

Use all eight domains: `GO_TO_MARKET`, `CUSTOMER_DISCOVERY`, `SOLUTION_ENGINEERING`, `COMMERCIAL_CONTRACT`, `CUSTOMER_ONBOARDING`, `DELIVERY_MANAGEMENT`, `CUSTOMER_SUCCESS_SUPPORT`, and `PARTNER_REVENUE_OPERATIONS`.

Model normal and exceptional lifecycle states with explicit entry criteria, exit criteria, owner, next action, due date, risk, amount, technical scope, and evidence. Support exactly these motions: `direct-sales`, `poc-led-sales`, `enterprise-subscription`, `professional-services`, `partner-led-delivery`, and `managed-migration-service`. Each motion must be present in the catalog, contract model, and delivery support matrix.

## Sequential gates

- B13-A validates standardized discovery and POC evidence.
- B13-B validates catalog, pricing, quote, SOW, contract, margin, discount, and security alignment.
- B13-C validates safe onboarding, owned delivery baselines, scope control, evidence, acceptance, and billing triggers.
- B13-D validates supportability, SLA response, customer health, value, renewal, churn, and advocacy consent.
- B13-E validates partner diligence, certification, bounded access, quality, channel ownership, and settlement.
- B13-F validates source-owned metrics, forecast, capacity, cost visibility, profitability, value, and risk ownership.
- B13-G validates external scale acceptance, traceability, retention, commercial consistency, and zero critical blocker.

Gates are sequential and fail closed. Evidence must be `PASSED`, complete, current, version-matched, and independently supplied by the appropriate external authority. Never compensate for a failed earlier domain with a later metric.

## Blocking rules

Block discovery bypass; unscanned automation promises; a POC without objective criteria or with hidden failures; quote, SOW, contract, entitlement, or scope mismatch; unauthorized discount; missing or unacceptable margin; security or SLA overcommitment; production source access before security approval; onboarding without customer owner or baseline; uncontrolled scope creep; missing deliverable or acceptance evidence; billing before an authorized milestone; unowned P1 failure; churn risk without action; uncertified partner work; excessive partner access; unresolved channel conflict or settlement; missing cost visibility; conflicting metric definitions; or any ownerless critical risk.

## Required output contract

Every result is append-only and identifies input versions, decision, blockers, unknowns, owner, next action, timestamps, evidence references, and external system of record. Preserve failed and `NOT_RUN` results. Do not overwrite prior versions.

Set `commercial_operation_executed=false` in control-plane artifacts. Set `commercial_scale_candidate=true` only when B13-G is reached, every external evidence envelope is complete and passed, all references are traceable, and no blocker remains. Repository tests and synthetic fixtures prove only deterministic fail-closed behavior, never real customer delivery, revenue, acceptance, settlement, or production readiness.

