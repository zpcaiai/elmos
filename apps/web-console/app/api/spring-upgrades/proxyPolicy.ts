const organizationPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export type SpringProxyConfiguration =
  | {
      configured: true;
      engineBase: string;
      organizationId: string;
      controlPlaneBase: string | null;
    }
  | { configured: false };

export function springProxyConfiguration(): SpringProxyConfiguration {
  if (process.env.ELMOS_SPRING_PROXY_ENABLED !== "true") return { configured: false };
  const organizationId = process.env.ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID?.trim();
  const configuredBase = process.env.JAVA_ENGINE_BASE_URL?.trim();
  if (!organizationId || !organizationPattern.test(organizationId) || !configuredBase) {
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
      organizationId,
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
