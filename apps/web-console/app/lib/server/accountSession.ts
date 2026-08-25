import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
  timingSafeEqual,
} from "node:crypto";
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";

export const accountCookieNames = {
  session: "__Host-elmos_session",
  accessToken: "__Host-elmos_access_token",
  refreshToken: "__Host-elmos_refresh_token",
  authorizationFlow: "__Host-elmos_authorization_flow",
  tenant: "__Host-elmos_tenant",
} as const;

export type AccountCookieName =
  typeof accountCookieNames[keyof typeof accountCookieNames];

export function accountCookieDeletionOptions(name: AccountCookieName) {
  return {
    httpOnly: true,
    secure: true,
    sameSite: name === accountCookieNames.refreshToken ? "strict" : "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  } as const;
}

const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$/;
const organizationPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const roleNames = [
  "VIEWER",
  "DEVELOPER",
  "MAINTAINER",
  "OPERATOR",
  "APPROVER",
  "TENANT_ADMIN",
] as const;
const maximumCookieValueLength = 3_800;
const maximumTenantMemberships = 32;

export type AccountRole = typeof roleNames[number];
export type AccountPermission =
  | "workspace:view"
  | "spring:execute"
  | "translation:execute"
  | "generation:execute"
  | "modernization:execute"
  | "intake:read"
  | "intake:write"
  | "intake:review"
  | "intake:admin"
  | "repository:read"
  | "repository:write"
  | "repository:commit"
  | "repository:push"
  | "repository:pr"
  | "usage:read"
  | "billing:write"
  | "admin:read"
  | "admin:operate"
  | "admin:approve"
  | "configuration:manage";

const knownPermissions = new Set<AccountPermission>([
  "workspace:view",
  "spring:execute",
  "translation:execute",
  "generation:execute",
  "modernization:execute",
  "intake:read",
  "intake:write",
  "intake:review",
  "intake:admin",
  "repository:read",
  "repository:write",
  "repository:commit",
  "repository:push",
  "repository:pr",
  "usage:read",
  "billing:write",
  "admin:read",
  "admin:operate",
  "admin:approve",
  "configuration:manage",
]);

const rolePermissions: Record<AccountRole, AccountPermission[]> = {
  VIEWER: ["workspace:view", "intake:read", "repository:read", "usage:read"],
  DEVELOPER: [
    "workspace:view",
    "spring:execute",
    "translation:execute",
    "generation:execute",
    "modernization:execute",
    "intake:read",
    "intake:write",
    "repository:read",
    "repository:write",
    "repository:commit",
    "usage:read",
  ],
  MAINTAINER: [
    "workspace:view",
    "spring:execute",
    "translation:execute",
    "generation:execute",
    "modernization:execute",
    "intake:read",
    "intake:write",
    "intake:review",
    "repository:read",
    "repository:write",
    "repository:commit",
    "repository:push",
    "repository:pr",
    "usage:read",
    "billing:write",
  ],
  OPERATOR: [
    "workspace:view",
    "spring:execute",
    "translation:execute",
    "generation:execute",
    "modernization:execute",
    "intake:read",
    "intake:write",
    "intake:review",
    "repository:read",
    "repository:write",
    "repository:commit",
    "repository:push",
    "repository:pr",
    "usage:read",
    "billing:write",
    "admin:read",
    "admin:operate",
  ],
  APPROVER: [
    "workspace:view",
    "spring:execute",
    "translation:execute",
    "generation:execute",
    "modernization:execute",
    "intake:read",
    "intake:write",
    "intake:review",
    "repository:read",
    "repository:write",
    "repository:commit",
    "repository:push",
    "repository:pr",
    "usage:read",
    "billing:write",
    "admin:read",
    "admin:operate",
    "admin:approve",
  ],
  TENANT_ADMIN: [...knownPermissions],
};

export type TenantMembership = {
  organizationId: string;
  roles: AccountRole[];
  permissions: AccountPermission[];
};

export type AccountPrincipal = {
  actorId: string;
  displayName: string;
  email?: string;
  organizationId: string;
  roles: AccountRole[];
  permissions: AccountPermission[];
  memberships: TenantMembership[];
};

type SealedSession = {
  version: 1;
  principal: AccountPrincipal;
  accessTokenHash: string;
  issuedAt: number;
  expiresAt: number;
};

export type AuthorizationFlow = {
  version: 1;
  state: string;
  nonce: string;
  verifier: string;
  returnTo: string;
  expiresAt: number;
};

export type OidcConfiguration = {
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  jwksUri: string;
  userInfoEndpoint?: string;
  endSessionEndpoint?: string;
  revocationEndpoint?: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  audience: string;
  scopes: string;
};

export type TokenExchange = {
  accessToken: string;
  refreshToken?: string;
  idToken: string;
  expiresIn: number;
};

export class AccountSessionError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

function requiredEnvironment(name: string, minimumLength = 1): string {
  const value = process.env[name]?.trim() ?? "";
  if (value.length < minimumLength) {
    throw new AccountSessionError(503, "OIDC_NOT_CONFIGURED", "企业身份提供商尚未完整配置。");
  }
  return value;
}

function exactUrl(name: string, optional = false): string | undefined {
  const value = process.env[name]?.trim() ?? "";
  if (!value && optional) return undefined;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new AccountSessionError(503, "OIDC_CONFIGURATION_INVALID", `${name} 不是有效 URL。`);
  }
  const localDevelopment = process.env.NODE_ENV !== "production"
    && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  if (
    (parsed.protocol !== "https:" && !(localDevelopment && parsed.protocol === "http:"))
    || parsed.username
    || parsed.password
    || parsed.hash
  ) {
    throw new AccountSessionError(503, "OIDC_CONFIGURATION_INVALID", `${name} 必须使用可信 HTTPS 地址。`);
  }
  return value;
}

