import { NextRequest, NextResponse } from "next/server";
import type { GenerationJobCreateRequest } from "../../../lib/contracts";
import {
  authorize,
  createJob,
  GenerationRunnerError,
} from "../../../lib/server/generationRunner";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
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
    const job = await createJob(context, body);
    return NextResponse.json(job, { status: 202 });
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "INVALID_REQUEST";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
