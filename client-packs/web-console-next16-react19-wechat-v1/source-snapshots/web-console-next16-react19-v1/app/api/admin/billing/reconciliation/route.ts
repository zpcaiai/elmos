import { NextRequest, NextResponse } from "next/server";
import {
  BillingReconciliationPolicyError,
  parseReconciliationResolution,
  reconciliationBodyLimitBytes,
  reconciliationListQuery,
  requireFinancialOidcAdmin,
} from "../../../../lib/server/billingReconciliationPolicy";
import {
  commercialBillingRequest,
  CommercialBillingProxyError,
  proxyError,
} from "../../../../lib/server/commercialBillingProxy";
import {
  authorizeAdmin,
  proxyErrorResponse,
} from "../../../../lib/server/operationsProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
} as const;

export async function GET(request: NextRequest) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    requireFinancialOidcAdmin(administrator, "VIEWER");
    const query = reconciliationListQuery(request.nextUrl.searchParams);
    const upstream = await commercialBillingRequest(
      request,
      `/commercial/v1/billing/reconciliation?${query}`,
    );
    return forward(upstream);
  } catch (error) {
    return mappedFailure(error);
  }
}

export async function POST(request: NextRequest) {
  let mutation;
  try {
    const administrator = authorizeAdmin(request, "APPROVER");
    requireFinancialOidcAdmin(administrator, "APPROVER");
    const mediaType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
    if (mediaType !== "application/json") {
      throw new BillingReconciliationPolicyError(
        415,
        "BILLING_RECONCILIATION_CONTENT_TYPE_INVALID",
        "财务对账结案请求必须使用 application/json。",
      );
    }
    mutation = parseReconciliationResolution(
      await readBoundedBody(request),
      request.headers.get("idempotency-key") ?? "",
    );
  } catch (error) {
    return mappedFailure(error);
  }

  try {
    const upstream = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/reconciliation/resolve",
      {
        method: "POST",
        idempotencyKey: mutation.idempotencyKey,
        body: JSON.stringify({
          reconciliationCaseId: mutation.reconciliationCaseId,
          resolutionStatus: mutation.resolutionStatus,
          resolutionRef: mutation.resolutionRef,
        }),
      },
    );
    if (upstream.status >= 500) return unknownMutationResult();
    const payload = await upstream.text();
    if (upstream.ok && !confirmedResolution(payload, mutation.resolutionStatus)) {
      return unknownMutationResult();
    }
    return new NextResponse(payload, {
      status: upstream.status,
      headers: {
        ...privateHeaders,
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    if (!(error instanceof CommercialBillingProxyError) || error.retryable) {
      return unknownMutationResult();
    }
    return mappedFailure(error);
  }
}

async function readBoundedBody(request: Request): Promise<string> {
  const declared = request.headers.get("content-length");
  if (declared && (!/^[0-9]+$/.test(declared) || Number(declared) > reconciliationBodyLimitBytes)) {
    throw new BillingReconciliationPolicyError(
      413,
      "BILLING_RECONCILIATION_BODY_TOO_LARGE",
      "财务对账请求超过允许大小。",
    );
  }
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > reconciliationBodyLimitBytes) {
        try {
          await reader.cancel();
        } catch {
          // Preserve the bounded-input error even if the client disconnects
          // while its over-sized stream is being cancelled.
        }
        throw new BillingReconciliationPolicyError(
          413,
          "BILLING_RECONCILIATION_BODY_TOO_LARGE",
          "财务对账请求超过允许大小。",
        );
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(merged);
  } catch {
    throw new BillingReconciliationPolicyError(
      400,
      "BILLING_RECONCILIATION_REQUEST_INVALID",
      "财务对账结案请求无效。",
    );
  }
}

function confirmedResolution(payload: string, expected: "RESOLVED" | "REJECTED"): boolean {
  try {
    const value = JSON.parse(payload) as { status?: unknown };
    return value?.status === expected;
  } catch {
    return false;
  }
}

function forward(upstream: Response): NextResponse {
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      ...privateHeaders,
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}

function mappedFailure(error: unknown): Response {
  if (error instanceof BillingReconciliationPolicyError) {
    return NextResponse.json({
      status: "ERROR",
      code: error.code,
      message: error.message,
      retryable: false,
    }, { status: error.status, headers: privateHeaders });
  }
  if (error instanceof CommercialBillingProxyError) {
    const mapped = proxyError(error);
    return NextResponse.json(mapped.body, { status: mapped.status, headers: privateHeaders });
  }
  const mapped = proxyErrorResponse(error);
  mapped.headers.set("Cache-Control", privateHeaders["Cache-Control"]);
  mapped.headers.set("Vary", privateHeaders.Vary);
  return mapped;
}

function unknownMutationResult(): Response {
  return NextResponse.json({
    status: "UNKNOWN",
    code: "BILLING_RECONCILIATION_RESULT_UNKNOWN",
    message: "商业服务未能确认本次对账结案结果。系统未自动重试；请先重新读取案件状态，再人工决定是否使用同一 Idempotency-Key 重放。",
    retryable: false,
    operationMayHaveCompleted: true,
  }, { status: 503, headers: privateHeaders });
}
