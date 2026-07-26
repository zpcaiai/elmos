import { NextRequest, NextResponse } from "next/server";
import {
  authorize,
  cancelJob,
  GenerationRunnerError,
} from "../../../../../lib/server/generationRunner";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorize(request);
    const { jobId } = await context.params;
    return NextResponse.json(await cancelJob(authorized, jobId));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
