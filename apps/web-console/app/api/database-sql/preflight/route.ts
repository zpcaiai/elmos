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
  let context;
  try {
    context = chinaDbSqlContext(request);
  } catch (error) {
    return blocked(error);
  }

  try {
    return await withBusinessAudit(
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
          );
          const preflightRequest = parseChinaDbSqlPreflightRequest(raw);
          const capabilities = await fetchChinaDbSqlCapabilities(context);
          const result = await assessChinaDbSql(context, preflightRequest, capabilities);
          return NextResponse.json(result, { headers: chinaDbSqlPrivateHeaders });
        } catch (error) {
          return blocked(error);
        }
      },
    );
  } catch {
    return blocked(new ChinaDbSqlPolicyError(
      503,
      "BUSINESS_AUDIT_UNAVAILABLE",
      "SQL 预检业务审计当前不可用。",
    ));
  }
}
