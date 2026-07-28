import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import {
  authorizeTranslation,
  cancelTranslationJob,
} from "../../../../../lib/server/translationRunner";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorizeTranslation(request);
    const { jobId } = await context.params;
    return NextResponse.json(await cancelTranslationJob(authorized, jobId));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "TRANSLATION_RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
