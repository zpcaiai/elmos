export const accountCookieNames = Object.freeze({
  session: "__Host-elmos_session",
  accessToken: "__Host-elmos_access_token",
  refreshToken: "__Host-elmos_refresh_token",
  authorizationFlow: "__Host-elmos_authorization_flow",
  tenant: "__Host-elmos_tenant",
});

export const localAccountCookieNames = Object.freeze({
  session: "elmos_local_session",
  accessToken: "elmos_local_access_token",
});

const defaultFlow = Object.freeze({
  version: 1,
  state: "expected-state",
  nonce: "test-nonce",
  verifier: "test-verifier",
  returnTo: "/admin",
  loginMode: "ADMIN",
  expiresAt: Date.now() + 60_000,
});

const defaultPrincipal = Object.freeze({
  actorId: "oidc-admin",
  displayName: "ELMOS Administrator",
  email: "zpchoney@gmail.com",
  emailVerified: true,
  isPlatformAdmin: true,
  organizationId: "tenant-a",
  roles: ["APPROVER"],
  permissions: ["admin:read", "admin:approve"],
  memberships: [],
});

function defaultExchangeResult() {
  const now = Date.now();
  return {
    tokens: {
      accessToken: "oidc-access-token",
      refreshToken: "oidc-refresh-token",
      idToken: "oidc-id-token",
      expiresIn: 900,
    },
    session: "sealed-admin-session",
    expiresAt: now + 900_000,
    refreshExpiresAt: now + 8 * 60 * 60_000,
    principal: { ...defaultPrincipal },
  };
}

export const authCallbackFixture = {
  flow: { ...defaultFlow },
  exchangeResult: defaultExchangeResult(),
  exchangeImplementation: null,
  sessionMaxAge: 900,
  notificationImplementation: async () => ({
    eventId: "11111111-1111-4111-8111-111111111111",
    providerMessageId: "22222222-2222-4222-8222-222222222222",
    acceptedAt: "2026-08-31T03:00:00.000Z",
  }),
  revocationImplementation: async () => true,
  calls: {
    events: [],
    readAuthorizationFlow: [],
    exchangeAuthorizationCode: [],
    notifications: [],
    revokedTokens: [],
    sessionCookieExpiries: [],
  },
};

export function resetAuthCallbackFixture() {
  authCallbackFixture.flow = { ...defaultFlow };
  authCallbackFixture.exchangeResult = defaultExchangeResult();
  authCallbackFixture.exchangeImplementation = null;
  authCallbackFixture.sessionMaxAge = 900;
  authCallbackFixture.notificationImplementation = async () => ({
    eventId: "11111111-1111-4111-8111-111111111111",
    providerMessageId: "22222222-2222-4222-8222-222222222222",
    acceptedAt: "2026-08-31T03:00:00.000Z",
  });
  authCallbackFixture.revocationImplementation = async () => true;
  authCallbackFixture.calls = {
    events: [],
    readAuthorizationFlow: [],
    exchangeAuthorizationCode: [],
    notifications: [],
    revokedTokens: [],
    sessionCookieExpiries: [],
  };
  return authCallbackFixture;
}

export function accountCookieDeletionOptions(name) {
  return {
    httpOnly: true,
    secure: true,
    sameSite: name === accountCookieNames.refreshToken ? "strict" : "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  };
}

export function localAccountCookieDeletionOptions() {
  return {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  };
}

export function readAuthorizationFlow(sealedFlow, presentedState) {
  authCallbackFixture.calls.events.push("read-authorization-flow");
  authCallbackFixture.calls.readAuthorizationFlow.push({ sealedFlow, presentedState });
  if (
    sealedFlow !== "sealed-authorization-flow"
    || presentedState !== authCallbackFixture.flow.state
  ) {
    throw Object.assign(new Error("OIDC state is invalid"), { code: "OIDC_STATE_INVALID" });
  }
  return authCallbackFixture.flow;
}

export async function exchangeAuthorizationCode(code, flow) {
  authCallbackFixture.calls.events.push("exchange-authorization-code");
  authCallbackFixture.calls.exchangeAuthorizationCode.push({ code, flow });
  if (authCallbackFixture.exchangeImplementation) {
    return authCallbackFixture.exchangeImplementation(code, flow);
  }
  return authCallbackFixture.exchangeResult;
}

export function isPlatformAdministrator(principal) {
  return principal?.isPlatformAdmin === true;
}

export async function revokeToken(token) {
  authCallbackFixture.calls.events.push(`revoke:${token}`);
  authCallbackFixture.calls.revokedTokens.push(token);
  return authCallbackFixture.revocationImplementation(token);
}

export function sessionCookieMaxAge(expiresAt) {
  authCallbackFixture.calls.sessionCookieExpiries.push(expiresAt);
  return authCallbackFixture.sessionMaxAge;
}

export function refreshSessionCookieMaxAge(refreshExpiresAt) {
  return Math.max(0, Math.floor((refreshExpiresAt - Date.now()) / 1_000));
}

export function trustedPublicOrigin(request) {
  return new URL(request.url).origin;
}

export async function notifyAdministratorLogin(request, principal, authentication) {
  authCallbackFixture.calls.events.push("notify-administrator-login");
  authCallbackFixture.calls.notifications.push({ request, principal, authentication });
  return authCallbackFixture.notificationImplementation(request, principal, authentication);
}
