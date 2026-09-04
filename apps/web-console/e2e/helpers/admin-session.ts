import { createCipheriv, createHash, randomBytes } from "node:crypto";
import type { Page } from "@playwright/test";

export const administratorEmail = "zpchoney@gmail.com";

const localSessionSecret = "elmos-local-e2e-session-secret-at-least-32-characters";
const productionSessionSecret = "elmos-production-e2e-session-secret-at-least-32-characters";

function base64url(value: Buffer): string {
  return value.toString("base64url");
}

function sealedAdministratorSession(accessToken: string): string {
  const secret = process.env.ELMOS_E2E_WEB_SERVER_MODE === "production"
    ? productionSessionSecret
    : localSessionSecret;
  const key = createHash("sha256").update(secret, "utf8").digest();
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const permissions = [
    "workspace:view",
    "admin:read",
    "admin:operate",
    "admin:approve",
    "configuration:manage",
  ];
  const principal = {
    actorId: "oidc-e2e-admin",
    displayName: "ELMOS E2E Administrator",
    email: administratorEmail,
    emailVerified: true,
    isPlatformAdmin: true,
    organizationId: "tenant-operations-a",
    roles: ["APPROVER"],
    permissions,
    memberships: [{
      organizationId: "tenant-operations-a",
      roles: ["APPROVER"],
      permissions,
    }],
  };
  const plaintext = Buffer.from(JSON.stringify({
    version: 1,
    principal,
    accessTokenHash: createHash("sha256").update(accessToken, "utf8").digest("hex"),
    issuedAt: Date.now(),
    expiresAt: Date.now() + 60 * 60_000,
  }), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return `v1.${base64url(iv)}.${base64url(ciphertext)}.${base64url(cipher.getAuthTag())}`;
}

/**
 * Installs a self-attested browser fixture session for UI-only E2E tests.
 * It is not OIDC evidence and must never be used as certification evidence.
 */
export async function installAdministratorSession(page: Page): Promise<void> {
  const accessToken = "e2e-admin-access-token-not-a-provider-credential";
  const session = sealedAdministratorSession(accessToken);
  await page.setExtraHTTPHeaders({
    Cookie: `__Host-elmos_session=${session}; __Host-elmos_access_token=${accessToken}`,
  });
}