export function oidcConfiguration(): OidcConfiguration {
  return {
    issuer: exactUrl("ELMOS_OIDC_ISSUER_URI") as string,
    authorizationEndpoint: exactUrl("ELMOS_OIDC_AUTHORIZATION_ENDPOINT") as string,
    tokenEndpoint: exactUrl("ELMOS_OIDC_TOKEN_ENDPOINT") as string,
    jwksUri: exactUrl("ELMOS_OIDC_JWKS_URI") as string,
    userInfoEndpoint: exactUrl("ELMOS_OIDC_USERINFO_ENDPOINT", true),
    endSessionEndpoint: exactUrl("ELMOS_OIDC_END_SESSION_ENDPOINT", true),
    revocationEndpoint: exactUrl("ELMOS_OIDC_REVOCATION_ENDPOINT", true),
    clientId: requiredEnvironment("ELMOS_OIDC_CLIENT_ID"),
    clientSecret: requiredEnvironment("ELMOS_OIDC_CLIENT_SECRET", 16),
    redirectUri: exactUrl("ELMOS_OIDC_REDIRECT_URI") as string,
    audience: requiredEnvironment("ELMOS_OIDC_AUDIENCE"),
    scopes: process.env.ELMOS_OIDC_SCOPES?.trim() || "openid profile email offline_access",
  };
}

export function oidcConfigured(): boolean {
  try {
    oidcConfiguration();
    sessionKey();
    return true;
  } catch {
    return false;
  }
}

function sessionKey(): Buffer {
  const secret = requiredEnvironment("ELMOS_SESSION_SECRET", 32);
  return createHash("sha256").update(secret, "utf8").digest();
}

function base64url(value: Buffer): string {
  return value.toString("base64url");
}

function seal(value: unknown): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", sessionKey(), iv);
  const plaintext = Buffer.from(JSON.stringify(value), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const sealed = `v1.${base64url(iv)}.${base64url(ciphertext)}.${base64url(cipher.getAuthTag())}`;
  if (sealed.length > maximumCookieValueLength) {
    throw new AccountSessionError(
      403,
      "ACCOUNT_SESSION_TOO_LARGE",
      "账户授权上下文超过安全会话容量，请联系管理员减少租户或权限范围。",
    );
  }
  return sealed;
}

