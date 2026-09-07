import { decodeJwt } from "jose";

const organizationPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

/**
 * A local routing guard for cookie-backed commercial requests.
 *
 * The caller must obtain `selectedOrganizationId` from the authenticated,
 * encrypted account session. This decoder deliberately does not pretend to
 * replace JWT verification: commercial-api remains responsible for signature,
 * issuer, audience, expiry and scope validation. The comparison prevents the
 * Web BFF from forwarding an old tenant token after the user has switched the
 * selected organization in the sealed session.
 */
export function assertCommercialTenantDelegation(
  accessToken: string,
  selectedOrganizationId: string,
): void {
  let tokenOrganizationId: unknown;
  try {
    tokenOrganizationId = decodeJwt(accessToken).organization_id;
  } catch {
    throw tenantDelegationRequired();
  }
  if (
    !organizationPattern.test(selectedOrganizationId)
    || typeof tokenOrganizationId !== "string"
    || !organizationPattern.test(tokenOrganizationId)
    || tokenOrganizationId !== selectedOrganizationId
  ) {
    throw tenantDelegationRequired();
  }
}

export class CommercialBillingPolicyError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(
    status: number,
    code: string,
    message: string,
  ) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function tenantDelegationRequired(): CommercialBillingPolicyError {
  return new CommercialBillingPolicyError(
    403,
    "COMMERCIAL_TENANT_DELEGATION_REQUIRED",
    "当前租户需要重新获取商业服务授权，请重新登录后再试。",
  );
}
