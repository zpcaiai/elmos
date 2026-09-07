import { NextRequest, NextResponse } from "next/server";
import {
  chinaDbSqlFailure,
  chinaDbSqlPrivateHeaders,
  fetchChinaDbSqlCapabilities,
  optionalChinaDbSqlContext,
} from "../../../lib/server/chinadbSqlPreflight";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  try {
    const context = optionalChinaDbSqlContext(request, "workspace:view");
    const capabilities = await fetchChinaDbSqlCapabilities(context, request.signal);
    return NextResponse.json(capabilities, {
      headers: context ? chinaDbSqlPrivateHeaders : { "cache-control": "no-store" },
    });
  } catch (error) {
    const failure = chinaDbSqlFailure(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: chinaDbSqlPrivateHeaders,
    });
  }
}
