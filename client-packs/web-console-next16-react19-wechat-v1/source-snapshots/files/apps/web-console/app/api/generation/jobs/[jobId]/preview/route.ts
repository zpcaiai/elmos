import { NextRequest, NextResponse } from "next/server";
import {
  authorize,
  GenerationRunnerError,
  runtimePreview,
} from "../../../../../lib/server/generationRunner";
import { hostedExecutionEnabled } from "../../../../../lib/server/hostedExecutionClient";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    if (hostedExecutionEnabled()) {
      throw new GenerationRunnerError(409, "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE");
    }
    const authorized = authorize(request);
    const { jobId } = await context.params;
    return NextResponse.json(await runtimePreview(authorized, jobId), {
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof GenerationRunnerError ? error.code : "RUNNER_ERROR";
    return NextResponse.json(
      { status: "BLOCKED", reason },
      { status, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}
