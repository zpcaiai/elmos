import assert from "node:assert/strict";
import {
  aggregateGenerationReadiness,
  productionSubstrateReadiness,
} from "./generationReadiness.ts";

const runner = (status, reason) => ({
  status,
  persistence: "FILESYSTEM_ATOMIC",
  auth: "BEARER_TENANT_BOUND",
  storage: status === "READY" ? "READ_WRITE" : status === "DISABLED" ? "NOT_RUN" : "BLOCKED",
  isolation: status === "READY" ? "ROOTLESS_CONTAINER" : "NOT_CONFIGURED",
  recovery: "PERSISTENT_RECONCILIATION",
  activeJobs: 0,
  activeRuntimes: 0,
  activeAnalyses: 0,
  ...(reason ? { reason } : {}),
  checkedAt: "2026-09-04T00:00:00.000Z",
});

const secretDatabaseValue = "postgresql://secret-user:secret-password@db.example/test";
const secretNeonValue = "https://secret-neon-auth.example";
const neon = productionSubstrateReadiness({
  DATABASE_URL: secretDatabaseValue,
  DATABASE_URL_UNPOOLED: `${secretDatabaseValue}?pool=false`,
  NEON_AUTH_BASE_URL: secretNeonValue,
});
assert.equal(neon.database.configurationStatus, "CONFIGURED");
assert.deepEqual(neon.database.configuredEnvironmentNames, [
  "DATABASE_URL",
  "DATABASE_URL_UNPOOLED",
]);
assert.equal(neon.database.runtimeConnection, "NOT_RUN");
assert.equal(neon.database.runtimeVersion, "NOT_RUN");
assert.equal(neon.identity.providerConfiguration, "NEON_AUTH");
assert.equal(neon.identity.applicationBinding, "ADAPTER_REQUIRED");
assert.equal(neon.identity.jwks, "CONFIGURED_NOT_PROBED");
assert.equal(neon.identity.requiredSigningAlgorithm, "RS256");
assert.equal(neon.identity.signingAlgorithmVerification, "NOT_RUN");
assert.equal(neon.identity.signingAlgorithmCompatibility, "NOT_VERIFIED");
assert.equal(neon.identity.runtimeAuthentication, "NOT_RUN");
const serializedNeon = JSON.stringify(neon);
assert.equal(serializedNeon.includes(secretDatabaseValue), false);
assert.equal(serializedNeon.includes(secretNeonValue), false);

const oidcEnvironment = {
  ELMOS_OIDC_ISSUER_URI: "https://identity.example/",
  ELMOS_OIDC_AUTHORIZATION_ENDPOINT: "https://identity.example/authorize",
  ELMOS_OIDC_TOKEN_ENDPOINT: "https://identity.example/token",
  ELMOS_OIDC_JWKS_URI: "https://identity.example/jwks",
  ELMOS_OIDC_CLIENT_ID: "client",
  ELMOS_OIDC_CLIENT_SECRET: "secret-value-never-returned",
  ELMOS_OIDC_REDIRECT_URI: "https://console.example/api/auth/callback",
  ELMOS_OIDC_AUDIENCE: "elmos",
  ELMOS_SESSION_SECRET: "session-secret-value-never-returned",
};
const oidc = productionSubstrateReadiness(oidcEnvironment);
assert.equal(oidc.identity.configurationStatus, "CONFIGURED");
assert.equal(oidc.identity.providerConfiguration, "OIDC");
assert.equal(oidc.identity.applicationBinding, "CONFIGURED");
assert.equal(JSON.stringify(oidc).includes("secret-value-never-returned"), false);

const localReady = aggregateGenerationReadiness({
  environment: { ELMOS_LOCAL_RUNNER_ENABLED: "true" },
  localRunner: runner("READY"),
  dependencies: [],
});
assert.equal(localReady.mode, "LOCAL_RUNNER");
assert.equal(localReady.status, "READY");
assert.equal(localReady.externalRuntimeAcceptance, "NOT_RUN");
assert.equal(localReady.productionCertification, "NOT_CERTIFIED");

const localBlocked = aggregateGenerationReadiness({
  environment: { ELMOS_LOCAL_RUNNER_ENABLED: "true" },
  localRunner: runner("BLOCKED", "RUNTIME_REAPER_NOT_READY"),
  dependencies: [],
});
assert.equal(localBlocked.status, "BLOCKED");
assert.deepEqual(localBlocked.reasons, ["RUNTIME_REAPER_NOT_READY"]);

const hostedWithMarketplaceConfiguration = aggregateGenerationReadiness({
  environment: {
    ELMOS_HOSTED_EXECUTION_ENABLED: "true",
    DATABASE_URL: secretDatabaseValue,
    NEON_AUTH_BASE_URL: secretNeonValue,
  },
  localRunner: runner("DISABLED"),
  dependencies: [{ dependency: "control-plane", status: "UP" }],
});
assert.equal(hostedWithMarketplaceConfiguration.mode, "HOSTED_EXECUTION");
assert.equal(hostedWithMarketplaceConfiguration.status, "BLOCKED");
assert.deepEqual(hostedWithMarketplaceConfiguration.reasons, [
  "IDENTITY_APPLICATION_BINDING_INCOMPLETE",
]);

const hostedWithUnverifiedOidcAlgorithm = aggregateGenerationReadiness({
  environment: { ELMOS_HOSTED_EXECUTION_ENABLED: "true", DATABASE_URL: secretDatabaseValue, ...oidcEnvironment },
  localRunner: runner("DISABLED"),
  dependencies: [{ dependency: "control-plane", status: "UP" }],
});
assert.equal(hostedWithUnverifiedOidcAlgorithm.status, "BLOCKED");
assert.deepEqual(hostedWithUnverifiedOidcAlgorithm.reasons, [
  "IDENTITY_SIGNING_ALGORITHM_NOT_VERIFIED",
]);

const hostedWithoutDatabase = aggregateGenerationReadiness({
  environment: { ELMOS_HOSTED_EXECUTION_ENABLED: "true", ...oidcEnvironment },
  localRunner: runner("DISABLED"),
  dependencies: [{ dependency: "control-plane", status: "UP" }],
});
assert.equal(hostedWithoutDatabase.status, "BLOCKED");
assert.deepEqual(hostedWithoutDatabase.reasons, ["PRODUCTION_DATABASE_NOT_CONFIGURED"]);

const hostedBlocked = aggregateGenerationReadiness({
  environment: { ELMOS_HOSTED_EXECUTION_ENABLED: "true", ...oidcEnvironment },
  localRunner: runner("DISABLED"),
  dependencies: [{ dependency: "control-plane", status: "BLOCKED", reason: "TIMEOUT" }],
});
assert.equal(hostedBlocked.status, "BLOCKED");
assert(hostedBlocked.reasons.includes("CONTROL_PLANE_TIMEOUT"));

const conflict = aggregateGenerationReadiness({
  environment: {
    ELMOS_LOCAL_RUNNER_ENABLED: "true",
    ELMOS_HOSTED_EXECUTION_ENABLED: "true",
  },
  localRunner: runner("READY"),
  dependencies: [],
});
assert.equal(conflict.mode, "CONFLICT");
assert.equal(conflict.status, "BLOCKED");

const disabled = aggregateGenerationReadiness({
  environment: {},
  localRunner: runner("DISABLED"),
  dependencies: [],
});
assert.equal(disabled.mode, "NONE");
assert.equal(disabled.status, "NOT_CONFIGURED");

console.log("generation readiness policy passed");
