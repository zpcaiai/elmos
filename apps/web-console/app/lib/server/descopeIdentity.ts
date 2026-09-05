import { createSdk } from "@descope/nextjs-sdk/server";
import { AccountSessionError, type DescopeAuthenticationMethod, type DescopeIdentity } from "./accountSession";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const phonePattern = /^\+[1-9]\d{7,14}$/;

type DescopeConfiguration = {
  projectId: string;
  baseUrl?: string;
  wechatProvider?: string;
};

type DescopeUser = {
  userId: string;
  loginIds: string[];
  name?: string;
  email?: string;
  verifiedEmail?: boolean;
  phone?: string;
  verifiedPhone?: boolean;
  OAuth?: Record<string, boolean>;
};

export type VerifiedDescopeSession = {
  identity: DescopeIdentity;
  authenticationMethod: DescopeAuthenticationMethod;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  refreshExpiresAt: number;
};

function exactBaseUrl(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new AccountSessionError(503, "DESCOPE_CONFIGURATION_INVALID", "Descope API 地址无效。");
  }
  if (
    parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
  ) {
    throw new AccountSessionError(503, "DESCOPE_CONFIGURATION_INVALID", "Descope API 必须使用可信 HTTPS 地址。");
  }
  return parsed.toString().replace(/\/$/, "");
}

export function descopeConfiguration(): DescopeConfiguration {
  const projectId = process.env.NEXT_PUBLIC_DESCOPE_PROJECT_ID?.trim() ?? "";
  if (!/^[A-Za-z0-9_-]{10,128}$/.test(projectId)) {
    throw new AccountSessionError(503, "DESCOPE_NOT_CONFIGURED", "Descope 项目标识尚未配置。");
  }
  const rawBaseUrl = process.env.NEXT_PUBLIC_DESCOPE_BASE_URL?.trim() ?? "";
  const rawWechatProvider = process.env.ELMOS_DESCOPE_WECHAT_PROVIDER?.trim()
    .toLocaleLowerCase("en-US") ?? "";
  const wechatProvider = /^[a-z0-9][a-z0-9_-]{1,63}$/.test(rawWechatProvider)
    ? rawWechatProvider
    : undefined;
  return {
    projectId,
    ...(rawBaseUrl ? { baseUrl: exactBaseUrl(rawBaseUrl) } : {}),
    ...(wechatProvider ? { wechatProvider } : {}),
  };
}

export function descopeConfigured(): boolean {
  try {
    descopeConfiguration();
    return true;
  } catch {
    return false;
  }
}

export function descopeWechatConfigured(): boolean {
  try {
    return Boolean(descopeConfiguration().wechatProvider);
  } catch {
    return false;
  }
}

function sdk() {
  const configuration = descopeConfiguration();
  return createSdk({
    projectId: configuration.projectId,
    ...(configuration.baseUrl ? { baseUrl: configuration.baseUrl } : {}),
  });
}

function normalizedEmail(value: string): string {
  const normalized = value.trim().toLocaleLowerCase("en-US");
  if (normalized.length > 254 || !emailPattern.test(normalized)) {
    throw new AccountSessionError(400, "DESCOPE_EMAIL_INVALID", "请输入有效邮箱地址。");
  }
  return normalized;
}

function normalizedPhone(value: string): string {
  const normalized = value.trim().replace(/[\s()-]/g, "");
  if (!phonePattern.test(normalized)) {
    throw new AccountSessionError(400, "DESCOPE_PHONE_INVALID", "手机号需使用含国家区号的 E.164 格式，例如 +8613812345678。");
  }
  return normalized;
}

function providerFailure(code: string, status = 401): AccountSessionError {
  return new AccountSessionError(status, code, "身份提供商未接受本次请求，请检查输入后重试。");
}

function assertProviderResponse<T>(
  response: { ok: boolean; data?: T; code?: number },
  code: string,
): T {
  if (!response.ok || response.data === undefined) {
    const status = response.code === 429 ? 429 : response.code === 404 ? 401 : 502;
    throw providerFailure(code, status);
  }
  return response.data;
}

