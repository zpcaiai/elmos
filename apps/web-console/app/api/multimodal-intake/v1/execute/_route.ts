import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { authorize, GenerationRunnerError } from "../../../../lib/server/generationRunner";
import {
  executeMultimodalSkill,
  multimodalBoundaryEnvelope,
  MultimodalIntakeRunnerError,
  parseMultimodalExecuteBody,
  parseStrictMultimodalJson,
  requiredMultimodalPermission,
} from "../../../../lib/server/multimodalIntakeRunner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization",
};
const maximumRequestBytes = 2 * 1024 * 1024;

function boundaryError(
  status: number,
  code: string,
  retryable: boolean,
  traceId: string,
) {
  return NextResponse.json(
    multimodalBoundaryEnvelope(status, code, retryable, traceId),
    { status, headers: privateHeaders },
  );
}

async function readBoundedBody(request: NextRequest, declaredBytes?: number): Promise<string> {
  if (!request.body) {
    if (declaredBytes !== undefined) {
      throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_SIZE_INVALID");
    }
    return "";
  }
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let observed = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      observed += value.byteLength;
      if (observed > maximumRequestBytes) {
        try {
          await reader.cancel("MULTIMODAL_REQUEST_TOO_LARGE");
        } catch {
          // The rejection is still deterministic even if the peer closed first.
        }
        throw new MultimodalIntakeRunnerError(413, "MULTIMODAL_REQUEST_TOO_LARGE");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (declaredBytes !== undefined && observed !== declaredBytes) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_SIZE_INVALID");
  }
  const bytes = new Uint8Array(observed);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_JSON_INVALID");
  }
}

export async function POST(request: NextRequest) {
  const boundaryTraceId = `mmi-bff-${randomUUID()}`;
  try {
    const mediaType = request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
    if (mediaType !== "application/json") {
      return boundaryError(415, "JSON_CONTENT_TYPE_REQUIRED", false, boundaryTraceId);
    }
    const contentEncoding = request.headers.get("content-encoding")?.trim().toLowerCase();
    if (contentEncoding && contentEncoding !== "identity") {
      return boundaryError(
        415,
        "MULTIMODAL_CONTENT_ENCODING_UNSUPPORTED",
        false,
        boundaryTraceId,
      );
    }
    const declared = request.headers.get("content-length");
    if (declared && (!/^[0-9]{1,10}$/.test(declared) || Number(declared) <= 0)) {
      return boundaryError(400, "MULTIMODAL_REQUEST_SIZE_INVALID", false, boundaryTraceId);
    }
    if (declared && Number(declared) > maximumRequestBytes) {
      return boundaryError(413, "MULTIMODAL_REQUEST_TOO_LARGE", false, boundaryTraceId);
    }
    const raw = await readBoundedBody(request, declared ? Number(declared) : undefined);
    const body = parseMultimodalExecuteBody(parseStrictMultimodalJson(raw));
    const permission = requiredMultimodalPermission(body.skill, body.operation);
    const identity = authorize(request, permission);
    const result = await executeMultimodalSkill(
      { tenantId: identity.tenantId, actor: identity.actor },
      body,
      request.headers.get("idempotency-key") ?? "",
    );
    return NextResponse.json(result, { status: 200, headers: privateHeaders });
  } catch (error) {
    const candidate = error instanceof MultimodalIntakeRunnerError
      ? error
      : error instanceof GenerationRunnerError
        ? new MultimodalIntakeRunnerError(error.status, error.message)
        : new MultimodalIntakeRunnerError(500, "MULTIMODAL_INTERNAL_ERROR");
    const status = Number.isSafeInteger(candidate.status) && candidate.status >= 400 && candidate.status <= 599
      ? candidate.status
      : 500;
    const code = /^[A-Z][A-Z0-9_:-]{0,127}$/.test(candidate.code)
      ? candidate.code
      : status >= 500
        ? "MULTIMODAL_INTERNAL_ERROR"
        : "MULTIMODAL_BOUNDARY_ERROR";
    return boundaryError(status, code, candidate.retryable === true, boundaryTraceId);
  }
}
