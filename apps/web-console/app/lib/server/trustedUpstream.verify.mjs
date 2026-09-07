import assert from "node:assert/strict";
import {
  configuredControlPlaneBaseUrl,
  configuredLiveWorkbenchBaseUrl,
  configuredWorkspaceServiceBaseUrl,
  UpstreamConfigurationError,
  validateCommercialApiBaseUrl,
  validateControlPlaneBaseUrl,
  validateLiveWorkbenchBaseUrl,
  validateRepositoryWorkspaceBaseUrl,
} from "./trustedUpstream.ts";

const production = Object.freeze({ NODE_ENV: "production" });
const trustedProduction = Object.freeze({
  NODE_ENV: "production",
  ELMOS_TRUSTED_INTERNAL_HTTP: "true",
});
let checks = 0;

function accepted(actual, expected) {
  assert.equal(actual, expected);
  checks += 1;
}

function rejected(action, failure = "POLICY_REJECTED") {
  assert.throws(action, (error) => {
    assert.ok(error instanceof UpstreamConfigurationError);
    assert.equal(error.failure, failure);
    assert.equal(error.message, "UPSTREAM_CONFIGURATION_INVALID");
    return true;
  });
  checks += 1;
}

accepted(
  validateControlPlaneBaseUrl("https://control.example.test/", production),
  "https://control.example.test",
);
accepted(
  validateControlPlaneBaseUrl("http://control-plane:8080", trustedProduction),
  "http://control-plane:8080",
);
accepted(
  validateCommercialApiBaseUrl("http://commercial-api:8085", trustedProduction),
  "http://commercial-api:8085",
);
accepted(
  validateRepositoryWorkspaceBaseUrl("http://workspace-service:8082", trustedProduction),
  "http://workspace-service:8082",
);
accepted(
  validateLiveWorkbenchBaseUrl("http://live-workbench:8092", trustedProduction),
  "http://live-workbench:8092",
);
accepted(
  validateControlPlaneBaseUrl("http://127.0.0.1:8080", { NODE_ENV: "development" }),
  "http://127.0.0.1:8080",
);

rejected(() => validateControlPlaneBaseUrl("http://control-plane:8080", production));
rejected(() => validateControlPlaneBaseUrl("http://127.0.0.1:8080", production));
rejected(() => validateControlPlaneBaseUrl(
  "http://control-plane:8080",
  { NODE_ENV: "production", ELMOS_TRUSTED_INTERNAL_HTTP: "TRUE" },
));
rejected(() => validateControlPlaneBaseUrl("http://commercial-api:8085", trustedProduction));
rejected(() => validateCommercialApiBaseUrl("http://control-plane:8080", trustedProduction));
rejected(() => validateLiveWorkbenchBaseUrl("http://control-plane:8080", trustedProduction));
rejected(() => validateLiveWorkbenchBaseUrl("http://live-workbench:8092", production));
rejected(() => validateControlPlaneBaseUrl("http://control-plane.example:8080", trustedProduction));
rejected(() => validateControlPlaneBaseUrl("http://control-plane.:8080", trustedProduction));
rejected(() => validateControlPlaneBaseUrl("http://control-plane-evil:8080", trustedProduction));
rejected(() => validateControlPlaneBaseUrl("http://control-plane:8081", trustedProduction));
rejected(() => validateControlPlaneBaseUrl("http://control-plane", trustedProduction));
rejected(() => validateControlPlaneBaseUrl("https://user:secret@control.example.test", production));
rejected(() => validateControlPlaneBaseUrl("https://@control.example.test", production));
rejected(() => validateControlPlaneBaseUrl("https://control.example.test/api", production));
rejected(() => validateControlPlaneBaseUrl("https://control.example.test/api/../", production));
rejected(() => validateControlPlaneBaseUrl("https://control.example.test/?token=secret", production));
rejected(() => validateControlPlaneBaseUrl("https://control.example.test/#secret", production));
rejected(() => validateControlPlaneBaseUrl("ftp://control.example.test", production), "MALFORMED");
rejected(() => configuredControlPlaneBaseUrl({
  environment: {
    NODE_ENV: "production",
    ELMOS_CONTROL_PLANE_BASE_URL: "https://one.example.test",
    CONTROL_PLANE_BASE_URL: "https://two.example.test",
  },
}), "CONFLICTING_CONFIGURATION");
rejected(() => configuredWorkspaceServiceBaseUrl({
  NODE_ENV: "production",
  ELMOS_TRUSTED_INTERNAL_HTTP: "true",
  ELMOS_WORKSPACE_SERVICE_URL: "http://control-plane:8080",
}));
accepted(
  configuredLiveWorkbenchBaseUrl({
    NODE_ENV: "production",
    ELMOS_LIVE_WORKBENCH_BASE_URL: "https://workbench.example.test",
  }),
  "https://workbench.example.test",
);

const secret = "do-not-leak-this-secret";
try {
  validateControlPlaneBaseUrl(`https://operator:${secret}@control.example.test`, production);
  assert.fail("credential-bearing URL must fail closed");
} catch (error) {
  assert.ok(error instanceof UpstreamConfigurationError);
  assert.equal(JSON.stringify(error).includes(secret), false);
  assert.equal(error.message.includes(secret), false);
  checks += 1;
}

console.log(`trusted upstream policy: ${checks} checks passed`);
