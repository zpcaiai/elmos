# Normative Invariants

1. Downstream authority is never wider than upstream authority.
2. Status observation never starts/reconnects/authenticates a runtime.
3. Missing/unknown runtime status is never interpreted as READY.
4. Removed/changed upstream security enums fail closed until mapping is revalidated.
5. `SUSPENDED` and `HANDOFF_READY` are nonterminal.
6. Handoff requires quiesce + durable checkpoint + writer close before ownership transfer.
7. Stale owner epoch cannot append timeline events or commit results.
8. Parent termination/archive leaves no runnable descendant unless subtree ownership was explicitly transferred.
9. Internal reviewer/verifier sessions do not inherit user plugins/MCP/extensions by default.
10. Only root-user authorization semantics may authorize protected effects; summaries/assistant prose cannot fabricate consent.
11. Context provenance survives truncation, compaction, replay, fork and model switch.
12. Failed tool/MCP calls are durably replayable with terminal status and result/error content.
13. Approval binds exact action/effect, plan digest and protected resource digest.
14. Builder cannot publish; publication requires a certified checkpoint and PublicationBroker authority.
15. Evidence status distinguishes PASS, FAIL, WAIVED and PENDING.
16. PENDING or material WAIVED checks cannot be reported as PASS.
17. File↔directory repository transformations preserve path-kind semantics in checkpoints.
18. Side effects use idempotency keys and durable receipts before retry/recovery.
19. Model-generated JSON is not Truth evidence without trusted execution provenance.
20. Release verification binds the exact bytes/digests that were published, not only pre-publication build outputs.
