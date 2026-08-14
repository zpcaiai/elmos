import { NextRequest, NextResponse } from "next/server";
import {
  chinaDbSqlContext,
  chinaDbSqlFailure,
  chinaDbSqlPrivateHeaders,
  fetchChinaDbSqlCapabilities,
} from "../../../lib/server/chinadbSqlPreflight";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  try {
    const context = chinaDbSqlContext(request);
    return NextResponse.json(await fetchChinaDbSqlCapabilities(context), {
      headers: chinaDbSqlPrivateHeaders,
    });
  } catch (error) {
    const failure = chinaDbSqlFailure(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: chinaDbSqlPrivateHeaders,
    });
  }
}
