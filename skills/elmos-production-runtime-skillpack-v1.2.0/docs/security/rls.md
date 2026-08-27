# Tenant Isolation and RLS

RLS must have an explicit service model.

## Request-scoped services

Set within the transaction:

`SET LOCAL app.tenant_id = '<tenant uuid>'`

Policies compare row tenant_id with `current_setting('app.tenant_id', true)`.

## Cross-tenant background services

Do not grant broad table bypass casually.

Prefer:
- controlled SECURITY DEFINER functions exposing only necessary rows/actions;
- dedicated database roles with narrowly scoped permissions;
- explicit audit of cross-tenant operations.

Billing and RLS must be tested with negative cross-tenant cases.
