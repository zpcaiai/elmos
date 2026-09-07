import { NextRequest, NextResponse } from "next/server";
import {
  authorize,
  GenerationRunnerError,
  stopRuntime,
} from "../../../../../lib/server/generationRunner";
import { withBusinessAudit } from "../../../../../lib/server/operationsProxy";
import { hostedExecutionEnabled } from "../../../../../lib/server/hostedExecutionClient";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "GENERATION_RUNTIME_STOP",
        businessLine: "PROJECT_SYNTHESIS",
        route: "/api/generation/jobs/:id/stop",
        target: "generation-runtime",
      },
      () => stop(request, context),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function stop(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    if (hostedExecutionEnabled()) {
      throw new GenerationRunnerError(409, "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE");
    }
    const authorized = authorize(request);
    const { jobId } = await context.params;
    return NextResponse.json(await stopRuntime(authorized, jobId));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
