import type { GenerationRunnerHealth } from "./generationRunner";
import type { UpstreamReadiness } from "./upstreamReadiness";

export const databaseEnvironmentNames = [
  "ELMOS_DATABASE_URL",
  "DATABASE_URL",
  "DATABASE_URL_UNPOOLED",
  "POSTGRES_URL",
  "POSTGRES_URL_NON_POOLING",
] as const;

export const neonAuthEnvironmentNames = ["NEON_AUTH_BASE_URL"] as const;

const webOidcEnvironmentNames = [
  "ELMOS_OIDC_ISSUER_URI",
  "ELMOS_OIDC_AUTHORIZATION_ENDPOINT",
  "ELMOS_OIDC_TOKEN_ENDPOINT",
  "ELMOS_OIDC_JWKS_URI",
  "ELMOS_OIDC_CLIENT_ID",
  "ELMOS_OIDC_CLIENT_SECRET",
  "ELMOS_OIDC_REDIRECT_URI",
  "ELMOS_OIDC_AUDIENCE",
  "ELMOS_SESSION_SECRET",
] as const;

type Environment = Record<string, string | undefined>;

export type ConfigurationStatus = "CONFIGURED" | "PARTIAL" | "NOT_CONFIGURED";
export type GenerationAvailability = "READY" | "DEGRADED" | "BLOCKED" | "NOT_CONFIGURED";

export type ProductionSubstrateReadiness = {
  database: {
    configurationStatus: ConfigurationStatus;
    configuredEnvironmentNames: string[];
    expectedEngine: "PostgreSQL";
    expectedMajorVersion: 17;
    runtimeConnection: "NOT_RUN";
    runtimeVersion: "NOT_RUN";
    migrations: "NOT_RUN";
  };
  identity: {
    configurationStatus: ConfigurationStatus;
    configuredEnvironmentNames: string[];
    providerConfiguration: "NEON_AUTH" | "OIDC" | "NEON_AUTH_AND_OIDC" | "NOT_CONFIGURED";
    applicationBinding: "CONFIGURED" | "ADAPTER_REQUIRED" | "NOT_CONFIGURED";
    jwks: "CONFIGURED_NOT_PROBED" | "NOT_CONFIGURED";
    requiredSigningAlgorithm: "RS256";
    signingAlgorithmVerification: "VERIFIED" | "NOT_RUN" | "MISMATCH";
    signingAlgorithmCompatibility: "NOT_VERIFIED";
    runtimeAuthentication: "NOT_RUN";
  };
  boundary: "CONFIGURATION_PRESENCE_ONLY";
};

export type GenerationOperationalReadiness = {
  status: GenerationAvailability;
  mode: "LOCAL_RUNNER" | "HOSTED_EXECUTION" | "CONFLICT" | "NONE";
  reasons: string[];
  localRunner: GenerationRunnerHealth;
  dependencies: UpstreamReadiness[];
  productionSubstrate: ProductionSubstrateReadiness;
  externalRuntimeAcceptance: "NOT_RUN";
  productionCertification: "NOT_CERTIFIED";
};

function configuredNames(environment: Environment, names: readonly string[]): string[] {
  return names.filter((name) => (environment[name]?.trim().length ?? 0) > 0);
}

