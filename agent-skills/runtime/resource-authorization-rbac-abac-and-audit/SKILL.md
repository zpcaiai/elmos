---
name: resource-authorization-rbac-abac-and-audit
description: "Implement role permissions, resource grants, contextual authorization, separation of duties, and auditable decisions for repositories, projects, runners, artifacts, approvals, and evidence."
---

# Objective

Authentication answers who the caller is.

This skill implements what the caller may do to a specific resource.

Authorization chain:

TenantContext
→ role permissions
→ resource relationship or grant
→ contextual constraints
→ separation-of-duties check
→ authorization decision
→ enforcement
→ audit

# Permission model

Implement stable permission codes.

Initial minimum catalog:

```text
repository.read
repository.import
repository.manage

project.create
project.read
project.execute
project.cancel

plan.read
plan.approve
plan.reject

delivery.read
delivery.approve
delivery.publish

runner.read
runner.enroll
runner.approve
runner.revoke

artifact.read
artifact.download
evidence.read
evidence.export

audit.read
policy.read
policy.override
billing.read
billing.manage
