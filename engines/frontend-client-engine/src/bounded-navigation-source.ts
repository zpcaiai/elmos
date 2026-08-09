import { Buffer } from "node:buffer";

import type { UiFrameworkId } from "./project-types.js";

export interface BoundedNavigationRouteSource {
  readonly id: string;
  readonly path: string;
  readonly title: string;
  readonly text: string;
  readonly requiresAuth: boolean;
  readonly deepLink: boolean;
}

export interface BoundedNavigationSemanticModel {
  readonly schemaVersion: "1.0";
  readonly profile: "bounded-navigation-v1";
  readonly projectTitle: string;
  readonly navigation: { readonly label: "主要导航" };
  readonly render: { readonly mainRole: "main"; readonly headingLevel: 1 };
  readonly fallback: { readonly strategy: "FIRST_DECLARED_ROUTE" };
  readonly routes: readonly BoundedNavigationRouteSource[];
}

export interface NavigationSourceSpec {
  readonly sourcePath: string;
  readonly entryPath: string;
  readonly parser: "TYPESCRIPT_AST" | "DART_BOUNDED_BASE64";
}

export function navigationSourceSpec(profile: UiFrameworkId): NavigationSourceSpec {
  switch (profile) {
    case "vue2":
      return { sourcePath: "src/elmos-bounded-navigation.js", entryPath: "src/main.js", parser: "TYPESCRIPT_AST" };
    case "react":
      return { sourcePath: "src/elmos-bounded-navigation.ts", entryPath: "src/main.tsx", parser: "TYPESCRIPT_AST" };
    case "react-native":
      return { sourcePath: "src/elmos-bounded-navigation.ts", entryPath: "index.ts", parser: "TYPESCRIPT_AST" };
    case "flutter":
      return { sourcePath: "lib/elmos_bounded_navigation.dart", entryPath: "lib/main.dart", parser: "DART_BOUNDED_BASE64" };
    case "harmony-arkui":
      return {
        sourcePath: "entry/src/main/ets/elmos-bounded-navigation.ets",
        entryPath: "entry/src/main/ets/pages/Index.ets",
        parser: "TYPESCRIPT_AST",
      };
    case "vue3":
    case "jquery":
    case "angular":
    case "svelte":
      return { sourcePath: "src/elmos-bounded-navigation.ts", entryPath: "src/main.ts", parser: "TYPESCRIPT_AST" };
  }
}

function tsContract(model: BoundedNavigationSemanticModel, javascript: boolean): string {
  const annotation = javascript ? "" : ": string";
  const constAssertion = javascript ? "" : " as const";
  return [
    "// Generated executable proof boundary for bounded-navigation-v1.",
    `export const ELMOS_BOUNDED_NAVIGATION = ${JSON.stringify(model, null, 2)}${constAssertion};`,
    "export const ELMOS_ROUTES = ELMOS_BOUNDED_NAVIGATION.routes;",
    "",
    `export function elmosSelectBoundedRoute(path${annotation}) {`,
    "  const selected = ELMOS_BOUNDED_NAVIGATION.routes.find(route => route.path === path);",
    "  const fallback = ELMOS_BOUNDED_NAVIGATION.routes[0];",
    '  if (!fallback) throw new Error("bounded navigation requires at least one route");',
    "  return selected ?? fallback;",
    "}",
    "",
    `export function elmosObserveBoundedRoute(path${annotation}) {`,
    "  const route = elmosSelectBoundedRoute(path);",
    "  return {",
    "    routeId: route.id, path: route.path, title: route.title, text: route.text,",
    "    requiresAuth: route.requiresAuth, deepLink: route.deepLink,",
    "    navigationLabel: ELMOS_BOUNDED_NAVIGATION.navigation.label,",
    "    mainRole: ELMOS_BOUNDED_NAVIGATION.render.mainRole,",
    "    headingLevel: ELMOS_BOUNDED_NAVIGATION.render.headingLevel,",
    "  };",
    "}",
    "",
    "export const ELMOS_INITIAL_RENDER = elmosObserveBoundedRoute(",
    "  ELMOS_BOUNDED_NAVIGATION.routes[0]?.path ?? \"/__elmos_missing_initial_route__\",",
    ");",
    "",
  ].join("\n");
}

function dartContract(model: BoundedNavigationSemanticModel): string {
  const encoded = Buffer.from(JSON.stringify(model), "utf8").toString("base64");
  return [
    "// Generated executable proof boundary for bounded-navigation-v1.",
    "import 'dart:convert';",
    "",
    `const String elmosBoundedNavigationBase64 = ${JSON.stringify(encoded)};`,
    "final Map<String, Object?> elmosBoundedNavigation =",
    "    jsonDecode(utf8.decode(base64Decode(elmosBoundedNavigationBase64))) as Map<String, Object?>;",
    "",
    "typedef ElmosBoundedRoute = Map<String, Object?>;",
    "extension ElmosBoundedRouteFields on ElmosBoundedRoute {",
    "  String get id => this['id']! as String;",
    "  String get path => this['path']! as String;",
    "  String get title => this['title']! as String;",
    "  String get text => this['text']! as String;",
    "  bool get requiresAuth => this['requiresAuth']! as bool;",
    "  bool get deepLink => this['deepLink']! as bool;",
    "}",
    "",
    "final List<Object?> elmosBoundedRoutes = elmosBoundedNavigation['routes']! as List<Object?>;",
    "ElmosBoundedRoute elmosRoute(Object? raw) => raw! as ElmosBoundedRoute;",
    "ElmosBoundedRoute get elmosFirstRoute => elmosRoute(elmosBoundedRoutes.first);",
    "",
    "ElmosBoundedRoute elmosSelectBoundedRoute(String path) {",
    "  if (elmosBoundedRoutes.isEmpty) throw StateError('bounded navigation requires at least one route');",
    "  final selected = elmosBoundedRoutes.firstWhere((raw) => elmosRoute(raw).path == path, orElse: () => elmosBoundedRoutes.first);",
    "  return elmosRoute(selected);",
    "}",
    "",
    "Map<String, Object?> elmosObserveBoundedRoute(String path) {",
    "  final route = elmosSelectBoundedRoute(path);",
    "  final navigation = elmosBoundedNavigation['navigation']! as Map<String, Object?>;",
    "  final render = elmosBoundedNavigation['render']! as Map<String, Object?>;",
    "  return <String, Object?>{",
    "    'routeId': route.id, 'path': route.path, 'title': route.title, 'text': route.text,",
    "    'requiresAuth': route.requiresAuth, 'deepLink': route.deepLink,",
    "    'navigationLabel': navigation['label'], 'mainRole': render['mainRole'],",
    "    'headingLevel': render['headingLevel'],",
    "  };",
    "}",
    "",
    "final Map<String, Object?> elmosInitialRender = elmosObserveBoundedRoute(",
    "  elmosFirstRoute.path,",
    ");",
    "",
  ].join("\n");
}

export function attachBoundedNavigationSource(
  profile: UiFrameworkId,
  model: BoundedNavigationSemanticModel,
  files: Readonly<Record<string, string>>,
): Readonly<Record<string, string>> {
  if (model.routes.length === 0) throw new Error("bounded navigation requires at least one route");
  const spec = navigationSourceSpec(profile);
  if (files[spec.entryPath] === undefined) throw new Error(`bounded navigation entry is missing: ${spec.entryPath}`);
  const source = profile === "flutter"
    ? dartContract(model)
    : tsContract(model, profile === "vue2");
  return {
    ...files,
    [spec.sourcePath]: source,
  };
}
