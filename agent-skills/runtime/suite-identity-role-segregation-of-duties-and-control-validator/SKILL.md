---
name: suite-identity-role-segregation-of-duties-and-control-validator
description: Map and validate enterprise suite identities, business duties, technical roles, permissions, approval limits, record and field access, emergency access, service identities, and Segregation of Duties. Use for SAP, Oracle, Dynamics, Salesforce, ERP, CRM, HCM, or SCM access migration and Cutover gates.
---

# Suite Access Governance

## Execute

1. Classify workforce, contractor, partner, service, integration, support, administrator, and emergency identities.
2. Map source technical role to business duty, business role, and target technical role; never copy by name alone.
3. Validate suite, module, process, transaction, object, record, field, action, and approval-limit access.
4. Version SoD rules and test conflicts such as vendor creation plus payment, PO creation plus approval, journal posting plus approval, and user creation plus privileged assignment.
5. Validate compensating approval, monitoring, limits, independent review, reports, and time-bound access.
6. Give integration, batch, and robot identities independent least-privilege credentials, owner, rotation, and audit.
7. Run positive and negative user tests, cross-company denial, sensitive-field denial, and emergency-access expiry.

## Hard gate

Block activation on critical conflict, unknown duty mapping, failed negative test, unverified compensating control, or shared service identity. Agents cannot accept SoD risk.
