export type UpstreamEnvironment = Readonly<Record<string, string | undefined>>;

export type UpstreamConfigurationFailure =
  | "MALFORMED"
  | "POLICY_REJECTED"
  | "CONFLICTING_CONFIGURATION";

export class UpstreamConfigurationError extends Error {
  readonly failure: UpstreamConfigurationFailure;

  constructor(failure: UpstreamConfigurationFailure) {
    // Never retain the configured value in the exception. These errors can reach
    // readiness and BFF error responses, and upstream URLs may contain secrets
    // when an operator has made a configuration mistake.
    super("UPSTREAM_CONFIGURATION_INVALID");
    this.name = "UpstreamConfigurationError";
    this.failure = failure;
  }
}

type ResolutionOptions = {
  environment?: UpstreamEnvironment;
  developmentFallback?: string;
};

type RepositoryResolutionOptions = ResolutionOptions & {
  fallbackToControlPlane?: boolean;
};

const internalServiceLabelPattern = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const developmentLoopbackHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);

function rootOnlyBaseUrl(value: string): boolean {
  const schemeSeparator = value.indexOf("://");
  if (schemeSeparator < 0) return false;
  const authorityAndSuffix = value.slice(schemeSeparator + 3);
  const suffixIndex = authorityAndSuffix.search(/[/?#\\]/);
  if (suffixIndex < 0) return true;
  return authorityAndSuffix.slice(suffixIndex) === "/";
}

function containsUserInfo(value: string): boolean {
  const schemeSeparator = value.indexOf("://");
  if (schemeSeparator < 0) return true;
  const authorityAndSuffix = value.slice(schemeSeparator + 3);
  const authorityEnd = authorityAndSuffix.search(/[/?#\\]/);
  const authority = authorityEnd < 0
    ? authorityAndSuffix
    : authorityAndSuffix.slice(0, authorityEnd);
  return authority.includes("@");
}

function validateBaseUrl(
  configured: string,
  allowedInternalHttpAuthorities: readonly string[],
  environment: UpstreamEnvironment,
): string {
  const value = configured.trim();
  if (!/^https?:\/\//i.test(value)) {
    throw new UpstreamConfigurationError("MALFORMED");
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new UpstreamConfigurationError("MALFORMED");
  }
  if (
    !rootOnlyBaseUrl(value)
    || containsUserInfo(value)
    || parsed.pathname !== "/"
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
    || !parsed.hostname
  ) {
    throw new UpstreamConfigurationError("POLICY_REJECTED");
  }
  if (parsed.protocol === "https:") return parsed.origin;
  if (parsed.protocol !== "http:") {
    throw new UpstreamConfigurationError("POLICY_REJECTED");
  }

  const hostname = parsed.hostname.toLowerCase();
  const developmentLoopback = environment.NODE_ENV !== "production"
    && developmentLoopbackHosts.has(hostname);
  const explicitlyTrustedInternalService = environment.ELMOS_TRUSTED_INTERNAL_HTTP === "true"
    && internalServiceLabelPattern.test(hostname)
    && allowedInternalHttpAuthorities.includes(parsed.host.toLowerCase());
  if (!developmentLoopback && !explicitlyTrustedInternalService) {
    throw new UpstreamConfigurationError("POLICY_REJECTED");
  }
  return parsed.origin;
}

export function validateControlPlaneBaseUrl(
  configured: string,
  environment: UpstreamEnvironment = process.env,
): string {
  return validateBaseUrl(configured, ["control-plane:8080"], environment);
}

export function validateCommercialApiBaseUrl(
  configured: string,
  environment: UpstreamEnvironment = process.env,
): string {
  return validateBaseUrl(configured, ["commercial-api:8085"], environment);
}

export function validateRepositoryWorkspaceBaseUrl(
  configured: string,
  environment: UpstreamEnvironment = process.env,
): string {
  // Repository APIs are currently hosted either by the dedicated service or by
  // the control plane in the development topology. Both names are exact.
  return validateBaseUrl(
    configured,
    ["workspace-service:8082", "control-plane:8080"],
    environment,
  );
}

export function validateWorkspaceServiceBaseUrl(
  configured: string,
  environment: UpstreamEnvironment = process.env,
): string {
  return validateBaseUrl(configured, ["workspace-service:8082"], environment);
}

export function configuredControlPlaneBaseUrl(
  options: ResolutionOptions = {},
): string | null {
  const environment = options.environment ?? process.env;
  const candidates = [
    environment.ELMOS_CONTROL_PLANE_BASE_URL?.trim(),
    environment.CONTROL_PLANE_BASE_URL?.trim(),
  ].filter((value): value is string => Boolean(value));
  if (candidates.length === 0) {
    if (environment.NODE_ENV === "production" || !options.developmentFallback) return null;
    return validateControlPlaneBaseUrl(options.developmentFallback, environment);
  }
  const normalized = candidates.map((candidate) => (
    validateControlPlaneBaseUrl(candidate, environment)
  ));
  if (new Set(normalized).size !== 1) {
    throw new UpstreamConfigurationError("CONFLICTING_CONFIGURATION");
  }
  return normalized[0];
}

export function configuredCommercialApiBaseUrl(
  environment: UpstreamEnvironment = process.env,
): string | null {
  const configured = environment.ELMOS_COMMERCIAL_API_URL?.trim();
  return configured ? validateCommercialApiBaseUrl(configured, environment) : null;
}

export function configuredWorkspaceServiceBaseUrl(
  environment: UpstreamEnvironment = process.env,
): string | null {
  const configured = environment.ELMOS_WORKSPACE_SERVICE_URL?.trim();
  return configured ? validateWorkspaceServiceBaseUrl(configured, environment) : null;
}

export function configuredRepositoryWorkspaceBaseUrl(
  options: RepositoryResolutionOptions = {},
): string | null {
  const environment = options.environment ?? process.env;
  const configured = environment.ELMOS_REPOSITORY_WORKSPACE_BASE_URL?.trim();
  if (configured) return validateRepositoryWorkspaceBaseUrl(configured, environment);
  if (!options.fallbackToControlPlane) return null;
  return configuredControlPlaneBaseUrl({
    environment,
    developmentFallback: options.developmentFallback,
  });
}
