import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  AccountSessionError,
  accountSessionFromRequest,
  isPlatformAdministrator,
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
    const session = accountSessionFromRequest(
      new Request(`https://elmos.invalid${surface}`, { headers: requestHeaders }),
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
