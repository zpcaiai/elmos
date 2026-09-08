import assert from "node:assert/strict";
import test from "node:test";

import { exportJWK, generateKeyPair, SignJWT } from "jose";

import {
  startDescopeOtp,
  verifyDescopeOtp,
} from "../app/lib/server/descopeIdentity.ts";

const originalFetch = globalThis.fetch;
const originalProjectId = process.env.NEXT_PUBLIC_DESCOPE_PROJECT_ID;
const originalBaseUrl = process.env.NEXT_PUBLIC_DESCOPE_BASE_URL;

function configure(projectId) {
  process.env.NEXT_PUBLIC_DESCOPE_PROJECT_ID = projectId;
  process.env.NEXT_PUBLIC_DESCOPE_BASE_URL = "https://descope.example.test";
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test.after(() => {
  globalThis.fetch = originalFetch;
  if (originalProjectId === undefined) delete process.env.NEXT_PUBLIC_DESCOPE_PROJECT_ID;
  else process.env.NEXT_PUBLIC_DESCOPE_PROJECT_ID = originalProjectId;
  if (originalBaseUrl === undefined) delete process.env.NEXT_PUBLIC_DESCOPE_BASE_URL;
  else process.env.NEXT_PUBLIC_DESCOPE_BASE_URL = originalBaseUrl;
});

test("Descope email OTP start uses the provisioned public API contract", async () => {
  const projectId = "PtestEmailOtp12345678901234567";
  configure(projectId);
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: url.toString(), init });
    return jsonResponse({ maskedEmail: "u***@example.com" });
  };

  const result = await startDescopeOtp({
    channel: "EMAIL",
    intent: "LOGIN",
    loginId: " User@Example.COM ",
  });

  assert.deepEqual(result, {
    loginId: "user@example.com",
    maskedDestination: "u***@example.com",
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://descope.example.test/v1/auth/otp/signin/email");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${projectId}`);
  assert.equal(calls[0].init.headers["x-descope-project-id"], projectId);
  assert.deepEqual(JSON.parse(calls[0].init.body), { loginId: "user@example.com" });
});

test("Descope email registration creates a pending user with the normalized profile", async () => {
  configure("PtestEmailSignup123456789012345");
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url: url.toString(), init };
    return jsonResponse({ maskedEmail: "n***@example.com" });
  };

  const result = await startDescopeOtp({
    channel: "EMAIL",
    intent: "REGISTER",
    loginId: " New.User@Example.COM ",
    displayName: " New ELMOS User ",
  });

  assert.deepEqual(result, {
    loginId: "new.user@example.com",
    maskedDestination: "n***@example.com",
  });
  assert.equal(captured.url, "https://descope.example.test/v1/auth/otp/signup/email");
  assert.deepEqual(JSON.parse(captured.init.body), {
    loginId: "new.user@example.com",
    user: { email: "new.user@example.com", name: "New ELMOS User" },
  });
});

test("Descope phone registration sends normalized identity and profile", async () => {
  configure("PtestPhoneOtp12345678901234567");
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url: url.toString(), init };
    return jsonResponse({ maskedPhone: "+86******5678" });
  };

  const result = await startDescopeOtp({
    channel: "SMS",
    intent: "REGISTER",
    loginId: "+86 (138) 1234-5678",
    displayName: "ELMOS User",
  });

  assert.equal(result.loginId, "+8613812345678");
  assert.equal(captured.url, "https://descope.example.test/v1/auth/otp/signup/sms");
  assert.deepEqual(JSON.parse(captured.init.body), {
    loginId: "+8613812345678",
    user: { phone: "+8613812345678", name: "ELMOS User" },
  });
});

test("Descope OTP verification accepts only signed tokens bound to the verified user", async () => {
  const projectId = "PtestVerifyOtp1234567890123456";
  const userId = "descope-user-123";
  configure(projectId);
  const { publicKey, privateKey } = await generateKeyPair("RS256");
  const jwk = await exportJWK(publicKey);
  jwk.kid = "verification-key";
  jwk.alg = "RS256";
  jwk.use = "sig";
  const signed = (expiresIn) => new SignJWT({})
    .setProtectedHeader({ alg: "RS256", kid: jwk.kid })
    .setIssuer(projectId)
    .setSubject(userId)
    .setIssuedAt()
    .setExpirationTime(expiresIn)
    .sign(privateKey);
  const [sessionJwt, refreshJwt] = await Promise.all([signed("5m"), signed("1h")]);
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: url.toString(), init });
    if (url.toString().endsWith(`/v2/keys/${projectId}`)) {
      return jsonResponse({ keys: [jwk] });
    }
    return jsonResponse({
      sessionJwt,
      refreshJwt,
      user: {
        userId,
        loginIds: ["zpchoney@gmail.com"],
        email: "zpchoney@gmail.com",
        verifiedEmail: true,
      },
    });
  };

  const session = await verifyDescopeOtp({
    channel: "EMAIL",
    loginId: "zpchoney@gmail.com",
    code: "123456",
  });

  assert.equal(session.identity.userId, userId);
  assert.equal(session.identity.email, "zpchoney@gmail.com");
  assert.equal(session.identity.verifiedEmail, true);
  assert.equal(session.authenticationMethod, "EMAIL_OTP");
  assert.equal(calls[0].url, "https://descope.example.test/v1/auth/otp/verify/email");
  assert.equal(calls.filter(({ url }) => url.endsWith(`/v2/keys/${projectId}`)).length, 1);
});

test("Descope provider errors fail closed without exposing the provider response", async () => {
  configure("PtestFailureOtp123456789012345");
  globalThis.fetch = async () => jsonResponse({ error: "sensitive-provider-detail" }, 429);

  await assert.rejects(
    startDescopeOtp({ channel: "EMAIL", intent: "LOGIN", loginId: "user@example.com" }),
    (error) => {
      assert.equal(error.status, 429);
      assert.equal(error.code, "DESCOPE_OTP_START_REJECTED");
      assert.doesNotMatch(error.message, /sensitive-provider-detail/);
      return true;
    },
  );
});
