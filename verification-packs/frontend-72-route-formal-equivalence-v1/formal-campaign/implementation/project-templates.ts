import type {
  ExactUiTargetProfile,
  UiIrComponent,
  UiIrRoute,
  UiProjectGenerationRequest,
} from "./project-types.js";

export interface ProjectTemplateContext {
  readonly request: UiProjectGenerationRequest;
  readonly profile: ExactUiTargetProfile;
  readonly safeProjectName: string;
  readonly routes: ReadonlyArray<UiIrRoute & { readonly title: string; readonly text: string }>;
}

function lines(...values: readonly string[]): string {
  return `${values.join("\n")}\n`;
}

function json(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function html(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function js(value: unknown): string {
  return JSON.stringify(value);
}

function commonWebFiles(context: ProjectTemplateContext): Record<string, string> {
  return {
    "index.html": lines(
      "<!doctype html>",
      '<html lang="zh-CN">',
      "  <head>",
      '    <meta charset="UTF-8" />',
      '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
      `    <title>${html(context.request.title)}</title>`,
      "  </head>",
      '  <body><div id="app"></div><script type="module" src="/src/main.ts"></script></body>',
      "</html>",
    ),
    "src/styles.css": lines(
      ":root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }",
      "* { box-sizing: border-box; }",
      "body { margin: 0; min-width: 320px; background: #f5f7fb; color: #172033; }",
      "a { color: inherit; }",
      ".shell { min-height: 100vh; display: grid; grid-template-columns: minmax(14rem, 20rem) 1fr; }",
      ".nav { padding: 1.5rem; background: #15223d; color: #fff; }",
      ".nav a { display: block; padding: .7rem .8rem; margin: .25rem 0; border-radius: .6rem; }",
      ".nav a:focus-visible { outline: 3px solid #fbbf24; outline-offset: 2px; }",
      ".content { padding: clamp(1.25rem, 4vw, 4rem); }",
      ".card { max-width: 52rem; padding: 2rem; border-radius: 1rem; background: #fff; color: #172033; box-shadow: 0 1rem 3rem #17203318; }",
      ".status { display: inline-block; margin-top: 1rem; padding: .4rem .65rem; border-radius: 999px; background: #fff4ce; color: #6b4f00; }",
      "@media (max-width: 720px) { .shell { grid-template-columns: 1fr; } .nav { position: static; } }",
      "@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; } }",
    ),
  };
}

function packageJson(
  context: ProjectTemplateContext,
  scripts: Readonly<Record<string, string>>,
  dependencies: Readonly<Record<string, string>>,
  devDependencies: Readonly<Record<string, string>>,
): string {
  return json({
    name: context.safeProjectName,
    version: "0.1.0",
    private: true,
    type: "module",
    engines: { node: context.profile.nodeVersion ?? context.profile.runtimeVersion },
    packageManager: `${context.profile.packageManager}@${context.profile.packageManagerVersion}`,
    scripts,
    dependencies,
    devDependencies,
  });
}

function viteTypeScriptConfig(exactOptionalPropertyTypes = true): string {
  return json({
    compilerOptions: {
      target: "ES2022",
      useDefineForClassFields: true,
      module: "ESNext",
      moduleResolution: "Bundler",
      strict: true,
      noUncheckedIndexedAccess: true,
      exactOptionalPropertyTypes,
      resolveJsonModule: true,
      isolatedModules: true,
      noEmit: true,
      jsx: "react-jsx",
      types: ["vite/client"],
      lib: ["ES2022", "DOM", "DOM.Iterable"],
    },
    include: ["src"],
  });
}

function routeTest(context: ProjectTemplateContext, importPath = "./routes"): string {
  return lines(
    'import { describe, expect, it } from "vitest";',
    `import { routes } from ${js(importPath)};`,
    "",
    'describe("generated UI route contract", () => {',
    `  it("preserves every declared route", () => expect(routes).toHaveLength(${context.routes.length}));`,
    '  it("keeps route paths unique", () => expect(new Set(routes.map(route => route.path)).size).toBe(routes.length));',
    "});",
  );
}

function reactTemplate(context: ProjectTemplateContext): Record<string, string> {
  const web = commonWebFiles(context);
  web["index.html"] = web["index.html"]!.replace("/src/main.ts", "/src/main.tsx");
  return {
    ...web,
    "package.json": packageJson(
      context,
      { dev: "vite", build: "tsc -b && vite build", test: "vitest run" },
      {
        react: "19.2.8",
        "react-dom": "19.2.8",
        "react-router-dom": "7.18.1",
      },
      {
        "@types/react": "19.2.17",
        "@types/react-dom": "19.2.3",
        "@vitejs/plugin-react": "6.0.4",
        typescript: "7.0.2",
        vite: "8.1.5",
        vitest: "4.1.10",
      },
    ),
    "tsconfig.json": viteTypeScriptConfig(),
    "vite.config.ts": lines(
      'import { defineConfig } from "vite";',
      'import react from "@vitejs/plugin-react";',
      "export default defineConfig({ plugins: [react()] });",
    ),
    "src/routes.ts": lines(
      'import { ELMOS_ROUTES } from "./elmos-bounded-navigation";',
      "export type GeneratedRoute = (typeof ELMOS_ROUTES)[number];",
      "export const routes = ELMOS_ROUTES;",
    ),
    "src/App.tsx": lines(
      'import { NavLink, Navigate, Route, Routes } from "react-router-dom";',
      'import { routes, type GeneratedRoute } from "./routes";',
      'import "./styles.css";',
      "",
      "function GeneratedPage({ route }: { readonly route: GeneratedRoute }) {",
      '  return <main className="content" id="main" data-route-id={route.id} data-route-path={route.path} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink}><article className="card">',
      "    <h1>{route.title}</h1><p>{route.text}</p>",
      '    <p className="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>',
      "  </article></main>;",
      "}",
      "",
      "export function App() {",
      '  return <div className="shell">',
      '    <nav className="nav" aria-label="主要导航"><strong>' + html(context.request.title) + "</strong>",
      '      {routes.map(route => <NavLink key={route.id} to={route.path} data-route-id={route.id} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink}>{route.title}</NavLink>)}',
      "    </nav>",
      "    <Routes>",
      "      {routes.map(route => <Route key={route.id} path={route.path} element={<GeneratedPage route={route} />} />)}",
      '      <Route path="*" element={<Navigate to={routes[0]?.path ?? "/"} replace />} />',
      "    </Routes>",
      "  </div>;",
      "}",
    ),
    "src/main.tsx": lines(
      'import { StrictMode } from "react";',
      'import { createRoot } from "react-dom/client";',
      'import { BrowserRouter } from "react-router-dom";',
      'import { App } from "./App";',
      'const root = document.getElementById("app");',
      'if (!root) throw new Error("application root is missing");',
      "createRoot(root).render(<StrictMode><BrowserRouter><App /></BrowserRouter></StrictMode>);",
    ),
    "src/routes.test.ts": routeTest(context),
  };
}

function vue3Template(context: ProjectTemplateContext): Record<string, string> {
  const base = commonWebFiles(context);
  base["index.html"] = base["index.html"]!.replace("/src/main.ts", "/src/main.ts");
  return {
    ...base,
    "package.json": packageJson(
      context,
      { dev: "vite", build: "vue-tsc --noEmit && vite build", test: "vitest run" },
      { pinia: "4.0.2", vue: "3.5.40", "vue-router": "4.6.4" },
      {
        "@vitejs/plugin-vue": "6.0.8",
        typescript: "6.0.3",
        vite: "8.1.5",
        vitest: "4.1.10",
        "vue-tsc": "3.2.5",
      },
    ),
    "tsconfig.json": viteTypeScriptConfig(false),
    "vite.config.ts": lines(
      'import { defineConfig } from "vite";',
      'import vue from "@vitejs/plugin-vue";',
      "export default defineConfig({ plugins: [vue()] });",
    ),
    "src/routes.ts": lines(
      'import { ELMOS_ROUTES } from "./elmos-bounded-navigation";',
      "export const routes = ELMOS_ROUTES;",
    ),
    "src/router.ts": lines(
      'import { createRouter, createWebHistory } from "vue-router";',
      'import GeneratedPage from "./views/GeneratedPage.vue";',
      'import { routes } from "./routes";',
      "const generatedRoutes = routes.map(route => ({ path: route.path, component: GeneratedPage, meta: { generatedRoute: route } }));",
      "export const router = createRouter({",
      "  history: createWebHistory(),",
      '  routes: [...generatedRoutes, { path: "/:pathMatch(.*)*", redirect: routes[0]?.path ?? "/" }],',
      "});",
    ),
    "src/views/GeneratedPage.vue": lines(
      '<script setup lang="ts">',
      'import { computed } from "vue";',
      'import { useRoute } from "vue-router";',
      'import { routes } from "../routes";',
      "const current = useRoute();",
      "const page = computed(() => routes.find(route => route.path === current.path) ?? routes[0]);",
      "</script>",
      '<template><main class="content" id="main" :data-route-id="page?.id" :data-route-path="page?.path" :data-requires-auth="page?.requiresAuth" :data-deep-link="page?.deepLink"><article class="card">',
      "  <h1>{{ page?.title }}</h1><p>{{ page?.text }}</p>",
      "  <p class=\"status\" role=\"status\">生成状态：等待真实浏览器与可访问性验证</p>",
      "</article></main></template>",
    ),
    "src/App.vue": lines(
      '<script setup lang="ts">import { routes } from "./routes";</script>',
      '<template><div class="shell"><nav class="nav" aria-label="主要导航">',
      `  <strong>${html(context.request.title)}</strong>`,
      '  <RouterLink v-for="route in routes" :key="route.id" :to="route.path" :data-route-id="route.id" :data-requires-auth="route.requiresAuth" :data-deep-link="route.deepLink">{{ route.title }}</RouterLink>',
      "</nav><RouterView /></div></template>",
    ),
    "src/main.ts": lines(
      'import { createApp } from "vue";',
      'import { createPinia } from "pinia";',
      'import App from "./App.vue";',
      'import { router } from "./router";',
      'import "./styles.css";',
      "createApp(App).use(createPinia()).use(router).mount(\"#app\");",
    ),
    "src/routes.test.ts": routeTest(context),
  };
}

function vue2Template(context: ProjectTemplateContext): Record<string, string> {
  const web = commonWebFiles(context);
  web["index.html"] = web["index.html"]!.replace("/src/main.ts", "/src/main.js");
  return {
    ...web,
    "package.json": packageJson(
      context,
      { dev: "vite", build: "vite build", test: "vitest run" },
      { vue: "2.7.16", "vue-router": "3.6.5" },
      {
        "@vitejs/plugin-vue2": "2.3.4",
        vite: "7.3.6",
        vitest: "4.1.10",
      },
    ),
    "vite.config.js": lines(
      'import { defineConfig } from "vite";',
      'import vue from "@vitejs/plugin-vue2";',
      "export default defineConfig({ plugins: [vue()] });",
    ),
    "src/routes.js": lines(
      'import { ELMOS_ROUTES } from "./elmos-bounded-navigation";',
      "export const routes = ELMOS_ROUTES;",
    ),
    "src/router.js": lines(
      'import Vue from "vue";',
      'import VueRouter from "vue-router";',
      'import GeneratedPage from "./views/GeneratedPage.vue";',
      'import { routes } from "./routes";',
      "Vue.use(VueRouter);",
      "const generatedRoutes = routes.map(route => ({ path: route.path, component: GeneratedPage, meta: { generatedRoute: route } }));",
      'export const router = new VueRouter({ mode: "history", routes: [...generatedRoutes, { path: "*", redirect: routes[0]?.path ?? "/" }] });',
    ),
    "src/views/GeneratedPage.vue": lines(
      "<script>",
      'import { routes } from "../routes";',
      "export default { computed: { page() { return routes.find(route => route.path === this.$route.path) || routes[0]; } } };",
      "</script>",
      `<template><main class="content" id="main" :data-route-id="page && page.id" :data-route-path="page && page.path" :data-requires-auth="page && page.requiresAuth ? 'true' : 'false'" :data-deep-link="page && page.deepLink ? 'true' : 'false'"><article class="card">`,
      "  <h1>{{ page && page.title }}</h1><p>{{ page && page.text }}</p>",
      "  <p class=\"status\" role=\"status\">生成状态：等待真实浏览器与可访问性验证</p>",
      "</article></main></template>",
    ),
    "src/App.vue": lines(
      "<script>",
      'import { routes } from "./routes";',
      "export default { data: () => ({ routes }) };",
      "</script>",
      '<template><div class="shell"><nav class="nav" aria-label="主要导航">',
      `  <strong>${html(context.request.title)}</strong>`,
      `  <RouterLink v-for="route in routes" :key="route.id" :to="route.path" :data-route-id="route.id" :data-requires-auth="route.requiresAuth ? 'true' : 'false'" :data-deep-link="route.deepLink ? 'true' : 'false'">{{ route.title }}</RouterLink>`,
      "</nav><RouterView /></div></template>",
    ),
    "src/main.js": lines(
      'import Vue from "vue";',
      'import App from "./App.vue";',
      'import { router } from "./router";',
      'import "./styles.css";',
      "Vue.config.productionTip = false;",
      'new Vue({ router, render: create => create(App) }).$mount("#app");',
    ),
    "src/routes.test.js": routeTest(context),
  };
}

function jqueryTemplate(context: ProjectTemplateContext): Record<string, string> {
  return {
    ...commonWebFiles(context),
    "package.json": packageJson(
      context,
      { dev: "vite", build: "tsc -b && vite build", test: "vitest run" },
      { jquery: "4.0.0" },
      {
        "@types/jquery": "4.0.1",
        typescript: "7.0.2",
        vite: "8.1.5",
        vitest: "4.1.10",
      },
    ),
    "tsconfig.json": viteTypeScriptConfig(),
    "vite.config.ts": lines('import { defineConfig } from "vite";', "export default defineConfig({});"),
    "src/routes.ts": lines(
      'import { ELMOS_ROUTES } from "./elmos-bounded-navigation";',
      "export const routes = ELMOS_ROUTES;",
    ),
    "src/main.ts": lines(
      'import $ from "jquery";',
      'import { routes } from "./routes";',
      'import "./styles.css";',
      "",
      "function render(path: string): void {",
      "  const route = routes.find(candidate => candidate.path === path) ?? routes[0];",
      '  if (!route) throw new Error("at least one route is required");',
      '  const article = document.createElement("article");',
      '  article.className = "card";',
      '  $("<h1>").text(route.title).appendTo(article);',
      '  $("<p>").text(route.text).appendTo(article);',
      '  $("<p>", { class: "status", role: "status" }).text("生成状态：等待真实浏览器与可访问性验证").appendTo(article);',
      '  $("#main").attr({ "data-route-id": route.id, "data-route-path": route.path, "data-requires-auth": String(route.requiresAuth), "data-deep-link": String(route.deepLink) }).empty().append(article);',
      "}",
      "",
      'const nav = $("<nav>", { class: "nav", "aria-label": "主要导航" }).append($("<strong>").text(' + js(context.request.title) + "));",
      'for (const route of routes) nav.append($("<a>", { href: route.path, "data-route-id": route.id, "data-requires-auth": String(route.requiresAuth), "data-deep-link": String(route.deepLink) }).text(route.title));',
      'const shell = $("<div>", { class: "shell" }).append(nav, $("<main>", { id: "main", class: "content" }));',
      '$("body").empty().append(shell);',
      'nav.on("click", "a", event => { event.preventDefault(); const path = $(event.currentTarget).attr("href") ?? "/"; history.pushState({}, "", path); render(path); });',
      'window.addEventListener("popstate", () => render(window.location.pathname));',
      "render(window.location.pathname);",
    ),
    "src/routes.test.ts": routeTest(context),
  };
}

function svelteTemplate(context: ProjectTemplateContext): Record<string, string> {
  return {
    ...commonWebFiles(context),
    "package.json": packageJson(
      context,
      { dev: "vite", build: "svelte-check && vite build", test: "vitest run" },
      { svelte: "5.56.8" },
      {
        "@sveltejs/vite-plugin-svelte": "7.2.0",
        "svelte-check": "4.4.5",
        typescript: "6.0.3",
        vite: "8.1.5",
        vitest: "4.1.10",
      },
    ),
    "tsconfig.json": viteTypeScriptConfig(),
    "svelte.config.js": lines(
      'import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";',
      "export default { preprocess: vitePreprocess() };",
    ),
    "vite.config.ts": lines(
      'import { defineConfig } from "vite";',
      'import { svelte } from "@sveltejs/vite-plugin-svelte";',
      "export default defineConfig({ plugins: [svelte()] });",
    ),
    "src/routes.ts": lines(
      'import { ELMOS_ROUTES } from "./elmos-bounded-navigation";',
      "export const routes = ELMOS_ROUTES;",
    ),
    "src/App.svelte": lines(
      '<script lang="ts">',
      '  import { onMount } from "svelte";',
      '  import { routes } from "./routes";',
      "  let path = window.location.pathname;",
      "  let page = routes.find(route => route.path === path) ?? routes[0];",
      "  function navigate(event: MouseEvent, next: string) { event.preventDefault(); history.pushState({}, \"\", next); path = next; page = routes.find(route => route.path === path) ?? routes[0]; }",
      "  onMount(() => { const listener = () => { path = window.location.pathname; page = routes.find(route => route.path === path) ?? routes[0]; }; window.addEventListener(\"popstate\", listener); return () => window.removeEventListener(\"popstate\", listener); });",
      "</script>",
      '<div class="shell"><nav class="nav" aria-label="主要导航">',
      `  <strong>${html(context.request.title)}</strong>`,
      '  {#each routes as route}<a data-route-id={route.id} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink} href={route.path} onclick={(event) => navigate(event, route.path)}>{route.title}</a>{/each}',
      '</nav><main class="content" id="main" data-route-id={page?.id} data-route-path={page?.path} data-requires-auth={page?.requiresAuth} data-deep-link={page?.deepLink}><article class="card">',
      "  <h1>{page?.title}</h1><p>{page?.text}</p>",
      '  <p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>',
      "</article></main></div>",
    ),
    "src/main.ts": lines(
      'import { mount } from "svelte";',
      'import App from "./App.svelte";',
      'import "./styles.css";',
      'const target = document.getElementById("app");',
      'if (!target) throw new Error("application root is missing");',
      "mount(App, { target });",
    ),
    "src/routes.test.ts": routeTest(context),
  };
}

function angularTemplate(context: ProjectTemplateContext): Record<string, string> {
  return {
    "package.json": packageJson(
      context,
      { start: "ng serve", build: "ng build", test: "ng build --configuration development" },
      {
        "@angular/common": "22.0.8",
        "@angular/compiler": "22.0.8",
        "@angular/core": "22.0.8",
        "@angular/platform-browser": "22.0.8",
        "@angular/router": "22.0.8",
        rxjs: "7.8.2",
        tslib: "2.8.1",
        "zone.js": "0.16.2",
      },
      {
        "@angular/build": "22.0.8",
        "@angular/cli": "22.0.8",
        "@angular/compiler-cli": "22.0.8",
        typescript: "6.0.3",
      },
    ),
    "angular.json": json({
      $schema: "./node_modules/@angular/cli/lib/config/schema.json",
      version: 1,
      newProjectRoot: "projects",
      projects: {
        [context.safeProjectName]: {
          projectType: "application",
          root: "",
          sourceRoot: "src",
          prefix: "app",
          architect: {
            build: {
              builder: "@angular/build:application",
              options: {
                outputPath: `dist/${context.safeProjectName}`,
                index: "src/index.html",
                browser: "src/main.ts",
                tsConfig: "tsconfig.app.json",
                styles: ["src/styles.css"],
              },
              configurations: {
                production: {
                  budgets: [
                    { type: "initial", maximumWarning: "500kB", maximumError: "1MB" },
                    { type: "anyComponentStyle", maximumWarning: "4kB", maximumError: "8kB" },
                  ],
                  outputHashing: "all",
                },
                development: {
                  optimization: false,
                  extractLicenses: false,
                  sourceMap: true,
                },
              },
              defaultConfiguration: "production",
            },
            serve: {
              builder: "@angular/build:dev-server",
              configurations: {
                production: { buildTarget: `${context.safeProjectName}:build:production` },
                development: { buildTarget: `${context.safeProjectName}:build:development` },
              },
              defaultConfiguration: "development",
            },
          },
        },
      },
    }),
    "tsconfig.json": json({
      compilerOptions: {
        target: "ES2022",
        useDefineForClassFields: false,
        strict: true,
        noImplicitOverride: true,
        noPropertyAccessFromIndexSignature: true,
        noImplicitReturns: true,
        noFallthroughCasesInSwitch: true,
        skipLibCheck: true,
        isolatedModules: true,
        experimentalDecorators: true,
        importHelpers: true,
        module: "preserve",
        moduleResolution: "bundler",
      },
      angularCompilerOptions: {
        strictInjectionParameters: true,
        strictInputAccessModifiers: true,
        strictTemplates: true,
      },
    }),
    "tsconfig.app.json": json({ extends: "./tsconfig.json", compilerOptions: { outDir: "./out-tsc/app" }, files: ["src/main.ts"] }),
    "src/index.html": lines(
      "<!doctype html>",
      '<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
      `<title>${html(context.request.title)}</title></head><body><app-root></app-root></body></html>`,
    ),
    "src/routes.ts": lines(
      'import type { Routes } from "@angular/router";',
      'import { GeneratedPageComponent } from "./app/generated-page.component";',
      'import { ELMOS_ROUTES } from "./elmos-bounded-navigation";',
      "const generatedRoutes: Routes = ELMOS_ROUTES.map(route => ({ path: route.path.replace(/^\\//, \"\"), component: GeneratedPageComponent, data: route }));",
      'export const routes: Routes = [...generatedRoutes, { path: "**", redirectTo: ELMOS_ROUTES[0]?.path.replace(/^\\//, "") ?? "" }];',
    ),
    "src/app/generated-page.component.ts": lines(
      'import { Component } from "@angular/core";',
      'import { ActivatedRoute } from "@angular/router";',
      "@Component({",
      "  standalone: true,",
      '  selector: "app-generated-page",',
      '  template: `<main class="content" id="main" [attr.data-route-id]="id" [attr.data-route-path]="path" [attr.data-requires-auth]="requiresAuth" [attr.data-deep-link]="deepLink"><article class="card"><h1>{{ title }}</h1><p>{{ text }}</p><p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p></article></main>`,',
      "})",
      "export class GeneratedPageComponent {",
      '  readonly id = String(this.route.snapshot.data["id"] ?? "");',
      '  readonly path = String(this.route.snapshot.data["path"] ?? "");',
      '  readonly title = String(this.route.snapshot.data["title"] ?? "");',
      '  readonly text = String(this.route.snapshot.data["text"] ?? "");',
      '  readonly requiresAuth = Boolean(this.route.snapshot.data["requiresAuth"]);',
      '  readonly deepLink = Boolean(this.route.snapshot.data["deepLink"]);',
      "  constructor(private readonly route: ActivatedRoute) {}",
      "}",
    ),
    "src/app/app.component.ts": lines(
      'import { Component } from "@angular/core";',
      'import { RouterLink, RouterOutlet } from "@angular/router";',
      'import { ELMOS_ROUTES } from "../elmos-bounded-navigation";',
      "@Component({",
      "  standalone: true, selector: \"app-root\", imports: [RouterLink, RouterOutlet],",
      '  template: `<div class="shell"><nav class="nav" aria-label="主要导航"><strong>' + html(context.request.title) + '</strong>@for (route of routes; track route.id) {<a [routerLink]="route.path" [attr.data-route-id]="route.id" [attr.data-requires-auth]="route.requiresAuth" [attr.data-deep-link]="route.deepLink">{{ route.title }}</a>}</nav><router-outlet /></div>`,',
      "})",
      "export class AppComponent { readonly routes = ELMOS_ROUTES; }",
    ),
    "src/main.ts": lines(
      'import { bootstrapApplication } from "@angular/platform-browser";',
      'import { provideRouter } from "@angular/router";',
      'import { AppComponent } from "./app/app.component";',
      'import { routes } from "./routes";',
      "bootstrapApplication(AppComponent, { providers: [provideRouter(routes)] }).catch(error => console.error(error));",
    ),
    "src/styles.css": commonWebFiles(context)["src/styles.css"]!,
  };
}

function reactNativeTemplate(context: ProjectTemplateContext): Record<string, string> {
  const screenNames = context.routes.map((route, index) => ({
    ...route,
    screen: `Screen${index + 1}`,
  }));
  const routeTypeEntries = screenNames.map(route => `  readonly ${js(route.screen)}: GeneratedScreenParams;`);
  return {
    "package.json": packageJson(
      context,
      {
        start: "expo start",
        android: "expo run:android",
        ios: "expo run:ios",
        web: "expo start --web",
        "export:web": "expo export --platform web",
        typecheck: "tsc --noEmit",
      },
      {
        "@expo/metro-runtime": "57.0.7",
        "@react-navigation/native": "7.3.14",
        "@react-navigation/native-stack": "7.18.6",
        expo: "57.0.8",
        "expo-status-bar": "57.0.1",
        react: "19.2.3",
        "react-dom": "19.2.3",
        "react-native": "0.86.0",
        "react-native-safe-area-context": "5.8.0",
        "react-native-screens": "4.26.2",
        "react-native-web": "0.21.2",
      },
      {
        "@types/react": "19.2.2",
        typescript: "6.0.3",
      },
    ),
    "app.json": json({
      expo: {
        name: context.request.title,
        slug: context.safeProjectName,
        version: "0.1.0",
        orientation: "default",
        userInterfaceStyle: "automatic",
        scheme: context.safeProjectName,
        ios: { bundleIdentifier: context.request.bundleId, supportsTablet: true },
        android: { package: context.request.bundleId },
        web: { bundler: "metro" },
      },
    }),
    "tsconfig.json": json({ extends: "expo/tsconfig.base", compilerOptions: { strict: true, noUncheckedIndexedAccess: true } }),
    "index.ts": lines(
      'import { registerRootComponent } from "expo";',
      'import { App } from "./App";',
      "registerRootComponent(App);",
    ),
    "src/navigation.tsx": lines(
      'import { NavigationContainer, type LinkingOptions } from "@react-navigation/native";',
      'import { createNativeStackNavigator } from "@react-navigation/native-stack";',
      'import { ScrollView, StyleSheet, Text, View } from "react-native";',
      'import { ELMOS_ROUTES, elmosSelectBoundedRoute } from "./elmos-bounded-navigation";',
      "",
      "export interface GeneratedScreenParams {",
      "  readonly id: string; readonly path: string; readonly title: string; readonly text: string;",
      "  readonly requiresAuth: boolean; readonly deepLink: boolean;",
      "}",
      "export type RootStackParamList = {",
      ...routeTypeEntries,
      "};",
      "function generatedScreenName(index: number): keyof RootStackParamList { return `Screen${index + 1}` as keyof RootStackParamList; }",
      "function resolveGeneratedScreen(path: string): keyof RootStackParamList {",
      "  const selected = elmosSelectBoundedRoute(path);",
      "  const index = ELMOS_ROUTES.findIndex(route => route === selected);",
      '  if (index < 0) throw new Error("selected bounded route has no generated screen");',
      "  return generatedScreenName(index);",
      "}",
      "const Stack = createNativeStackNavigator<RootStackParamList>();",
      "interface GeneratedProps { readonly route: { readonly params: GeneratedScreenParams } }",
      "function GeneratedScreen({ route }: GeneratedProps) {",
      '  return <ScrollView contentContainerStyle={styles.content}><View accessible accessibilityRole="summary" accessibilityLabel={`${route.params.id}|${route.params.path}|auth:${route.params.requiresAuth}|deep:${route.params.deepLink}`}>',
      '    <Text accessibilityRole="header" style={styles.title}>{route.params.title}</Text>',
      "    <Text style={styles.body}>{route.params.text}</Text>",
      '    <Text accessibilityLiveRegion="polite" style={styles.status}>生成状态：等待 Android/iOS 设备验证</Text>',
      "  </View></ScrollView>;",
      "}",
      `const linking: LinkingOptions<RootStackParamList> = { prefixes: [${js(`${context.safeProjectName}://`)}], config: { screens: Object.fromEntries(ELMOS_ROUTES.map((route, index) => [generatedScreenName(index), route.path.replace(/^\\//, "") || "home"])) } };`,
      'export function GeneratedNavigation({ requestedPath = "/__elmos_initial__" }: { readonly requestedPath?: string } = {}) {',
      "  const initialScreen = resolveGeneratedScreen(requestedPath);",
      "  return <NavigationContainer linking={linking}><Stack.Navigator initialRouteName={initialScreen}>",
      "    {ELMOS_ROUTES.map((route, index) => <Stack.Screen key={route.id} name={generatedScreenName(index)} component={GeneratedScreen} initialParams={{ id: route.id, path: route.path, title: route.title, text: route.text, requiresAuth: route.requiresAuth, deepLink: route.deepLink }} />)}",
      "  </Stack.Navigator></NavigationContainer>;",
      "}",
      "const styles = StyleSheet.create({ content: { flexGrow: 1, padding: 24, justifyContent: \"center\", backgroundColor: \"#f5f7fb\" }, title: { fontSize: 30, fontWeight: \"700\", color: \"#172033\" }, body: { marginTop: 12, fontSize: 18, color: \"#334155\" }, status: { marginTop: 20, color: \"#6b4f00\" } });",
    ),
    "App.tsx": lines(
      'import { StatusBar } from "expo-status-bar";',
      'import { GeneratedNavigation } from "./src/navigation";',
      'export function App() { return <><GeneratedNavigation /><StatusBar style="auto" /></>; }',
      "export default App;",
    ),
  };
}

function flutterTemplate(context: ProjectTemplateContext): Record<string, string> {
  return {
    "pubspec.yaml": lines(
      `name: ${context.safeProjectName.replaceAll("-", "_")}`,
      "description: Generated by the ELMOS UI project generator.",
      "publish_to: none",
      "version: 0.1.0+1",
      "environment:",
      "  sdk: 3.12.1",
      "dependencies:",
      "  flutter:",
      "    sdk: flutter",
      "dev_dependencies:",
      "  flutter_test:",
      "    sdk: flutter",
      "  flutter_lints: 6.0.0",
      "flutter:",
      "  uses-material-design: true",
      "  assets:",
      "    - assets/ui_ir.json",
    ),
    "analysis_options.yaml": lines(
      "include: package:flutter_lints/flutter.yaml",
      "analyzer:",
      "  language:",
      "    strict-casts: true",
      "    strict-inference: true",
      "    strict-raw-types: true",
      "linter:",
      "  rules:",
      "    avoid_dynamic_calls: true",
      "    use_build_context_synchronously: true",
    ),
    "assets/ui_ir.json": json(context.request.uiIr),
    "lib/main.dart": lines(
      "import 'package:flutter/material.dart';",
      "import 'elmos_bounded_navigation.dart';",
      "",
      "void main() => runApp(const GeneratedApp());",
      "",
      "class GeneratedApp extends StatelessWidget {",
      "  const GeneratedApp({super.key});",
      "  @override",
      "  Widget build(BuildContext context) {",
      `    return MaterialApp(title: ${js(context.request.title)}, initialRoute: elmosFirstRoute.path,`,
      "      routes: { for (final raw in elmosBoundedRoutes) elmosRoute(raw).path: (_) => GeneratedPage(route: elmosRoute(raw)) },",
      "      onUnknownRoute: (_) => MaterialPageRoute<void>(builder: (_) => GeneratedPage(route: elmosFirstRoute)));",
      "  }",
      "}",
      "",
      "class GeneratedPage extends StatelessWidget {",
      "  const GeneratedPage({required this.route, super.key});",
      "  final ElmosBoundedRoute route;",
      "  @override",
      "  Widget build(BuildContext context) {",
      "    return Scaffold(",
      "      appBar: AppBar(title: Text(route.title)),",
      "      drawer: Drawer(",
      "        child: SafeArea(",
      "          child: ListView(",
      "            children: [",
      "              for (final raw in elmosBoundedRoutes)",
      "                ListTile(",
      "                  title: Text(elmosRoute(raw).title),",
      "                  onTap: () => Navigator.of(context).pushReplacementNamed(elmosRoute(raw).path),",
      "                ),",
      "            ],",
      "          ),",
      "        ),",
      "      ),",
      "      body: Center(",
      "        child: Semantics(",
      "          container: true,",
      "          header: true,",
      "          label: '${route.id}|${route.path}|auth:${route.requiresAuth}|deep:${route.deepLink}',",
      "          child: Card(",
      "            child: Padding(",
      "              padding: const EdgeInsets.all(24),",
      "              child: Column(",
      "                mainAxisSize: MainAxisSize.min,",
      "                children: [",
      "                  Text(route.title, style: Theme.of(context).textTheme.headlineMedium),",
      "                  const SizedBox(height: 12),",
      "                  Text(route.text),",
      "                  const SizedBox(height: 20),",
      "                  const Text(",
      "                    '生成状态：等待 Android/iOS/Web 设备验证',",
      "                    semanticsLabel: '生成状态，等待设备验证',",
      "                  ),",
      "                ],",
      "              ),",
      "            ),",
      "          ),",
      "        ),",
      "      ),",
      "    );",
      "  }",
      "}",
    ),
    "test/widget_test.dart": lines(
      "import 'package:flutter_test/flutter_test.dart';",
      `import 'package:${context.safeProjectName.replaceAll("-", "_")}/elmos_bounded_navigation.dart';`,
      "void main() {",
      `  test('preserves all generated routes', () { expect(elmosBoundedRoutes.length, ${context.routes.length}); expect(elmosBoundedRoutes.map((raw) => elmosRoute(raw).path).toSet().length, elmosBoundedRoutes.length); });`,
      "}",
    ),
  };
}

function harmonyTemplate(context: ProjectTemplateContext): Record<string, string> {
  return {
    "oh-package.json5": json({
      modelVersion: "5.0.0",
      name: context.safeProjectName,
      version: "0.1.0",
      description: "ELMOS generated ArkUI project",
      main: "",
      author: "",
      license: "UNLICENSED",
      dependencies: {},
    }),
    "hvigor/hvigor-config.json5": json({
      modelVersion: "5.0.0",
      dependencies: {},
      execution: {},
      logging: {},
      debugging: {},
      nodeOptions: {},
    }),
    "hvigorfile.ts": lines("import { appTasks } from '@ohos/hvigor-ohos-plugin';", "export default { system: appTasks, plugins: [] };"),
    "build-profile.json5": json({
      app: {
        signingConfigs: [],
        products: [{
          name: "default",
          compileSdkVersion: 20,
          compatibleSdkVersion: 20,
          targetSdkVersion: 20,
          runtimeOS: "OpenHarmony",
          buildOption: { strictMode: { caseSensitiveCheck: true, useNormalizedOHMUrl: true } },
        }],
        buildModeSet: [{ name: "debug" }, { name: "release" }],
      },
      modules: [{ name: "entry", srcPath: "./entry", targets: [{ name: "default", applyToProducts: ["default"] }] }],
    }),
    "AppScope/app.json5": json({
      app: {
        bundleName: context.request.bundleId,
        vendor: "elmos-generated",
        versionCode: 1,
        versionName: "0.1.0",
        icon: "$media:app_icon",
        label: "$string:app_name",
      },
    }),
    "AppScope/resources/base/element/string.json": json({ string: [{ name: "app_name", value: context.request.title }] }),
    "AppScope/resources/base/media/app_icon.svg": lines(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">',
      '  <rect width="128" height="128" rx="28" fill="#15223d"/>',
      '  <path d="M30 38h68v14H46v12h44v14H46v12h52v14H30z" fill="#fbbf24"/>',
      "</svg>",
    ),
    "entry/oh-package.json5": lines('{ "name": "entry", "version": "0.1.0", "description": "ELMOS generated entry module", "main": "", "author": "", "license": "UNLICENSED", "dependencies": {} }'),
    "entry/hvigorfile.ts": lines("import { hapTasks } from '@ohos/hvigor-ohos-plugin';", "export default { system: hapTasks, plugins: [] };"),
    "entry/build-profile.json5": json({ apiType: "stageMode", buildOption: {}, targets: [{ name: "default" }] }),
    "entry/src/main/module.json5": json({
      module: {
        name: "entry",
        type: "entry",
        description: "$string:module_desc",
        mainElement: "EntryAbility",
        deviceTypes: ["default"],
        deliveryWithInstall: true,
        installationFree: false,
        pages: "$profile:main_pages",
        abilities: [{
          name: "EntryAbility",
          srcEntry: "./ets/entryability/EntryAbility.ets",
          description: "$string:ability_desc",
          label: "$string:app_name",
          startWindowIcon: "$media:app_icon",
          startWindowBackground: "$color:start_window_background",
          exported: true,
          skills: [{ entities: ["entity.system.home"], actions: ["action.system.home"] }],
        }],
      },
    }),
    "entry/src/main/resources/base/element/string.json": json({
      string: [
        { name: "app_name", value: context.request.title },
        { name: "module_desc", value: "ELMOS generated ArkUI module" },
        { name: "ability_desc", value: "ELMOS generated entry ability" },
      ],
    }),
    "entry/src/main/resources/base/element/color.json": json({
      color: [{ name: "start_window_background", value: "#15223D" }],
    }),
    "entry/src/main/resources/base/profile/main_pages.json": json({ src: ["pages/Index"] }),
    "entry/src/main/resources/rawfile/ui_ir.json": json(context.request.uiIr),
    "entry/src/main/ets/entryability/EntryAbility.ets": lines(
      "import { AbilityConstant, UIAbility, Want } from '@kit.AbilityKit';",
      "import { window } from '@kit.ArkUI';",
      "export default class EntryAbility extends UIAbility {",
      "  onCreate(_want: Want, _launchParam: AbilityConstant.LaunchParam): void {}",
      "  onWindowStageCreate(windowStage: window.WindowStage): void { windowStage.loadContent('pages/Index'); }",
      "}",
    ),
    "entry/src/main/ets/pages/Index.ets": lines(
      "import { ELMOS_ROUTES, elmosSelectBoundedRoute } from '../elmos-bounded-navigation';",
      "interface GeneratedRoute { id: string; path: string; title: string; text: string; requiresAuth: boolean; deepLink: boolean; }",
      "const GENERATED_ROUTES: readonly GeneratedRoute[] = ELMOS_ROUTES;",
      "@Entry",
      "@Component",
      "struct Index {",
      "  @State selected: number = 0;",
      "  private currentRoute(): GeneratedRoute { return elmosSelectBoundedRoute(GENERATED_ROUTES[this.selected]?.path ?? '/__unknown__'); }",
      "  build() {",
      "    Navigation() {",
      "      Row() {",
      "        Column({ space: 8 }) {",
      "          Text(" + js(context.request.title) + ").fontSize(22).fontWeight(FontWeight.Bold)",
      "          ForEach(GENERATED_ROUTES.slice(), (item: GeneratedRoute) => {",
      "            Button(item.title).width('100%').accessibilityText(item.id + '|' + item.path + '|auth:' + item.requiresAuth + '|deep:' + item.deepLink).onClick(() => { this.selected = GENERATED_ROUTES.indexOf(item); })",
      "          }, (item: GeneratedRoute) => item.id)",
      "        }.width('34%').padding(16)",
      "        Column({ space: 16 }) {",
      "          Text(this.currentRoute().title).fontSize(30).fontWeight(FontWeight.Bold)",
      "          Text(this.currentRoute().text).fontSize(18)",
      "          Text('生成状态：等待 HarmonyOS 真机与无障碍验证').fontColor('#6B4F00')",
      "        }.alignItems(HorizontalAlign.Start).width('66%').padding(24)",
      "      }.height('100%')",
      "    }.title(" + js(context.request.title) + ")",
      "  }",
      "}",
    ),
  };
}

export function renderTargetProject(context: ProjectTemplateContext): Readonly<Record<string, string>> {
  switch (context.profile.id) {
    case "vue2": return vue2Template(context);
    case "vue3": return vue3Template(context);
    case "react": return reactTemplate(context);
    case "react-native": return reactNativeTemplate(context);
    case "jquery": return jqueryTemplate(context);
    case "flutter": return flutterTemplate(context);
    case "harmony-arkui": return harmonyTemplate(context);
    case "angular": return angularTemplate(context);
    case "svelte": return svelteTemplate(context);
  }
}

export function componentForRoute(
  components: readonly UiIrComponent[],
  route: UiIrRoute,
): UiIrComponent {
  const component = components.find(candidate => candidate.id === route.componentId);
  if (!component) throw new Error(`route ${route.id} references a missing component`);
  return component;
}