function unseal<T>(value: string, code: string): T {
  const parts = value.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") {
    throw new AccountSessionError(401, code, "会话格式无效。");
  }
  try {
    const decipher = createDecipheriv(
      "aes-256-gcm",
      sessionKey(),
      Buffer.from(parts[1], "base64url"),
    );
    decipher.setAuthTag(Buffer.from(parts[3], "base64url"));
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(parts[2], "base64url")),
      decipher.final(),
    ]);
    return JSON.parse(plaintext.toString("utf8")) as T;
  } catch (error) {
    if (error instanceof AccountSessionError) throw error;
    throw new AccountSessionError(401, code, "会话签名或加密校验失败。");
  }
}

function hashToken(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function safeEqual(left: string, right: string): boolean {
  const leftDigest = createHash("sha256").update(left).digest();
  const rightDigest = createHash("sha256").update(right).digest();
  return timingSafeEqual(leftDigest, rightDigest);
}

function cookieMap(header: string | null): Map<string, string> {
  const result = new Map<string, string>();
  for (const pair of (header ?? "").split(";")) {
    const index = pair.indexOf("=");
    if (index < 1) continue;
    const key = pair.slice(0, index).trim();
    const value = pair.slice(index + 1).trim();
    if (key && value) result.set(key, decodeURIComponent(value));
  }
  return result;
}

function rolesFrom(value: unknown): AccountRole[] {
  if (!Array.isArray(value)) return [];
  const allowed = new Set<string>(roleNames);
  return [...new Set(
    value
      .filter((item): item is string => typeof item === "string")
      .map((item) => item.trim().toUpperCase())
      .filter((item): item is AccountRole => allowed.has(item)),
  )];
}

function directPermissions(value: unknown): AccountPermission[] {
  const raw = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(/\s+/)
      : [];
  return [...new Set(
    raw
      .filter((item): item is string => typeof item === "string")
      .map((item) => item.startsWith("elmos:") ? item.slice(6) : item)
      .filter((item): item is AccountPermission => knownPermissions.has(item as AccountPermission)),
  )];
}

function effectivePermissions(roles: AccountRole[], explicit: AccountPermission[]): AccountPermission[] {
  return [...new Set([
    "workspace:view" as AccountPermission,
    ...roles.flatMap((role) => rolePermissions[role]),
    ...explicit,
  ])].sort();
}

function membership(
  organizationId: string,
  roles: AccountRole[],
  permissions: AccountPermission[],
): TenantMembership {
  if (!organizationPattern.test(organizationId)) {
    throw new AccountSessionError(403, "OIDC_TENANT_CLAIM_INVALID", "身份令牌缺少有效租户声明。");
  }
  return {
    organizationId,
    roles,
    permissions: effectivePermissions(roles, permissions),
  };
}

function principalFromClaims(claims: JWTPayload): AccountPrincipal {
  const actorId = typeof claims.sub === "string" ? claims.sub : "";
  const organizationId = typeof claims.organization_id === "string"
    ? claims.organization_id
    : "";
  if (!identifierPattern.test(actorId)) {
    throw new AccountSessionError(403, "OIDC_SUBJECT_CLAIM_INVALID", "身份令牌缺少有效主体声明。");
  }
  const realmRoles = claims.realm_access && typeof claims.realm_access === "object"
    ? (claims.realm_access as { roles?: unknown }).roles
    : undefined;
  const roles = rolesFrom(claims.roles ?? realmRoles);
  const permissions = directPermissions(
    claims.permissions ?? claims.scope ?? claims.scp,
  );
  const primary = membership(organizationId, roles, permissions);
  const memberships = new Map<string, TenantMembership>([[organizationId, primary]]);
  if (Array.isArray(claims.elmos_tenants)) {
    for (const raw of claims.elmos_tenants.slice(0, maximumTenantMemberships)) {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
      const candidate = raw as Record<string, unknown>;
      if (typeof candidate.organization_id !== "string") continue;
      const tenantRoles = rolesFrom(candidate.roles);
      memberships.set(
        candidate.organization_id,
        membership(
          candidate.organization_id,
          tenantRoles,
          directPermissions(candidate.permissions),
        ),
      );
    }
  }
  const displayName = [claims.name, claims.preferred_username, claims.email, actorId]
    .find((value): value is string => typeof value === "string" && value.trim().length > 0)
    ?.trim()
    .slice(0, 160) ?? actorId;
  const email = typeof claims.email === "string" && claims.email.length <= 254
    ? claims.email
    : undefined;
  return {
    actorId,
    displayName,
    ...(email ? { email } : {}),
    organizationId,
    roles: primary.roles,
    permissions: primary.permissions,
    memberships: [...memberships.values()],
  };
}

const globalJwks = globalThis as typeof globalThis & {
  __elmosOidcJwks?: ReturnType<typeof createRemoteJWKSet>;
  __elmosOidcJwksUri?: string;
};

async function verifyIdToken(
  idToken: string,
  configuration: OidcConfiguration,
  expectedNonce?: string,
): Promise<{ claims: JWTPayload; expiresAt: number }> {
  if (
    !globalJwks.__elmosOidcJwks
    || globalJwks.__elmosOidcJwksUri !== configuration.jwksUri
  ) {
    globalJwks.__elmosOidcJwks = createRemoteJWKSet(new URL(configuration.jwksUri), {
      cooldownDuration: 30_000,
      timeoutDuration: 5_000,
    });
    globalJwks.__elmosOidcJwksUri = configuration.jwksUri;
  }
  const verified = await jwtVerify(idToken, globalJwks.__elmosOidcJwks, {
    issuer: configuration.issuer,
    audience: configuration.clientId,
    algorithms: ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
    clockTolerance: 5,
  });
  if (
    expectedNonce
    && (typeof verified.payload.nonce !== "string"
      || !safeEqual(verified.payload.nonce, expectedNonce))
  ) {
    throw new AccountSessionError(401, "OIDC_NONCE_INVALID", "OIDC nonce 校验失败。");
  }
  const expiresAt = (verified.payload.exp ?? 0) * 1_000;
  if (expiresAt <= Date.now()) {
    throw new AccountSessionError(401, "OIDC_TOKEN_EXPIRED", "OIDC 身份令牌已过期。");
  }
  return { claims: verified.payload, expiresAt };
}

export function createAuthorizationFlow(returnTo: string): {
  flow: AuthorizationFlow;
  sealedFlow: string;
  authorizationUrl: string;
} {
  const configuration = oidcConfiguration();
  const safeReturnTo = returnTo.startsWith("/")
    && !returnTo.startsWith("//")
    && !/[\r\n\0]/.test(returnTo)
    ? returnTo
    : "/";
  const verifier = base64url(randomBytes(48));
  const challenge = base64url(createHash("sha256").update(verifier).digest());
  const flow: AuthorizationFlow = {
    version: 1,
    state: base64url(randomBytes(32)),
    nonce: base64url(randomBytes(32)),
    verifier,
    returnTo: safeReturnTo,
    expiresAt: Date.now() + 10 * 60_000,
  };
  const target = new URL(configuration.authorizationEndpoint);
  target.search = new URLSearchParams({
    response_type: "code",
    client_id: configuration.clientId,
    redirect_uri: configuration.redirectUri,
    scope: configuration.scopes,
    state: flow.state,
    nonce: flow.nonce,
    code_challenge: challenge,
    code_challenge_method: "S256",
    audience: configuration.audience,
  }).toString();
  return { flow, sealedFlow: seal(flow), authorizationUrl: target.toString() };
}

export function readAuthorizationFlow(
  sealedFlow: string,
  presentedState: string,
): AuthorizationFlow {
  const flow = unseal<AuthorizationFlow>(sealedFlow, "OIDC_FLOW_INVALID");
  if (
    flow.version !== 1
    || flow.expiresAt <= Date.now()
    || !safeEqual(flow.state, presentedState)
  ) {
    throw new AccountSessionError(401, "OIDC_STATE_INVALID", "OIDC state 已过期或不匹配。");
  }
  return flow;
}

function tokenResponse(value: unknown): TokenExchange {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new AccountSessionError(502, "OIDC_TOKEN_RESPONSE_INVALID", "身份提供商返回无效令牌响应。");
  }
  const record = value as Record<string, unknown>;
  const accessToken = typeof record.access_token === "string" ? record.access_token : "";
  const idToken = typeof record.id_token === "string" ? record.id_token : "";
  const refreshToken = typeof record.refresh_token === "string" ? record.refresh_token : undefined;
  const expiresIn = Number(record.expires_in);
  if (
    accessToken.length < 16
    || accessToken.length > maximumCookieValueLength
    || idToken.length < 64
    || idToken.length > 16_384
    || (refreshToken?.length ?? 0) > maximumCookieValueLength
    || !Number.isFinite(expiresIn)
    || expiresIn < 60
    || expiresIn > 24 * 60 * 60
  ) {
    throw new AccountSessionError(502, "OIDC_TOKEN_RESPONSE_INVALID", "身份提供商令牌响应缺少必要字段。");
  }
  return { accessToken, idToken, ...(refreshToken ? { refreshToken } : {}), expiresIn };
}

