import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import {
  authorizeTranslation,
  cancelTranslationJob,
} from "../../../../../lib/server/translationRunner";
import { withBusinessAudit } from "../../../../../lib/server/operationsProxy";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "TRANSLATION_JOB_CANCEL",
        businessLine: "LANGUAGE_TRANSLATION",
        route: "/api/translation/jobs/:id/cancel",
        target: "translation-job",
      },
      () => cancel(request, context),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function cancel(
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
