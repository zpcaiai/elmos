import { createHash } from "node:crypto";

import ts from "typescript";

import type { MiniappConversionRequest, MiniappPlatform, MiniappSourceInventory } from "./miniapp-types.js";
import { validateMiniappConversionRequest } from "./miniapp-contract-validation.js";
import {
  miniappIrDigest,
  miniappRuntimeStateKey,
  resolveMiniappRouteComponentRoots,
  validateMiniappSemanticIr,
  type MiniappAnalyzedComponent,
  type MiniappAnalyzedInteraction,
  type MiniappSemanticIr,
} from "./miniapp-semantic-ir.js";
import {
  exactMiniappTargetRoutePath,
  miniappPlatformDescriptor,
  validateMiniappConversionPlan,
  type MiniappComponentDecision,
  type MiniappConversionPlan,
  type MiniappPlatformDescriptor,
  type MiniappStyleDecision,
} from "./miniapp-planning.js";

export interface MiniappGeneratedArtifact {
  readonly path: string;
  readonly sha256: string;
  readonly bytes: number;
  readonly mediaType: string;
  readonly role: "runtime" | "configuration" | "evidence";
  readonly sourceNodeIds: readonly string[];
}

export interface MiniappGeneratedProject {
  readonly schemaVersion: "1.0";
  readonly platform: MiniappPlatform;
  readonly platformVersion: string;
  readonly toolchainVersion: string;
  readonly profileVersion: string;
  readonly status: "GENERATED" | "GENERATED_WITH_BLOCKERS" | "BLOCKED";
  readonly files: Readonly<Record<string, string>>;
  readonly artifacts: readonly MiniappGeneratedArtifact[];
  readonly traceMap: Readonly<Record<string, readonly string[]>>;
  readonly findings: readonly string[];
  readonly staticValidation: "PASSED" | "BLOCKED";
  readonly officialBuild: "NOT_RUN";
  readonly preview: "NOT_RUN";
  readonly deviceRuntime: "NOT_RUN";
  readonly upload: "NOT_RUN";
  readonly review: "NOT_RUN";
  readonly release: "NOT_RUN";
  readonly certification: "NOT_CERTIFIED";
  readonly deterministicDigest: string;
}

interface TargetSyntax {
  readonly templateExtension: string;
  readonly styleExtension: string;
  readonly eventTap: string;
  readonly eventInput: string;
  readonly loopOpen: (items: string, item: string, key: string) => string;
  readonly loopClose: string;
}

function xml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&apos;");
}