async function postToken(parameters: URLSearchParams): Promise<TokenExchange> {
  const configuration = oidcConfiguration();
  const response = await fetch(configuration.tokenEndpoint, {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: parameters,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10_000),
  });
  const raw = await response.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new AccountSessionError(502, "OIDC_TOKEN_RESPONSE_INVALID", "身份提供商返回非 JSON 响应。");
  }
  if (!response.ok) {
    throw new AccountSessionError(401, "OIDC_TOKEN_EXCHANGE_REJECTED", "身份提供商拒绝了令牌交换。");
  }
  return tokenResponse(parsed);
}

export async function exchangeAuthorizationCode(
  code: string,
  flow: AuthorizationFlow,
): Promise<{ tokens: TokenExchange; session: string; expiresAt: number; principal: AccountPrincipal }> {
  const configuration = oidcConfiguration();
  const tokens = await postToken(new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: configuration.redirectUri,
    client_id: configuration.clientId,
    client_secret: configuration.clientSecret,
    code_verifier: flow.verifier,
  }));
  const verified = await verifyIdToken(tokens.idToken, configuration, flow.nonce);
  const expiresAt = Math.min(
    verified.expiresAt,
    Date.now() + tokens.expiresIn * 1_000,
    Date.now() + 60 * 60_000,
  );
  const principal = principalFromClaims(verified.claims);
  const session = seal({
    version: 1,
    principal,
    accessTokenHash: hashToken(tokens.accessToken),
    issuedAt: Date.now(),
    expiresAt,
  } satisfies SealedSession);
  return { tokens, session, expiresAt, principal };
}

