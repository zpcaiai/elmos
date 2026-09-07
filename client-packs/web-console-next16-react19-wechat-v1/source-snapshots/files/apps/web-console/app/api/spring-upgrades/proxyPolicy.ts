import { createHash, timingSafeEqual } from "node:crypto";
import { lstatSync, readFileSync } from "node:fs";
import path from "node:path";
import type { NextRequest } from "next/server";
import {
  accountCookieNames,
  AccountSessionError,
  accountSessionFromRequest,
  unsafeCookieValue,
} from "../../lib/server/accountSession";

const organizationPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const actorPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$/;

export type SpringProxyConfiguration =
  | {
      configured: true;
      engineBase: string;
      organizationId: string | null;
      multiTenant: boolean;
      controlPlaneBase: string | null;
    }
  | { configured: false };

export function springProxyConfiguration(): SpringProxyConfiguration {
  if (process.env.ELMOS_SPRING_PROXY_ENABLED !== "true") return { configured: false };
  const organizationId = process.env.ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID?.trim();
  const multiTenant = process.env.ELMOS_SPRING_PROXY_MULTI_TENANT === "true";
  const configuredBase = process.env.JAVA_ENGINE_BASE_URL?.trim();
  if (
    (!multiTenant && (!organizationId || !organizationPattern.test(organizationId)))
    || (multiTenant && organizationId)
    || !configuredBase
  ) {
    return { configured: false };
  }
  try {
    const engine = new URL(configuredBase);
    if (!["http:", "https:"].includes(engine.protocol) || engine.username || engine.password) {
      return { configured: false };
    }
    return {
      configured: true,
      engineBase: engine.toString().replace(/\/$/, ""),
      organizationId: organizationId ?? null,
      multiTenant,
      controlPlaneBase: safeBaseUrl(
        process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim(),
      ),
    };
  } catch {
    return { configured: false };
  }
}

function safeBaseUrl(value?: string) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      return null;
    }
    return url.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

export function githubAppProxyConfiguration() {
  const configuration = springProxyConfiguration();
  if (!configuration.configured || !configuration.controlPlaneBase) {
    return null;
  }
  return configuration;
}

function safeEqual(left: string, right: string) {
  return timingSafeEqual(
    createHash("sha256").update(left).digest(),
    createHash("sha256").update(right).digest(),
  );
}

function configuredToken(): string | null {
  const direct = process.env.ELMOS_SPRING_PROXY_AUTH_TOKEN;
  const tokenFile = process.env.ELMOS_SPRING_PROXY_AUTH_TOKEN_FILE;
  if (Boolean(direct) === Boolean(tokenFile)) return null;
  if (direct) return direct.length >= 24 && direct.length <= 4_096 ? direct : null;
  if (!tokenFile || !path.isAbsolute(tokenFile)) return null;
  try {
    const details = lstatSync(tokenFile);
    if (
      details.isSymbolicLink()
      || !details.isFile()
      || details.size > 4_096
      || (details.mode & 0o077) !== 0
    ) return null;
    const token = readFileSync(tokenFile, "utf-8").trim();
    return token.length >= 24 && token.length <= 4_096 ? token : null;
  } catch {
    return null;
  }
}

export type SpringActorContext = { organizationId: string; actorId: string };

export function authenticateSpringProxy(
  request: NextRequest,
): SpringActorContext | Response {
  const configuration = springProxyConfiguration();
  if (unsafeCookieValue(request, accountCookieNames.session)) {
    try {
      const account = accountSessionFromRequest(request, "spring:execute");
      if (
        configuration.configured
        && !configuration.multiTenant
        && account.principal.organizationId !== configuration.organizationId
      ) {
        return Response.json(
          {
            errorCode: "TENANT_ID_NOT_BOUND_TO_ENGINE",
            message: "账户租户与单租户 Spring Engine 绑定不一致。",
            retryable: false,
          },
          { status: 403, headers: { "cache-control": "no-store" } },
        );
      }
      return {
        organizationId: account.principal.organizationId,
        actorId: account.principal.actorId,
      };
    } catch (error) {
      if (error instanceof AccountSessionError) {
        return Response.json(
          { errorCode: error.code, message: error.message, retryable: false },
          { status: error.status, headers: { "cache-control": "no-store" } },
        );
      }
      throw error;
    }
  }
  if (process.env.NODE_ENV === "production") {
    return Response.json(
      { errorCode: "ACCOUNT_SESSION_REQUIRED", message: "请先登录企业账户。", retryable: false },
      { status: 401, headers: { "cache-control": "no-store" } },
    );
  }
  const token = configuredToken();
  const actor = process.env.ELMOS_SPRING_PROXY_ACTOR_ID?.trim() ?? "";
  const expiresAt = process.env.ELMOS_SPRING_PROXY_AUTH_TOKEN_EXPIRES_AT?.trim() ?? "";
  const expiry = Date.parse(expiresAt);
  if (
    !configuration.configured
    || !token
    || !actorPattern.test(actor)
    || Number.isNaN(expiry)
    || !/(Z|[+-]\d{2}:\d{2})$/.test(expiresAt)
    || expiry <= Date.now()
    || expiry > Date.now() + 24 * 60 * 60_000
  ) {
    return Response.json(
      {
        errorCode: "SPRING_PROXY_AUTH_NOT_CONFIGURED",
        message: "Spring 迁移代理未配置有效的短期租户身份租约。",
        retryable: false,
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
  const authorization = request.headers.get("authorization") ?? "";
  const presentedToken = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!safeEqual(presentedToken, token)) {
    return Response.json(
      { errorCode: "AUTHENTICATION_REQUIRED", message: "需要有效的 Spring 迁移短期令牌。", retryable: false },
      { status: 401, headers: { "cache-control": "no-store" } },
    );
  }
  const tenant = request.headers.get("x-elmos-tenant") ?? "";
  if (
    !configuration.organizationId
    || !safeEqual(tenant, configuration.organizationId)
  ) {
    return Response.json(
      {
        errorCode: "TENANT_ID_NOT_BOUND_TO_CREDENTIAL",
        message: "请求租户与 Spring 迁移凭证绑定不一致。",
        retryable: false,
      },
      { status: 403, headers: { "cache-control": "no-store" } },
    );
  }
  const presentedActor = request.headers.get("x-elmos-actor") ?? "";
  if (!actorPattern.test(presentedActor) || !safeEqual(presentedActor, actor)) {
    return Response.json(
      {
        errorCode: "ACTOR_ID_NOT_BOUND_TO_CREDENTIAL",
        message: "请求执行者与 Spring 迁移凭证绑定不一致。",
        retryable: false,
      },
      { status: 403, headers: { "cache-control": "no-store" } },
    );
  }
  return { organizationId: tenant, actorId: presentedActor };
}

export function proxyNotConfiguredResponse() {
  return Response.json(
    {
      errorCode: "SPRING_UPGRADE_PROXY_NOT_CONFIGURED",
      message: "Spring 迁移代理尚未绑定可信的单租户组织与 Java Engine；未执行任何客户代码。",
      retryable: false,
    },
    { status: 503, headers: { "cache-control": "no-store" } },
  );
}
