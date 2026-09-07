# Batch 38–45 strict test strategy

The suite preserves 400 exact seed cases owned by 30 test Skills and covers product Skills 1325–1496. Every Batch has two direct cases for each of twelve categories: success, boundary, negative, dependency failure, security, replay/idempotency, version drift, evidence tamper, recovery, performance, privacy, and governance. Cross-cutting cases cover edition topology, upgrade, SRE/DR, supply chain, compliance, knowledge isolation, Agent control, compatibility, FinOps, privacy, customer evidence, performance, and final certification.

Qualification order is deterministic: validate Skills and Schemas, validate the catalog and coverage matrix, run negative gate tests, execute approved environments and corpora, capture immutable evidence, independently replay results, run M38–M45 domain gates, collect authorized customer and third-party evidence, then submit the exact signed certification request.

P0 and P1 require 100% pass. P2 requires at least 98%, but every case must have an executed terminal result before certification; `not-run`, blocked, missing, invalid, or waived P0/P1 cases block. Zero-tolerance security, tenant, data, signature, Agent kill-switch, billing, integrity, freshness, and replay findings always block.
