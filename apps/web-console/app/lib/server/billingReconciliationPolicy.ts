const roleRank = { VIEWER: 1, OPERATOR: 2, APPROVER: 3 } as const;
const allowedListStatuses = new Set(["OPEN", "RESOLVED", "REJECTED"]);
const allowedResolutionStatuses = new Set(["RESOLVED", "REJECTED"]);
const allowedListQueryKeys = new Set(["status", "limit"]);
const caseIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;
const resolutionRefPattern = /^[A-Za-z0-9][A-Za-z0-9._:/-]{7,254}$/;
const idempotencyKeyPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/;

export const reconciliationBodyLimitBytes = 4_096;

export type FinancialAdminPrincipal = {
  role: "VIEWER" | "OPERATOR" | "APPROVER";
  authentication: "OIDC_SESSION";
  accessToken?: string;
};

export type ReconciliationResolution = {
  reconciliationCaseId: string;
  resolutionStatus: "RESOLVED" | "REJECTED";
  resolutionRef: string;
  idempotencyKey: string;
};

export class BillingReconciliationPolicyError extends Error {
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

export function requireFinancialOidcAdmin(
  principal: FinancialAdminPrincipal,
  requiredRole: "VIEWER" | "APPROVER",
): void {
  if (
    principal.authentication !== "OIDC_SESSION"
    || typeof principal.accessToken !== "string"
    || principal.accessToken.length < 24
    || principal.accessToken.length > 16_384
  ) {
    throw new BillingReconciliationPolicyError(
      403,
      "FINANCIAL_OIDC_SESSION_REQUIRED",
      "财务对账只接受已验证的管理员企业账户会话。",
    );
  }
  const actualRank = roleRank[principal.role];
  if (!actualRank || actualRank < roleRank[requiredRole]) {
    throw new BillingReconciliationPolicyError(
      403,
      "FINANCIAL_ADMIN_ROLE_INSUFFICIENT",
      requiredRole === "APPROVER" ? "财务对账结案需要 APPROVER。" : "当前账户无权查看财务对账。",
    );
  }
}

export function reconciliationListQuery(search: URLSearchParams): string {
  for (const key of search.keys()) {
    if (!allowedListQueryKeys.has(key) || search.getAll(key).length !== 1) {
      throw invalidFilter();
    }
  }
  const status = search.has("status") ? search.get("status") as string : "OPEN";
  const rawLimit = search.has("limit") ? search.get("limit") as string : "100";
  if (!allowedListStatuses.has(status) || !/^[1-9][0-9]{0,2}$/.test(rawLimit)) {
    throw invalidFilter();
  }
  const limit = Number(rawLimit);
  if (limit < 1 || limit > 200) throw invalidFilter();
  return new URLSearchParams({ status, limit: String(limit) }).toString();
}

export function parseReconciliationResolution(
  rawBody: string,
  idempotencyKey: string,
): ReconciliationResolution {
  if (new TextEncoder().encode(rawBody).byteLength > reconciliationBodyLimitBytes) {
    throw new BillingReconciliationPolicyError(
      413,
      "BILLING_RECONCILIATION_BODY_TOO_LARGE",
      "财务对账请求超过允许大小。",
    );
  }
  if (!idempotencyKeyPattern.test(idempotencyKey)) {
    throw new BillingReconciliationPolicyError(
      400,
      "IDEMPOTENCY_KEY_INVALID",
      "必须提供 8 到 160 字符、由客户端稳定复用的 Idempotency-Key。",
    );
  }
  let source: unknown;
  try {
    source = JSON.parse(rawBody);
  } catch {
    throw invalidMutation();
  }
  if (typeof source !== "object" || source === null || Array.isArray(source)) {
    throw invalidMutation();
  }
  const body = source as Record<string, unknown>;
  const expectedKeys = ["reconciliationCaseId", "resolutionStatus", "resolutionRef"];
  const keys = Object.keys(body);
  if (keys.length !== expectedKeys.length || keys.some((key) => !expectedKeys.includes(key))) {
    throw invalidMutation();
  }
  if (
    typeof body.reconciliationCaseId !== "string"
    || !caseIdPattern.test(body.reconciliationCaseId)
  ) {
    throw invalidMutation();
  }
  if (
    typeof body.resolutionStatus !== "string"
    || !allowedResolutionStatuses.has(body.resolutionStatus)
  ) {
    throw new BillingReconciliationPolicyError(
      400,
      "BILLING_RECONCILIATION_STATUS_INVALID",
      "对账结案状态必须是 RESOLVED 或 REJECTED。",
    );
  }
  if (typeof body.resolutionRef !== "string" || !resolutionRefPattern.test(body.resolutionRef)) {
    throw invalidMutation();
  }
  return {
    reconciliationCaseId: body.reconciliationCaseId,
    resolutionStatus: body.resolutionStatus as "RESOLVED" | "REJECTED",
    resolutionRef: body.resolutionRef,
    idempotencyKey,
  };
}

function invalidFilter(): BillingReconciliationPolicyError {
  return new BillingReconciliationPolicyError(
    400,
    "BILLING_RECONCILIATION_FILTER_INVALID",
    "财务对账筛选条件无效。",
  );
}

function invalidMutation(): BillingReconciliationPolicyError {
  return new BillingReconciliationPolicyError(
    400,
    "BILLING_RECONCILIATION_REQUEST_INVALID",
    "财务对账结案请求无效。",
  );
}
