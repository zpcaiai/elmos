---
name: test-data-privacy-synthetic-data-and-fixture-manager
description: Govern classified test data, synthetic generation, masking, subset selection, recorded traffic, fixture versions, short-lived leases, and destruction. Use when tests need database, message, file, tenant, permission, temporal, or sensitive data.
---

# Test Data Privacy and Fixture Management

## Prefer minimal data

Choose hand-authored minimal fixtures, then synthetic data, then masked/subset data, and only then explicitly authorized restricted production-like data. Never copy a full production database by default.

## Define the contract

Record schema, keys, relationships, distributions, boundaries, nulls, time zones, locales, volumes, lifecycle, owner, purpose, and compatible tests. Classify public, internal, confidential, personal, financial, health, authentication, and secret data.

## Generate and mask correctly

Preserve referential integrity, tenant/permission semantics, time order, conservation rules, and rare/invalid cases. Distinguish reversible tokenization, irreversible masking, pseudonymization, generalization, and synthetic replacement. Validate that masking preserves required cross-table identities without exposing originals.

## Version fixtures and leases

Record fixture version, schema version, generator, seed, hash, owner, retention, and compatible tests. Issue a short-lived lease, materialize, use, destroy, and audit. Mark fixtures, generators, golden masters, and contracts stale when production schemas change.

## Record traffic safely

Require authorization, redaction/tokenization, cookie and secret removal, payload limits, encryption, and retention before recording. Emit inventory, data contracts, synthetic plan, masking results, fixture manifest, and lease evidence.
