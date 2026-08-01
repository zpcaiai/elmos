import { NextRequest, NextResponse } from "next/server";

import {
  cancelPrecisionJob,
  getPrecisionJob,
  precisionContext,
  PrecisionMigrationRunnerError,
  retryPrecisionJob,
} from "../../../../lib/server/precisionMigrationRunner";

export const dynamic = "force-dynamic";

function blocked(error: unknown): NextResponse {
  const status = error instanceof PrecisionMigrationRunnerError ? error.status : 500;
  const reason = error instanceof Error ? error.message : "PRECISION_RUNNER_FAILED";
  return NextResponse.json({ status: "BLOCKED", reason }, { status });
}

export async function GET(request: NextRequest, context: { params: Promise<{ jobId: string }> }) {
  try {
    const { jobId } = await context.params;
    return NextResponse.json(await getPrecisionJob(precisionContext(request), jobId), {
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    return blocked(error);
  }
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ jobId: string }> }) {
  try {
    const { jobId } = await context.params;
    return NextResponse.json(await cancelPrecisionJob(precisionContext(request), jobId));
  } catch (error) {
    return blocked(error);
  }
}

export async function POST(request: NextRequest, context: { params: Promise<{ jobId: string }> }) {
  try {
    const { jobId } = await context.params;
    const body = await request.json() as { action?: unknown };
    if (body.action !== "retry") {
      return NextResponse.json({ status: "BLOCKED", reason: "ACTION_NOT_SUPPORTED" }, { status: 400 });
    }
    return NextResponse.json(await retryPrecisionJob(precisionContext(request), jobId), { status: 202 });
  } catch (error) {
    return blocked(error);
  }
}