function identityFromUser(user: DescopeUser): DescopeIdentity {
  if (!user.userId || user.userId.length > 128 || !Array.isArray(user.loginIds)) {
    throw providerFailure("DESCOPE_IDENTITY_INVALID", 502);
  }
  return {
    userId: user.userId,
    ...(user.name ? { displayName: user.name } : {}),
    ...(user.email ? { email: user.email } : {}),
    verifiedEmail: user.verifiedEmail === true,
    ...(user.phone ? { phone: user.phone } : {}),
    verifiedPhone: user.verifiedPhone === true,
  };
}

async function verifiedSession(
  data: {
    sessionJwt: string;
    refreshJwt?: string;
    user?: DescopeUser;
  },
  method: DescopeAuthenticationMethod,
  expectedLoginId?: string,
): Promise<VerifiedDescopeSession> {
  if (!data.sessionJwt || !data.refreshJwt || !data.user) {
    throw providerFailure("DESCOPE_TOKEN_RESPONSE_INVALID", 502);
  }
  const client = sdk();
  let sessionInfo: Awaited<ReturnType<typeof client.validateSession>>;
  let refreshInfo: Awaited<ReturnType<typeof client.validateJwt>>;
  try {
    [sessionInfo, refreshInfo] = await Promise.all([
      client.validateSession(data.sessionJwt),
      client.validateJwt(data.refreshJwt),
    ]);
  } catch {
    throw providerFailure("DESCOPE_TOKEN_INVALID", 401);
  }
  const identity = identityFromUser(data.user);
  if (
    sessionInfo.token.sub !== identity.userId
    || refreshInfo.token.sub !== identity.userId
    || typeof sessionInfo.token.exp !== "number"
    || typeof refreshInfo.token.exp !== "number"
  ) {
    throw providerFailure("DESCOPE_IDENTITY_MISMATCH", 403);
  }
  if (method === "EMAIL_OTP") {
    const actual = identity.email ? normalizedEmail(identity.email) : "";
    const expected = expectedLoginId ? normalizedEmail(expectedLoginId) : actual;
    if (!actual || actual !== expected || !identity.verifiedEmail) {
      throw providerFailure("DESCOPE_EMAIL_NOT_VERIFIED", 403);
    }
  }
  if (method === "PHONE_OTP") {
    const actual = identity.phone ? normalizedPhone(identity.phone) : "";
    const expected = expectedLoginId ? normalizedPhone(expectedLoginId) : actual;
    if (!actual || actual !== expected || !identity.verifiedPhone) {
      throw providerFailure("DESCOPE_PHONE_NOT_VERIFIED", 403);
    }
  }
  return {
    identity,
    authenticationMethod: method,
    accessToken: data.sessionJwt,
    refreshToken: data.refreshJwt,
    expiresAt: sessionInfo.token.exp * 1_000,
    refreshExpiresAt: refreshInfo.token.exp * 1_000,
  };
}

export async function startDescopeOtp(input: {
  channel: "EMAIL" | "SMS";
  intent: "LOGIN" | "REGISTER";
  loginId: string;
  displayName?: string;
  allowSignUpOrIn?: boolean;
}): Promise<{ loginId: string; maskedDestination: string }> {
  const client = sdk();
  if (input.channel === "EMAIL") {
    const loginId = normalizedEmail(input.loginId);
    const response = input.allowSignUpOrIn
      ? await client.otp.signUpOrIn.email(loginId)
      : input.intent === "REGISTER"
        ? await client.otp.signUp.email(
          loginId,
          { email: loginId, ...(input.displayName ? { name: input.displayName.trim() } : {}) },
        )
        : await client.otp.signIn.email(loginId);
    const data = assertProviderResponse(response, "DESCOPE_OTP_START_REJECTED");
    return { loginId, maskedDestination: data.maskedEmail };
  }
  const loginId = normalizedPhone(input.loginId);
  const response = input.intent === "REGISTER"
    ? await client.otp.signUp.sms(
      loginId,
      { phone: loginId, ...(input.displayName ? { name: input.displayName.trim() } : {}) },
    )
    : await client.otp.signIn.sms(loginId);
  const data = assertProviderResponse(response, "DESCOPE_OTP_START_REJECTED");
  return { loginId, maskedDestination: data.maskedPhone };
}

