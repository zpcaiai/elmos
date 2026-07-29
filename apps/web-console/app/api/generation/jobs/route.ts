import { NextRequest, NextResponse } from "next/server";
import type { GenerationJobCreateRequest } from "../../../lib/contracts";
import {
  authorize,
  createJob,
  GenerationRunnerError,
} from "../../../lib/server/generationRunner";
import {
  createHostedGenerationJob,
  hostedExecutionEnabled,
} from "../../../lib/server/hostedExecutionClient";
import { withBusinessAudit } from "../../../lib/server/operationsProxy";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "GENERATION_JOB_CREATE",
        businessLine: "PROJECT_SYNTHESIS",
        route: "/api/generation/jobs",
        target: "generation-job",
      },
      () => create(request),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function create(request: NextRequest) {
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" },
        { status: 415 },
      );
    }
    const rawBody = await request.text();
    if (Buffer.byteLength(rawBody, "utf-8") > 96 * 1024) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "REQUEST_TOO_LARGE" },
        { status: 413 },
      );
    }
    const context = authorize(request);
    const body = JSON.parse(rawBody) as GenerationJobCreateRequest;
    const job = hostedExecutionEnabled()
      ? await createHostedGenerationJob(context, body)
      : await createJob(context, body);
    return NextResponse.json(job, { status: 202 });
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "INVALID_REQUEST";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
