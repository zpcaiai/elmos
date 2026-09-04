import assert from "node:assert/strict";
import test from "node:test";

import {
  accountCookieNames,
  accountSessionFromRequest,
  assertLocalCredentialRequest,
  authenticateLocalCredentials,
  localCredentialsConfigured,
} from "../app/lib/server/accountSession.ts";

const trackedEnvironment = [
  "NODE_ENV",
  "ELMOS_ALLOW_LOCAL_CREDENTIALS",
  "ELMOS_SESSION_SECRET",
  "ELMOS_LOCAL_CREDENTIALS_USERNAME",
  "ELMOS_LOCAL_CREDENTIALS_PASSWORD",
  "ELMOS_LOCAL_CREDENTIALS_ORGANIZATION_ID",
];

function withEnvironment(overrides, callback) {
  const previous = new Map(trackedEnvironment.map((name) => [name, process.env[name]]));
  try {
    for (const name of trackedEnvironment) {
      delete process.env[name];
    }
    Object.assign(process.env, overrides);
    return callback();
  } finally {
    for (const name of trackedEnvironment) {
      const value = previous.get(name);
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
}

test("local test account issues an encrypted least-privilege session", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    assert.equal(localCredentialsConfigured(), true);
    const result = authenticateLocalCredentials("test", "test");
    assert.equal(result.principal.actorId, "local:test");
    assert.equal(result.principal.organizationId, "local-test");
    assert.deepEqual(result.principal.roles, ["DEVELOPER"]);
    assert.ok(result.principal.permissions.includes("spring:execute"));
    assert.ok(!result.principal.permissions.includes("admin:approve"));

    const request = new Request("http://127.0.0.1/api/auth/session", {
      headers: {
        cookie: `${accountCookieNames.session}=${result.session}; ${accountCookieNames.accessToken}=${result.accessToken}`,
      },
    });
    const session = accountSessionFromRequest(request, "spring:execute");
    assert.equal(session.principal.actorId, "local:test");
  });
});

test("local test account rejects invalid credentials", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    assert.throws(
      () => authenticateLocalCredentials("test", "wrong"),
      (error) => error?.code === "LOCAL_CREDENTIALS_INVALID" && error?.status === 401,
    );
  });
});

test("local test account is disabled in production", () => {
  withEnvironment({
    NODE_ENV: "production",
    ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    assert.equal(localCredentialsConfigured(), false);
    assert.throws(
      () => authenticateLocalCredentials("test", "test"),
      (error) => error?.code === "LOCAL_CREDENTIALS_DISABLED" && error?.status === 404,
    );
  });
});

test("local test account rejects non-loopback requests", () => {
  withEnvironment({
    NODE_ENV: "development",
    ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    assert.throws(
      () => assertLocalCredentialRequest(new Request("http://192.0.2.10:3200/api/auth/login", {
        method: "POST",
        headers: { host: "192.0.2.10:3200" },
      })),
      (error) => error?.code === "LOCAL_CREDENTIALS_LOOPBACK_ONLY" && error?.status === 403,
    );
  });
});