export async function refreshAccountSession(
  refreshToken: string,
): Promise<{ tokens: TokenExchange; session: string; expiresAt: number; principal: AccountPrincipal }> {
  const configuration = oidcConfiguration();
  const tokens = await postToken(new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
    client_id: configuration.clientId,
    client_secret: configuration.clientSecret,
  }));
  const verified = await verifyIdToken(tokens.idToken, configuration);
  const expiresAt = Math.min(
    verified.expiresAt,
    Date.now() + tokens.expiresIn * 1_000,
    Date.now() + 60 * 60_000,
  );
  const principal = principalFromClaims(verified.claims);
  return {
    tokens: { ...tokens, refreshToken: tokens.refreshToken ?? refreshToken },
    session: seal({
      version: 1,
      principal,
      accessTokenHash: hashToken(tokens.accessToken),
      issuedAt: Date.now(),
      expiresAt,
    } satisfies SealedSession),
    expiresAt,
    principal,
  };
}

function activeMembership(
  principal: AccountPrincipal,
  sealedTenant: string | undefined,
): TenantMembership {
  if (!sealedTenant) {
    return principal.memberships.find(
      (candidate) => candidate.organizationId === principal.organizationId,
    ) as TenantMembership;
  }
  const selection = unseal<{
    version: 1;
    actorId: string;
    organizationId: string;
    expiresAt: number;
    roles?: AccountRole[];
    permissions?: AccountPermission[];
  }>(sealedTenant, "TENANT_SELECTION_INVALID");
  if (
    selection.version !== 1
    || selection.expiresAt <= Date.now()
    || !safeEqual(selection.actorId, principal.actorId)
  ) {
    throw new AccountSessionError(401, "TENANT_SELECTION_EXPIRED", "租户选择已过期。");
  }
  const selected = principal.memberships.find(
    (candidate) => candidate.organizationId === selection.organizationId,
  );
  if (selected) return selected;
  const roles = (selection.roles ?? []).filter(
    (role): role is AccountRole => roleNames.includes(role),
  );
  const permissions = (selection.permissions ?? []).filter(
    (permission): permission is AccountPermission => knownPermissions.has(permission),
  );
  if (
    !organizationPattern.test(selection.organizationId)
    || roles.length === 0
    || permissions.length === 0
    || roles.length !== (selection.roles?.length ?? 0)
    || permissions.length !== (selection.permissions?.length ?? 0)
  ) {
    throw new AccountSessionError(403, "CROSS_TENANT_ACCESS_DENIED", "当前身份无权访问所选租户。");
  }
  return {
    organizationId: selection.organizationId,
    roles,
    permissions,
  };
}

