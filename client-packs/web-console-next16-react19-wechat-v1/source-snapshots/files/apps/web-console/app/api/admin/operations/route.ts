import {
  authorizeAdmin,
  fetchOperationsConsole,
  mutateOperations,
  OperationsProxyError,
  proxyErrorResponse,
  requireAdminMutationSameOrigin,
} from "../../../lib/server/operationsProxy";
import { readBoundedAdminJsonObject } from "../../../lib/server/adminMutationPolicy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    const upstream = await fetchOperationsConsole(
      new URL(request.url).searchParams,
      administrator,
    );
    return relay(upstream);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}

const actionRoles = {
  EVALUATE: "OPERATOR",
  ACKNOWLEDGE_ALERT: "OPERATOR",
  ASSIGN_INCIDENT: "OPERATOR",
  RESOLVE_INCIDENT: "OPERATOR",
  APPROVE_REMEDIATION: "APPROVER",
  REJECT_REMEDIATION: "APPROVER",
  PREPARE_SCM: "APPROVER",
  ENFORCE_RETENTION: "APPROVER",
} as const;

type Action = keyof typeof actionRoles;

export async function POST(request: Request) {
  try {
    requireAdminMutationSameOrigin(request);
    const body = await readBoundedAdminJsonObject(request);
    const action = body.action;
    if (typeof action !== "string" || !Object.hasOwn(actionRoles, action)) {
      throw new OperationsProxyError(400, "ADMIN_OPERATION_INVALID", "管理操作不在允许清单中。");
    }
    const resolved = resolveAction(action as Action, body);
    const administrator = authorizeAdmin(request, actionRoles[action as Action]);
    const upstream = await mutateOperations(
      resolved.path,
      resolved.body,
      administrator,
    );
    return relay(upstream);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}

function resolveAction(action: Action, body: Record<string, unknown>): {
  path: string;
  body: Record<string, unknown>;
} {
  const fieldsByAction: Record<Action, readonly string[]> = {
    EVALUATE: ["action"],
    ACKNOWLEDGE_ALERT: ["action", "alertId", "expectedVersion"],
    ASSIGN_INCIDENT: ["action", "incidentId", "ownerActorId", "expectedVersion"],
    RESOLVE_INCIDENT: ["action", "incidentId", "resolutionCode", "expectedVersion"],
    APPROVE_REMEDIATION: ["action", "proposalId", "expectedVersion"],
    REJECT_REMEDIATION: ["action", "proposalId", "expectedVersion"],
    PREPARE_SCM: ["action", "proposalId", "expectedVersion"],
    ENFORCE_RETENTION: ["action", "retentionDays"],
  };
  const allowedFields = new Set(fieldsByAction[action]);
  if (
    Object.keys(body).length !== allowedFields.size
    || Object.keys(body).some((field) => !allowedFields.has(field))
  ) {
    throw new OperationsProxyError(400, "ADMIN_OPERATION_INVALID", "管理操作包含缺失或多余字段。");
  }
  const identifier = (field: string): string => {
    const value = body[field];
    if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) {
      throw new OperationsProxyError(400, "ADMIN_OPERATION_INVALID", `${field} 无效。`);
    }
    return value;
  };
  const version = (): number => {
    const value = Number(body.expectedVersion);
    if (!Number.isInteger(value) || value < 1 || value > 1_000_000) {
      throw new OperationsProxyError(400, "ADMIN_OPERATION_INVALID", "expectedVersion 无效。");
    }
    return value;
  };
  switch (action) {
    case "EVALUATE":
      return { path: "/evaluate", body: {} };
    case "ACKNOWLEDGE_ALERT":
      return {
        path: `/alerts/${identifier("alertId")}/acknowledge`,
        body: { expectedVersion: version() },
      };
    case "ASSIGN_INCIDENT":
      return {
        path: `/incidents/${identifier("incidentId")}/assign`,
        body: { ownerActorId: identifier("ownerActorId"), expectedVersion: version() },
      };
    case "RESOLVE_INCIDENT":
      return {
        path: `/incidents/${identifier("incidentId")}/resolve`,
        body: { resolutionCode: identifier("resolutionCode"), expectedVersion: version() },
      };
    case "APPROVE_REMEDIATION":
    case "REJECT_REMEDIATION":
      return {
        path: `/remediations/${identifier("proposalId")}/decision`,
        body: {
          decision: action === "APPROVE_REMEDIATION" ? "APPROVE" : "REJECT",
          expectedVersion: version(),
        },
      };
    case "PREPARE_SCM":
      return {
        path: `/remediations/${identifier("proposalId")}/prepare-scm`,
        body: { expectedVersion: version() },
      };
    case "ENFORCE_RETENTION": {
      const days = Number(body.retentionDays);
      if (!Number.isInteger(days) || days < 7 || days > 365) {
        throw new OperationsProxyError(400, "ADMIN_OPERATION_INVALID", "retentionDays 无效。");
      }
      return { path: "/retention/enforce", body: { retentionDays: days } };
    }
  }
}

async function relay(upstream: Response): Promise<Response> {
  const payload = await upstream.text();
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store, private",
      "Vary": "Authorization",
    },
  });
}
