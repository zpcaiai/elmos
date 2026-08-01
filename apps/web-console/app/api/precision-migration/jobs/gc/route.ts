import { NextRequest, NextResponse } from "next/server";

import {
  archiveExpiredPrecisionJobs,
  precisionContext,
  PrecisionMigrationRunnerError,
} from "../../../../lib/server/precisionMigrationRunner";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as { olderThanSeconds?: unknown };
    const olderThanSeconds = Number(body.olderThanSeconds);
    const context = precisionContext(request, "admin:operate");
    return NextResponse.json(await archiveExpiredPrecisionJobs(context, olderThanSeconds));
  } catch (error) {
    const status = error instanceof PrecisionMigrationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "PRECISION_RUNNER_FAILED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
