import assert from "node:assert/strict";
import {
  BillingReconciliationPolicyError,
  parseReconciliationResolution,
  reconciliationListQuery,
  requireFinancialOidcAdmin,
} from "./billingReconciliationPolicy.ts";
import {
  assertCommercialTenantDelegation,
  CommercialBillingPolicyError,
} from "./commercialBillingPolicy.ts";

let checks = 0;

function jwt(organizationId) {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({
    sub: "finance-approver",
    organization_id: organizationId,
    scope: "commercial:billing:admin",
  })).toString("base64url");
  return `${header}.${payload}.test-signature`;
}

function rejected(action, ErrorType, code) {
  assert.throws(action, (error) => {
    assert.ok(error instanceof ErrorType);
    assert.equal(error.code, code);
    return true;
  });
  checks += 1;
}

// A selected tenant can never be paired with a token for another tenant, and a
// token that cannot even expose an organization claim also fails closed.
rejected(
  () => assertCommercialTenantDelegation(jwt("tenant-a"), "tenant-b"),
  CommercialBillingPolicyError,
  "COMMERCIAL_TENANT_DELEGATION_REQUIRED",
);
rejected(
  () => assertCommercialTenantDelegation("not-a-jwt", "tenant-a"),
  CommercialBillingPolicyError,
  "COMMERCIAL_TENANT_DELEGATION_REQUIRED",
);
assert.doesNotThrow(() => assertCommercialTenantDelegation(jwt("tenant-a"), "tenant-a"));
checks += 1;

// Any non-OIDC authentication discriminator fails closed.
rejected(
  () => requireFinancialOidcAdmin({
    role: "APPROVER",
    authentication: "UNSUPPORTED_CREDENTIAL",
  }, "VIEWER"),
  BillingReconciliationPolicyError,
  "FINANCIAL_OIDC_SESSION_REQUIRED",
);
rejected(
  () => requireFinancialOidcAdmin({
    role: "VIEWER",
    authentication: "OIDC_SESSION",
    accessToken: "enterprise-oidc-token-long-enough",
  }, "APPROVER"),
  BillingReconciliationPolicyError,
  "FINANCIAL_ADMIN_ROLE_INSUFFICIENT",
);
rejected(
  () => requireFinancialOidcAdmin({
    role: "OWNER",
    authentication: "OIDC_SESSION",
    accessToken: "enterprise-oidc-token-long-enough",
  }, "VIEWER"),
  BillingReconciliationPolicyError,
  "FINANCIAL_ADMIN_ROLE_INSUFFICIENT",
);
assert.doesNotThrow(() => requireFinancialOidcAdmin({
  role: "APPROVER",
  authentication: "OIDC_SESSION",
  accessToken: "enterprise-oidc-token-long-enough",
}, "APPROVER"));
checks += 1;

assert.equal(
  reconciliationListQuery(new URLSearchParams({ status: "OPEN", limit: "100" })),
  "status=OPEN&limit=100",
);
checks += 1;
rejected(
  () => reconciliationListQuery(new URLSearchParams({ status: "UNKNOWN" })),
  BillingReconciliationPolicyError,
  "BILLING_RECONCILIATION_FILTER_INVALID",
);
rejected(
  () => reconciliationListQuery(new URLSearchParams({ status: "" })),
  BillingReconciliationPolicyError,
  "BILLING_RECONCILIATION_FILTER_INVALID",
);
rejected(
  () => reconciliationListQuery(new URLSearchParams("status=OPEN&status=REJECTED")),
  BillingReconciliationPolicyError,
  "BILLING_RECONCILIATION_FILTER_INVALID",
);

const validBody = JSON.stringify({
  reconciliationCaseId: "recon-case-1",
  resolutionStatus: "RESOLVED",
  resolutionRef: "bank-statement:2026-08-09/42",
});
const validKey = "finance-resolve-recon-case-1-attempt-1";
assert.deepEqual(parseReconciliationResolution(validBody, validKey), {
  reconciliationCaseId: "recon-case-1",
  resolutionStatus: "RESOLVED",
  resolutionRef: "bank-statement:2026-08-09/42",
  idempotencyKey: validKey,
});
checks += 1;
assert.equal(parseReconciliationResolution(JSON.stringify({
  reconciliationCaseId: "recon-case-2",
  resolutionStatus: "REJECTED",
  resolutionRef: "provider-receipt:reject/42",
}), "finance-reject-recon-case-2-attempt-1").resolutionStatus, "REJECTED");
checks += 1;
rejected(
  () => parseReconciliationResolution(
    JSON.stringify({
      reconciliationCaseId: "recon-case-1",
      resolutionStatus: "OPEN",
      resolutionRef: "bank-statement:2026-08-09/42",
    }),
    validKey,
  ),
  BillingReconciliationPolicyError,
  "BILLING_RECONCILIATION_STATUS_INVALID",
);
rejected(
  () => parseReconciliationResolution(validBody, "new-key"),
  BillingReconciliationPolicyError,
  "IDEMPOTENCY_KEY_INVALID",
);
rejected(
  () => parseReconciliationResolution(
    JSON.stringify({
      reconciliationCaseId: "recon-case-1",
      resolutionStatus: "REJECTED",
      resolutionRef: "evidence/42",
      organizationId: "tenant-b",
    }),
    validKey,
  ),
  BillingReconciliationPolicyError,
  "BILLING_RECONCILIATION_REQUEST_INVALID",
);

console.log(`billing reconciliation policy: ${checks} checks passed`);
