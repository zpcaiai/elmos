export class RequestBodyError extends Error {
  readonly status: number;
  constructor(status: number, code: string) {
    super(code);
    this.status = status;
  }
}

/** Enforce the byte budget while reading; Content-Length is only an early check. */
export async function readBoundedRequestBody(
  request: Request,
  maximumBytes: number,
  timeoutMs = 10_000,
): Promise<string> {
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes < 1
    || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1) {
    throw new Error("REQUEST_BODY_BUDGET_INVALID");
  }
  const declared = request.headers.get("content-length");
  if (declared !== null && !/^(0|[1-9][0-9]*)$/.test(declared)) {
    throw new RequestBodyError(400, "CONTENT_LENGTH_INVALID");
  }
  if (declared !== null && Number(declared) > maximumBytes) {
    void request.body?.cancel("REQUEST_TOO_LARGE").catch(() => undefined);
    throw new RequestBodyError(413, "REQUEST_TOO_LARGE");
  }
  if (request.signal.aborted) throw new RequestBodyError(408, "REQUEST_ABORTED");
  if (!request.body) return "";
  const reader = request.body.getReader();
  let rejectWait: (reason: Error) => void = () => undefined;
  const interrupted = new Promise<never>((_, reject) => { rejectWait = reject; });
  const abort = () => rejectWait(new RequestBodyError(408, "REQUEST_ABORTED"));
  request.signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => rejectWait(new RequestBodyError(408, "REQUEST_BODY_TIMEOUT")), timeoutMs);
  const chunks: Uint8Array[] = [];
  let observed = 0;
  try {
    while (true) {
      const { done, value } = await Promise.race([reader.read(), interrupted]);
      if (done) break;
      observed += value.byteLength;
      if (observed > maximumBytes) throw new RequestBodyError(413, "REQUEST_TOO_LARGE");
      chunks.push(value);
    }
    if (declared !== null && Number(declared) !== observed) {
      throw new RequestBodyError(400, "CONTENT_LENGTH_MISMATCH");
    }
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks, observed));
    } catch {
      throw new RequestBodyError(400, "REQUEST_UTF8_INVALID");
    }
  } catch (error) {
    // Do not let a stalled producer's cancellation hook retain the HTTP handler.
    void reader.cancel(error).catch(() => undefined);
    throw error;
  } finally {
    clearTimeout(timer);
    request.signal.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}
