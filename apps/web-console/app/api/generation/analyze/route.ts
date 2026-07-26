import { NextRequest, NextResponse } from "next/server";
import type { GenerationAnalyzeRequest } from "../../../lib/contracts";
import {
  analyzeIntent,
  authorize,
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
    if (Buffer.byteLength(rawBody, "utf-8") > 64 * 1024) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "REQUEST_TOO_LARGE" },
        { status: 413 },
      );
    }
    const context = authorize(request);
    const body = JSON.parse(rawBody) as GenerationAnalyzeRequest;
    return NextResponse.json(await analyzeIntent(context, body));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "INVALID_REQUEST";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
