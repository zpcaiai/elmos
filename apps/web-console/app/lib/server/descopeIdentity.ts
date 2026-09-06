import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";
import { AccountSessionError, type DescopeAuthenticationMethod, type DescopeIdentity } from "./accountSession";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const phonePattern = /^\+[1-9]\d{7,14}$/;
const defaultDescopeBaseUrl = "https://api.descope.com";
const maximumProviderResponseLength = 256_000;
const providerRequestTimeoutMs = 15_000;

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

type DescopeTokenResponse = {
  sessionJwt: string;
  refreshJwt?: string;
  user?: DescopeUser;
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

function providerStatus(status: number): number {
  if (status === 429) return 429;
  if ([400, 401, 403, 404].includes(status)) return 401;
  return 502;
}

function descopeApiBaseUrl(configuration: DescopeConfiguration): string {
  return configuration.baseUrl ?? defaultDescopeBaseUrl;
}

async function providerRequest<T>(input: {
  path: string;
  method?: "GET" | "POST";
  body?: Record<string, unknown>;
  query?: Record<string, string>;
  refreshToken?: string;
  errorCode: string;
}): Promise<T> {
  const configuration = descopeConfiguration();
  const target = new URL(input.path, `${descopeApiBaseUrl(configuration)}/`);
  Object.entries(input.query ?? {}).forEach(([name, value]) => target.searchParams.set(name, value));
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), providerRequestTimeoutMs);
  let response: Response;
  try {
    response = await fetch(target, {
      method: input.method ?? "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${configuration.projectId}${input.refreshToken ? `:${input.refreshToken}` : ""}`,
        "x-descope-project-id": configuration.projectId,
        ...(input.body ? { "Content-Type": "application/json" } : {}),
      },
      ...(input.body ? { body: JSON.stringify(input.body) } : {}),
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
    });
  } catch {
    throw providerFailure(input.errorCode, 502);
  } finally {
    clearTimeout(timeout);
  }
  const raw = await response.text();
  if (!response.ok) {
    throw providerFailure(input.errorCode, providerStatus(response.status));
  }
  if (raw.length > maximumProviderResponseLength) {
    throw providerFailure(`${input.errorCode}_RESPONSE_TOO_LARGE`, 502);
  }
  if (!raw) return {} as T;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("response is not an object");
    }
    return parsed as T;
  } catch {
    throw providerFailure(`${input.errorCode}_RESPONSE_INVALID`, 502);
  }
}

const descopeJwks = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

function trustedIssuer(issuer: unknown, projectId: string): boolean {
  if (issuer === projectId) return true;
  if (typeof issuer !== "string" || !issuer) return false;
  try {
    const segments = new URL(issuer).pathname.split("/").filter(Boolean);
    return segments.at(-1) === projectId || segments.at(-2) === projectId;
  } catch {
    const segments = issuer.split("/").filter(Boolean);
    return segments.at(-1) === projectId || segments.at(-2) === projectId;
  }
}

async function validateDescopeJwt(token: string): Promise<JWTPayload> {
  if (!token || token.length > 32_768) throw providerFailure("DESCOPE_TOKEN_INVALID", 401);
  const configuration = descopeConfiguration();
  const key = `${descopeApiBaseUrl(configuration)}/${configuration.projectId}`;
  let jwks = descopeJwks.get(key);
  if (!jwks) {
    jwks = createRemoteJWKSet(
      new URL(`/v2/keys/${encodeURIComponent(configuration.projectId)}`, `${descopeApiBaseUrl(configuration)}/`),
      { timeoutDuration: providerRequestTimeoutMs, cooldownDuration: 30_000 },
    );
    descopeJwks.set(key, jwks);
  }
  try {
    const verified = await jwtVerify(token, jwks, {
      algorithms: ["RS256"],
      clockTolerance: 5,
    });
    if (!trustedIssuer(verified.payload.iss, configuration.projectId)) {
      throw new Error("issuer mismatch");
    }
    return verified.payload;
  } catch {
    throw providerFailure("DESCOPE_TOKEN_INVALID", 401);
  }
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
  const [sessionClaims, refreshClaims] = await Promise.all([
    validateDescopeJwt(data.sessionJwt),
    validateDescopeJwt(data.refreshJwt),
  ]);
  const identity = identityFromUser(data.user);
  if (
    sessionClaims.sub !== identity.userId
    || refreshClaims.sub !== identity.userId
    || typeof sessionClaims.exp !== "number"
    || typeof refreshClaims.exp !== "number"
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
    expiresAt: sessionClaims.exp * 1_000,
    refreshExpiresAt: refreshClaims.exp * 1_000,
  };
}