function json(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function safeIdentifier(value: string, fallback: string): string {
  const normalized = value.replace(/[^A-Za-z0-9_$]/g, "_");
  return /^[A-Za-z_$]/.test(normalized) ? normalized : fallback;
}

function safePageSegment(value: string, fallback: string): string {
  return exactMiniappTargetRoutePath(value) ?? fallback;
}

function syntaxFor(platform: MiniappPlatform): TargetSyntax {
  const profile = miniappPlatformDescriptor(platform);
  if (platform === "alipay") {
    return {
      templateExtension: profile.templateExtension,
      styleExtension: profile.styleExtension,
      eventTap: "onTap",
      eventInput: "onInput",
      loopOpen: (items, item, key) => `<block a:for="{{${items}}}" a:for-item="${item}" a:key="${key}">`,
      loopClose: "</block>",
    };
  }
  if (platform === "douyin") {
    return {
      templateExtension: profile.templateExtension,
      styleExtension: profile.styleExtension,
      eventTap: "bindtap",
      eventInput: "bindinput",
      loopOpen: (items, item, key) => `<block tt:for="{{${items}}}" tt:for-item="${item}" tt:key="${key}">`,
      loopClose: "</block>",
    };
  }
  if (platform === "xiaohongshu") {
    return {
      templateExtension: profile.templateExtension,
      styleExtension: profile.styleExtension,
      eventTap: "bindtap",
      eventInput: "bindinput",
      loopOpen: (items, _item, key) => `<block xhs:for="{{${items}}}" xhs:key="${key}">`,
      loopClose: "</block>",
    };
  }
  return {
    templateExtension: profile.templateExtension,
    styleExtension: profile.styleExtension,
    eventTap: "bindtap",
    eventInput: "bindinput",
    loopOpen: (items, item, key) => `<block wx:for="{{${items}}}" wx:for-item="${item}" wx:key="${key}">`,
    loopClose: "</block>",
  };
}

function componentTag(decision: MiniappComponentDecision | undefined): string {
  const candidate = decision?.targetComponent ?? "view";
  return /^[a-z][a-z0-9-]*$/.test(candidate) ? candidate : "view";
}

interface RuntimeInteractionBinding {
  readonly interaction: MiniappAnalyzedInteraction;
  readonly index: number;
  readonly draftKey: string;
  readonly collectionKey: string;
  readonly renderCollectionKey: string;
  readonly canSubmitKey: string;
  readonly inputHandler: string;
  readonly submitHandler: string;
  readonly collectionScope: "component" | "page" | "application" | "persistent";
  readonly itemKeyMode: "index" | "value-index";
}

function runtimeInteractions(ir: MiniappSemanticIr, componentIds?: ReadonlySet<string>): readonly RuntimeInteractionBinding[] {
  for (const interaction of ir.interactions) {
    if (miniappRuntimeStateKey(interaction.draftState) === null || miniappRuntimeStateKey(interaction.collectionState) === null) {
      throw new Error(`unsafe runtime state key in interaction ${interaction.id}`);
    }
  }
  return ir.interactions.map((interaction, index) => ({
    interaction,
    index,
    draftKey: miniappRuntimeStateKey(interaction.draftState) ?? safeIdentifier(interaction.draftStateId, `draft${index}`),
    collectionKey: miniappRuntimeStateKey(interaction.collectionState) ?? safeIdentifier(interaction.collectionStateId, `items${index}`),
    renderCollectionKey: `${miniappRuntimeStateKey(interaction.collectionState) ?? safeIdentifier(interaction.collectionStateId, `items${index}`)}Render`,
    canSubmitKey: `canSubmit${index}`,
    inputHandler: `handleInput${index}`,
    submitHandler: `handleSubmit${index}`,
    collectionScope: ir.states.find(state => state.id === interaction.collectionStateId)?.scope ?? "component",
    itemKeyMode: (() => {
      const component = ir.components.find(item => item.id === interaction.listComponentId);
      const binding = component?.collectionBinding;
      const normalized = binding?.keyExpression?.replace(/[\s()]/gu, "") ?? "";
      const indexAlias = binding?.indexAlias ?? "index";
      const templateKey = binding ? "`" + "${" + binding.itemAlias + "}-${" + indexAlias + "}`" : "";
      return binding && (normalized === `${binding.itemAlias}+'-'+${indexAlias}` || normalized === `${binding.itemAlias}+\"-\"+${indexAlias}` || normalized === templateKey)
        ? "value-index" as const
        : "index" as const;
    })(),
  })).filter(binding => !componentIds || [
    binding.interaction.inputComponentId,
    binding.interaction.submitComponentId,
    binding.interaction.listComponentId,
  ].every(id => componentIds.has(id)));
}

function componentSubgraph(
  ir: MiniappSemanticIr,
  roots: readonly MiniappAnalyzedComponent[],
): readonly MiniappAnalyzedComponent[] {
  const byId = new Map(ir.components.map(component => [component.id, component]));
  const selected: MiniappAnalyzedComponent[] = [];
  const visit = (component: MiniappAnalyzedComponent): void => {
    if (selected.some(item => item.id === component.id)) return;
    selected.push(component);
    for (const childId of component.children) {
      const child = byId.get(childId);
      if (child) visit(child);
    }
  };
  roots.forEach(visit);
  return selected;
}

function routeContentComponents(ir: MiniappSemanticIr, routeId: string): readonly MiniappAnalyzedComponent[] {
  const route = ir.routes.find(item => item.id === routeId);
  if (!route) return [];
  return componentSubgraph(ir, resolveMiniappRouteComponentRoots(ir.components, route));
}

function applicationShellComponents(
  ir: MiniappSemanticIr,
  routeContent: readonly MiniappAnalyzedComponent[],
): readonly MiniappAnalyzedComponent[] {
  const contentIds = new Set(routeContent.map(component => component.id));
  const outlets = ir.components.filter(component => component.semanticRole === "route-outlet");
  const outletPaths = new Set(outlets.flatMap(component => component.sourceRefs.map(ref => ref.path)));
  if (outlets.length === 0) return [];
  if (outlets.length !== 1 || outletPaths.size !== 1) return [];
  const shellPath = [...outletPaths][0]!;
  const candidates = ir.components.filter(component => !contentIds.has(component.id)
    && component.sourceRefs.some(ref => ref.path === shellPath)
    && component.semanticRole !== "non-render-metadata");
  const childIds = new Set(candidates.flatMap(component => component.children));
  const roots = candidates.filter(component => component.semanticRole !== "route-outlet" && !childIds.has(component.id));
  return roots.length === 1 ? componentSubgraph(ir, roots) : [];
}

function componentsForRoute(ir: MiniappSemanticIr, routeId: string): readonly MiniappAnalyzedComponent[] {
  const routeContent = routeContentComponents(ir, routeId);
  const byId = new Map<string, MiniappAnalyzedComponent>();
  for (const component of [...applicationShellComponents(ir, routeContent), ...routeContent]) byId.set(component.id, component);
  return [...byId.values()];
}

function staticAttribute(component: MiniappAnalyzedComponent, name: string): string | undefined {
  const value = component.attributes[name];
  if (!value || /\{\{|\}\}/u.test(value)) return undefined;
  return value;
}

function hasStaticBooleanAttribute(component: MiniappAnalyzedComponent, name: string): boolean {
  const value = component.attributes[name];
  return value !== undefined && !/\{\{|\}\}/u.test(value);
}

function commonAttributes(component: MiniappAnalyzedComponent, className: string): string {
  const sourceClass = staticAttribute(component, "class") ?? staticAttribute(component, "className");
  const values: Array<[string, string]> = [["class", [className, sourceClass].filter(Boolean).join(" ")], ["data-source-node", component.id]];
  for (const name of ["id", "role", "aria-label", "tabindex", "name", "placeholder"]) {
    const value = staticAttribute(component, name);
    if (value !== undefined) values.push([name, value]);
  }
  for (const [source, target] of [["tabIndex", "tabindex"]] as const) {
    const value = staticAttribute(component, source);
    if (value !== undefined) values.push([target, value]);
  }
  for (const booleanName of ["required", "autofocus", "disabled"]) {
    if (hasStaticBooleanAttribute(component, booleanName)) values.push([booleanName, "true"]);
  }
  return values.map(([name, value]) => `${name}="${xml(value)}"`).join(" ");
}

function pageMarkup(
  ir: MiniappSemanticIr,
  plan: MiniappConversionPlan,
  platform: MiniappPlatform,
  routeId: string,
): string {
  const syntax = syntaxFor(platform);
  const lines = ['<view class="elmos-page" role="main" aria-label="{{pageLabel}}">'];
  const selected = componentsForRoute(ir, routeId).slice(0, 64);
  const routeContent = routeContentComponents(ir, routeId).filter(component => selected.some(item => item.id === component.id));
  const shell = applicationShellComponents(ir, routeContent).filter(component => selected.some(item => item.id === component.id));
  const selectedIds = new Set(selected.map(component => component.id));
  const byId = new Map(selected.map(component => [component.id, component]));
  const childIds = new Set(selected.flatMap(component => component.children));
  const routeContentChildIds = new Set(routeContent.flatMap(component => component.children));
  const routeContentRoots = routeContent.filter(component => !routeContentChildIds.has(component.id));
  const interactions = runtimeInteractions(ir, selectedIds);
  const interactionByComponent = new Map(interactions.flatMap(binding => [
    [binding.interaction.inputComponentId, binding] as const,
    [binding.interaction.submitComponentId, binding] as const,
    [binding.interaction.listComponentId, binding] as const,
  ]));
  const decisionByComponent = new Map(plan.components
    .filter(item => item.platform === platform)
    .map(item => [item.componentId, item]));
  const rendered = new Set<string>();
  const staticDescendantText = (component: MiniappAnalyzedComponent, seen = new Set<string>()): string => {
    if (seen.has(component.id)) return "";
    seen.add(component.id);
    const own = /\{\{|\}\}/u.test(component.textContent) ? "" : component.textContent;
    return [own, ...component.children.map(childId => {
      const child = byId.get(childId);
      return child ? staticDescendantText(child, seen) : "";
    })].filter(Boolean).join(" ").replace(/\s+/gu, " ").trim();
  };
  const renderComponent = (component: MiniappAnalyzedComponent, indent: string): string[] => {
    if (rendered.has(component.id)) return [];
    rendered.add(component.id);
    if (component.semanticRole === "non-render-metadata") return [];
    if (component.semanticRole === "route-outlet") {
      return routeContentRoots.flatMap(root => renderComponent(root, indent));
    }
    const decision = decisionByComponent.get(component.id);
    const tag = componentTag(decision);
    const binding = interactionByComponent.get(component.id);
    if (binding && component.id === binding.interaction.inputComponentId) {
      const attributes = commonAttributes(component, "elmos-control");
      return [`${indent}<input ${attributes} value="{{${binding.draftKey}}}" ${syntax.eventInput}="${binding.inputHandler}" />`];
    }
    if (binding && component.id === binding.interaction.submitComponentId) {
      const attributes = commonAttributes(component, "elmos-control");
      const label = staticDescendantText(component) || staticAttribute(component, "aria-label") || "Submit";
      const disabled = hasStaticBooleanAttribute(component, "disabled")
        ? ""
        : ` disabled="{{!${binding.canSubmitKey}}}"`;
      return [`${indent}<button ${attributes}${disabled} ${syntax.eventTap}="${binding.submitHandler}">${xml(label)}</button>`];
    }
    if (binding && component.id === binding.interaction.listComponentId) {
      return [
        `${indent}${syntax.loopOpen(binding.renderCollectionKey, "item", "__elmosKey")}`,
        `${indent}  <view class="elmos-list-item"><text>{{item.value}}</text></view>`,
        `${indent}${syntax.loopClose}`,
      ];
    }
    const attributes = commonAttributes(component, decision?.strategy === "decision" ? "elmos-node elmos-blocked" : "elmos-node");
    if (component.semanticRole === "form-control") return [`${indent}<input ${attributes} />`];
    if (component.semanticRole === "media") return [`${indent}<${tag} ${attributes} mode="aspectFit" />`];
    const label = /\{\{|\}\}/u.test(component.textContent) ? "" : component.textContent;
    const children = component.children.flatMap(childId => {
      const child = byId.get(childId);
      return child ? renderComponent(child, `${indent}  `) : [];
    });
    const ownText = label ? [`${indent}  <text>${xml(label)}</text>`] : [];
    if (component.semanticRole === "button") {
      return [`${indent}<button ${attributes}>${xml(staticDescendantText(component) || staticAttribute(component, "aria-label") || "")}</button>`];
    }
    return [`${indent}<${tag} ${attributes}>`, ...ownText, ...children, `${indent}</${tag}>`];
  };
  const primaryRoots = shell.length > 0 ? shell.filter(item => !childIds.has(item.id)) : routeContentRoots;
  for (const component of primaryRoots) lines.push(...renderComponent(component, "  "));
  for (const component of selected) lines.push(...renderComponent(component, "  "));
  if (selected.length === 0) {
    lines.push('  <view class="elmos-blocked" role="alert"><text>No source component could be recovered; see migration-findings.json.</text></view>');
  }
  lines.push("</view>", "");
  return lines.join("\n");
}

function generatedItemKeyExpression(binding: RuntimeInteractionBinding): string {
  return binding.itemKeyMode === "value-index" ? "`${item}-${index}`" : "String(index)";
}

function pageLogic(ir: MiniappSemanticIr, routeId: string): string {
  const route = ir.routes.find(item => item.id === routeId);
  const data: Record<string, unknown> = {
    pageLabel: route?.path ?? "/",
  };
  const selectedIds = new Set(componentsForRoute(ir, routeId).map(component => component.id));
  const interactions = runtimeInteractions(ir, selectedIds);
  for (const binding of interactions) {
    data[binding.draftKey] = "";
    data[binding.collectionKey] = [];
    data[binding.renderCollectionKey] = [];
    data[binding.canSubmitKey] = false;
  }
  const handlers = interactions.flatMap(binding => [
    `  ${binding.inputHandler}(event) {\n    const raw = event && event.detail ? (event.detail.value ?? \"\") : \"\";\n    const value = String(raw);\n    this.setData({ ${binding.draftKey}: value, ${binding.canSubmitKey}: value.trim().length > 0 });\n  }`,
    `  ${binding.submitHandler}() {\n    const value = String(this.data.${binding.draftKey} ?? \"\").trim();\n    if (!value) {\n      this.setData({ ${binding.canSubmitKey}: false });\n      return;\n    }\n    const current = Array.isArray(this.data.${binding.collectionKey}) ? this.data.${binding.collectionKey} : [];\n    const next = [...current, value];\n    const rendered = next.map((item, index) => ({ value: item, __elmosKey: ${generatedItemKeyExpression(binding)} }));${binding.collectionScope === "application" ? `\n    const application = typeof getApp === \"function\" ? getApp() : null;\n    if (application && application.globalData) application.globalData.${binding.collectionKey} = next;` : ""}\n    this.setData({ ${binding.collectionKey}: next, ${binding.renderCollectionKey}: rendered, ${binding.draftKey}: \"\", ${binding.canSubmitKey}: false });\n  }`,
  ]);
  const globalBindings = interactions.filter(binding => binding.collectionScope === "application");
  const loadData = ["routeOptions: options || {}", ...globalBindings.flatMap(binding => {
    const source = `application && application.globalData && Array.isArray(application.globalData.${binding.collectionKey}) ? application.globalData.${binding.collectionKey} : []`;
    return [
      `${binding.collectionKey}: ${source}`,
      `${binding.renderCollectionKey}: (${source}).map((item, index) => ({ value: item, __elmosKey: ${generatedItemKeyExpression(binding)} }))`,
    ];
  })];
  return [
    "Page({",
    `  data: ${JSON.stringify(data, null, 2).replaceAll("\n", "\n  ")},`,
    "  onLoad(options) {",
    ...(globalBindings.length > 0 ? ['    const application = typeof getApp === "function" ? getApp() : null;'] : []),
    `    this.setData({ ${loadData.join(", ")} });`,
    "  },",
    "  onUnload() {",
    "    this.__elmosCancelled = true;",
    "  },",
    handlers.join(",\n"),
    "});",
    "",
  ].join("\n");
}

function appLogic(ir: MiniappSemanticIr): string {
  const globalData = Object.fromEntries(runtimeInteractions(ir)
    .filter(binding => binding.collectionScope === "application")
    .map(binding => [binding.collectionKey, []]));
  return [
    "App({",
    `  globalData: ${JSON.stringify(globalData)},`,
    "  onLaunch() {},",
    "  onError(error) { console.error('MINIAPP_RUNTIME_ERROR', error && error.message ? error.message : 'unknown'); },",
    "});",
    "",
  ].join("\n");
}

function pageStyles(plan: MiniappConversionPlan, platform: MiniappPlatform): string {
  const selected = plan.styles.find(item => item.platform === platform);
  const rules = selected?.rules.flatMap(rule => {
    if (rule.unsupported.length > 0) return [];
    const declarations = Object.entries(rule.declarations).map(([key, value]) => `  ${key}: ${value};`).join("\n");
    return declarations ? [`${rule.selector} {\n${declarations}\n}`] : [];
  }) ?? [];
  return [
    "page { min-height: 100%; background: #ffffff; color: #1f2937; }",
    ".elmos-page { box-sizing: border-box; padding: 32rpx; padding-bottom: calc(32rpx + env(safe-area-inset-bottom)); }",
    ".elmos-title { display: block; font-size: 40rpx; font-weight: 600; margin-bottom: 24rpx; }",
    ".elmos-control { margin: 12rpx 0; min-height: 80rpx; }",
    ".elmos-list-item { padding: 16rpx; border-bottom: 1rpx solid #d1d5db; }",
    ".elmos-blocked { color: #991b1b; border: 2rpx solid #991b1b; padding: 16rpx; }",
    ...rules,
    "",
  ].join("\n");
}

function platformAdapter(platform: MiniappPlatform, profile: MiniappPlatformDescriptor): string {
  const api = profile.apiNamespace;
  return [
    '"use strict";',
    `const platformApi = typeof ${api} === "object" ? ${api} : null;`,
    "function requireApi(name) {",
    "  if (!platformApi || typeof platformApi[name] !== \"function\") {",
    "    const error = new Error(`PLATFORM_CAPABILITY_UNAVAILABLE:${name}`);",
    "    error.code = \"PLATFORM_CAPABILITY_UNAVAILABLE\";",
    "    throw error;",
    "  }",
    "  return platformApi[name].bind(platformApi);",
    "}",
    "module.exports = Object.freeze({",
    `  platform: ${JSON.stringify(platform)},`,
    "  navigateTo: options => requireApi(\"navigateTo\")(options),",
    "  request: options => requireApi(\"request\")(options),",
    "  getStorage: options => requireApi(\"getStorage\")(options),",
    "  setStorage: options => requireApi(\"setStorage\")(options),",
    "});",
    "",
  ].join("\n");
}

function projectConfiguration(platform: MiniappPlatform, request: MiniappConversionRequest): Readonly<Record<string, unknown>> {
  const target = request.targets.find(item => item.platform === platform)!;
  if (platform === "wechat") {
    return {
      appid: "touristappid",
      compileType: "miniprogram",
      libVersion: target.platformVersion,
      projectname: request.requestId,
      setting: { es6: true, minified: true, postcss: true, urlCheck: true },
    };
  }
  if (platform === "alipay") {
    return {
      appid: "__CONFIGURE_APP_ID__",
      miniprogramRoot: "./",
      compileOptions: { component2: true, typescript: false },
    };
  }
  if (platform === "douyin") {
    return {
      appid: "testAppId",
      projectname: request.requestId,
      douyinProjectType: "native",
      setting: { es6: true, minified: true, postcss: true, urlCheck: true },
    };
  }
  return {
    appid: "__CONFIGURE_APP_ID__",
    projectname: request.requestId,
    miniprogramRoot: "./",
    profileVersion: target.platformVersion,
  };
}

function mediaType(path: string): string {
  if (path.endsWith(".json")) return "application/json";
  if (/\.(?:js|ts)$/.test(path)) return "text/javascript";
  if (/\.(?:wxml|axml|ttml|xhsml)$/.test(path)) return "text/xml";
  if (/\.(?:wxss|acss|ttss|css)$/.test(path)) return "text/css";
  return "text/plain";
}

function artifactRole(path: string): MiniappGeneratedArtifact["role"] {
  if (path === "migration-findings.json" || path === "trace-map.json") return "evidence";
  if (path.endsWith(".json") || /(?:^|\/)project\.config\.json$/u.test(path) || path === "mini.project.json") return "configuration";
  return "runtime";
}

function rawTextDigest(content: string): string {
  return `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`;
}

function validateMarkup(source: string): void {
  const stack: string[] = [];
  let cursor = 0;
  while (cursor < source.length) {
    const start = source.indexOf("<", cursor);
    if (start < 0) break;
    const end = source.indexOf(">", start + 1);
    if (end < 0) throw new Error("template tag is unterminated");
    const raw = source.slice(start + 1, end).trim();
    if (!raw.startsWith("!") && !raw.startsWith("?")) {
      const closing = raw.startsWith("/");
      const selfClosing = raw.endsWith("/") || /^(?:input|image|icon|progress|checkbox|radio|slider|switch)\b/.test(raw);
      const name = raw.replace(/^\//, "").split(/[\s/]/, 1)[0] ?? "";
      if (!/^[a-z][a-z0-9-]*$/.test(name)) throw new Error(`invalid template tag: ${name}`);
      if (closing) {
        if (stack.pop() !== name) throw new Error(`unbalanced template tag: ${name}`);
      } else if (!selfClosing) stack.push(name);
    }
    cursor = end + 1;
  }
  if (stack.length > 0) throw new Error(`unclosed template tag: ${stack.at(-1)}`);
}

function validateGeneratedFiles(platform: MiniappPlatform, files: Readonly<Record<string, string>>): readonly string[] {
  const findings: string[] = [];
  const profile = miniappPlatformDescriptor(platform);
  for (const [path, content] of Object.entries(files)) {
    if (path.endsWith(".json")) {
      try { JSON.parse(content); } catch { findings.push(`INVALID_JSON:${path}`); }
    } else if (path.endsWith(".js")) {
      const file = ts.createSourceFile(path, content, ts.ScriptTarget.ES2022, true, ts.ScriptKind.JS);
      const diagnostics = (file as ts.SourceFile & { readonly parseDiagnostics?: readonly unknown[] }).parseDiagnostics ?? [];
      if (diagnostics.length > 0) findings.push(`INVALID_JAVASCRIPT:${path}`);
    } else if (path.endsWith(profile.templateExtension)) {
      try { validateMarkup(content); } catch (error) { findings.push(`INVALID_TEMPLATE:${path}:${error instanceof Error ? error.message : String(error)}`); }
    }
    if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:appsecret|client_secret|refresh_token)\s*[:=]/i.test(content)) {
      findings.push(`SECRET_EXPOSURE:${path}`);
    }
    if (/\bweb-view\b|<canvas[^>]*class=["']?(?:page|root)/i.test(content)) findings.push(`FORBIDDEN_FALLBACK:${path}`);
  }
  const templateSources = Object.entries(files)
    .filter(([path]) => path.endsWith(profile.templateExtension))
    .map(([, content]) => content);
  const scriptSources = Object.entries(files).filter(([path]) => path.endsWith(".js")).map(([, content]) => content).join("\n");
  const declaredHandlers = new Set(templateSources.flatMap(source => [...source.matchAll(/\b(?:bind(?:tap|input|change|submit)|catch(?:tap|input)|on(?:Tap|Input|Change|Submit))="([A-Za-z_$][\w$]*)"/gu)]
    .map(match => match[1]!)));
  for (const handler of declaredHandlers) {
    const escaped = handler.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!new RegExp(`\\b${escaped}\\s*\\(`, "u").test(scriptSources)) findings.push(`MISSING_EVENT_HANDLER:${handler}`);
  }
  const allowedTags = new Set(["view", "text", "button", "input", "image", "block", "scroll-view", "navigator", "form", "textarea", "label"]);
  for (const source of templateSources) {
    for (const match of source.matchAll(/<\/?([a-z][a-z0-9-]*)\b/gu)) {
      if (!allowedTags.has(match[1]!)) findings.push(`UNREGISTERED_CUSTOM_COMPONENT:${match[1]}`);
    }
    if (source.includes("generated-composite")) findings.push("UNREGISTERED_CUSTOM_COMPONENT:generated-composite");
  }
  return findings.sort();
}

function buildFiles(
  platform: MiniappPlatform,
  ir: MiniappSemanticIr,
  plan: MiniappConversionPlan,
  request: MiniappConversionRequest,
): { files: Record<string, string>; traceMap: Record<string, readonly string[]>; findings: string[] } {
  const profile = miniappPlatformDescriptor(platform);
  const syntax = syntaxFor(platform);
  const files: Record<string, string> = {};
  const traceMap: Record<string, readonly string[]> = {};
  const findings = plan.findings.filter(item => item.platform === "all" || item.platform === platform)
    .map(item => `${item.classification}:${item.code}:${item.message}`);
  const routeEntries = ir.routes.length > 0 ? ir.routes : [{ id: "route.missing", path: "/", component: "Missing", parameters: [], guards: [], sourceRefs: [] }];
  const used = new Set<string>();
  const pages: string[] = [];
  const emittedStyleIds = plan.styles.find(item => item.platform === platform)?.rules.filter(item => item.unsupported.length === 0).map(item => item.styleId) ?? [];
  for (const [index, route] of routeEntries.entries()) {
    let segment = safePageSegment(route.path, index === 0 ? "index" : `page-${index}`);
    if (used.has(segment)) segment = `${segment}-${index}`;
    used.add(segment);
    const page = `pages/${segment}/${segment.split("/").at(-1) ?? `page-${index}`}`;
    pages.push(page);
    const templatePath = `${page}${syntax.templateExtension}`;
    const stylePath = `${page}${syntax.styleExtension}`;
    const scriptPath = `${page}.js`;
    const configPath = `${page}.json`;
    files[templatePath] = pageMarkup(ir, plan, platform, route.id);
    files[stylePath] = pageStyles(plan, platform);
    files[scriptPath] = pageLogic(ir, route.id);
    files[configPath] = json({ navigationBarTitleText: ir.application.title, usingComponents: {} });
    const routeComponents = componentsForRoute(ir, route.id).slice(0, 64);
    const routeComponentIds = new Set(routeComponents.map(item => item.id));
    const routeSourcePaths = new Set(routeComponents.flatMap(component => component.sourceRefs.map(ref => ref.path)));
    const routeInteractions = runtimeInteractions(ir, routeComponentIds);
    const interactionIds = routeInteractions.map(item => item.interaction.id);
    const interactionStateIds = routeInteractions.flatMap(item => [item.interaction.draftStateId, item.interaction.collectionStateId]);
    const emittedComponentIds = routeComponents.map(item => item.id);
    const emittedFormIds = ir.forms.filter(form => form.sourceRefs.some(ref => routeSourcePaths.has(ref.path))).map(form => form.id);
    traceMap[templatePath] = [...new Set([route.id, ...emittedComponentIds, ...emittedFormIds, ...interactionIds])].sort();
    traceMap[stylePath] = emittedStyleIds;
    traceMap[scriptPath] = [...new Set([route.id, ...interactionIds, ...interactionStateIds])].sort();
    traceMap[configPath] = [route.id];
  }
  files["app.js"] = appLogic(ir);
  files["app.json"] = json({
    pages,
    window: {
      navigationBarTitleText: ir.application.title,
      navigationBarBackgroundColor: "#ffffff",
      navigationBarTextStyle: "black",
      backgroundTextStyle: "light",
    },
  });
  files[`app${syntax.styleExtension}`] = pageStyles(plan, platform);
  files[profile.projectFile] = json(projectConfiguration(platform, request));
  files["adapters/platform.js"] = platformAdapter(platform, profile);
  const applicationInteractionStateIds = new Set(runtimeInteractions(ir)
    .filter(binding => binding.collectionScope === "application")
    .map(binding => binding.interaction.collectionStateId));
  traceMap["app.js"] = ir.states.filter(state => applicationInteractionStateIds.has(state.id)).map(state => state.id).sort();
  traceMap["app.json"] = ir.routes.map(item => item.id);
  traceMap[`app${syntax.styleExtension}`] = emittedStyleIds;
  traceMap[profile.projectFile] = [];
  traceMap["adapters/platform.js"] = [];
  traceMap["migration-findings.json"] = [];
  files["migration-findings.json"] = json({
    schemaVersion: "1.0",
    platform,
    findings,
    unsupportedBehaviorMustNotBeDropped: true,
    officialBuild: "NOT_RUN",
    runtime: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  });
  files["trace-map.json"] = json(traceMap);
  traceMap["trace-map.json"] = [];
  return { files, traceMap, findings };
}

export function generateMiniappTarget(
  platform: MiniappPlatform,
  ir: MiniappSemanticIr,
  plan: MiniappConversionPlan,
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
): MiniappGeneratedProject {
  request = validateMiniappConversionRequest(request);
  validateMiniappSemanticIr(ir, inventory);
  const { deterministicDigest: suppliedPlanDigest, ...planBody } = plan;
  if (suppliedPlanDigest !== miniappIrDigest(planBody)) throw new Error("miniapp plan deterministic digest does not match its content");
  if (
    plan.irDigest !== ir.deterministicDigest
    || plan.requestId !== request.requestId
    || plan.requestDigest !== miniappIrDigest(request)
  ) {
    throw new Error("miniapp plan does not belong to the exact request and IR");
  }
  if (
    ir.source.label !== request.source.sourceLabel
    || ir.source.frameworkVersion !== request.source.frameworkVersion
    || ir.source.snapshotDigest !== request.source.snapshotDigest
    || ir.source.revision !== request.source.revision
  ) {
    throw new Error("miniapp IR source tuple does not match the conversion request");
  }
  validateMiniappConversionPlan(plan, ir, request, inventory);
  const requestedPlatforms = request.targets.map(target => target.platform);
  const plannedPlatforms = plan.platformProfiles.map(profile => profile.platform);
  if (JSON.stringify(plannedPlatforms) !== JSON.stringify(requestedPlatforms)) {
    throw new Error("miniapp plan target platforms do not match the exact request");
  }
  const target = request.targets.find(item => item.platform === platform);
  if (!target) throw new Error(`target platform was not requested: ${platform}`);
  const built = buildFiles(platform, ir, plan, request);
  const validationFindings = validateGeneratedFiles(platform, built.files);
  const findings = [...new Set([...built.findings, ...validationFindings])].sort();
  const artifacts = Object.entries(built.files).sort(([a], [b]) => a.localeCompare(b, "en-US")).map(([path, content]) => ({
    path,
    sha256: rawTextDigest(content),
    bytes: Buffer.byteLength(content, "utf8"),
    mediaType: mediaType(path),
    role: artifactRole(path),
    sourceNodeIds: built.traceMap[path] ?? [],
  }));
  const blocking = plan.findings.some(item => (item.platform === "all" || item.platform === platform) && item.blocking);
  const base = {
    schemaVersion: "1.0" as const,
    platform,
    platformVersion: target.platformVersion,
    toolchainVersion: target.toolchainVersion,
    profileVersion: miniappPlatformDescriptor(platform).profileVersion,
    status: validationFindings.length > 0 ? "BLOCKED" as const : blocking ? "GENERATED_WITH_BLOCKERS" as const : "GENERATED" as const,
    files: Object.fromEntries(Object.entries(built.files).sort(([a], [b]) => a.localeCompare(b, "en-US"))),
    artifacts,
    traceMap: Object.fromEntries(Object.entries(built.traceMap).sort(([a], [b]) => a.localeCompare(b, "en-US"))),
    findings,
    staticValidation: validationFindings.length > 0 ? "BLOCKED" as const : "PASSED" as const,
    officialBuild: "NOT_RUN" as const,
    preview: "NOT_RUN" as const,
    deviceRuntime: "NOT_RUN" as const,
    upload: "NOT_RUN" as const,
    review: "NOT_RUN" as const,
    release: "NOT_RUN" as const,
    certification: "NOT_CERTIFIED" as const,
  };
  return { ...base, deterministicDigest: miniappIrDigest(base) };
}

export function generateAllMiniappTargets(
  ir: MiniappSemanticIr,
  plan: MiniappConversionPlan,
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
): readonly MiniappGeneratedProject[] {
  const normalizedRequest = validateMiniappConversionRequest(request);
  return normalizedRequest.targets.map(target =>
    generateMiniappTarget(target.platform, ir, plan, normalizedRequest, inventory));
}
