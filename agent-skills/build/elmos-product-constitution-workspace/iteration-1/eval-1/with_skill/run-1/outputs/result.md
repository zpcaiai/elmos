# Decision: DENY cross-tenant request

- Treat the authenticated server context as authoritative: actor `org-a`. The body field `organizationId=org-b` is untrusted input. Reject the mismatch; do not silently create an `org-b` object and do not reveal whether `org-b` exists.
- Replace the unscoped lookup with an organization-scoped repository operation such as `findByOrganizationIdAndId(org-a, runId)`. Before any SQL, bind `app.organization_id=org-a` transaction-locally.
- Keep PostgreSQL `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` policies as the database backstop. Application predicates and RLS are both required; neither substitutes for the other.
- Return a generic denied/not-found response. Emit an append-only audit event containing actor/workload, server-derived organization, action, policy version, correlation id, decision `DENY`, and reason `TENANT_CONTEXT_MISMATCH`. Do not copy target-tenant record content into the event.
- No customer build, shell, Recipe, or agent work belongs in this control-plane path.

Required evidence: authorization decision, transaction tenant-binding record, zero cross-tenant rows returned, RLS integration-test result using a non-owner database role, and hash-chain-valid audit event.
