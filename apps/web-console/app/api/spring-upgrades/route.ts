import { NextRequest } from "next/server";
import {
  authenticateSpringProxy,
  githubAppProxyConfiguration,
  proxyNotConfiguredResponse,
  springProxyConfiguration,
} from "./proxyPolicy";
import { withBusinessAudit } from "../../lib/server/operationsProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const maximumRequestBytes = 32_768;

export async function POST(request: NextRequest) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "SPRING_UPGRADE_CREATE",
        businessLine: "SPRING_MODERNIZATION",
        route: "/api/spring-upgrades",
        target: "spring-upgrade",
      },
      () => start(request),
    );
  } catch {
    return Response.json(
      { errorCode: "BUSINESS_AUDIT_UNAVAILABLE", message: "业务审计不可用，未启动迁移。", retryable: true },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}

async function start(request: NextRequest) {
  const configuration = springProxyConfiguration();
  if (!configuration.configured) return proxyNotConfiguredResponse();
  const authentication = authenticateSpringProxy(request);
  if (authentication instanceof Response) return authentication;
  const { actorId, organizationId } = authentication;
  let input: Record<string, unknown>;
  try {
    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > maximumRequestBytes) {
      return Response.json(
        { errorCode: "SPRING_UPGRADE_REQUEST_TOO_LARGE", message: "迁移请求超过 32 KB 上限。", retryable: false },
        { status: 413 },
      );
    }
    input = JSON.parse(body) as Record<string, unknown>;
    if (!input || Array.isArray(input) || typeof input !== "object") throw new Error("object required");
  } catch {
    return Response.json(
      { errorCode: "SPRING_UPGRADE_REQUEST_INVALID", message: "请求 JSON 无法解析。", retryable: false },
      { status: 400 },
    );
  }

  if (input.sourceMode === "GITHUB_APP") {
    return startFromGitHubApp(input, organizationId, actorId);
  }
  return forward(`${configuration.engineBase}/engine/v1/spring-upgrades`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-ELMOS-Organization-ID": organizationId,
      "X-ELMOS-Actor-ID": actorId,
    },
    body: JSON.stringify({ ...input, organizationId }),
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
}

async function startFromGitHubApp(
  input: Record<string, unknown>,
  organizationId: string,
  actorId: string,
) {
  const configuration = githubAppProxyConfiguration();
  if (!configuration) {
    return Response.json(
      {
        errorCode: "GITHUB_APP_SNAPSHOT_NOT_CONFIGURED",
        message: "GitHub App 私有仓库快照服务尚未配置；未获取 Token 或客户代码。",
        retryable: false,
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
  const repositoryId = typeof input.repositoryId === "string"
    ? input.repositoryId.trim()
    : "";
  const requestedRef = typeof input.requestedRef === "string"
    ? input.requestedRef.trim()
    : "";
  const idempotencyKey = typeof input.idempotencyKey === "string"
    ? input.idempotencyKey.trim()
    : "";
  if (
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(repositoryId)
    || !requestedRef
    || requestedRef.length > 512
    || !idempotencyKey
    || idempotencyKey.length > 128
  ) {
    return Response.json(
      {
        errorCode: "GITHUB_APP_SNAPSHOT_REQUEST_INVALID",
        message: "请选择已授权仓库并填写有效 Branch / Tag。",
        retryable: false,
      },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  let materialized: {
    repositoryFullName: string;
    snapshot: {
      snapshotId: string;
      requestedRef: string;
      resolvedCommitSha: string;
      archiveSha256: string;
    };
    materialization: {
      relativePath: string;
      archiveSha256: string;
    };
  };
  try {
    const response = await fetch(
      `${configuration.controlPlaneBase}/api/v1/repository-snapshots/spring-materializations`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "X-ELMOS-Organization-ID": organizationId,
          "X-ELMOS-Actor-ID": actorId,
        },
        body: JSON.stringify({
          repositoryId,
          requestedRef,
          correlationId: crypto.randomUUID(),
          idempotencyKey: `${idempotencyKey}:snapshot`,
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(120_000),
      },
    );
    if (!response.ok) {
      return Response.json(
        {
          errorCode: "GITHUB_APP_SNAPSHOT_FAILED",
          message: "GitHub App 无法生成租户绑定的不可变 Snapshot；未启动转换。",
          retryable: response.status >= 500,
        },
        { status: response.status, headers: { "cache-control": "no-store" } },
      );
    }
    materialized = await response.json() as typeof materialized;
  } catch {
    return Response.json(
      {
        errorCode: "GITHUB_APP_SNAPSHOT_UNAVAILABLE",
        message: "GitHub App 快照服务当前不可用；未启动转换。",
        retryable: true,
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }

  if (
    !materialized.repositoryFullName?.match(
      /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/,
    )
    || !materialized.snapshot?.snapshotId
    || !materialized.snapshot?.resolvedCommitSha?.match(/^[0-9a-f]{40}$/)
    || !materialized.snapshot?.archiveSha256?.match(/^[0-9a-f]{64}$/)
    || materialized.materialization?.archiveSha256
      !== materialized.snapshot.archiveSha256
    || !materialized.materialization?.relativePath
  ) {
    return Response.json(
      {
        errorCode: "GITHUB_APP_SNAPSHOT_EVIDENCE_INVALID",
        message: "快照服务响应未通过 Commit、摘要和物化路径一致性检查。",
        retryable: false,
      },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  return forward(`${configuration.engineBase}/engine/v1/spring-upgrades`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-ELMOS-Organization-ID": organizationId,
      "X-ELMOS-Actor-ID": actorId,
    },
    body: JSON.stringify({
      organizationId,
      sourceMode: "MATERIALIZED_SNAPSHOT",
      repositoryUrl: `https://github.com/${materialized.repositoryFullName}.git`,
      requestedRef: materialized.snapshot.requestedRef,
      expectedCommitSha: materialized.snapshot.resolvedCommitSha,
      snapshotId: materialized.snapshot.snapshotId,
      materializedRelativePath: materialized.materialization.relativePath,
      startAfterVerification: input.startAfterVerification === true,
      idempotencyKey,
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
}

async function forward(url: string, init: RequestInit) {
  try {
    const upstream = await fetch(url, init);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: safeHeaders(upstream.headers),
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

function safeHeaders(upstream: Headers) {
  const headers = new Headers();
  headers.set("cache-control", "no-store");
  headers.set("content-type", upstream.get("content-type") ?? "application/json");
  return headers;
}
