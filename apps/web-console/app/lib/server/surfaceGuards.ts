import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  AccountSessionError,
  accountSessionFromRequest,
  isPlatformAdministrator,
  localAccountCookieNames,
  trustedPublicOrigin,
} from "./accountSession";
import type { PlatformOperationsSurface } from "../surfaceAudience";

/**
 * Fail closed for every platform operations surface.
 *
 * A customer session created at /login never satisfies this guard: the surface
 * requires admin:read plus the verified platform administrator identity that
 * only the /admin/login entry can establish.
 */
export async function requirePlatformOperationsSurface(
  surface: PlatformOperationsSurface,
): Promise<void> {
  const requestHeaders = new Headers(await headers());
  let denialCode: string | null = null;
  try {
    const syntheticRequest = new Request(`https://elmos.invalid${surface}`, { headers: requestHeaders });
    // Only the development bootstrap needs a real loopback URL. Its validator
    // still requires both that URL and Host to match; never trust arbitrary Host.
    const temporary = (requestHeaders.get("cookie") ?? "").includes(`${localAccountCookieNames.administratorSession}=`);
    const request = temporary
      ? new Request(new URL(surface, trustedPublicOrigin(syntheticRequest)), { headers: requestHeaders })
      : syntheticRequest;
    const session = accountSessionFromRequest(
      request,
      "admin:read",
    );
    if (!isPlatformAdministrator(session.principal)) {
      denialCode = "ADMIN_EMAIL_REQUIRED";
    }
  } catch (error) {
    denialCode = error instanceof AccountSessionError
      ? error.code
      : "ADMIN_SESSION_REQUIRED";
  }
  if (denialCode) {
    redirect(`/admin/login?${new URLSearchParams({ error: denialCode, returnTo: surface })}`);
  }
}

/**
 * Read-only check for public pages that must decide whether to surface
 * administrator-only links. Never redirects and never throws.
 */
export async function hasPlatformAdministratorSession(): Promise<boolean> {
  const requestHeaders = new Headers(await headers());
  try {
    const syntheticRequest = new Request("https://elmos.invalid/", { headers: requestHeaders });
    const temporary = (requestHeaders.get("cookie") ?? "").includes(
      `${localAccountCookieNames.administratorSession}=`,
    );
    const request = temporary
      ? new Request(new URL("/", trustedPublicOrigin(syntheticRequest)), { headers: requestHeaders })
      : syntheticRequest;
    const session = accountSessionFromRequest(request, "admin:read");
    return isPlatformAdministrator(session.principal);
  } catch {
    return false;
  }
}
