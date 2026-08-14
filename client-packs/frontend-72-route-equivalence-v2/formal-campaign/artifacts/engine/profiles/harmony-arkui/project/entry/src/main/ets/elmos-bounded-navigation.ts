// Direct identity projection for bounded-navigation-v1 compatibility; no second route literal is permitted.
import { ELMOS_FRONTEND_INTERACTION } from "./elmos-bounded-interaction";
export const ELMOS_BOUNDED_NAVIGATION = {
  schemaVersion: "1.0", profile: "bounded-navigation-v1",
  projectTitle: ELMOS_FRONTEND_INTERACTION.projectTitle,
  navigation: { label: ELMOS_FRONTEND_INTERACTION.navigation.label },
  render: { mainRole: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.mainRole, headingLevel: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.headingLevel },
  fallback: { strategy: ELMOS_FRONTEND_INTERACTION.navigation.fallback },
  routes: ELMOS_FRONTEND_INTERACTION.navigation.routes,
} as const;
export const ELMOS_ROUTES = ELMOS_BOUNDED_NAVIGATION.routes;

export function elmosSelectBoundedRoute(path: string) {
  const selected = ELMOS_ROUTES.find(route => route.path === path);
  const fallback = ELMOS_ROUTES[0];
  if (!fallback) throw new Error("bounded navigation requires at least one route");
  return selected ?? fallback;
}
