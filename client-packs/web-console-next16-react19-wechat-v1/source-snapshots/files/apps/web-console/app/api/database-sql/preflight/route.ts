import { NextRequest, NextResponse } from "next/server";

import {
  ChinaDbSqlPolicyError,
  chinaDbSqlRequestLimitBytes,
  parseChinaDbSqlPreflightRequest,
} from "../../../lib/chinadbSqlContracts";
import { BoundedJsonError, readBoundedJson } from "../../../lib/server/boundedJson";
import {
  assessChinaDbSql,
  chinaDbSqlContext,
  chinaDbSqlFailure,
  chinaDbSqlPrivateHeaders,
  fetchChinaDbSqlCapabilities,
  type ChinaDbSqlContext,
} from "../../../lib/server/chinadbSqlPreflight";
import { withBusinessAudit } from "../../../lib/server/operationsProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function blocked(error: unknown): NextResponse {
  const normalized = error instanceof BoundedJsonError
    ? new ChinaDbSqlPolicyError(error.status, error.message)
    : error;
  const failure = chinaDbSqlFailure(normalized);
  return NextResponse.json(failure.body, {
    status: failure.status,
    headers: chinaDbSqlPrivateHeaders,
  });
}

export async function POST(request: NextRequest) {
  let context: ChinaDbSqlContext;
  try {
    context = chinaDbSqlContext(request, "translation:execute");
  } catch (error) {
    return blocked(error);
  }

  try {
    const response = await withBusinessAudit(
      request,
      {
        action: "DATABASE_SQL_PREFLIGHT_ASSESS",
        businessLine: "DATABASE_DATA_SQL",
        route: "/api/database-sql/preflight",
        target: "chinadb-sql-preflight",
      },
      async () => {
        try {
          const raw = await readBoundedJson(
            request,
            chinaDbSqlRequestLimitBytes,
            "CHINADB_SQL_REQUEST_TOO_LARGE",
            true,
          );
          const preflightRequest = parseChinaDbSqlPreflightRequest(raw);
          const capabilities = await fetchChinaDbSqlCapabilities(context, request.signal);
          const result = await assessChinaDbSql(
            context,
            preflightRequest,
            capabilities,
            request.signal,
          );
          return NextResponse.json(result, { headers: chinaDbSqlPrivateHeaders });
        } catch (error) {
          return blocked(error);
        }
      },
    );
    if (!response.ok && response.headers.get("X-ELMOS-ChinaDB-Fail-Closed") !== "1") {
      return blocked(new ChinaDbSqlPolicyError(
        503,
        "BUSINESS_AUDIT_COMPLETION_UNAVAILABLE",
        "SQL 预检完成审计当前不可用。",
      ));
    }
    return response;
  } catch {
    return blocked(new ChinaDbSqlPolicyError(
      503,
      "BUSINESS_AUDIT_UNAVAILABLE",
      "SQL 预检业务审计当前不可用。",
    ));
  }
}