export function selectTenantCookie(
  principal: AccountPrincipal,
  organizationId: string,
  expiresAt: number,
): string {
  if (!principal.memberships.some((item) => item.organizationId === organizationId)) {
    throw new AccountSessionError(403, "CROSS_TENANT_ACCESS_DENIED", "当前身份无权访问所选租户。");
  }
  return seal({
    version: 1,
    actorId: principal.actorId,
    organizationId,
    expiresAt,
  });
}

export function databaseTenantMembership(
  organizationId: string,
  memberRole: string,
): TenantMembership {
  if (!organizationPattern.test(organizationId)) {
    throw new AccountSessionError(400, "TENANT_SELECTION_INVALID", "租户选择无效。");
  }
  switch (memberRole.toUpperCase()) {
    case "OWNER":
    case "ADMIN":
      return {
        organizationId,
        roles: ["TENANT_ADMIN"],
        permissions: [...rolePermissions.TENANT_ADMIN],
      };
    case "MAINTAINER":
      return {
        organizationId,
        roles: ["MAINTAINER"],
        permissions: [...rolePermissions.MAINTAINER],
      };
    case "MEMBER":
      return {
        organizationId,
        roles: ["DEVELOPER"],
        permissions: [...rolePermissions.DEVELOPER],
      };
    case "BILLING":
      return {
        organizationId,
        roles: ["VIEWER"],
        permissions: ["workspace:view", "repository:read", "usage:read", "billing:write"],
      };
    case "VIEWER":
      return {
        organizationId,
        roles: ["VIEWER"],
        permissions: [...rolePermissions.VIEWER],
      };
    default:
      throw new AccountSessionError(403, "CROSS_TENANT_ACCESS_DENIED", "成员角色无效。");
  }
}

export function selectDatabaseTenantCookie(
  principal: AccountPrincipal,
  membership: TenantMembership,
  expiresAt: number,
): string {
  return seal({
    version: 1,
    actorId: principal.actorId,
    organizationId: membership.organizationId,
    roles: membership.roles,
    permissions: membership.permissions,
    expiresAt,
  });
}

