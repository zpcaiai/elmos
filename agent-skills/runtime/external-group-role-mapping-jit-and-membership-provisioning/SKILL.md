---
name: external-group-role-mapping-jit-and-membership-provisioning
description: "Implement versioned external-group mappings, impact simulation, source authority, JIT membership policies, role provisioning, and privilege-escalation controls."
---

# Objective

Convert SAML group claims and SCIM Groups into approved ELMOS entitlements
without allowing external names to become implicit roles.

# External group model

Create:

```text
iam.external_groups
iam.external_group_members
iam.external_group_versions
iam.group_entitlement_mappings
iam.group_mapping_versions
iam.group_mapping_simulations
iam.group_mapping_approvals
iam.provisioned_entitlements
iam.entitlement_sources
