import { NextRequest, NextResponse } from "next/server";
import {
  authorizeTranslation,
  createTranslationJob,
} from "../../../lib/server/translationRunner";
import { GenerationRunnerError } from "../../../lib/server/generationRunner";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" }, { status: 415 });
    }
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf-8") > 8 * 1024) {
      return NextResponse.json({ status: "BLOCKED", reason: "REQUEST_TOO_LARGE" }, { status: 413 });
    }
    const context = authorizeTranslation(request);
    return NextResponse.json(await createTranslationJob(context, JSON.parse(raw)), { status: 202 });
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "TRANSLATION_REQUEST_INVALID";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
