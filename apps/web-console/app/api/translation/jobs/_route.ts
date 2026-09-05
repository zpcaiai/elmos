import { NextRequest, NextResponse } from "next/server";
import {
  authorizeTranslation,
  createTranslationJob,
} from "../../../lib/server/translationRunner";
import { GenerationRunnerError } from "../../../lib/server/generationRunner";
import { withBusinessAudit } from "../../../lib/server/operationsProxy";
import {
  readBoundedTranslationRequest,
  rejectDuplicateTopLevelJsonFields,
} from "../../../lib/server/translationRequestBody";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "TRANSLATION_JOB_CREATE",
        businessLine: "LANGUAGE_TRANSLATION",
        route: "/api/translation/jobs",
        target: "translation-job",
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
    const context = authorizeTranslation(request);
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" }, { status: 415 });
    }
    const raw = await readBoundedTranslationRequest(request);
    const body = JSON.parse(raw);
    rejectDuplicateTopLevelJsonFields(raw);
    return NextResponse.json(
      await createTranslationJob(context, body),
      { status: 202, headers: { "Cache-Control": "private, no-store" } },
    );
  } catch (error) {
    const status = error instanceof GenerationRunnerError
      ? error.status
      : error instanceof SyntaxError ? 400 : 500;
    const reason = error instanceof GenerationRunnerError
      ? error.message
      : error instanceof SyntaxError ? "TRANSLATION_REQUEST_INVALID" : "TRANSLATION_RUNNER_ERROR";
    return NextResponse.json(
      { status: "BLOCKED", reason },
      { status, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}
