export class RequestBodyError extends Error {
  readonly status: number;
  constructor(status: number, code: string) {
    super(code);
    this.status = status;
  }
}

/** Enforce the byte budget while reading; Content-Length is only an early check. */
export async function readBoundedRequestBody(
  request: Pick<Request, "headers" | "signal" | "body">,
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
  const deadline = Date.now() + timeoutMs;
  const bytes = new Uint8Array(maximumBytes);
  let observed = 0;
  let reads = 0;
  const next = (): Promise<ReadableStreamReadResult<Uint8Array>> => new Promise((resolve, reject) => {
    const remaining = deadline - Date.now();
    if (remaining <= 0) { reject(new RequestBodyError(408, "REQUEST_BODY_TIMEOUT")); return; }
    if (request.signal.aborted) { reject(new RequestBodyError(408, "REQUEST_ABORTED")); return; }
    let finished = false;
    const finish = (error?: Error, result?: ReadableStreamReadResult<Uint8Array>) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      request.signal.removeEventListener("abort", abort);
      if (error) reject(error);
      else resolve(result!);
    };
    const abort = () => finish(new RequestBodyError(408, "REQUEST_ABORTED"));
    const timer = setTimeout(() => finish(new RequestBodyError(408, "REQUEST_BODY_TIMEOUT")), remaining);
    request.signal.addEventListener("abort", abort, { once: true });
    if (request.signal.aborted) abort();
    else void reader.read().then((result) => finish(undefined, result), (error) => finish(error));
  });
  try {
    while (true) {
      if (++reads > maximumBytes * 4 + 1024) throw new RequestBodyError(400, "REQUEST_BODY_CHUNK_LIMIT");
      const { done, value } = await next();
      if (done) break;
      if (observed + value.byteLength > maximumBytes) throw new RequestBodyError(413, "REQUEST_TOO_LARGE");
      bytes.set(value, observed);
      observed += value.byteLength;
      // Yield even when the producer supplies an immediately available empty
      // chunk forever; deadlines and client aborts must get an event-loop turn.
      if (reads % 1024 === 0) await new Promise<void>((resolve) => setImmediate(resolve));
    }
    if (declared !== null && Number(declared) !== observed) {
      throw new RequestBodyError(400, "CONTENT_LENGTH_MISMATCH");
    }
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes.subarray(0, observed));
    } catch {
      throw new RequestBodyError(400, "REQUEST_UTF8_INVALID");
    }
  } catch (error) {
    // Do not let a stalled producer's cancellation hook retain the HTTP handler.
    void reader.cancel(error).catch(() => undefined);
    throw error;
  } finally {
    reader.releaseLock();
  }
}
