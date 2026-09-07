import type {
  OperationsJobBusinessLine,
  OperationsJobStatus,
} from "../operationsContracts";

export const operationsJobsRequiredRoles = Object.freeze({
  list: "VIEWER",
  cancel: "OPERATOR",
} as const);

export const operationsJobBusinessLines = [
  "GENERATION",
  "TRANSLATION",
  "SPRING_UPGRADE",
  "REPOSITORY_WORKSPACE",
  "MODERNIZATION_PROOF",
] as const satisfies readonly OperationsJobBusinessLine[];

export const operationsJobStatuses = [
  "QUEUED",
  "CLAIMED",
  "RUNNING",
  "SUCCEEDED",
  "PARTIAL",
  "FAILED",
  "CANCELLED",
  "LOST",
] as const satisfies readonly OperationsJobStatus[];

const allowedListParameters = new Set(["limit", "businessLine", "status"]);
const businessLines = new Set<string>(operationsJobBusinessLines);
const statuses = new Set<string>(operationsJobStatuses);
const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const boundedLimitPattern = /^(?:[1-9]|[1-9][0-9]|100)$/;

export class OperationsJobsPolicyError extends Error {
  readonly errorCode: string;

  constructor(errorCode: string, message: string) {
    super(message);
    this.name = "OperationsJobsPolicyError";
    this.errorCode = errorCode;
  }
}

function rejectQuery(message: string): never {
  throw new OperationsJobsPolicyError("ADMIN_JOBS_QUERY_INVALID", message);
}

function singleValue(search: URLSearchParams, field: string): string | null {
  const values = search.getAll(field);
  if (values.length > 1) {
    rejectQuery(`${field} 只能提供一次。`);
  }
  return values[0] ?? null;
}

/**
 * Produces the only query shape accepted by the control-plane jobs endpoint.
 * Unknown, repeated, blank, non-canonical, or out-of-range values fail here
 * instead of being silently dropped or reinterpreted upstream.
 */
export function operationsJobListQuery(search: URLSearchParams): URLSearchParams {
  for (const key of search.keys()) {
    if (!allowedListParameters.has(key)) {
      rejectQuery("存在不支持的作业筛选条件。");
    }
  }

  const rawLimit = singleValue(search, "limit");
  const limit = rawLimit ?? "50";
  if (!boundedLimitPattern.test(limit)) {
    rejectQuery("limit 必须是 1 到 100 之间的规范整数。");
  }

  const query = new URLSearchParams({ limit });
  const businessLine = singleValue(search, "businessLine");
  if (businessLine !== null) {
    if (!businessLines.has(businessLine)) {
      rejectQuery("businessLine 不在允许清单中。");
    }
    query.set("businessLine", businessLine);
  }

  const status = singleValue(search, "status");
  if (status !== null) {
    if (!statuses.has(status)) {
      rejectQuery("status 不在允许清单中。");
    }
    query.set("status", status);
  }
  return query;
}

export function operationsJobId(value: unknown): string {
  if (typeof value !== "string" || !identifierPattern.test(value)) {
    throw new OperationsJobsPolicyError(
      "ADMIN_JOB_ID_INVALID",
      "jobId 不符合管理作业标识契约。",
    );
  }
  return value;
}

export function assertEmptyOperationsJobQuery(search: URLSearchParams): void {
  if ([...search.keys()].length > 0) {
    rejectQuery("取消作业不接受查询参数。");
  }
}

/** Preserve upstream status and payload, including 200 idempotent replays and 202 first requests. */
export async function relayOperationsJobResponse(upstream: Response): Promise<Response> {
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store, private",
      Vary: "Authorization",
    },
  });
}
