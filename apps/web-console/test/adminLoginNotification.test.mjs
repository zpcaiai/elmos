import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  ADMINISTRATOR_EMAIL,
  accountPrincipalFromOidcClaims,
} from "../app/lib/server/accountSession.ts";
import { notifyAdministratorLogin } from "../app/lib/server/adminLoginNotification.ts";

const configuredEnvironment = {
  ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED: "true",
  ELMOS_ADMIN_LOGIN_EMAIL_FROM: "ELMOS Security <security@example.com>",
  ELMOS_RESEND_API_KEY: "re_test_key_with_more_than_24_chars",
};

function administratorPrincipal() {
  return accountPrincipalFromOidcClaims({
    sub: "oidc-admin",
    organization_id: "tenant-a",
    email: ADMINISTRATOR_EMAIL,
    email_verified: true,
    roles: ["VIEWER"],
  });
}

test("administrator login notification is fixed to the administrator mailbox", async () => {
  let observedUrl = "";
  let observedInit;
  const receipt = await notifyAdministratorLogin(
    new Request("https://console.example.com/api/auth/callback", {
      headers: { "user-agent": "ELMOS notification test" },
    }),
    administratorPrincipal(),
    "OIDC",
    {
      environment: configuredEnvironment,
      eventId: "11111111-1111-4111-8111-111111111111",
      now: new Date("2026-08-31T03:00:00.000Z"),
      fetchImpl: async (url, init) => {
        observedUrl = String(url);
        observedInit = init;
        return new Response(
          JSON.stringify({ id: "22222222-2222-4222-8222-222222222222" }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      },
    },
  );

  assert.equal(observedUrl, "https://api.resend.com/emails");
  assert.equal(observedInit.method, "POST");
  assert.equal(observedInit.headers.Authorization, `Bearer ${configuredEnvironment.ELMOS_RESEND_API_KEY}`);
  assert.equal(
    observedInit.headers["Idempotency-Key"],
    "elmos-admin-login-11111111-1111-4111-8111-111111111111",
  );
  const payload = JSON.parse(observedInit.body);
  assert.deepEqual(payload.to, [ADMINISTRATOR_EMAIL]);
  assert.match(payload.subject, /管理员账户已登录/);
  assert.match(payload.text, /认证方式：OIDC/);
  assert.match(payload.text, /ELMOS notification test/);
  assert.equal(receipt.eventId, "11111111-1111-4111-8111-111111111111");
  assert.equal(receipt.providerMessageId, "22222222-2222-4222-8222-222222222222");
});

test("notification configuration fails closed before establishing an admin session", async () => {
  let called = false;
  await assert.rejects(
    notifyAdministratorLogin(
      new Request("https://console.example.com/api/auth/callback"),
      administratorPrincipal(),
      "OIDC",
      {
        environment: { ...configuredEnvironment, ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED: "false" },
        fetchImpl: async () => {
          called = true;
          return new Response();
        },
      },
    ),
    (error) => error?.code === "ADMIN_LOGIN_NOTIFICATION_NOT_CONFIGURED"
      && error?.status === 503,
  );
  assert.equal(called, false);
});

test("Vercel Marketplace RESEND_API_KEY is accepted without copying the secret", async () => {
  let authorization = "";
  await notifyAdministratorLogin(
    new Request("https://console.example.com/api/auth/descope/otp/verify"),
    administratorPrincipal(),
    "DESCOPE_EMAIL_OTP",
    {
      environment: {
        ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED: "true",
        ELMOS_ADMIN_LOGIN_EMAIL_FROM: "ELMOS Security <onboarding@resend.dev>",
        RESEND_API_KEY: "re_marketplace_key_with_more_than_24_chars",
      },
      eventId: "66666666-6666-4666-8666-666666666666",
      fetchImpl: async (_url, init) => {
        authorization = init.headers.Authorization;
        return new Response(
          JSON.stringify({ id: "77777777-7777-4777-8777-777777777777" }),
          { status: 200 },
        );
      },
    },
  );
  assert.equal(authorization, "Bearer re_marketplace_key_with_more_than_24_chars");
});

test("provider rejection fails closed and does not return a delivery receipt", async () => {
  await assert.rejects(
    notifyAdministratorLogin(
      new Request("https://console.example.com/api/auth/callback"),
      administratorPrincipal(),
      "OIDC",
      {
        environment: configuredEnvironment,
        eventId: "33333333-3333-4333-8333-333333333333",
        fetchImpl: async () => new Response(
          JSON.stringify({ message: "rate limited" }),
          { status: 429, headers: { "Content-Type": "application/json" } },
        ),
      },
    ),
    (error) => error?.code === "ADMIN_LOGIN_NOTIFICATION_RATE_LIMITED"
      && error?.status === 503,
  );
});

test("ordinary accounts cannot trigger an administrator login notification", async () => {
  const ordinary = accountPrincipalFromOidcClaims({
    sub: "ordinary-user",
    organization_id: "tenant-a",
    email: "ordinary@example.com",
    email_verified: true,
    roles: ["TENANT_ADMIN"],
  });
  await assert.rejects(
    notifyAdministratorLogin(
      new Request("https://console.example.com/api/auth/callback"),
      ordinary,
      "OIDC",
      { environment: configuredEnvironment },
    ),
    (error) => error?.code === "ADMIN_EMAIL_REQUIRED" && error?.status === 403,
  );
});

test("owner-only API key files are accepted by the production notification path", async () => {
  const root = mkdtempSync(path.join(tmpdir(), "elmos-resend-secret-test-"));
  const secretPath = path.join(root, "resend-api-key");
  try {
    writeFileSync(secretPath, "re_file_key_with_more_than_24_chars\n", { mode: 0o600 });
    const receipt = await notifyAdministratorLogin(
      new Request("https://console.example.com/api/auth/callback"),
      administratorPrincipal(),
      "OIDC",
      {
        environment: {
          ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED: "true",
          ELMOS_ADMIN_LOGIN_EMAIL_FROM: "ELMOS Security <security@example.com>",
          ELMOS_RESEND_API_KEY_FILE: secretPath,
        },
        eventId: "44444444-4444-4444-8444-444444444444",
        fetchImpl: async (_url, init) => {
          assert.equal(init.headers.Authorization, "Bearer re_file_key_with_more_than_24_chars");
          return new Response(
            JSON.stringify({ id: "55555555-5555-4555-8555-555555555555" }),
            { status: 200 },
          );
        },
      },
    );
    assert.equal(receipt.providerMessageId, "55555555-5555-4555-8555-555555555555");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("unsafe or ambiguous API key configuration fails closed", async () => {
  const root = mkdtempSync(path.join(tmpdir(), "elmos-resend-unsafe-test-"));
  const secretPath = path.join(root, "resend-api-key");
  try {
    writeFileSync(secretPath, "re_file_key_with_more_than_24_chars\n", { mode: 0o600 });
    chmodSync(secretPath, 0o640);
    await assert.rejects(
      notifyAdministratorLogin(
        new Request("https://console.example.com/api/auth/callback"),
        administratorPrincipal(),
        "OIDC",
        {
          environment: {
            ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED: "true",
            ELMOS_ADMIN_LOGIN_EMAIL_FROM: "security@example.com",
            ELMOS_RESEND_API_KEY_FILE: secretPath,
          },
        },
      ),
      (error) => error?.code === "ADMIN_LOGIN_NOTIFICATION_SECRET_FILE_UNSAFE",
    );
    await assert.rejects(
      notifyAdministratorLogin(
        new Request("https://console.example.com/api/auth/callback"),
        administratorPrincipal(),
        "OIDC",
        {
          environment: {
            ...configuredEnvironment,
            ELMOS_RESEND_API_KEY_FILE: secretPath,
          },
        },
      ),
      (error) => error?.code === "ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("symbolic-link API key paths fail closed", async () => {
  const root = mkdtempSync(path.join(tmpdir(), "elmos-resend-symlink-test-"));
  const targetPath = path.join(root, "resend-api-key-target");
  const linkPath = path.join(root, "resend-api-key-link");
  try {
    writeFileSync(targetPath, "re_file_key_with_more_than_24_chars\n", { mode: 0o600 });
    symlinkSync(targetPath, linkPath);
    await assert.rejects(
      notifyAdministratorLogin(
        new Request("https://console.example.com/api/auth/callback"),
        administratorPrincipal(),
        "OIDC",
        {
          environment: {
            ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED: "true",
            ELMOS_ADMIN_LOGIN_EMAIL_FROM: "security@example.com",
            ELMOS_RESEND_API_KEY_FILE: linkPath,
          },
        },
      ),
      (error) => error?.code === "ADMIN_LOGIN_NOTIFICATION_SECRET_FILE_UNAVAILABLE",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