export function productionSubstrateReadiness(
  environment: Environment = process.env,
): ProductionSubstrateReadiness {
  const configuredDatabaseNames = configuredNames(environment, databaseEnvironmentNames);
  const configuredNeonNames = configuredNames(environment, neonAuthEnvironmentNames);
  const configuredOidcNames = configuredNames(environment, webOidcEnvironmentNames);
  const oidcComplete = configuredOidcNames.length === webOidcEnvironmentNames.length;
  const neonConfigured = configuredNeonNames.length === neonAuthEnvironmentNames.length;
  const identityNames = [...configuredNeonNames, ...configuredOidcNames].sort();

  return {
    database: {
      configurationStatus: configuredDatabaseNames.length > 0 ? "CONFIGURED" : "NOT_CONFIGURED",
      configuredEnvironmentNames: configuredDatabaseNames,
      expectedEngine: "PostgreSQL",
      expectedMajorVersion: 17,
      runtimeConnection: "NOT_RUN",
      runtimeVersion: "NOT_RUN",
      migrations: "NOT_RUN",
    },
    identity: {
      configurationStatus: oidcComplete || neonConfigured
        ? "CONFIGURED"
        : identityNames.length > 0
          ? "PARTIAL"
          : "NOT_CONFIGURED",
      configuredEnvironmentNames: identityNames,
      providerConfiguration: neonConfigured && oidcComplete
        ? "NEON_AUTH_AND_OIDC"
        : neonConfigured
          ? "NEON_AUTH"
          : oidcComplete
            ? "OIDC"
            : "NOT_CONFIGURED",
      // The current Web Console consumes the explicit ELMOS_OIDC_* contract.
      // A Marketplace-provided NEON_AUTH_BASE_URL proves configuration presence,
      // not that the account-session adapter has authenticated a real request.
      applicationBinding: oidcComplete
        ? "CONFIGURED"
        : neonConfigured
          ? "ADAPTER_REQUIRED"
          : "NOT_CONFIGURED",
      jwks: oidcComplete || neonConfigured ? "CONFIGURED_NOT_PROBED" : "NOT_CONFIGURED",
      // Configuration presence cannot prove that the provider key set contains
      // the production RS256 algorithm required by the Web OIDC contract.
      // In particular, a Marketplace base URL is not an accepted JWT key.
      requiredSigningAlgorithm: "RS256",
      signingAlgorithmVerification: "NOT_RUN",
      signingAlgorithmCompatibility: "NOT_VERIFIED",
      runtimeAuthentication: "NOT_RUN",
    },
    boundary: "CONFIGURATION_PRESENCE_ONLY",
  };
}

export function aggregateGenerationReadiness(input: {
  environment?: Environment;
  localRunner: GenerationRunnerHealth;
  dependencies: UpstreamReadiness[];
}): GenerationOperationalReadiness {
  const environment = input.environment ?? process.env;
  const localRequested = environment.ELMOS_LOCAL_RUNNER_ENABLED === "true";
  const hostedRequested = environment.ELMOS_HOSTED_EXECUTION_ENABLED === "true";
  const substrate = productionSubstrateReadiness(environment);
  const reasons: string[] = [];
  let mode: GenerationOperationalReadiness["mode"] = "NONE";
  let status: GenerationAvailability = "NOT_CONFIGURED";

  if (localRequested && hostedRequested) {
    mode = "CONFLICT";
    status = "BLOCKED";
    reasons.push("LOCAL_AND_HOSTED_EXECUTION_CONFLICT");
  } else if (localRequested) {
    mode = "LOCAL_RUNNER";
    status = input.localRunner.status === "READY" ? "READY" : "BLOCKED";
    if (status === "BLOCKED") {
      reasons.push(input.localRunner.reason ?? "LOCAL_RUNNER_NOT_READY");
    }
  } else if (hostedRequested) {
    mode = "HOSTED_EXECUTION";
    const controlPlane = input.dependencies.find(
      (dependency) => dependency.dependency === "control-plane",
    );
    if (!controlPlane || controlPlane.status !== "UP") {
      status = "BLOCKED";
      reasons.push(controlPlane?.reason ?? "CONTROL_PLANE_NOT_CONFIGURED");
    } else if (substrate.database.configurationStatus !== "CONFIGURED") {
      status = "BLOCKED";
      reasons.push("PRODUCTION_DATABASE_NOT_CONFIGURED");
    } else if (substrate.identity.applicationBinding !== "CONFIGURED") {
      status = "BLOCKED";
      reasons.push("IDENTITY_APPLICATION_BINDING_INCOMPLETE");
    } else if (substrate.identity.signingAlgorithmVerification !== "VERIFIED") {
      status = "BLOCKED";
      reasons.push("IDENTITY_SIGNING_ALGORITHM_NOT_VERIFIED");
    } else {
      status = "READY";
    }
  } else {
    reasons.push("NO_GENERATION_EXECUTION_MODE_ENABLED");
  }

  for (const dependency of input.dependencies) {
    if (dependency.status === "BLOCKED") {
      const reason = `${dependency.dependency.toUpperCase().replaceAll("-", "_")}_${dependency.reason ?? "BLOCKED"}`;
      if (!reasons.includes(reason)) reasons.push(reason);
      status = "BLOCKED";
    }
  }

  return {
    status,
    mode,
    reasons,
    localRunner: input.localRunner,
    dependencies: input.dependencies,
    productionSubstrate: substrate,
    externalRuntimeAcceptance: "NOT_RUN",
    productionCertification: "NOT_CERTIFIED",
  };
}
