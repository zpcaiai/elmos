import { NextRequest, NextResponse } from "next/server";
import type { GenerationTargetId } from "../../../../../lib/contracts";
import {
  authorize,
  GenerationRunnerError,
  startRuntime,
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
        action: "GENERATION_RUNTIME_START",
        businessLine: "PROJECT_SYNTHESIS",
        route: "/api/generation/jobs/:id/run",
        target: "generation-runtime",
      },
      () => run(request, context),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function run(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    if (hostedExecutionEnabled()) {
      throw new GenerationRunnerError(409, "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE");
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" },
        { status: 415 },
      );
    }
    const rawBody = await request.text();
    if (Buffer.byteLength(rawBody, "utf-8") > 4 * 1024) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "REQUEST_TOO_LARGE" },
        { status: 413 },
      );
    }
    const authorized = authorize(request);
    const { jobId } = await context.params;
    const body = JSON.parse(rawBody) as { language?: GenerationTargetId };
    if (!body.language) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "LANGUAGE_REQUIRED" },
        { status: 400 },
      );
    }
    return NextResponse.json(await startRuntime(authorized, jobId, body.language));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