export function trustedPublicOrigin(request: Request): string {
  const configured = process.env.ELMOS_PUBLIC_ORIGIN?.trim() ?? "";
  if (configured) {
    const parsed = new URL(configured);
    const localDevelopment = process.env.NODE_ENV !== "production"
      && ["127.0.0.1", "localhost"].includes(parsed.hostname);
    if (
      (parsed.protocol !== "https:" && !(localDevelopment && parsed.protocol === "http:"))
      || parsed.username
      || parsed.password
      || parsed.hash
      || parsed.pathname !== "/"
      || parsed.search
    ) {
      throw new AccountSessionError(
        503,
        "PUBLIC_ORIGIN_INVALID",
        "ELMOS_PUBLIC_ORIGIN 必须是无路径、无凭据的可信 HTTPS 源。",
      );
    }
    return parsed.origin;
  }
  if (process.env.NODE_ENV === "production") {
    throw new AccountSessionError(
      503,
      "PUBLIC_ORIGIN_NOT_CONFIGURED",
      "生产环境尚未配置可信公开源。",
    );
  }
  return new URL(request.url).origin;
}

export function assertSameOriginMutation(request: Request): void {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())) return;
  const expected = trustedPublicOrigin(request);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (origin !== expected || (fetchSite && fetchSite !== "same-origin")) {
    throw new AccountSessionError(403, "CSRF_ORIGIN_REJECTED", "跨站状态变更请求已被拒绝。");
  }
}

export function accountSessionFromRequest(
  request: Request,
  requiredPermission?: AccountPermission,
): {
  principal: AccountPrincipal;
  accessToken: string;
  expiresAt: number;
} {
  const cookies = cookieMap(request.headers.get("cookie"));
  const sealed = cookies.get(accountCookieNames.session) ?? "";
  const accessToken = cookies.get(accountCookieNames.accessToken) ?? "";
  if (!sealed || !accessToken) {
    throw new AccountSessionError(401, "ACCOUNT_SESSION_REQUIRED", "请先登录企业账户。");
  }
  const session = unseal<SealedSession>(sealed, "ACCOUNT_SESSION_INVALID");
  if (
    session.version !== 1
    || session.expiresAt <= Date.now()
    || !safeEqual(session.accessTokenHash, hashToken(accessToken))
  ) {
    throw new AccountSessionError(401, "ACCOUNT_SESSION_EXPIRED", "企业账户会话已过期，请重新登录。");
  }
  const selected = activeMembership(
    session.principal,
    cookies.get(accountCookieNames.tenant),
  );
  const principal = {
    ...session.principal,
    organizationId: selected.organizationId,
    roles: selected.roles,
    permissions: selected.permissions,
  };
  if (requiredPermission && !principal.permissions.includes(requiredPermission)) {
    throw new AccountSessionError(403, "ACCOUNT_PERMISSION_REQUIRED", "当前账户缺少执行此操作的权限。");
  }
  assertSameOriginMutation(request);
  return { principal, accessToken, expiresAt: session.expiresAt };
}

export function sessionCookieMaxAge(expiresAt: number): number {
  return Math.max(0, Math.floor((expiresAt - Date.now()) / 1_000));
}

export function authorizationFlowCookieMaxAge(): number {
  return 10 * 60;
}

export function accountSessionErrorResponse(error: unknown): Response {
  if (error instanceof AccountSessionError) {
    return Response.json(
      { errorCode: error.code, message: error.message, retryable: false },
      { status: error.status, headers: { "Cache-Control": "no-store, private" } },
    );
  }
  return Response.json(
    {
      errorCode: "ACCOUNT_SESSION_UNAVAILABLE",
      message: "企业账户会话服务当前不可用。",
      retryable: true,
    },
    { status: 503, headers: { "Cache-Control": "no-store, private" } },
  );
}

export async function revokeToken(token: string): Promise<boolean> {
  const configuration = oidcConfiguration();
  if (!configuration.revocationEndpoint || !token) return false;
  const response = await fetch(configuration.revocationEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      token,
      client_id: configuration.clientId,
      client_secret: configuration.clientSecret,
    }),
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) {
    throw new AccountSessionError(502, "OIDC_REVOCATION_FAILED", "身份提供商未确认令牌撤销。");
  }
  return true;
}

export function unsafeCookieValue(request: Request, name: string): string {
  return cookieMap(request.headers.get("cookie")).get(name) ?? "";
}
