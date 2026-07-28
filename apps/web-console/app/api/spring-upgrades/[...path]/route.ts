import { NextRequest } from "next/server";
import { springRouteCatalogFallback } from "../../../lib/springRoutes";
import { proxyNotConfiguredResponse, springProxyConfiguration } from "../proxyPolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const runId = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const allowedPath = new RegExp(
  `^(?:capabilities|${runId}(?:/(?:logs|artifact|retry|cancel|runtime/(?:start|stop)))?)$`,
);

type Context = { params: Promise<{ path: string[] }> };

export async function GET(_request: NextRequest, context: Context) {
  return proxy("GET", context);
}

export async function POST(request: NextRequest, context: Context) {
  return proxy("POST", context, request);
}

async function proxy(method: "GET" | "POST", context: Context, request?: NextRequest) {
  const path = (await context.params).path.join("/");
  const configuration = springProxyConfiguration();
  if (!configuration.configured) {
    if (method === "GET" && path === "capabilities") {
      return Response.json(
        {
          packKey: "spring-boot-2-7-18-to-3-5-3",
          sourceTuple: { springBoot: "2.7.18", java: "17", build: "Maven 3.9.11" },
          targetTuple: { springBoot: "3.5.3", java: "21", build: "Maven 3.9.11" },
          openRewrite: { rewriteSpring: "6.35.0", mavenPlugin: "6.44.0" },
          routes: springRouteCatalogFallback,
          experimentalRoutesRequireOptIn: true,
          transformerConfigured: false,
          transformerReason: "SPRING_UPGRADE_PROXY_NOT_CONFIGURED",
          runtimeRunnerConfigured: false,
          runtimeRunnerReason: "ISOLATED_APPLICATION_RUNNER_NOT_CONFIGURED",
          independentVerifierConfigured: false,
          independentVerifierReason: "INDEPENDENT_VERIFIER_NOT_CONFIGURED",
          downloadRequiresIndependentPass: true,
          runtimeRequiresIndependentPass: true,
        },
        { headers: { "cache-control": "no-store" } },
      );
    }
    return proxyNotConfiguredResponse();
  }
  if (!allowedPath.test(path)) {
    return Response.json(
      { errorCode: "SPRING_UPGRADE_PROXY_PATH_REJECTED", message: "不支持的迁移操作。", retryable: false },
      { status: 404 },
    );
  }
  const headers = new Headers({ "X-ELMOS-Organization-ID": configuration.organizationId });
  let body: string | undefined;
  if (method === "POST") {
    headers.set("content-type", "application/json");
    body = await request?.text();
    if (!body) body = "{}";
    if (new TextEncoder().encode(body).byteLength > 4_096) {
      return Response.json(
        { errorCode: "SPRING_UPGRADE_ACTION_TOO_LARGE", message: "迁移操作请求超过 4 KB 上限。", retryable: false },
        { status: 413 },
      );
    }
  }
  try {
    const upstream = await fetch(`${configuration.engineBase}/engine/v1/spring-upgrades/${path}`, {
      method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
    const responseHeaders = new Headers();
    responseHeaders.set("cache-control", "no-store");
    for (const header of ["content-type", "content-disposition", "content-length", "x-content-sha256", "etag"]) {
      const value = upstream.headers.get(header);
      if (value) responseHeaders.set(header, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        errorCode: "SPRING_UPGRADE_ENGINE_UNAVAILABLE",
        message: "Java 转换引擎当前不可用，未执行任何客户代码。",
        retryable: true,
      },
      { status: 503 },
    );
  }
}
