import type { NextRequest } from "next/server";

import { parseStrictJson, StrictJsonError } from "./strictJson";

export class BoundedJsonError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export async function readBoundedJson(
  request: NextRequest,
  maxBytes: number,
  tooLargeCode = "REQUEST_TOO_LARGE",
  strictTransport = false,
): Promise<unknown> {
  const mediaType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new BoundedJsonError(415, "JSON_CONTENT_TYPE_REQUIRED");
  }
  if (strictTransport) {
    const contentEncoding = request.headers.get("content-encoding")?.trim().toLowerCase();
    if (contentEncoding && contentEncoding !== "identity") {
      throw new BoundedJsonError(415, "CONTENT_ENCODING_REJECTED");
    }
    if (request.headers.has("transfer-encoding")) {
      throw new BoundedJsonError(400, "TRANSFER_ENCODING_REJECTED");
    }
  }

  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null) {
    if (!/^(?:0|[1-9][0-9]*)$/.test(declaredLength)) {
      throw new BoundedJsonError(400, "CONTENT_LENGTH_INVALID");
    }
    const parsedLength = Number(declaredLength);
    if (!Number.isSafeInteger(parsedLength)) throw new BoundedJsonError(400, "CONTENT_LENGTH_INVALID");
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

  if (declaredLength !== null && Number(declaredLength) !== received) {
    throw new BoundedJsonError(400, "CONTENT_LENGTH_MISMATCH");
  }

  try {
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks, received));
    return strictTransport ? parseStrictJson(decoded) : JSON.parse(decoded);
  } catch (error) {
    if (error instanceof StrictJsonError) {
      throw new BoundedJsonError(400, error.code);
    }
    throw new BoundedJsonError(400, "INVALID_JSON");
  }
}
