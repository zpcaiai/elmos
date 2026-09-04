import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { authorize, GenerationRunnerError } from "../../../../../../lib/server/generationRunner";
import {
  multimodalBoundaryEnvelope,
  MultimodalIntakeRunnerError,
  readMultimodalProgressBatch,
} from "../../../../../../lib/server/multimodalIntakeRunner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization, Last-Event-ID",
};
const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const cursorPattern = /^p1-[1-9][0-9]{0,15}-[0-9a-f]{64}$/;

function errorResponse(status: number, code: string, retryable: boolean, traceId: string) {
  return NextResponse.json(
    multimodalBoundaryEnvelope(status, code, retryable, traceId),
    { status, headers: privateHeaders },
  );
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  const traceId = `mmi-progress-bff-${randomUUID()}`;
  try {
    const keys = [...new Set(request.nextUrl.searchParams.keys())];
    if (keys.length !== 1 || keys[0] !== "projectId") {
      return errorResponse(400, "MULTIMODAL_PROGRESS_QUERY_INVALID", false, traceId);
    }
    const projectId = request.nextUrl.searchParams.get("projectId") ?? "";
    const { jobId } = await context.params;
    if (!identifierPattern.test(projectId) || !identifierPattern.test(jobId)) {
      return errorResponse(400, "MULTIMODAL_PROGRESS_RESOURCE_INVALID", false, traceId);
    }
    const rawCursor = request.headers.get("last-event-id");
    const cursor = rawCursor && rawCursor.length > 0 ? rawCursor : undefined;
    if (cursor !== undefined && !cursorPattern.test(cursor)) {
      return errorResponse(400, "MULTIMODAL_PROGRESS_CURSOR_INVALID", false, traceId);
    }
    const identity = authorize(request, "intake:read");
    const batch = await readMultimodalProgressBatch(
      { tenantId: identity.tenantId, actor: identity.actor },
      projectId,
      "jobs",
      jobId,
      cursor,
      request.signal,
    );
    return new NextResponse(batch, {
      status: 200,
      headers: {
        ...privateHeaders,
        "Content-Type": "text/event-stream; charset=utf-8",
        "Content-Length": String(Buffer.byteLength(batch, "utf8")),
        "X-Accel-Buffering": "no",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return errorResponse(499, "MULTIMODAL_PROGRESS_CLIENT_CLOSED", false, traceId);
    }
    const candidate = error instanceof MultimodalIntakeRunnerError
      ? error
      : error instanceof GenerationRunnerError
        ? new MultimodalIntakeRunnerError(error.status, error.message)
        : new MultimodalIntakeRunnerError(500, "MULTIMODAL_PROGRESS_INTERNAL_ERROR");
    const status = Number.isSafeInteger(candidate.status)
      && candidate.status >= 400 && candidate.status <= 599
      ? candidate.status
      : 500;
    const code = /^[A-Z][A-Z0-9_:-]{0,127}$/.test(candidate.code)
      ? candidate.code
      : "MULTIMODAL_PROGRESS_BOUNDARY_ERROR";
    return errorResponse(status, code, candidate.retryable === true, traceId);
  }
}
