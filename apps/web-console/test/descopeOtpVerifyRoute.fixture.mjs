export const accountCookieNames = {
  session: "__Host-elmos_session",
  accessToken: "__Host-elmos_access_token",
  refreshToken: "__Host-elmos_refresh_token",
  authorizationFlow: "__Host-elmos_authorization_flow",
  descopeOtpChallenge: "__Host-elmos_descope_otp_challenge",
  descopeOauthFlow: "__Host-elmos_descope_oauth_flow",
  tenant: "__Host-elmos_tenant",
};

export const localAccountCookieNames = {
  session: "elmos_local_session",
  accessToken: "elmos_local_access_token",
};

const adminPrincipal = {
  actorId: "descope:admin-user-123",
  displayName: "Administrator",
  email: "zpchoney@gmail.com",
  emailVerified: true,
  isPlatformAdmin: true,
  organizationId: "elmos-public",
  roles: ["APPROVER"],
  permissions: ["admin:read", "admin:approve"],
  memberships: [],
};

export const descopeOtpVerifyFixture = {
  administrator: true,
  notificationImplementation: async () => ({
    eventId: "11111111-1111-4111-8111-111111111111",
    providerMessageId: "22222222-2222-4222-8222-222222222222",
    acceptedAt: "2026-09-05T12:00:00.000Z",
  }),
  calls: null,
};

export function resetDescopeOtpVerifyFixture() {
  descopeOtpVerifyFixture.administrator = true;
  descopeOtpVerifyFixture.notificationImplementation = async () => ({
    eventId: "11111111-1111-4111-8111-111111111111",
    providerMessageId: "22222222-2222-4222-8222-222222222222",
    acceptedAt: "2026-09-05T12:00:00.000Z",
  });
  descopeOtpVerifyFixture.calls = {
    events: [],
    notifications: [],
    revoked: [],
  };
}

resetDescopeOtpVerifyFixture();

export function accountCookieDeletionOptions() {
  return { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 0 };
}

export function localAccountCookieDeletionOptions() {
  return { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 0 };
}

export function assertSameOriginMutation() {
  descopeOtpVerifyFixture.calls.events.push("same-origin");
}

export function readDescopeOtpChallenge() {
  descopeOtpVerifyFixture.calls.events.push("read-challenge");
  return {
    version: 1,
    channel: "EMAIL",
    intent: "LOGIN",
    loginMode: descopeOtpVerifyFixture.administrator ? "ADMIN" : "USER",
    loginId: descopeOtpVerifyFixture.administrator ? "zpchoney@gmail.com" : "user@example.com",
    returnTo: descopeOtpVerifyFixture.administrator ? "/admin" : "/",
    expiresAt: Date.now() + 60_000,
  };
}

export function createDescopeAccountSession({ loginMode }) {
  descopeOtpVerifyFixture.calls.events.push("create-session");
  return {
    tokens: { accessToken: "descope-access-token", refreshToken: "descope-refresh-token" },
    session: "sealed-descope-session",
    expiresAt: Date.now() + 10 * 60_000,
    refreshExpiresAt: Date.now() + 4 * 60 * 60_000,
    principal: descopeOtpVerifyFixture.administrator
      ? adminPrincipal
      : { ...adminPrincipal, actorId: "descope:user-123", email: "user@example.com", emailVerified: true, isPlatformAdmin: false, roles: ["DEVELOPER"], permissions: ["workspace:view"] },
    loginMode,
  };
}

export function isPlatformAdministrator(principal) {
  return principal.isPlatformAdmin === true;
}

export function refreshSessionCookieMaxAge() {
  return 14_400;
}

export function sessionCookieMaxAge() {
  return 600;
}

export function trustedPublicOrigin() {
  return "https://console.example.test";
}

export function accountSessionErrorResponse(error) {
  return Response.json({ errorCode: error?.code ?? "UNEXPECTED" }, { status: 500 });
}

export async function notifyAdministratorLogin(_request, _principal, authentication) {
  descopeOtpVerifyFixture.calls.events.push("notify-admin");
  descopeOtpVerifyFixture.calls.notifications.push(authentication);
  return descopeOtpVerifyFixture.notificationImplementation();
}

export async function verifyDescopeOtp() {
  descopeOtpVerifyFixture.calls.events.push("verify-otp");
  return {
    identity: { userId: "admin-user-123", email: "zpchoney@gmail.com", verifiedEmail: true },
    authenticationMethod: "EMAIL_OTP",
    accessToken: "descope-access-token",
    refreshToken: "descope-refresh-token",
    expiresAt: Date.now() + 10 * 60_000,
    refreshExpiresAt: Date.now() + 4 * 60 * 60_000,
  };
}

export async function revokeDescopeSession(token) {
  descopeOtpVerifyFixture.calls.events.push("revoke-session");
  descopeOtpVerifyFixture.calls.revoked.push(token);
  return true;
}