export async function verifyDescopeOtp(input: {
  channel: "EMAIL" | "SMS";
  loginId: string;
  code: string;
}): Promise<VerifiedDescopeSession> {
  const code = input.code.trim();
  if (!/^\d{4,10}$/.test(code)) {
    throw new AccountSessionError(400, "DESCOPE_OTP_CODE_INVALID", "验证码格式无效。");
  }
  const client = sdk();
  const response = input.channel === "EMAIL"
    ? await client.otp.verify.email(normalizedEmail(input.loginId), code)
    : await client.otp.verify.sms(normalizedPhone(input.loginId), code);
  const data = assertProviderResponse(response, "DESCOPE_OTP_VERIFY_REJECTED");
  return verifiedSession(
    data,
    input.channel === "EMAIL" ? "EMAIL_OTP" : "PHONE_OTP",
    input.loginId,
  );
}

export async function startDescopeWechat(redirectUrl: string): Promise<{
  provider: string;
  authorizationUrl: string;
}> {
  const configuration = descopeConfiguration();
  if (!configuration.wechatProvider) {
    throw new AccountSessionError(503, "DESCOPE_WECHAT_NOT_CONFIGURED", "微信开放平台登录尚未配置。");
  }
  const response = await sdk().oauth.start(configuration.wechatProvider, redirectUrl);
  const data = assertProviderResponse(response, "DESCOPE_WECHAT_START_REJECTED");
  const rawUrl = "url" in data && typeof data.url === "string" ? data.url : "";
  let target: URL;
  try {
    target = new URL(rawUrl);
  } catch {
    throw providerFailure("DESCOPE_WECHAT_RESPONSE_INVALID", 502);
  }
  if (target.protocol !== "https:" || target.username || target.password) {
    throw providerFailure("DESCOPE_WECHAT_RESPONSE_INVALID", 502);
  }
  return { provider: configuration.wechatProvider, authorizationUrl: target.toString() };
}

export async function exchangeDescopeWechat(
  provider: string,
  code: string,
): Promise<VerifiedDescopeSession> {
  if (!code || code.length > 4_096) {
    throw new AccountSessionError(400, "DESCOPE_WECHAT_CALLBACK_INVALID", "微信登录回调无效。");
  }
  const configuredProvider = descopeConfiguration().wechatProvider;
  if (!configuredProvider || configuredProvider !== provider) {
    throw new AccountSessionError(403, "DESCOPE_WECHAT_PROVIDER_MISMATCH", "微信登录提供商不匹配。");
  }
  const response = await sdk().oauth.exchange(code);
  const data = assertProviderResponse(response, "DESCOPE_WECHAT_EXCHANGE_REJECTED");
  const providerLinked = Object.entries(data.user?.OAuth ?? {}).some(
    ([name, linked]) => name.toLocaleLowerCase("en-US") === provider && linked === true,
  );
  if (!providerLinked) {
    throw providerFailure("DESCOPE_WECHAT_IDENTITY_INVALID", 403);
  }
  return verifiedSession(data, "WECHAT_OAUTH");
}

export async function refreshDescopeSession(
  refreshToken: string,
  method: DescopeAuthenticationMethod,
): Promise<VerifiedDescopeSession> {
  const client = sdk();
  let refreshed: Awaited<ReturnType<typeof client.refreshSession>>;
  try {
    refreshed = await client.refreshSession(refreshToken);
  } catch {
    throw providerFailure("DESCOPE_REFRESH_REJECTED", 401);
  }
  const effectiveRefreshToken = refreshed.refreshJwt ?? refreshToken;
  const userResponse = await client.me(effectiveRefreshToken);
  const user = assertProviderResponse(userResponse, "DESCOPE_USER_LOOKUP_REJECTED");
  return verifiedSession({
    sessionJwt: refreshed.jwt,
    refreshJwt: effectiveRefreshToken,
    user,
  }, method);
}

export async function revokeDescopeSession(refreshToken: string): Promise<boolean> {
  try {
    const response = await sdk().logout(refreshToken);
    return response.ok;
  } catch {
    return false;
  }
}
