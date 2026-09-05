import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import test from "node:test";
import { tmpdir } from "node:os";
import path from "node:path";
import { exportJWK, generateKeyPair, SignJWT } from "jose";

import {
  ADMINISTRATOR_EMAIL,
  accountPrincipalFromOidcClaims,
  accountPrincipalFromDescopeIdentity,
  accountCookieNames,
  accountSessionFromRequest,
  assertLoginModeAccess,
  assertLocalCredentialRequest,
  authenticateLocalCredentials,
  createAuthorizationFlow,
  createDescopeAccountSession,
  createDescopeOauthFlow,
  createDescopeOtpChallenge,
  exchangeAuthorizationCode,
  localAccountCookieNames,
  localCredentialsConfigured,
  localRegistrationConfigured,
  refreshAccountSession,
  refreshSessionFromRequest,
  readDescopeOauthFlow,
  readDescopeOtpChallenge,
  registerLocalAccount,
} from "../app/lib/server/accountSession.ts";

const trackedEnvironment = [
  "NODE_ENV",
  "ELMOS_ALLOW_LOCAL_CREDENTIALS",
  "ELMOS_SESSION_SECRET",
  "ELMOS_LOCAL_CREDENTIALS_USERNAME",
  "ELMOS_LOCAL_CREDENTIALS_PASSWORD",
  "ELMOS_LOCAL_CREDENTIALS_EMAIL",
  "ELMOS_LOCAL_CREDENTIALS_ORGANIZATION_ID",
  "ELMOS_LOCAL_CREDENTIALS_STORE_PATH",
  "ELMOS_OIDC_ISSUER_URI",
  "ELMOS_OIDC_AUTHORIZATION_ENDPOINT",
  "ELMOS_OIDC_TOKEN_ENDPOINT",
  "ELMOS_OIDC_JWKS_URI",
  "ELMOS_OIDC_REVOCATION_ENDPOINT",
  "ELMOS_OIDC_CLIENT_ID",
  "ELMOS_OIDC_CLIENT_SECRET",
  "ELMOS_OIDC_REDIRECT_URI",
  "ELMOS_OIDC_AUDIENCE",
  "ELMOS_DESCOPE_DEFAULT_ORGANIZATION_ID",
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

async function withEnvironmentAsync(overrides, callback) {
  const previous = new Map(trackedEnvironment.map((name) => [name, process.env[name]]));
  try {
    for (const name of trackedEnvironment) {
      delete process.env[name];
    }
    Object.assign(process.env, overrides);
    return await callback();
  } finally {
    for (const name of trackedEnvironment) {
      const value = previous.get(name);
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
}

const oidcIssuer = "https://identity.example.test";
const oidcClientId = "elmos-test-client";
const oidcAudience = "elmos-test-api";
const oidcEnvironment = {
  NODE_ENV: "test",
  ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  ELMOS_OIDC_ISSUER_URI: oidcIssuer,
  ELMOS_OIDC_AUTHORIZATION_ENDPOINT: `${oidcIssuer}/authorize`,
  ELMOS_OIDC_TOKEN_ENDPOINT: `${oidcIssuer}/token`,
  ELMOS_OIDC_JWKS_URI: `${oidcIssuer}/jwks`,
  ELMOS_OIDC_REVOCATION_ENDPOINT: `${oidcIssuer}/revoke`,
  ELMOS_OIDC_CLIENT_ID: oidcClientId,
  ELMOS_OIDC_CLIENT_SECRET: "elmos-test-client-secret-at-least-16",
  ELMOS_OIDC_REDIRECT_URI: "https://console.example.test/api/auth/callback",
  ELMOS_OIDC_AUDIENCE: oidcAudience,
};
const oidcKeys = await generateKeyPair("RS256");
const oidcJwk = {
  ...await exportJWK(oidcKeys.publicKey),
  alg: "RS256",
  kid: "elmos-account-session-test-key",
  use: "sig",
};

async function signOidcJwt(claims, audience) {
  return new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256", kid: oidcJwk.kid, typ: "JWT" })
    .setIssuer(oidcIssuer)
    .setAudience(audience)
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(oidcKeys.privateKey);
}

function tokenProviderFetch(tokens, revokedTokens) {
  return async (input, init = {}) => {
    const url = input instanceof Request ? input.url : String(input);
    if (url === `${oidcIssuer}/jwks`) {
      return Response.json({ keys: [oidcJwk] });
    }
    if (url === `${oidcIssuer}/token`) {
      return Response.json({
        access_token: tokens.accessToken,
        id_token: tokens.idToken,
        refresh_token: tokens.refreshToken,
        expires_in: 300,
      });
    }
    if (url === `${oidcIssuer}/revoke`) {
      const body = init.body instanceof URLSearchParams
        ? init.body
        : new URLSearchParams(String(init.body ?? ""));
      revokedTokens.push(body.get("token"));
      return new Response(null, { status: 200 });
    }
    throw new Error(`unexpected OIDC test request: ${url}`);
  };
}

async function administratorIdToken(nonce) {
  return signOidcJwt({
    sub: "oidc-admin",
    organization_id: "tenant-a",
    email: ADMINISTRATOR_EMAIL,
    email_verified: true,
    roles: ["VIEWER"],
    ...(nonce ? { nonce } : {}),
  }, oidcClientId);
}

async function administratorAccessToken(overrides = {}) {
  return signOidcJwt({
    sub: "oidc-admin",
    email: ADMINISTRATOR_EMAIL,
    email_verified: true,
    ...overrides,
  }, oidcAudience);
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
    assert.equal(result.principal.email, "test@example.test");
    assert.equal(result.principal.emailVerified, false);
    assert.equal(result.principal.isPlatformAdmin, false);
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

test("local session cookies work on loopback HTTP without weakening production cookies", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    assert.ok(Object.values(accountCookieNames).every((name) => name.startsWith("__Host-")));
    assert.ok(Object.values(localAccountCookieNames).every((name) => !name.startsWith("__Host-")));
    const result = authenticateLocalCredentials("test", "test");
    const request = new Request("http://127.0.0.1:3200/api/auth/session", {
      headers: {
        host: "127.0.0.1:3200",
        cookie: `${localAccountCookieNames.session}=${result.session}; ${localAccountCookieNames.accessToken}=${result.accessToken}`,
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

test("local registration persists a hashed account and can sign it in", () => {
  const root = mkdtempSync(path.join(tmpdir(), "elmos-account-session-test-"));
  try {
    withEnvironment({
      NODE_ENV: "test",
      ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
      ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
      ELMOS_LOCAL_CREDENTIALS_STORE_PATH: path.join(root, "accounts.json"),
    }, () => {
      assert.equal(localRegistrationConfigured(), true);
      registerLocalAccount({
        username: "alice",
        displayName: "Alice",
        email: "alice@example.com",
        password: "correct-horse-battery",
        passwordConfirmation: "correct-horse-battery",
      });
      const persisted = readFileSync(path.join(root, "accounts.json"), "utf8");
      assert.match(persisted, /"passwordHash"/);
      assert.doesNotMatch(persisted, /correct-horse-battery/);
      const result = authenticateLocalCredentials("alice@example.com", "correct-horse-battery");
      assert.equal(result.principal.actorId, "local:alice");
      assert.equal(result.principal.displayName, "Alice");
      assert.match(result.principal.organizationId, /^local-[0-9a-f]{16}$/);
      assert.throws(
        () => authenticateLocalCredentials("alice", "wrong-password"),
        (error) => error?.code === "LOCAL_CREDENTIALS_INVALID" && error?.status === 401,
      );
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("legacy local stores remain readable without treating legacy email as verified", () => {
  const root = mkdtempSync(path.join(tmpdir(), "elmos-legacy-account-store-test-"));
  const storePath = path.join(root, "accounts.json");
  try {
    withEnvironment({
      NODE_ENV: "test",
      ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
      ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
      ELMOS_LOCAL_CREDENTIALS_STORE_PATH: storePath,
    }, () => {
      authenticateLocalCredentials("test@example.test", "test");
      const store = JSON.parse(readFileSync(storePath, "utf8"));
      store.accounts[0].email = "test@localhost";
      writeFileSync(storePath, `${JSON.stringify(store, null, 2)}\n`, "utf8");
      chmodSync(storePath, 0o600);

      const result = authenticateLocalCredentials("test", "test");

      assert.equal(result.principal.email, undefined);
      assert.equal(result.principal.emailVerified, false);
      assert.equal(result.principal.isPlatformAdmin, false);
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("only the verified exact administrator email receives administrator authority", () => {
  const exactAdministrator = accountPrincipalFromOidcClaims({
    sub: "oidc-admin",
    organization_id: "tenant-a",
    email: "ZPCHONEY@GMAIL.COM",
    email_verified: true,
    roles: ["VIEWER"],
  });
  assert.equal(exactAdministrator.email, ADMINISTRATOR_EMAIL);
  assert.equal(exactAdministrator.emailVerified, true);
  assert.equal(exactAdministrator.isPlatformAdmin, true);
  assert.ok(exactAdministrator.roles.includes("APPROVER"));
  assert.ok(exactAdministrator.permissions.includes("admin:approve"));
  assert.doesNotThrow(() => assertLoginModeAccess(exactAdministrator, "ADMIN"));
  assert.throws(
    () => assertLoginModeAccess(exactAdministrator, "USER"),
    (error) => error?.code === "ADMIN_LOGIN_ENTRY_REQUIRED" && error?.status === 403,
  );

  for (const [email, verified] of [
    ["zpchoney+alias@gmail.com", true],
    [ADMINISTRATOR_EMAIL, false],
    ["somebody@example.com", true],
  ]) {
    const candidate = accountPrincipalFromOidcClaims({
      sub: `candidate-${String(email).replace(/[^a-z]/gi, "-")}`,
      organization_id: "tenant-a",
      email,
      email_verified: verified,
      roles: ["TENANT_ADMIN"],
      permissions: ["admin:read", "admin:operate", "admin:approve", "configuration:manage"],
    });
    assert.equal(candidate.isPlatformAdmin, false);
    assert.ok(!candidate.roles.includes("TENANT_ADMIN"));
    assert.ok(!candidate.permissions.includes("admin:read"));
    assert.ok(!candidate.permissions.includes("admin:approve"));
    assert.throws(
      () => assertLoginModeAccess(candidate, "ADMIN"),
      (error) => error?.code === "ADMIN_EMAIL_REQUIRED" && error?.status === 403,
    );
    assert.doesNotThrow(() => assertLoginModeAccess(candidate, "USER"));
  }
});

test("administrator authorization-code exchange requires a matching API access JWT", async () => {
  await withEnvironmentAsync(oidcEnvironment, async () => {
    const originalFetch = globalThis.fetch;
    const idToken = await administratorIdToken("administrator-login-nonce");
    const flow = {
      version: 1,
      state: "administrator-login-state",
      nonce: "administrator-login-nonce",
      verifier: "administrator-pkce-verifier",
      returnTo: "/admin",
      loginMode: "ADMIN",
      expiresAt: Date.now() + 60_000,
    };
    try {
      const validAccessToken = await administratorAccessToken();
      const acceptedRevocations = [];
      globalThis.fetch = tokenProviderFetch({
        accessToken: validAccessToken,
        idToken,
        refreshToken: "administrator-refresh-token-valid",
      }, acceptedRevocations);
      const accepted = await exchangeAuthorizationCode("authorization-code", flow);
      assert.equal(accepted.principal.isPlatformAdmin, true);
      assert.equal(accepted.tokens.accessToken, validAccessToken);
      assert.ok(accepted.refreshExpiresAt > accepted.expiresAt);
      assert.deepEqual(acceptedRevocations, []);

      const originalNow = Date.now;
      try {
        Date.now = () => accepted.expiresAt + 1_000;
        const expiredAccessRequest = new Request("https://console.example.test/api/auth/refresh", {
          method: "POST",
          headers: {
            cookie: [
              `${accountCookieNames.session}=${accepted.session}`,
              `${accountCookieNames.refreshToken}=${accepted.tokens.refreshToken}`,
            ].join("; "),
          },
        });
        const refreshSession = refreshSessionFromRequest(expiredAccessRequest);
        assert.equal(refreshSession.actorId, "oidc-admin");
        assert.equal(refreshSession.loginMode, "ADMIN");
        assert.equal(refreshSession.refreshToken, accepted.tokens.refreshToken);
        assert.equal(refreshSession.refreshExpiresAt, accepted.refreshExpiresAt);
        assert.throws(
          () => accountSessionFromRequest(expiredAccessRequest),
          (error) => error?.code === "ACCOUNT_SESSION_REQUIRED" && error?.status === 401,
          "ordinary API session reads must still reject a request without a live access token",
        );

        const mismatchedRefreshRequest = new Request(expiredAccessRequest.url, {
          method: "POST",
          headers: {
            cookie: [
              `${accountCookieNames.session}=${accepted.session}`,
              `${accountCookieNames.refreshToken}=different-refresh-token`,
            ].join("; "),
          },
        });
        assert.throws(
          () => refreshSessionFromRequest(mismatchedRefreshRequest),
          (error) => error?.code === "ACCOUNT_REFRESH_SESSION_EXPIRED" && error?.status === 401,
        );

        Date.now = () => accepted.refreshExpiresAt + 1;
        assert.throws(
          () => refreshSessionFromRequest(expiredAccessRequest),
          (error) => error?.code === "ACCOUNT_REFRESH_SESSION_EXPIRED" && error?.status === 401,
        );
      } finally {
        Date.now = originalNow;
      }

      const missingEmailAccessToken = await signOidcJwt({
        sub: "oidc-admin",
        email_verified: true,
      }, oidcAudience);
      for (const [accessToken, expectedCode] of [
        ["opaque-administrator-access-token", "OIDC_ADMIN_ACCESS_TOKEN_INVALID"],
        [missingEmailAccessToken, "OIDC_ADMIN_ACCESS_TOKEN_IDENTITY_MISMATCH"],
      ]) {
        const revokedTokens = [];
        const refreshToken = `administrator-refresh-token-${expectedCode}`;
        globalThis.fetch = tokenProviderFetch({ accessToken, idToken, refreshToken }, revokedTokens);
        await assert.rejects(
          () => exchangeAuthorizationCode("authorization-code", flow),
          (error) => error?.code === expectedCode && error?.status === 403,
        );
        assert.deepEqual(
          revokedTokens.sort(),
          [accessToken, refreshToken].sort(),
          "failed exchanges must revoke every newly issued token before returning",
        );
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("administrator refresh rejects new access JWT identity changes and revokes rotated tokens", async () => {
  await withEnvironmentAsync(oidcEnvironment, async () => {
    const originalFetch = globalThis.fetch;
    const idToken = await administratorIdToken();
    try {
      const validAccessToken = await administratorAccessToken();
      globalThis.fetch = tokenProviderFetch({
        accessToken: validAccessToken,
        idToken,
        refreshToken: "administrator-rotated-refresh-token-valid",
      }, []);
      const accepted = await refreshAccountSession("administrator-current-refresh-token", {
        actorId: "oidc-admin",
        loginMode: "ADMIN",
        refreshExpiresAt: Date.now() + 8 * 60 * 60_000,
      });
      assert.equal(accepted.principal.isPlatformAdmin, true);
      assert.equal(accepted.tokens.accessToken, validAccessToken);

      const scenarios = [
        await administratorAccessToken({ sub: "different-oidc-subject" }),
        await administratorAccessToken({ email_verified: false }),
      ];
      for (const [index, accessToken] of scenarios.entries()) {
        const revokedTokens = [];
        const refreshToken = `administrator-rotated-refresh-token-${index}`;
        globalThis.fetch = tokenProviderFetch({ accessToken, idToken, refreshToken }, revokedTokens);
        await assert.rejects(
          () => refreshAccountSession("administrator-current-refresh-token", {
            actorId: "oidc-admin",
            loginMode: "ADMIN",
            refreshExpiresAt: Date.now() + 8 * 60 * 60_000,
          }),
          (error) => error?.code === "OIDC_ADMIN_ACCESS_TOKEN_IDENTITY_MISMATCH"
            && error?.status === 403,
        );
        assert.deepEqual(
          revokedTokens.sort(),
          [accessToken, refreshToken].sort(),
          "failed refreshes must revoke every newly issued token before returning",
        );
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("local registration reserves the administrator email for verified OIDC", () => {
  const root = mkdtempSync(path.join(tmpdir(), "elmos-admin-email-reservation-test-"));
  try {
    withEnvironment({
      NODE_ENV: "test",
      ELMOS_ALLOW_LOCAL_CREDENTIALS: "true",
      ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
      ELMOS_LOCAL_CREDENTIALS_STORE_PATH: path.join(root, "accounts.json"),
    }, () => {
      assert.throws(
        () => registerLocalAccount({
          username: "reserved-admin",
          displayName: "Reserved Admin",
          email: ADMINISTRATOR_EMAIL,
          password: "correct-horse-battery",
          passwordConfirmation: "correct-horse-battery",
        }),
        (error) => error?.code === "LOCAL_REGISTRATION_ADMIN_EMAIL_RESERVED"
          && error?.status === 403,
      );
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("authorization flows reject cross-origin path tricks and keep admin routes separate", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
    ELMOS_OIDC_ISSUER_URI: "https://identity.example.com",
    ELMOS_OIDC_AUTHORIZATION_ENDPOINT: "https://identity.example.com/authorize",
    ELMOS_OIDC_TOKEN_ENDPOINT: "https://identity.example.com/token",
    ELMOS_OIDC_JWKS_URI: "https://identity.example.com/jwks",
    ELMOS_OIDC_CLIENT_ID: "elmos-test-client",
    ELMOS_OIDC_CLIENT_SECRET: "elmos-test-client-secret-at-least-16",
    ELMOS_OIDC_REDIRECT_URI: "https://console.example.com/api/auth/callback",
    ELMOS_OIDC_AUDIENCE: "elmos-test-api",
  }, () => {
    assert.equal(createAuthorizationFlow("/\\evil.example", "USER").flow.returnTo, "/");
    assert.equal(createAuthorizationFlow("/admin", "USER").flow.returnTo, "/");
    assert.equal(createAuthorizationFlow("/workspace", "ADMIN").flow.returnTo, "/admin");
    assert.equal(createAuthorizationFlow("/admin/audit?hours=1", "ADMIN").flow.returnTo, "/admin/audit?hours=1");
  });
});

test("Descope grants administrator rights only after current email OTP verification", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    const identity = {
      userId: "descope-user-admin-123",
      displayName: "Platform Administrator",
      email: ADMINISTRATOR_EMAIL,
      verifiedEmail: true,
      phone: "+8613812345678",
      verifiedPhone: true,
    };
    const emailPrincipal = accountPrincipalFromDescopeIdentity(identity, "EMAIL_OTP");
    assert.equal(emailPrincipal.isPlatformAdmin, true);
    assert.ok(emailPrincipal.permissions.includes("admin:approve"));
    assert.doesNotThrow(() => assertLoginModeAccess(emailPrincipal, "ADMIN"));

    for (const method of ["PHONE_OTP", "WECHAT_OAUTH"]) {
      const principal = accountPrincipalFromDescopeIdentity(identity, method);
      assert.equal(principal.isPlatformAdmin, false, `${method} must not elevate a linked admin identity`);
      assert.ok(!principal.permissions.includes("admin:read"));
      assert.throws(
        () => assertLoginModeAccess(principal, "ADMIN"),
        (error) => error?.code === "ADMIN_EMAIL_REQUIRED" && error?.status === 403,
      );
    }
  });
});

test("Descope self-registration reserves the administrator mailbox", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    assert.throws(
      () => createDescopeOtpChallenge({
        channel: "EMAIL",
        intent: "REGISTER",
        loginMode: "USER",
        loginId: ADMINISTRATOR_EMAIL.toUpperCase(),
        displayName: "Reserved Admin",
        returnTo: "/",
      }),
      (error) => error?.code === "DESCOPE_ADMIN_EMAIL_RESERVED" && error?.status === 403,
    );
    assert.throws(
      () => createDescopeOtpChallenge({
        channel: "SMS",
        intent: "LOGIN",
        loginMode: "ADMIN",
        loginId: "+8613812345678",
        returnTo: "/admin",
      }),
      (error) => error?.code === "ADMIN_EMAIL_REQUIRED" && error?.status === 403,
    );
  });
});

test("Descope encrypted challenges bind method, mode, identity and safe return path", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    const { sealedChallenge } = createDescopeOtpChallenge({
      channel: "SMS",
      intent: "REGISTER",
      loginMode: "USER",
      loginId: "+8613812345678",
      displayName: "Phone User",
      returnTo: "/admin/audit",
    });
    const challenge = readDescopeOtpChallenge(sealedChallenge);
    assert.equal(challenge.channel, "SMS");
    assert.equal(challenge.intent, "REGISTER");
    assert.equal(challenge.loginId, "+8613812345678");
    assert.equal(challenge.returnTo, "/");

    const { sealedFlow } = createDescopeOauthFlow({
      provider: "wechat",
      intent: "LOGIN",
      returnTo: "//evil.example/path",
    });
    const flow = readDescopeOauthFlow(sealedFlow);
    assert.equal(flow.provider, "wechat");
    assert.equal(flow.loginMode, "USER");
    assert.equal(flow.returnTo, "/");
  });
});

test("Descope sessions retain provider and method bindings during refresh", () => {
  withEnvironment({
    NODE_ENV: "test",
    ELMOS_SESSION_SECRET: "local-test-session-secret-at-least-32-characters",
  }, () => {
    const accessToken = `access.${"a".repeat(100)}.signature`;
    const refreshToken = `refresh.${"b".repeat(100)}.signature`;
    const result = createDescopeAccountSession({
      identity: {
        userId: "descope-user-phone-123",
        displayName: "Phone User",
        phone: "+8613812345678",
        verifiedPhone: true,
      },
      authenticationMethod: "PHONE_OTP",
      loginMode: "USER",
      accessToken,
      refreshToken,
      expiresAt: Date.now() + 15 * 60_000,
      refreshExpiresAt: Date.now() + 4 * 60 * 60_000,
    });
    const request = new Request("https://console.example.test/api/auth/session", {
      headers: {
        cookie: `${accountCookieNames.session}=${result.session}; ${accountCookieNames.accessToken}=${accessToken}; ${accountCookieNames.refreshToken}=${refreshToken}`,
      },
    });
    assert.equal(accountSessionFromRequest(request).principal.actorId, "descope:descope-user-phone-123");
    const refresh = refreshSessionFromRequest(request);
    assert.equal(refresh.provider, "DESCOPE");
    assert.equal(refresh.descopeAuthenticationMethod, "PHONE_OTP");
    assert.equal(refresh.actorId, "descope:descope-user-phone-123");
  });
});

test("Descope production sessions fail closed without a random sealing secret", () => {
  withEnvironment({ NODE_ENV: "production" }, () => {
    assert.throws(
      () => createDescopeAccountSession({
        identity: {
          userId: "descope-user-phone-123",
          phone: "+8613812345678",
          verifiedPhone: true,
        },
        authenticationMethod: "PHONE_OTP",
        loginMode: "USER",
        accessToken: `access.${"a".repeat(100)}.signature`,
        refreshToken: `refresh.${"b".repeat(100)}.signature`,
        expiresAt: Date.now() + 15 * 60_000,
        refreshExpiresAt: Date.now() + 4 * 60 * 60_000,
      }),
      (error) => error?.code === "ACCOUNT_SESSION_SECRET_NOT_CONFIGURED"
        && error?.status === 503,
    );
  });
});
