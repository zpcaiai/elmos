import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

import { NextRequest } from "next/server.js";

import {
  accountCookieNames,
  descopeOtpVerifyFixture,
  resetDescopeOtpVerifyFixture,
} from "./descopeOtpVerifyRoute.fixture.mjs";

const routeUrl = new URL("../app/api/auth/descope/otp/verify/_route.ts", import.meta.url);
const fixtureUrl = new URL("./descopeOtpVerifyRoute.fixture.mjs", import.meta.url).href;
const dependencies = new Set([
  "../../../../../lib/server/accountSession",
  "../../../../../lib/server/adminLoginNotification",
  "../../../../../lib/server/descopeIdentity",
]);

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL === routeUrl.href && specifier === "next/server") {
      return nextResolve("next/server.js", context);
    }
    if (context.parentURL === routeUrl.href && dependencies.has(specifier)) {
      return { url: fixtureUrl, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});

const { POST } = await import(routeUrl.href);

function request() {
  return new NextRequest("https://console.example.test/api/auth/descope/otp/verify", {
    method: "POST",
    headers: {
      cookie: `${accountCookieNames.descopeOtpChallenge}=sealed-challenge`,
      origin: "https://console.example.test",
      "sec-fetch-site": "same-origin",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ code: "123456" }),
  });
}

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

test("Descope administrator OTP waits for notification acceptance before setting session cookies", async () => {
  resetDescopeOtpVerifyFixture();
  const notificationStarted = deferred();
  const notificationAccepted = deferred();
  descopeOtpVerifyFixture.notificationImplementation = async () => {
    notificationStarted.resolve();
    return notificationAccepted.promise;
  };

  let settled = false;
  const responsePromise = POST(request()).finally(() => { settled = true; });
  await notificationStarted.promise;
  assert.equal(settled, false);
  assert.deepEqual(descopeOtpVerifyFixture.calls.events, [
    "same-origin",
    "read-challenge",
    "verify-otp",
    "create-session",
    "notify-admin",
  ]);
  assert.deepEqual(descopeOtpVerifyFixture.calls.notifications, ["DESCOPE_EMAIL_OTP"]);

  notificationAccepted.resolve({
    eventId: "11111111-1111-4111-8111-111111111111",
    providerMessageId: "22222222-2222-4222-8222-222222222222",
    acceptedAt: "2026-09-05T12:00:00.000Z",
  });
  const response = await responsePromise;
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "https://console.example.test/admin");
  assert.equal(response.headers.get("x-elmos-admin-login-notification"), "ACCEPTED");
  assert.equal(response.cookies.get(accountCookieNames.session)?.value, "sealed-descope-session");
  assert.equal(response.cookies.get(accountCookieNames.accessToken)?.value, "descope-access-token");
  assert.equal(response.cookies.get(accountCookieNames.refreshToken)?.value, "descope-refresh-token");
  assert.deepEqual(descopeOtpVerifyFixture.calls.revoked, []);
});

test("Descope administrator OTP notification failure revokes provider session and writes no auth cookies", async () => {
  resetDescopeOtpVerifyFixture();
  descopeOtpVerifyFixture.notificationImplementation = async () => {
    throw Object.assign(new Error("notification unavailable"), {
      code: "ADMIN_LOGIN_NOTIFICATION_UNAVAILABLE",
    });
  };

  const response = await POST(request());
  const location = new URL(response.headers.get("location"));
  assert.equal(response.status, 303);
  assert.equal(location.pathname, "/admin/login");
  assert.equal(location.searchParams.get("error"), "ADMIN_LOGIN_NOTIFICATION_UNAVAILABLE");
  assert.equal(response.cookies.get(accountCookieNames.session), undefined);
  assert.equal(response.cookies.get(accountCookieNames.accessToken), undefined);
  assert.equal(response.cookies.get(accountCookieNames.refreshToken), undefined);
  assert.deepEqual(descopeOtpVerifyFixture.calls.revoked, ["descope-refresh-token"]);
});

test("ordinary Descope OTP never triggers the administrator notification", async () => {
  resetDescopeOtpVerifyFixture();
  descopeOtpVerifyFixture.administrator = false;
  const response = await POST(request());
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "https://console.example.test/");
  assert.deepEqual(descopeOtpVerifyFixture.calls.notifications, []);
  assert.equal(response.headers.get("x-elmos-admin-login-notification"), null);
});
