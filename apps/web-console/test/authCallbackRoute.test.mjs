import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

import { NextRequest } from "next/server.js";

import {
  accountCookieNames,
  authCallbackFixture,
  resetAuthCallbackFixture,
} from "./authCallbackRoute.fixture.mjs";

const callbackRouteUrl = new URL("../app/api/auth/callback/_route.ts", import.meta.url);
const fixtureUrl = new URL("./authCallbackRoute.fixture.mjs", import.meta.url).href;
const routeDependencySpecifiers = new Set([
  "../../../lib/server/accountSession",
  "../../../lib/server/adminLoginNotification",
]);

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL === callbackRouteUrl.href && specifier === "next/server") {
      return nextResolve("next/server.js", context);
    }
    if (
      context.parentURL === callbackRouteUrl.href
      && routeDependencySpecifiers.has(specifier)
    ) {
      return { url: fixtureUrl, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});

const { GET } = await import(callbackRouteUrl.href);

function callbackRequest() {
  return new NextRequest(
    "https://console.example.test/api/auth/callback?code=authorization-code&state=expected-state",
    {
      headers: {
        cookie: `${accountCookieNames.authorizationFlow}=sealed-authorization-flow`,
      },
    },
  );
}

function callbackRequestFor(search, flow = "sealed-authorization-flow") {
  const headers = flow
    ? { cookie: `${accountCookieNames.authorizationFlow}=${flow}` }
    : undefined;
  return new NextRequest(`https://console.example.test/api/auth/callback?${search}`, { headers });
}

