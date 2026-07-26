import {
  githubAppProxyConfiguration,
} from "../spring-upgrades/proxyPolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const configuration = githubAppProxyConfiguration();
  if (!configuration) {
    return Response.json(
      {
        status: "NOT_CONFIGURED",
        repositories: [],
        errorCode: "GITHUB_APP_NOT_CONFIGURED",
        message: "GitHub App 尚未配置或未绑定控制面。",
      },
      // The catalog request itself succeeded and returns a typed, fail-closed
      // capability state. Mutating GitHub operations remain unavailable.
      { status: 200, headers: { "cache-control": "no-store" } },
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.controlPlaneBase}/api/v1/github/repositories`,
      {
        headers: {
          "X-ELMOS-Organization-ID": configuration.organizationId,
        },
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
      },
    });
  } catch {
    return Response.json(
      {
        status: "UNAVAILABLE",
        repositories: [],
        errorCode: "GITHUB_REPOSITORY_CATALOG_UNAVAILABLE",
        message: "已授权私有仓库目录当前不可用。",
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
