export class AdminMutationPolicyError extends Error {
  readonly status: number;
  readonly errorCode: string;

  constructor(
    message: string,
    status = 403,
    errorCode = "ADMIN_MUTATION_SAME_ORIGIN_REQUIRED",
  ) {
    super(message);
    this.name = "AdminMutationPolicyError";
    this.status = status;
    this.errorCode = errorCode;
  }
}

function declaredBodyLength(request: Request): number | null {
  const raw = request.headers.get("content-length");
  if (raw === null) return null;
  if (!/^(?:0|[1-9][0-9]*)$/.test(raw)) {
    throw new AdminMutationPolicyError(
      "管理写请求的 Content-Length 无效。",
      400,
      "ADMIN_MUTATION_BODY_INVALID",
    );
  }
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed)) {
    throw new AdminMutationPolicyError(
      "管理写请求体大小无效。",
      413,
      "ADMIN_MUTATION_BODY_TOO_LARGE",
    );
  }
  return parsed;
}

async function readBoundedBody(request: Request, maximumBytes: number): Promise<Uint8Array> {
  const declared = declaredBodyLength(request);
  if (declared !== null && declared > maximumBytes) {
    throw new AdminMutationPolicyError(
      "管理写请求体超过允许上限。",
      413,
      "ADMIN_MUTATION_BODY_TOO_LARGE",
    );
  }
  if (request.body === null) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maximumBytes) {
        await reader.cancel();
        throw new AdminMutationPolicyError(
          "管理写请求体超过允许上限。",
          413,
          "ADMIN_MUTATION_BODY_TOO_LARGE",
        );
      }
      if (value.byteLength > 0) chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

/** Read a small, explicit JSON object without allowing the runtime to buffer an unbounded body. */
export async function readBoundedAdminJsonObject(
  request: Request,
  maximumBytes = 16 * 1024,
): Promise<Record<string, unknown>> {
  const mediaType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new AdminMutationPolicyError(
      "管理写请求必须使用 application/json。",
      415,
      "ADMIN_MUTATION_CONTENT_TYPE_INVALID",
    );
  }
  const bytes = await readBoundedBody(request, maximumBytes);
  if (bytes.byteLength === 0) {
    throw new AdminMutationPolicyError(
      "管理写请求体不能为空。",
      400,
      "ADMIN_MUTATION_BODY_INVALID",
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new AdminMutationPolicyError(
      "管理写请求体不是有效 JSON。",
      400,
      "ADMIN_MUTATION_BODY_INVALID",
    );
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new AdminMutationPolicyError(
      "管理写请求必须是 JSON 对象。",
      400,
      "ADMIN_MUTATION_BODY_INVALID",
    );
  }
  return parsed as Record<string, unknown>;
}

/** Mutation endpoints whose contract has no body reject even one streamed byte. */
export async function assertEmptyAdminMutationBody(request: Request): Promise<void> {
  try {
    const bytes = await readBoundedBody(request, 0);
    if (bytes.byteLength === 0) return;
  } catch (error) {
    if (
      error instanceof AdminMutationPolicyError
      && error.errorCode === "ADMIN_MUTATION_BODY_TOO_LARGE"
    ) {
      throw new AdminMutationPolicyError(
        "该管理写操作不接受请求体。",
        400,
        "ADMIN_MUTATION_BODY_INVALID",
      );
    }
    throw error;
  }
  throw new AdminMutationPolicyError(
    "该管理写操作不接受请求体。",
    400,
    "ADMIN_MUTATION_BODY_INVALID",
  );
}

/** Every administrator mutation is cookie-authenticated and same-origin. */
export function assertAdminMutationOrigin(request: Request): void {
  let expectedOrigin: string;
  try {
    expectedOrigin = new URL(request.url).origin;
  } catch {
    throw new AdminMutationPolicyError("无法确定管理端请求来源。");
  }
  const presentedOrigin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (
    presentedOrigin === null
    || presentedOrigin !== expectedOrigin
    || (fetchSite !== null && fetchSite !== "same-origin")
  ) {
    throw new AdminMutationPolicyError("使用企业会话 cookie 的管理写操作必须来自当前管理端同源页面。");
  }
}
