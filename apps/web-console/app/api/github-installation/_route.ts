import {
  authenticateSpringProxy,
  githubAppProxyConfiguration,
} from "../spring-upgrades/proxyPolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: import("next/server").NextRequest) {
  const configuration = githubAppProxyConfiguration();
  if (!configuration) {
    return Response.json(
      {
        errorCode: "GITHUB_APP_NOT_CONFIGURED",
        message: "GitHub App 控制面尚未配置。",
        retryable: false,
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
  const authentication = authenticateSpringProxy(request);
  if (authentication instanceof Response) return authentication;
  try {
    const upstream = await fetch(
      `${configuration.controlPlaneBase}/api/v1/github/installations/connect`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "X-ELMOS-Organization-ID": authentication.organizationId,
          "X-ELMOS-Actor-ID": authentication.actorId,
        },
        body: "{}",
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      },
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "cache-control": "no-store",
        "content-type": upstream.headers.get("content-type")
          ?? "application/json",
        "referrer-policy": "no-referrer",
      },
    });
  } catch {
    return Response.json(
      {
        errorCode: "GITHUB_APP_ONBOARDING_UNAVAILABLE",
        message: "GitHub App 安装流程当前不可用。",
        retryable: true,
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
