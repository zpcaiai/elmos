---
name: effect-system-inference
description: Infer explicit operation and callable effects to support safe transformation and verification. Use for purity, IO, database, mutation, blocking, async, security, or unknown calls.
---
# Effect System Inference
Read `../references/uir-v1.md`. Combine intrinsic operations, call summaries, evidenced framework metadata, and pinned knowledge to a recursive fixpoint. Unknown calls are not pure; getters may execute code; allocation, mutation, logging, exceptions, and suspension are separate observable effects. Record resource/access/condition/order/repetition/idempotency/confidence/evidence. Every operation has a fact or explicit unknown.
