# ADR-0002 — Durably queue the fourth task

## Status
Accepted.

## Context
Rejecting a valid fourth submission loses user intent and encourages retry storms. Executing it violates the hard limit.

## Decision
Persist the task as `WAITING_FOR_SLOT`, return a durable task ID and queue/admission details, and promote it when account, tenant, resource, budget, and platform gates permit.

## Consequences
- The API separates submission from execution admission.
- Queue retention/abuse limits and cancellation are required.
- UI must show queue reason, position, and estimated start.
