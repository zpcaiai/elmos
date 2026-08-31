import { NextRequest, NextResponse } from "next/server";

import {
  createPrecisionJob,
  listPrecisionJobs,
  precisionContext,
  PrecisionMigrationRunnerError,
} from "../../../lib/server/precisionMigrationRunner";
import { BoundedJsonError, readBoundedJson } from "../../../lib/server/boundedJson";

export const dynamic = "force-dynamic";

function blocked(error: unknown): NextResponse {
  const status = error instanceof PrecisionMigrationRunnerError || error instanceof BoundedJsonError ? error.status : 500;
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
    const context = precisionContext(request);
    const body = await readBoundedJson(request, 1024 * 1024, "PRECISION_REQUEST_TOO_LARGE");
    return NextResponse.json(await createPrecisionJob(context, body), { status: 202 });
  } catch (error) {
    return blocked(error);
  }
}
