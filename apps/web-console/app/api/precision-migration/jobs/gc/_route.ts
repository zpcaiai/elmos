import { NextRequest, NextResponse } from "next/server";

import {
  archiveExpiredPrecisionJobs,
  precisionContext,
  PrecisionMigrationRunnerError,
} from "../../../../lib/server/precisionMigrationRunner";
import { BoundedJsonError, readBoundedJson } from "../../../../lib/server/boundedJson";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const context = precisionContext(request, "admin:operate");
    const body = await readBoundedJson(request, 16 * 1024, "PRECISION_REQUEST_TOO_LARGE");
    const olderThanSeconds = Number(
      typeof body === "object" && body !== null ? (body as { olderThanSeconds?: unknown }).olderThanSeconds : undefined,
    );
    return NextResponse.json(await archiveExpiredPrecisionJobs(context, olderThanSeconds));
  } catch (error) {
    const status = error instanceof PrecisionMigrationRunnerError || error instanceof BoundedJsonError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "PRECISION_RUNNER_FAILED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
