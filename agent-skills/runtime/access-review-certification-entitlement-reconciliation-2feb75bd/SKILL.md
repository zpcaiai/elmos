---
name: access-review-certification-entitlement-reconciliation-2feb75bd
description: "Implement access-review campaigns covering human, machine, inherited, external-group, JIT, runner, token, and break-glass entitlements, with reviewer governance, decisions, remediation, verification, and evidence."
---

# Objective

Certify actual effective access rather than only reviewing role assignments.

Review chain:

scope definition
→ entitlement snapshot
→ reviewer assignment
→ review decision
→ remediation
→ verification
→ closure evidence

# Domain model

Create:

```text
iam.access_review_profiles
iam.access_review_campaigns
iam.access_review_scopes
iam.access_review_snapshots
iam.access_review_items
iam.access_review_reviewers
iam.access_review_decisions
iam.access_review_remediations
iam.access_review_verifications
iam.access_review_exceptions
iam.access_review_events
