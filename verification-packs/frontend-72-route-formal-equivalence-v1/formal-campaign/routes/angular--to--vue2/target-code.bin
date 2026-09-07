// Generated executable proof boundary for bounded-navigation-v1.
export const ELMOS_BOUNDED_NAVIGATION = {
  "schemaVersion": "1.0",
  "profile": "bounded-navigation-v1",
  "projectTitle": "ELMOS 有界导航验证",
  "navigation": {
    "label": "主要导航"
  },
  "render": {
    "mainRole": "main",
    "headingLevel": 1
  },
  "fallback": {
    "strategy": "FIRST_DECLARED_ROUTE"
  },
  "routes": [
    {
      "id": "route.home",
      "path": "/",
      "title": "component.home",
      "text": "首页内容",
      "requiresAuth": false,
      "deepLink": true
    },
    {
      "id": "route.account",
      "path": "/account",
      "title": "component.account",
      "text": "账户内容",
      "requiresAuth": true,
      "deepLink": true
    },
    {
      "id": "route.help",
      "path": "/help",
      "title": "component.help",
      "text": "帮助内容",
      "requiresAuth": false,
      "deepLink": false
    }
  ]
};
export const ELMOS_ROUTES = ELMOS_BOUNDED_NAVIGATION.routes;

export function elmosSelectBoundedRoute(path) {
  const selected = ELMOS_BOUNDED_NAVIGATION.routes.find(route => route.path === path);
  const fallback = ELMOS_BOUNDED_NAVIGATION.routes[0];
  if (!fallback) throw new Error("bounded navigation requires at least one route");
  return selected ?? fallback;
}

export function elmosObserveBoundedRoute(path) {
  const route = elmosSelectBoundedRoute(path);
  return {
    routeId: route.id, path: route.path, title: route.title, text: route.text,
    requiresAuth: route.requiresAuth, deepLink: route.deepLink,
    navigationLabel: ELMOS_BOUNDED_NAVIGATION.navigation.label,
    mainRole: ELMOS_BOUNDED_NAVIGATION.render.mainRole,
    headingLevel: ELMOS_BOUNDED_NAVIGATION.render.headingLevel,
  };
}

export const ELMOS_INITIAL_RENDER = elmosObserveBoundedRoute(
  ELMOS_BOUNDED_NAVIGATION.routes[0]?.path ?? "/__elmos_missing_initial_route__",
);
