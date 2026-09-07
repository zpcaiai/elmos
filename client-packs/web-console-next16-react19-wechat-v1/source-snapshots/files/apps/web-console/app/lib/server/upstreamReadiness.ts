import {
  configuredCommercialApiBaseUrl,
  configuredControlPlaneBaseUrl,
  configuredWorkspaceServiceBaseUrl,
  type UpstreamEnvironment,
} from "./trustedUpstream";

export type UpstreamDependencyName =
  | "control-plane"
  | "commercial-api"
  | "workspace-service";

export type UpstreamReadiness = {
  dependency: UpstreamDependencyName;
  status: "UP" | "BLOCKED";
  reason?:
    | "NOT_CONFIGURED"
    | "CONFIGURATION_INVALID"
    | "TIMEOUT"
    | "UNREACHABLE"
    | "NOT_READY";
};

type ProbeOptions = {
  environment?: UpstreamEnvironment;
  fetcher?: typeof fetch;
  timeoutMs?: number;
};

type ConfiguredDependency = {
  dependency: UpstreamDependencyName;
  baseUrl: string;
};

async function probeDependency(
  dependency: ConfiguredDependency,
  fetcher: typeof fetch,
  timeoutMs: number,
): Promise<UpstreamReadiness> {
  try {
    const response = await fetcher(
      `${dependency.baseUrl}/actuator/health/readiness`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
      },
    );
    try {
      await response.body?.cancel();
    } catch {
      // The status is authoritative; failure to cancel a completed response body
      // must not leak implementation details or turn a healthy probe into an error.
    }
    return response.ok
      ? { dependency: dependency.dependency, status: "UP" }
      : { dependency: dependency.dependency, status: "BLOCKED", reason: "NOT_READY" };
  } catch (error) {
    const timeout = error instanceof Error
      && (error.name === "TimeoutError" || error.name === "AbortError");
    return {
      dependency: dependency.dependency,
      status: "BLOCKED",
      reason: timeout ? "TIMEOUT" : "UNREACHABLE",
    };
  }
}

export async function probeConfiguredUpstreams(
  options: ProbeOptions = {},
): Promise<UpstreamReadiness[]> {
  const environment = options.environment ?? process.env;
  const fetcher = options.fetcher ?? fetch;
  const timeoutMs = options.timeoutMs ?? 3_000;
  const probes: Array<Promise<UpstreamReadiness>> = [];

  try {
    const controlPlane = configuredControlPlaneBaseUrl({ environment });
    if (controlPlane) {
      probes.push(probeDependency(
        { dependency: "control-plane", baseUrl: controlPlane }, fetcher, timeoutMs,
      ));
    } else if (environment.NODE_ENV === "production") {
      probes.push(Promise.resolve({
        dependency: "control-plane",
        status: "BLOCKED",
        reason: "NOT_CONFIGURED",
      }));
    }
  } catch {
    probes.push(Promise.resolve({
      dependency: "control-plane",
      status: "BLOCKED",
      reason: "CONFIGURATION_INVALID",
    }));
  }

  if (environment.ELMOS_COMMERCIAL_API_URL?.trim()) {
    try {
      const commercialApi = configuredCommercialApiBaseUrl(environment);
      if (commercialApi) {
        probes.push(probeDependency(
          { dependency: "commercial-api", baseUrl: commercialApi }, fetcher, timeoutMs,
        ));
      }
    } catch {
      probes.push(Promise.resolve({
        dependency: "commercial-api",
        status: "BLOCKED",
        reason: "CONFIGURATION_INVALID",
      }));
    }
  }

  if (environment.ELMOS_WORKSPACE_SERVICE_URL?.trim()) {
    try {
      const workspace = configuredWorkspaceServiceBaseUrl(environment);
      if (workspace) {
        probes.push(probeDependency(
          { dependency: "workspace-service", baseUrl: workspace }, fetcher, timeoutMs,
        ));
      }
    } catch {
      probes.push(Promise.resolve({
        dependency: "workspace-service",
        status: "BLOCKED",
        reason: "CONFIGURATION_INVALID",
      }));
    }
  }

  return Promise.all(probes);
}