export async function startDescopeOtp(input: {
  channel: "EMAIL" | "SMS";
  intent: "LOGIN" | "REGISTER";
  loginId: string;
  displayName?: string;
  allowSignUpOrIn?: boolean;
}): Promise<{ loginId: string; maskedDestination: string }> {
  if (input.channel === "EMAIL") {
    const loginId = normalizedEmail(input.loginId);
    const operation = input.allowSignUpOrIn
      ? "signup-in"
      : input.intent === "REGISTER" ? "signup" : "signin";
    const data = await providerRequest<{ maskedEmail: string }>({
      path: `/v1/auth/otp/${operation}/email`,
      body: {
        loginId,
        ...(input.intent === "REGISTER"
          ? { user: { email: loginId, ...(input.displayName ? { name: input.displayName.trim() } : {}) } }
          : {}),
      },
      errorCode: "DESCOPE_OTP_START_REJECTED",
    });
    if (typeof data.maskedEmail !== "string" || !data.maskedEmail) {
      throw providerFailure("DESCOPE_OTP_START_RESPONSE_INVALID", 502);
    }
    return { loginId, maskedDestination: data.maskedEmail };
  }
  const loginId = normalizedPhone(input.loginId);
  const operation = input.intent === "REGISTER" ? "signup" : "signin";
  const data = await providerRequest<{ maskedPhone: string }>({
    path: `/v1/auth/otp/${operation}/sms`,
    body: {
      loginId,
      ...(input.intent === "REGISTER"
        ? { user: { phone: loginId, ...(input.displayName ? { name: input.displayName.trim() } : {}) } }
        : {}),
    },
    errorCode: "DESCOPE_OTP_START_REJECTED",
  });
  if (typeof data.maskedPhone !== "string" || !data.maskedPhone) {
    throw providerFailure("DESCOPE_OTP_START_RESPONSE_INVALID", 502);
  }
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
  const loginId = input.channel === "EMAIL"
    ? normalizedEmail(input.loginId)
    : normalizedPhone(input.loginId);
  const data = await providerRequest<DescopeTokenResponse>({
    path: `/v1/auth/otp/verify/${input.channel === "EMAIL" ? "email" : "sms"}`,
    body: { loginId, code },
    errorCode: "DESCOPE_OTP_VERIFY_REJECTED",
  });
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
  const data = await providerRequest<{ url?: string }>({
    path: "/v1/auth/oauth/authorize",
    body: {},
    query: { provider: configuration.wechatProvider, redirectURL: redirectUrl },
    errorCode: "DESCOPE_WECHAT_START_REJECTED",
  });
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
  const data = await providerRequest<DescopeTokenResponse>({
    path: "/v1/auth/oauth/exchange",
    body: { code },
    errorCode: "DESCOPE_WECHAT_EXCHANGE_REJECTED",
  });
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
  await validateDescopeJwt(refreshToken);
  const refreshed = await providerRequest<DescopeTokenResponse>({
    path: "/v1/auth/refresh",
    refreshToken,
    errorCode: "DESCOPE_REFRESH_REJECTED",
  });
  const effectiveRefreshToken = refreshed.refreshJwt ?? refreshToken;
  const user = await providerRequest<DescopeUser>({
    path: "/v1/auth/me",
    method: "GET",
    refreshToken: effectiveRefreshToken,
    errorCode: "DESCOPE_USER_LOOKUP_REJECTED",
  });
  return verifiedSession({
    sessionJwt: refreshed.sessionJwt,
    refreshJwt: effectiveRefreshToken,
    user,
  }, method);
}

export async function revokeDescopeSession(refreshToken: string): Promise<boolean> {
  try {
    await providerRequest<Record<string, never>>({
      path: "/v1/auth/logout",
      refreshToken,
      errorCode: "DESCOPE_LOGOUT_REJECTED",
    });
    return true;
  } catch {
    return false;
  }
}