function assertClearedAuthorizationFlow(response) {
  assert.equal(response.cookies.get(accountCookieNames.authorizationFlow)?.value, "");
  assert.equal(response.cookies.get(accountCookieNames.authorizationFlow)?.maxAge, 0);
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function codedError(code) {
  return Object.assign(new Error(code), { code });
}

test("administrator OIDC callback establishes a session only after notification acceptance", async (t) => {
  await t.test("accepted Resend receipt releases the callback and writes session cookies", async () => {
    resetAuthCallbackFixture();
    const notificationStarted = deferred();
    const notificationAccepted = deferred();
    authCallbackFixture.notificationImplementation = async () => {
      notificationStarted.resolve();
      return notificationAccepted.promise;
    };

    let settled = false;
    const responsePromise = GET(callbackRequest()).finally(() => {
      settled = true;
    });

    await notificationStarted.promise;
    assert.equal(settled, false, "the callback must wait for the provider acceptance receipt");
    assert.deepEqual(authCallbackFixture.calls.events, [
      "read-authorization-flow",
      "exchange-authorization-code",
      "notify-administrator-login",
    ]);
    assert.equal(authCallbackFixture.calls.notifications[0].authentication, "OIDC");

    notificationAccepted.resolve({
      eventId: "11111111-1111-4111-8111-111111111111",
      providerMessageId: "22222222-2222-4222-8222-222222222222",
      acceptedAt: "2026-08-31T03:00:00.000Z",
    });
    const response = await responsePromise;

    assert.equal(response.status, 302);
    assert.equal(response.headers.get("location"), "https://console.example.test/admin");
    assert.equal(response.headers.get("cache-control"), "no-store, private");
    assert.equal(response.headers.get("x-elmos-admin-login-notification"), "ACCEPTED");
    assert.equal(response.cookies.get(accountCookieNames.session)?.value, "sealed-admin-session");
    assert.equal(response.cookies.get(accountCookieNames.accessToken)?.value, "oidc-access-token");
    assert.equal(response.cookies.get(accountCookieNames.refreshToken)?.value, "oidc-refresh-token");
    assert.ok(
      response.cookies.get(accountCookieNames.session).maxAge
      > response.cookies.get(accountCookieNames.accessToken).maxAge,
      "the sealed refresh binding must outlive the access-token cookie",
    );
    assert.equal(
      response.cookies.get(accountCookieNames.session).maxAge,
      response.cookies.get(accountCookieNames.refreshToken).maxAge,
    );
    assert.deepEqual(authCallbackFixture.calls.revokedTokens, []);
  });

  await t.test("notification failure writes no session cookies and revokes both issued tokens", async () => {
    resetAuthCallbackFixture();
    authCallbackFixture.notificationImplementation = async () => {
      throw codedError("ADMIN_LOGIN_NOTIFICATION_RATE_LIMITED");
    };

    const response = await GET(callbackRequest());
    const location = new URL(response.headers.get("location"));

    assert.equal(response.status, 302);
    assert.equal(location.origin, "https://console.example.test");
    assert.equal(location.pathname, "/admin/login");
    assert.equal(location.searchParams.get("error"), "ADMIN_LOGIN_NOTIFICATION_RATE_LIMITED");
    assert.equal(response.headers.get("cache-control"), "no-store, private");
    assert.equal(response.headers.get("x-elmos-admin-login-notification"), null);
    assert.equal(response.cookies.get(accountCookieNames.session), undefined);
    assert.equal(response.cookies.get(accountCookieNames.accessToken), undefined);
    assert.equal(response.cookies.get(accountCookieNames.refreshToken), undefined);
    assert.equal(response.cookies.get(accountCookieNames.authorizationFlow)?.value, "");
    assert.equal(response.cookies.get(accountCookieNames.authorizationFlow)?.maxAge, 0);
    assert.deepEqual(authCallbackFixture.calls.revokedTokens, [
      "oidc-access-token",
      "oidc-refresh-token",
    ]);
  });
});

test("OIDC callback recovers the login surface only from a sealed flow with matching state", async (t) => {
  await t.test("provider cancellation returns a validated admin flow to the admin login", async () => {
    resetAuthCallbackFixture();

    const response = await GET(callbackRequestFor("error=access_denied&state=expected-state"));
    const location = new URL(response.headers.get("location"));

    assert.equal(response.status, 302);
    assert.equal(location.pathname, "/admin/login");
    assert.equal(location.searchParams.get("error"), "OIDC_AUTHORIZATION_REJECTED");
    assertClearedAuthorizationFlow(response);
    assert.equal(authCallbackFixture.calls.readAuthorizationFlow.length, 1);
    assert.equal(authCallbackFixture.calls.exchangeAuthorizationCode.length, 0);
  });

  await t.test("missing authorization code returns a validated admin flow to the admin login", async () => {
    resetAuthCallbackFixture();

    const response = await GET(callbackRequestFor("state=expected-state"));
    const location = new URL(response.headers.get("location"));

    assert.equal(location.pathname, "/admin/login");
    assert.equal(location.searchParams.get("error"), "OIDC_CALLBACK_INVALID");
    assertClearedAuthorizationFlow(response);
    assert.equal(authCallbackFixture.calls.exchangeAuthorizationCode.length, 0);
  });

  await t.test("mismatched state cannot steer a provider error to the admin login", async () => {
    resetAuthCallbackFixture();

    const response = await GET(callbackRequestFor("error=access_denied&state=attacker-state"));
    const location = new URL(response.headers.get("location"));

    assert.equal(location.pathname, "/login");
    assert.equal(location.searchParams.get("error"), "OIDC_AUTHORIZATION_REJECTED");
    assertClearedAuthorizationFlow(response);
    assert.equal(authCallbackFixture.calls.readAuthorizationFlow.length, 1);
    assert.equal(authCallbackFixture.calls.exchangeAuthorizationCode.length, 0);
  });

  await t.test("missing state cannot use the sealed flow to select the admin login", async () => {
    resetAuthCallbackFixture();

    const response = await GET(callbackRequestFor("error=access_denied"));
    const location = new URL(response.headers.get("location"));

    assert.equal(location.pathname, "/login");
    assert.equal(location.searchParams.get("error"), "OIDC_AUTHORIZATION_REJECTED");
    assertClearedAuthorizationFlow(response);
    assert.equal(authCallbackFixture.calls.readAuthorizationFlow.length, 0);
  });
});

test("administrator access-token claim rejection cannot establish a callback session", async () => {
  resetAuthCallbackFixture();
  authCallbackFixture.exchangeImplementation = async () => {
    throw codedError("OIDC_ADMIN_ACCESS_TOKEN_SUBJECT_INVALID");
  };

  const response = await GET(callbackRequest());
  const location = new URL(response.headers.get("location"));

  assert.equal(response.status, 302);
  assert.equal(location.pathname, "/admin/login");
  assert.equal(location.searchParams.get("error"), "OIDC_ADMIN_ACCESS_TOKEN_SUBJECT_INVALID");
  assert.equal(authCallbackFixture.calls.notifications.length, 0);
  assert.equal(response.cookies.get(accountCookieNames.session), undefined);
  assert.equal(response.cookies.get(accountCookieNames.accessToken), undefined);
  assert.equal(response.cookies.get(accountCookieNames.refreshToken), undefined);
  assertClearedAuthorizationFlow(response);
});
