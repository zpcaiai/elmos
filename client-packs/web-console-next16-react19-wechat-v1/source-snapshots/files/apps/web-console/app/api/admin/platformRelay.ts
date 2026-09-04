import { OperationsProxyError } from "../../lib/server/operationsProxy";

/**
 * 把上游响应原样透出。
 *
 * 刻意不解析再重序列化：控制面已经决定了状态码与 body，
 * 中间层重新组装只会制造两处需要同步的真相。
 */
export async function relayPlatform(upstream: Response): Promise<Response> {
  const payload = await upstream.text();
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store, private",
      "Vary": "Authorization",
    },
  });
}

/**
 * 读取受限的请求体。
 *
 * 平台管理端的写操作体积都很小；不设上限等于给一个已认证的管理员一条
 * 把内存打满的路径。
 */
export async function readPlatformJson(request: Request): Promise<Record<string, unknown>> {
  const raw = await request.text();
  if (raw.length > 8_192) {
    throw new OperationsProxyError(413, "PLATFORM_BODY_TOO_LARGE", "请求体过大。");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new OperationsProxyError(400, "PLATFORM_BODY_INVALID", "请求体不是合法 JSON。");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new OperationsProxyError(400, "PLATFORM_BODY_INVALID", "请求体必须是对象。");
  }
  return parsed as Record<string, unknown>;
}
