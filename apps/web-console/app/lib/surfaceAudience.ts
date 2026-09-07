/**
 * Single source of truth for which console surface belongs to which audience.
 *
 * USER  surfaces are the product features a customer reaches after /login.
 * ADMIN surfaces are platform operations and are only reachable after
 *       /admin/login with a verified platform administrator session.
 * PUBLIC surfaces stay reachable without any account session.
 */
export type SurfaceAudience = "PUBLIC" | "USER" | "ADMIN";

export const platformOperationsSurfaces = [
  "/admin",
  "/observability",
  "/governance",
  "/commercialization",
  "/proof-loop",
  "/playground",
  "/smoke",
] as const;

export type PlatformOperationsSurface = (typeof platformOperationsSurfaces)[number];

const operationsSurfaceSet: ReadonlySet<string> = new Set(platformOperationsSurfaces);

export function isPlatformOperationsSurface(pathname: string): boolean {
  return platformOperationsSurfaces.some(
    (surface) => pathname === surface || pathname.startsWith(`${surface}/`),
  );
}

/** Only an exact, known operations surface may be used as a post-login target. */
export function safeOperationsReturnTo(candidate: string | undefined): PlatformOperationsSurface {
  if (candidate && operationsSurfaceSet.has(candidate)) {
    return candidate as PlatformOperationsSurface;
  }
  return "/admin";
}
