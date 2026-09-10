/**
 * @file router-ir-types.ts
 * @description Universal Router IR Contracts for cross-platform navigation migration.
 * Models route trees, nested layouts, dynamic path segments, route guards,
 * deep linking schemes, and framework-specific navigation adapters.
 * Conforms to Batch 32 Skill 1207 (b32-route-navigation-deeplink).
 */

export type RouteFramework =
  | 'nextjs-app-router'
  | 'react-router'
  | 'vue-router'
  | 'miniapp-router'
  | 'universal';

export type RouteSegmentKind =
  | 'static'
  | 'dynamic'           // :id or [id]
  | 'catch-all'         // * or [...slug]
  | 'optional-catch-all'// [[...slug]]
  | 'route-group';      // (marketing)

export interface RouteParamDescriptor {
  name: string;
  kind: RouteSegmentKind;
  type?: 'string' | 'number' | 'uuid';
  optional?: boolean;
}

export interface RouteGuardIR {
  name: string;
  type: 'auth' | 'role' | 'permission' | 'data-preload' | 'custom';
  redirectOnFailure?: string;
  requiredRoles?: string[];
  guardFunctionCode?: string;
}

export interface RouteNodeIR {
  id: string;
  path: string;              // relative segment, e.g. "users" or ":userId"
  fullPath: string;          // absolute path from root, e.g. "/users/:userId"
  segmentKind: RouteSegmentKind;
  componentIdentifier: string;
  layoutIdentifier?: string;
  loadingIdentifier?: string;
  errorIdentifier?: string;
  notFoundIdentifier?: string;
  params: RouteParamDescriptor[];
  queryParams?: string[];
  guards: RouteGuardIR[];
  children: RouteNodeIR[];
  isIndex?: boolean;
  isLazy?: boolean;
  meta?: Record<string, unknown>;
}

export interface DeepLinkConfigIR {
  scheme: string;            // e.g. "myapp://"
  host?: string;             // e.g. "app.example.com"
  pathMappings: Record<string, string>; // e.g. { "/profile/:id": "pages/profile/index?id=:id" }
}

export interface UniversalRouterIR {
  routerId: string;
  sourceFramework: RouteFramework;
  routes: RouteNodeIR[];
  notFoundRoute?: RouteNodeIR;
  deepLink?: DeepLinkConfigIR;
  basePath?: string;
  metadata?: Record<string, unknown>;
}

export interface RouterParseResult {
  success: boolean;
  routerIR?: UniversalRouterIR;
  errors: string[];
  warnings: string[];
  discoveredFramework: RouteFramework;
}

export interface RouterEmitResult {
  files: Array<{
    filePath: string;
    content: string;
    role: 'router-config' | 'page-component' | 'layout-component' | 'navigation-hook';
  }>;
  framework: RouteFramework;
  dependencies: Array<{ name: string; version: string; isDev: boolean }>;
  notes: string[];
}
