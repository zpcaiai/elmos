---
name: privileged-access-jit-request-approval-lease-and-expiry
description: "Implement just-in-time privileged access requests, risk evaluation, step-up authentication, separation of duties, approvals, time-bound grant leases, activation, automatic expiry, revocation, and verification."
---

# Objective

Replace permanent administrative access with purpose-bound, resource-bound,
time-bound privileged grants.

# Domain model

Create:

```text
iam.privileged_access_profiles
iam.privileged_access_requests
iam.privileged_access_request_resources
iam.privileged_access_risk_assessments
iam.privileged_access_approvals
iam.privileged_grants
iam.privileged_grant_leases
iam.privileged_access_sessions
iam.privileged_access_actions
iam.privileged_access_expiry_jobs
iam.privileged_access_reviews
