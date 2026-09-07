import { NextRequest, NextResponse } from "next/server";
import {
  authorize,
  GenerationRunnerError,
  getJob,
} from "../../../../lib/server/generationRunner";
import {
  getHostedGenerationJob,
  hostedExecutionEnabled,
} from "../../../../lib/server/hostedExecutionClient";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorize(request);
    const { jobId } = await context.params;
    return NextResponse.json(hostedExecutionEnabled()
      ? await getHostedGenerationJob(authorized, jobId)
      : await getJob(authorized, jobId));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
