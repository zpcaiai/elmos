# model-provider-adapter

**Providers:** OpenAI/compatible/private model endpoints

**Scope:** reasoning, generation, embeddings and judge candidates.

This directory is an implementation contract, not a live integration. Implement the abstract Elmos port, negotiate capabilities and versions, enforce environment-owned authority, return typed results, and pass every case in `conformance.yaml`. The Adapter never owns semantic truth, routing, or completion.
