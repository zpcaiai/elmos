import type { NextRequest } from "next/server";

export class BoundedJsonError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export async function readBoundedJson(
  request: NextRequest,
  maxBytes: number,
  tooLargeCode = "REQUEST_TOO_LARGE",
): Promise<unknown> {
  const mediaType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new BoundedJsonError(415, "JSON_CONTENT_TYPE_REQUIRED");
  }

  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null) {
    const parsedLength = Number(declaredLength);
    if (!Number.isSafeInteger(parsedLength) || parsedLength < 0) {
      throw new BoundedJsonError(400, "CONTENT_LENGTH_INVALID");
    }
    if (parsedLength > maxBytes) {
      throw new BoundedJsonError(413, tooLargeCode);
    }
  }

  const reader = request.body?.getReader();
  const chunks: Buffer[] = [];
  let received = 0;
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maxBytes) {
        await reader.cancel(tooLargeCode);
        throw new BoundedJsonError(413, tooLargeCode);
      }
      chunks.push(Buffer.from(value));
    }
  }

  try {
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks, received));
    return JSON.parse(decoded);
  } catch {
    throw new BoundedJsonError(400, "INVALID_JSON");
  }
}
