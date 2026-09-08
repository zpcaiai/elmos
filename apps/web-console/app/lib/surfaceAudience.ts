/**
 * Single source of truth for which console surface belongs to which audience.
 *
 * USER  surfaces are the four customer business lines a customer reaches after
 *       /login: Spring modernization, cross-language translation, project
 *       generation, and ChinaDB SQL conversion (/migration, including
 *       /migration/sql). Nothing else is visible to a customer session.
 * ADMIN surfaces are platform operations plus every other product surface;
 *       they are only reachable after /admin/login with a verified platform
 *       administrator session.
 * PUBLIC surfaces stay reachable without any account session.
 */
export type SurfaceAudience = "PUBLIC" | "USER" | "ADMIN";

export const cendBusinessLineSurfaces = [
  "/spring",
  "/translation",
  "/generation",
  "/migration",
] as const;

export type CendBusinessLineSurface = (typeof cendBusinessLineSurfaces)[number];

export const platformOperationsSurfaces = [
  "/admin",
  "/observability",
  "/governance",
  "/commercialization",
  "/proof-loop",
  "/playground",
  "/smoke",
  // Non-business-line product surfaces: administrators only.
  "/repositories",
  "/capabilities",
  "/intake",
  "/orchestration",
  "/frontend",
  "/pricing",
  "/account",
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
