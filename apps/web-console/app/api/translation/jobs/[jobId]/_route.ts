import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../lib/server/generationRunner";
import {
  authorizeTranslation,
  getTranslationJob,
} from "../../../../lib/server/translationRunner";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorizeTranslation(request);
    const { jobId } = await context.params;
    return NextResponse.json(
      await getTranslationJob(authorized, jobId),
      { headers: { "Cache-Control": "private, no-store" } },
    );
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof GenerationRunnerError
      ? error.message
      : "TRANSLATION_RUNNER_ERROR";
    return NextResponse.json(
      { status: "BLOCKED", reason },
      { status, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}
