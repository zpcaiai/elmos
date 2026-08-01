import { NextRequest, NextResponse } from "next/server";

import {
  createPrecisionJob,
  listPrecisionJobs,
  precisionContext,
  PrecisionMigrationRunnerError,
} from "../../../lib/server/precisionMigrationRunner";

export const dynamic = "force-dynamic";

function blocked(error: unknown): NextResponse {
  const status = error instanceof PrecisionMigrationRunnerError ? error.status : 500;
  const reason = error instanceof Error ? error.message : "PRECISION_RUNNER_FAILED";
  return NextResponse.json({ status: "BLOCKED", reason }, { status });
}

export async function GET(request: NextRequest) {
  try {
    return NextResponse.json(await listPrecisionJobs(precisionContext(request)), {
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    return blocked(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" }, { status: 415 });
    }
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf-8") > 1024 * 1024) {
      return NextResponse.json({ status: "BLOCKED", reason: "PRECISION_REQUEST_TOO_LARGE" }, { status: 413 });
    }
    return NextResponse.json(await createPrecisionJob(precisionContext(request), JSON.parse(raw)), { status: 202 });
  } catch (error) {
    return blocked(error);
  }
}
