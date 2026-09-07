import { createHash } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import ts from "typescript";

import {
  aggregateModelInfluence,
  aggregateRuntimeInfluence,
  boundedInteractionScenarios,
  canonicalBoundedFrontendInteractionModel,
  interactionBlockIds,
  interactionBlockSymbolMap,
  interactionContractSource,
  interactionInfluenceMatrix,
  interactionScenarioIds,
  interactionSourceSpec,
  navigationCompatibilitySource,
  observeBoundedFrontendInteraction,
  type BoundedFrontendInteractionModel,
  type InteractionBlockId,
  type InteractionObservation,
  type InteractionScenario,
} from "./bounded-interaction-source.js";
import {
  augmentBoundedInteractionFiles,
  boundedFrontendBlockObserverContracts,
  boundedFrontendRuntimeActualKeys,
  boundedInteractionConsumerPaths,
  boundedInteractionFixtureRequest,
  boundedInteractionSourceFixtureBytes,
  generateBoundedInteractionProject,
  projectBoundedFrontendRuntimeObservation,
  reduceBoundedFrontendRuntime,
  requiredRuntimeChannels,
} from "./bounded-interaction-project.js";
import { interactionRuntimeInfluenceMatrix } from "./bounded-interaction-source.js";
import type { BoundedNavigationSemanticModel } from "./bounded-navigation-source.js";
import {
  boundedNavigationGeneratedConsumerPaths,
  expectedBoundedNavigationConsumerFiles,
  frontendFormalDigest,
  runFrontendSolver,
  type FrontendFormalStatus,
  type FrontendSolverOptions,
  type FrontendSolverResult,
  type SourceByteSpan,
} from "./frontend-formal-equivalence.js";
import { uiConversionRoutes, uiTargetProfile, uiTargetProfiles } from "./project-profiles.js";
import type { UiFrameworkId } from "./project-types.js";

export type InteractionFormalStatus = FrontendFormalStatus;

export interface ReliftedBoundedFrontendInteraction {
  readonly schema_version: "1.0";
  readonly proof_profile: "bounded-frontend-interaction-v1";
  readonly profile_id: UiFrameworkId;
  readonly parser: "TYPESCRIPT_AST" | "DART_BOUNDED_BASE64";
  readonly source_path: string;
  readonly source_hash: string;
  readonly model: BoundedFrontendInteractionModel;
  readonly model_digest: string;
  readonly block_digests: Readonly<Record<InteractionBlockId, string>>;
  readonly spans: Readonly<Record<string, SourceByteSpan>>;
  readonly consumer_binding: {
    readonly sole_contract_literal: true;
    readonly navigation_identity_projection: true;
    readonly reducer_reachable: true;
    readonly state_dispatch_reachable: true;
    readonly effect_command_reachable: true;
    readonly form_and_focus_reachable: true;
    readonly api_adapter_reachable: true;
    readonly identity_tenant_guard_reachable: true;
    readonly hydration_observation_reachable: true;
    readonly i18n_theme_viewport_reachable: true;
    readonly native_adapter_reachable: true;
    readonly strict_generated_grammar: true;
  };
}

export interface InteractionCampaignOptions {
  readonly solver?: FrontendSolverOptions;
  readonly tamper?: {
    readonly profile_id: UiFrameworkId;
    readonly path: string;
    readonly find: string;
    readonly replace: string;
  };
}

export interface InteractionCampaignVerificationOptions {
  readonly solver?: {
    readonly command: string;
  };
}

const proofAssumptions = [
  "The proof is bounded to the typed bounded-frontend-interaction-v1 model, its finite input domains, and ELMOS-emitted strict grammar; arbitrary customer source is NOT_PROVED.",
  "The authoritative model, source emitters, re-lifters, reference reducer, and SMT encoder are produced by one engine; this is self-consistency evidence and NOT_INDEPENDENT_SINGLE_ENGINE.",
  "Strict expected consumer bytes establish generated-grammar reachability, not general compiler, framework, browser, operating-system, or device soundness.",
  "Real SSR hydration, network servers, identity authority, tenant isolation enforcement, native adapters, browser journeys, and device journeys remain NOT_RUN unless independent channel evidence is attached.",
  "Z3 UNSAT establishes only the encoded bounded transition obligations under these assumptions and therefore yields PROVED_UNDER_ASSUMPTIONS, never unconditional proof or certification.",
] as const;

const blockModelKeys: Readonly<Record<InteractionBlockId, keyof BoundedFrontendInteractionModel>> = {
  "route-navigation-deeplink-404": "navigation",
  "component-template-view": "componentTemplate",
  "state-management": "stateManagement",
  "action-event": "actionEvent",
  "effect-lifecycle": "effectLifecycle",
  "form-binding-validation": "formBindingValidation",
  "api-network": "apiNetwork",
  "identity-permission": "identityPermission",
  "rendering-hydration": "renderingHydration",
  "accessibility-focus": "accessibilityFocus",
  "i18n-theme-responsive": "i18nThemeResponsive",
  "native-platform": "nativePlatform",
};

const codePointCompare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => codePointCompare(left, right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function bytesDigest(value: string | Buffer): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function artifactBytes(value: unknown): string {
  return typeof value === "string" ? value : `${JSON.stringify(value, null, 2)}\n`;
}

function artifactDigest(value: unknown): string {
  return bytesDigest(artifactBytes(value));
}

function pointerEscape(value: string): string {
  return value.replaceAll("~", "~0").replaceAll("/", "~1");
}

function collectPointers(value: unknown, pointer = "", result: string[] = []): string[] {
  result.push(pointer);
  if (Array.isArray(value)) value.forEach((item, index) => collectPointers(item, `${pointer}/${index}`, result));
  else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value as Record<string, unknown>).sort(codePointCompare)) {
      collectPointers((value as Record<string, unknown>)[key], `${pointer}/${pointerEscape(key)}`, result);
    }
  }
  return result;
}

function resolvePointer(value: unknown, pointer: string): unknown {
  if (pointer === "") return value;
  let current = value;
  for (const raw of pointer.slice(1).split("/")) {
    const key = raw.replaceAll("~1", "/").replaceAll("~0", "~");
    if (Array.isArray(current)) current = current[Number(key)];
    else if (current !== null && typeof current === "object" && Object.hasOwn(current, key)) current = (current as Record<string, unknown>)[key];
    else throw new Error(`unresolved RFC6901 pointer: ${pointer}`);
  }
  return current;
}

function byteOffset(text: string, characterOffset: number): number {
  return Buffer.byteLength(text.slice(0, characterOffset), "utf8");
}

function unwrapExpression(node: ts.Expression): ts.Expression {
  let current = node;
  while (ts.isAsExpression(current) || ts.isTypeAssertionExpression(current) || ts.isParenthesizedExpression(current) || ts.isSatisfiesExpression(current)) current = current.expression;
  return current;
}

function propertyName(node: ts.PropertyName): string {
  if (ts.isIdentifier(node) || ts.isPrivateIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text;
  throw new Error("computed property is outside bounded interaction grammar");
}

function parseLiteral(
  node: ts.Expression,
  source: ts.SourceFile,
  sourcePath: string,
  pointer: string,
  spans: Record<string, SourceByteSpan>,
): unknown {
  const expression = unwrapExpression(node);
  const start = expression.getStart(source);
  const end = expression.getEnd();
  const raw = source.text.slice(start, end);
  const record = (value: unknown): unknown => {
    spans[pointer] = {
      path: sourcePath,
      start_byte: byteOffset(source.text, start),
      end_byte: byteOffset(source.text, end),
      content_hash: bytesDigest(raw),
      subtree_hash: frontendFormalDigest(value),
    };
    return value;
  };
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) return record(expression.text);
  if (ts.isNumericLiteral(expression)) return record(Number(expression.text));
  if (expression.kind === ts.SyntaxKind.TrueKeyword) return record(true);
  if (expression.kind === ts.SyntaxKind.FalseKeyword) return record(false);
  if (expression.kind === ts.SyntaxKind.NullKeyword) return record(null);
  if (ts.isArrayLiteralExpression(expression)) {
    return record(expression.elements.map((element, index) => {
      if (ts.isSpreadElement(element)) throw new Error("spread is outside bounded interaction grammar");
      return parseLiteral(element, source, sourcePath, `${pointer}/${index}`, spans);
    }));
  }
  if (ts.isObjectLiteralExpression(expression)) {
    const result: Record<string, unknown> = {};
    for (const member of expression.properties) {
      if (!ts.isPropertyAssignment(member)) throw new Error("non-property member is outside bounded interaction grammar");
      const key = propertyName(member.name);
      if (Object.hasOwn(result, key)) throw new Error(`duplicate bounded interaction property: ${key}`);
      result[key] = parseLiteral(member.initializer, source, sourcePath, `${pointer}/${pointerEscape(key)}`, spans);
    }
    return record(result);
  }
  throw new Error(`unsupported bounded interaction literal: ${ts.SyntaxKind[expression.kind]}`);
}

function validateModel(value: unknown, profile: UiFrameworkId): BoundedFrontendInteractionModel {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("bounded interaction model must be an object");
  const model = value as BoundedFrontendInteractionModel;
  const rootKeys = ["schemaVersion", "profile", "projectTitle", ...Object.values(blockModelKeys)].sort(codePointCompare);
  if (Object.keys(value).sort(codePointCompare).join("|") !== rootKeys.join("|")
    || model.schemaVersion !== "1.0" || model.profile !== "bounded-frontend-interaction-v1"
    || typeof model.projectTitle !== "string" || model.projectTitle.length === 0) throw new Error("bounded interaction root identity/shape drifted");
  if (!Array.isArray(model.navigation.routes) || model.navigation.routes.length === 0) throw new Error("bounded interaction routes are required");
  const routeIds = new Set<string>(); const routePaths = new Set<string>();
  for (const [index, route] of model.navigation.routes.entries()) {
    if (!route || Object.keys(route).sort(codePointCompare).join("|") !== "deepLink|id|path|requiresAuth|text|title"
      || typeof route.id !== "string" || typeof route.path !== "string" || typeof route.title !== "string" || typeof route.text !== "string"
      || typeof route.requiresAuth !== "boolean" || typeof route.deepLink !== "boolean") throw new Error(`bounded interaction route ${index} drifted`);
    if (routeIds.has(route.id) || routePaths.has(route.path)) throw new Error("bounded interaction route identity is duplicated");
    routeIds.add(route.id); routePaths.add(route.path);
  }
  const baseline = canonicalBoundedFrontendInteractionModel(boundedInteractionFixtureRequest(profile));
  for (const key of Object.values(blockModelKeys).filter(key => key !== "navigation")) {
    if (canonical(model[key]) !== canonical(baseline[key])) throw new Error(`bounded interaction ${String(key)} profile drifted`);
  }
  if (model.navigation.label !== baseline.navigation.label || model.navigation.fallback !== baseline.navigation.fallback) throw new Error("bounded interaction navigation profile drifted");
  return model;
}

function tsRelift(profile: UiFrameworkId, path: string, text: string): { model: BoundedFrontendInteractionModel; spans: Readonly<Record<string, SourceByteSpan>> } {
  const kind = path.endsWith(".js") ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind);
  const diagnostics = (source as ts.SourceFile & { readonly parseDiagnostics?: readonly ts.Diagnostic[] }).parseDiagnostics ?? [];
  if (diagnostics.length > 0) throw new Error(`interaction source parse failed for ${profile}`);
  let initializer: ts.Expression | undefined;
  for (const statement of source.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name) && declaration.name.text === "ELMOS_FRONTEND_INTERACTION") initializer = declaration.initializer;
    }
  }
  if (!initializer) throw new Error("ELMOS_FRONTEND_INTERACTION declaration is missing");
  const spans: Record<string, SourceByteSpan> = {};
  const model = validateModel(parseLiteral(initializer, source, path, "", spans), profile);
  return { model, spans };
}

function dartRelift(profile: UiFrameworkId, path: string, text: string): { model: BoundedFrontendInteractionModel; spans: Readonly<Record<string, SourceByteSpan>> } {
  const match = /const String elmosFrontendInteractionBase64 = "([A-Za-z0-9+/=]+)";/.exec(text);
  if (!match || match.index < 0 || !match[1]) throw new Error("Dart bounded interaction payload is missing");
  const decoded = Buffer.from(match[1], "base64").toString("utf8");
  if (Buffer.from(decoded, "utf8").toString("base64") !== match[1]) throw new Error("Dart bounded interaction payload is not canonical base64");
  const model = validateModel(JSON.parse(decoded), profile);
  const start = match.index + match[0].indexOf(match[1]); const end = start + match[1].length;
  const spans: Record<string, SourceByteSpan> = {};
  for (const pointer of collectPointers(model)) {
    spans[pointer] = { path, start_byte: byteOffset(text, start), end_byte: byteOffset(text, end), content_hash: bytesDigest(text.slice(start, end)), subtree_hash: frontendFormalDigest(resolvePointer(model, pointer)) };
  }
  return { model, spans };
}

function navigationProjection(model: BoundedFrontendInteractionModel): BoundedNavigationSemanticModel {
  return {
    schemaVersion: "1.0", profile: "bounded-navigation-v1", projectTitle: model.projectTitle,
    navigation: { label: model.navigation.label },
    render: { mainRole: model.accessibilityFocus.mainRole, headingLevel: model.accessibilityFocus.headingLevel },
    fallback: { strategy: model.navigation.fallback }, routes: model.navigation.routes,
  };
}

export function reliftBoundedInteractionProject(
  profile: UiFrameworkId,
  files: Readonly<Record<string, string>>,
): ReliftedBoundedFrontendInteraction {
  const spec = interactionSourceSpec(profile);
  const text = files[spec.sourcePath];
  if (text === undefined) throw new Error(`interaction source is missing: ${spec.sourcePath}`);
  const parsed = spec.parser === "TYPESCRIPT_AST" ? tsRelift(profile, spec.sourcePath, text) : dartRelift(profile, spec.sourcePath, text);
  if (text !== interactionContractSource(profile, parsed.model)) throw new Error("bounded interaction reducer/source grammar drifted");
  if (files[spec.compatibilityPath] !== navigationCompatibilitySource(profile)) throw new Error("bounded navigation compatibility is not the direct identity projection");
  for (const [path, content] of Object.entries(files)) {
    if (path !== spec.sourcePath && /(?:ELMOS_FRONTEND_INTERACTION|elmosFrontendInteraction)\s*=/.test(content)) {
      throw new Error(`duplicate bounded interaction contract literal: ${path}`);
    }
  }
  const navigation = navigationProjection(parsed.model);
  const expectedBase = expectedBoundedNavigationConsumerFiles(profile, navigation, files);
  const expected = augmentBoundedInteractionFiles(profile, parsed.model, { ...files, ...expectedBase });
  const paths = new Set([...boundedNavigationGeneratedConsumerPaths(profile), ...boundedInteractionConsumerPaths(profile)]);
  for (const path of paths) {
    if (files[path] === undefined || files[path] !== expected[path]) throw new Error(`reachable bounded interaction consumer grammar drifted: ${profile}:${path}`);
  }
  const blockDigests = Object.fromEntries(interactionBlockIds.map(blockId => [blockId, frontendFormalDigest(parsed.model[blockModelKeys[blockId]])])) as Record<InteractionBlockId, string>;
  return {
    schema_version: "1.0", proof_profile: "bounded-frontend-interaction-v1", profile_id: profile,
    parser: spec.parser, source_path: spec.sourcePath, source_hash: bytesDigest(text), model: parsed.model,
    model_digest: frontendFormalDigest(parsed.model), block_digests: blockDigests, spans: parsed.spans,
    consumer_binding: {
      sole_contract_literal: true, navigation_identity_projection: true, reducer_reachable: true,
      state_dispatch_reachable: true, effect_command_reachable: true, form_and_focus_reachable: true,
      api_adapter_reachable: true, identity_tenant_guard_reachable: true, hydration_observation_reachable: true,
      i18n_theme_viewport_reachable: true, native_adapter_reachable: true, strict_generated_grammar: true,
    },
  };
}

/** A deliberately separate table reducer. It is same-engine, not independent. */
export function referenceObserveBoundedInteraction(
  model: BoundedFrontendInteractionModel,
  scenario: InteractionScenario,
): InteractionObservation {
  const input = scenario.input;
  const routes = [...model.navigation.routes];
  const first = routes.at(0);
  if (!first) throw new Error("reference reducer requires a route");
  const requested = routes.filter(route => route.path === input.routePath).at(0) ?? first;
  const tenantMatch = model.identityPermission.tenantIsolation === "EXACT_TENANT_MATCH"
    && input.tenantId === input.resourceTenantId;
  const allowed = (route: typeof first): boolean => !route.requiresAuth
    || (input.authenticated && input.permissionGranted && tenantMatch);
  const authorized = allowed(requested); const selected = authorized ? requested : first;
  const query = input.query === "" ? model.formBindingValidation.initialValue : input.query;
  const submitted = input.event === "SUBMIT" || input.keyboardKey === model.actionEvent.keyboardSubmit;
  const validated = model.formBindingValidation.validation !== "ON_SUBMIT" || submitted;
  const valid = (!model.formBindingValidation.required || query.length > 0)
    && query.length >= model.formBindingValidation.minimumLength;
  const apiCalled = validated && valid && authorized;
  const canceled = input.event === "CANCEL" || (model.apiNetwork.cancelOnUnmount && input.lifecycle === "UNMOUNT");
  const staleIgnored = canceled && input.networkResult === "STALE"
    && model.effectLifecycle.staleResponsePolicy === "IGNORE_AFTER_CANCEL";
  const baseCounter = Math.max(input.counterBefore, model.stateManagement.initial);
  const rawCounter = baseCounter + input.incrementCount;
  const nextCounter = model.stateManagement.transition === "SATURATING_INCREMENT"
    ? Math.max(model.stateManagement.minimum, Math.min(model.stateManagement.maximum, rawCounter)) : baseCounter;
  const formError = validated && !valid ? model.formBindingValidation.invalidCode : null;
  const focusTarget = formError ? model.accessibilityFocus.invalidFocusTarget : submitted ? "result" : null;
  const locale = new Set<string>(model.i18nThemeResponsive.supportedLocales).has(input.locale)
    ? input.locale : model.i18nThemeResponsive.fallbackLocale;
  const theme = new Set<string>(model.i18nThemeResponsive.themes).has(input.theme)
    ? input.theme : model.i18nThemeResponsive.defaultTheme;
  const nativeTarget = input.deepLinkPath === null ? null : routes.filter(route => route.path === input.deepLinkPath).at(0) ?? first;
  const nativeTargetAuthorized = nativeTarget === null || allowed(nativeTarget);
  const nativeAttempted = input.event === "NATIVE_DEEPLINK" && input.deepLinkPath !== null
    && model.nativePlatform.capability === "OPEN_DEEP_LINK";
  const nativeLifecycleKnown = new Set<string>(model.nativePlatform.lifecycleStates).has(input.nativeLifecycle);
  const nativeAllowed = nativeAttempted && nativeTargetAuthorized && input.nativeAvailable
    && input.nativePermission === "GRANTED" && input.nativeLifecycle === "FOREGROUND" && nativeLifecycleKnown;
  const hydrationStatus = input.hydration === "MISMATCH" && model.renderingHydration.hydrationPolicy === "REQUIRE_MATCH"
    ? model.renderingHydration.mismatchBehavior : input.hydration === "MATCH" ? "MATCHED" : "NOT_ATTEMPTED";
  const networkOutcome = !apiCalled ? "NOT_CALLED" : canceled ? "CANCELED"
    : input.networkResult === "SUCCESS" ? "SUCCESS" : input.networkResult === "ERROR" ? "ERROR" : "PENDING";
  const resolution = requested === first && input.routePath !== first.path ? "FIRST_DECLARED_FALLBACK"
    : authorized ? "DECLARED" : "AUTH_DENIED_FALLBACK";
  return {
    scenarioId: scenario.scenarioId,
    before: { counter: input.counterBefore, lifecycle: input.lifecycle, query: input.query, authenticated: input.authenticated },
    after: { counter: nextCounter, selectedRouteId: selected.id, authorized, apiCalled, focusTarget, nativeAllowed },
    blocks: {
      "route-navigation-deeplink-404": { requestedPath: input.routePath, selectedRouteId: selected.id, selectedPath: selected.path, resolution, navigationLabel: model.navigation.label, fallback: model.navigation.fallback, deepLink: selected.deepLink, requiresAuth: selected.requiresAuth },
      "component-template-view": { componentId: model.componentTemplate.componentId, templateKind: model.componentTemplate.templateKind, keyedBy: model.componentTemplate.keyedBy, titleBinding: model.componentTemplate.titleBinding, textBinding: model.componentTemplate.textBinding, key: model.componentTemplate.keyedBy === "route.id" ? selected.id : "", title: model.componentTemplate.titleBinding === "route.title" ? selected.title : "", text: model.componentTemplate.textBinding === "route.text" ? selected.text : "", visible: true },
      "state-management": { stateId: model.stateManagement.stateId, initial: model.stateManagement.initial, minimum: model.stateManagement.minimum, maximum: model.stateManagement.maximum, transition: model.stateManagement.transition, before: input.counterBefore, after: nextCounter, saturated: rawCounter > model.stateManagement.maximum },
      "action-event": { event: input.event, keyboardKey: input.keyboardKey, handled: new Set<string>(model.actionEvent.acceptedEvents).has(input.event), action: submitted ? (valid && authorized ? "SUBMIT_ACCEPTED" : model.actionEvent.deniedAction) : input.event },
      "effect-lifecycle": { lifecycle: input.lifecycle, mountEffect: input.lifecycle === "MOUNT" ? model.effectLifecycle.mountEffect : "NONE", cleanupEffect: input.lifecycle === "UNMOUNT" ? model.effectLifecycle.cleanupEffect : "NONE", maxExecutionsPerMount: model.effectLifecycle.maxExecutionsPerMount, staleResponsePolicy: model.effectLifecycle.staleResponsePolicy, executions: input.lifecycle === "MOUNT" ? model.effectLifecycle.maxExecutionsPerMount : 0, cleanup: input.lifecycle === "UNMOUNT", staleResponseIgnored: staleIgnored },
      "form-binding-validation": { formId: model.formBindingValidation.formId, fieldId: model.formBindingValidation.fieldId, initialValue: model.formBindingValidation.initialValue, required: model.formBindingValidation.required, minimumLength: model.formBindingValidation.minimumLength, validation: model.formBindingValidation.validation, value: query, submitted, validated, valid, errorCode: formError },
      "api-network": { operationId: model.apiNetwork.operationId, called: apiCalled, method: model.apiNetwork.method, path: model.apiNetwork.path, timeoutMs: model.apiNetwork.timeoutMs, retry: model.apiNetwork.retry, cacheScope: model.apiNetwork.cacheScope, cancelOnUnmount: model.apiNetwork.cancelOnUnmount, outcome: networkOutcome, canceled, staleIgnored, cacheKey: model.apiNetwork.cacheScope === "TENANT_QUERY" ? `${input.tenantId}:${query}` : query },
      "identity-permission": { role: input.authenticated ? model.identityPermission.authenticatedRole : model.identityPermission.anonymousRole, permission: model.identityPermission.requiredPermission, permissionGranted: input.permissionGranted, deniedBehavior: model.identityPermission.deniedBehavior, tenantIsolation: model.identityPermission.tenantIsolation, tenantMatch, authorized, serverAuthorityRequired: model.identityPermission.serverAuthorityRequired },
      "rendering-hydration": { mode: model.renderingHydration.mode, hydrationPolicy: model.renderingHydration.hydrationPolicy, requested: input.hydration, status: hydrationStatus, duplicateEffectsAllowed: model.renderingHydration.duplicateEffectsAllowed, duplicateEffects: model.renderingHydration.duplicateEffectsAllowed && input.hydration === "MISMATCH", mismatchVisible: input.hydration === "MISMATCH" },
      "accessibility-focus": { mainRole: model.accessibilityFocus.mainRole, headingLevel: model.accessibilityFocus.headingLevel, formLabel: model.accessibilityFocus.formLabel, errorRole: formError === null ? null : model.accessibilityFocus.errorRole, liveRegion: model.accessibilityFocus.liveRegion, keyboardSubmit: input.keyboardKey === model.accessibilityFocus.keyboardSubmit, focusTarget },
      "i18n-theme-responsive": { requestedLocale: input.locale, localeSupported: new Set<string>(model.i18nThemeResponsive.supportedLocales).has(input.locale), locale, requestedTheme: input.theme, themeSupported: new Set<string>(model.i18nThemeResponsive.themes).has(input.theme), theme, viewportWidth: input.viewportWidth, columns: input.viewportWidth <= model.i18nThemeResponsive.compactBreakpoint ? model.i18nThemeResponsive.compactColumns : model.i18nThemeResponsive.wideColumns },
      "native-platform": { boundary: model.nativePlatform.boundary, capability: model.nativePlatform.capability, lifecycleStates: model.nativePlatform.lifecycleStates.join("|"), lifecycle: input.nativeLifecycle, lifecycleKnown: nativeLifecycleKnown, deepLinkPath: input.deepLinkPath, targetRouteId: nativeTarget?.id ?? null, targetAuthorized: nativeTargetAuthorized, attempted: nativeAttempted, permissionContract: model.nativePlatform.permission, permission: input.nativePermission, available: input.nativeAvailable, deniedBehavior: model.nativePlatform.deniedBehavior, outcome: !nativeAttempted ? "NOT_ATTEMPTED" : nativeAllowed ? "OPENED" : model.nativePlatform.deniedBehavior, recovery: nativeAllowed ? "NOT_REQUIRED" : model.nativePlatform.recovery },
    },
  };
}

function behaviorComparable(values: readonly InteractionObservation[]): unknown {
  return values;
}

export function observeInteractionScenarioSet(
  model: BoundedFrontendInteractionModel,
  kind: "canonical" | "source" | "target" | "reference",
): readonly InteractionObservation[] {
  const scenarios = boundedInteractionScenarios(model);
  return scenarios.map(scenario => kind === "reference"
    ? referenceObserveBoundedInteraction(model, scenario)
    : observeBoundedFrontendInteraction(model, scenario));
}

type SmtSort = "String" | "Bool" | "Int";
interface SmtOutput { readonly name: string; readonly sort: SmtSort; readonly expression: string }

function smtString(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

function smtLiteral(value: string | boolean | number, sort: SmtSort): string {
  if (sort === "String") return smtString(String(value));
  if (sort === "Bool") return value ? "true" : "false";
  return String(value);
}

function routeSelector(
  model: BoundedFrontendInteractionModel,
  field: keyof BoundedFrontendInteractionModel["navigation"]["routes"][number],
  sort: "String" | "Bool",
): string {
  const first = model.navigation.routes[0]!;
  let value = smtLiteral(first[field], sort);
  for (const route of [...model.navigation.routes].reverse()) {
    value = `(ite (= route_path ${smtString(route.path)}) ${smtLiteral(route[field], sort)} ${value})`;
  }
  return value;
}

function interactionSymbolicOutputs(
  model: BoundedFrontendInteractionModel,
  blockId: InteractionBlockId,
): readonly SmtOutput[] {
  const requestedId = routeSelector(model, "id", "String");
  const requestedPath = routeSelector(model, "path", "String");
  const requestedTitle = routeSelector(model, "title", "String");
  const requestedText = routeSelector(model, "text", "String");
  const requestedAuth = routeSelector(model, "requiresAuth", "Bool");
  const requestedDeep = routeSelector(model, "deepLink", "Bool");
  const first = model.navigation.routes[0]!;
  const tenantMatch = model.identityPermission.tenantIsolation === "EXACT_TENANT_MATCH" ? "tenant_match" : "false";
  const authorized = `(or (not ${requestedAuth}) (and authenticated permission_granted ${tenantMatch}))`;
  const select = (requested: string, fallback: string): string => `(ite ${authorized} ${requested} ${fallback})`;
  const selectedId = select(requestedId, smtString(first.id));
  const selectedPath = select(requestedPath, smtString(first.path));
  const selectedTitle = select(requestedTitle, smtString(first.title));
  const selectedText = select(requestedText, smtString(first.text));
  const selectedAuth = select(requestedAuth, first.requiresAuth ? "true" : "false");
  const selectedDeep = select(requestedDeep, first.deepLink ? "true" : "false");
  const submitted = `(or (= event 3) keyboard_submit)`;
  const boundQuery = `(ite (= (str.len query) 0) ${smtString(model.formBindingValidation.initialValue)} query)`;
  const required = model.formBindingValidation.required ? `(> (str.len ${boundQuery}) 0)` : "true";
  const valid = `(and ${required} (>= (str.len ${boundQuery}) ${model.formBindingValidation.minimumLength}))`;
  const validated = model.formBindingValidation.validation === "ON_SUBMIT" ? submitted : "true";
  const apiCalled = `(and ${validated} ${valid} ${authorized})`;
  const canceled = `(or (= event 4) ${model.apiNetwork.cancelOnUnmount ? "(= lifecycle 2)" : "false"})`;
  const counterBase = `(ite (> counter_before ${model.stateManagement.initial}) counter_before ${model.stateManagement.initial})`;
  const rawCounter = `(+ ${counterBase} increment_count)`;
  const afterCounter = model.stateManagement.transition === "SATURATING_INCREMENT"
    ? `(ite (< ${rawCounter} ${model.stateManagement.minimum}) ${model.stateManagement.minimum} (ite (> ${rawCounter} ${model.stateManagement.maximum}) ${model.stateManagement.maximum} ${rawCounter}))`
    : counterBase;
  const nativeTargetAuth = routeSelector(model, "requiresAuth", "Bool").replaceAll("route_path", "deep_link_path");
  const nativeAuthorized = `(or (not ${nativeTargetAuth}) (and authenticated permission_granted ${tenantMatch}))`;
  const nativeKnown = model.nativePlatform.lifecycleStates.includes("FOREGROUND") ? "true" : "false";
  const nativeAttempted = model.nativePlatform.capability === "OPEN_DEEP_LINK" ? "has_deep_link" : "false";
  const nativeAllowed = `(and ${nativeAttempted} native_available native_permission_granted native_foreground ${nativeKnown} ${nativeAuthorized})`;
  switch (blockId) {
    case "route-navigation-deeplink-404": return [
      { name: "selected_id", sort: "String", expression: selectedId },
      { name: "selected_path", sort: "String", expression: selectedPath },
      { name: "selected_auth", sort: "Bool", expression: selectedAuth },
      { name: "selected_deep", sort: "Bool", expression: selectedDeep },
      { name: "resolution", sort: "Int", expression: `(ite ${authorized} (ite (= ${requestedPath} route_path) 0 1) 2)` },
    ];
    case "component-template-view": return [
      { name: "key", sort: "String", expression: model.componentTemplate.keyedBy === "route.id" ? selectedId : smtString("") },
      { name: "title", sort: "String", expression: model.componentTemplate.titleBinding === "route.title" ? selectedTitle : smtString("") },
      { name: "text", sort: "String", expression: model.componentTemplate.textBinding === "route.text" ? selectedText : smtString("") },
    ];
    case "state-management": return [
      { name: "after", sort: "Int", expression: afterCounter },
      { name: "saturated", sort: "Bool", expression: `(> ${rawCounter} ${model.stateManagement.maximum})` },
    ];
    case "action-event": return [
      { name: "handled", sort: "Bool", expression: `(and (>= event 0) (< event ${model.actionEvent.acceptedEvents.length}))` },
      { name: "accepted", sort: "Bool", expression: `(and ${submitted} ${valid} ${authorized})` },
      { name: "denied_action", sort: "String", expression: `(ite (and ${submitted} (not (and ${valid} ${authorized}))) ${smtString(model.actionEvent.deniedAction)} ${smtString("NONE")})` },
    ];
    case "effect-lifecycle": return [
      { name: "executions", sort: "Int", expression: `(ite (= lifecycle 0) ${model.effectLifecycle.maxExecutionsPerMount} 0)` },
      { name: "cleanup", sort: "Bool", expression: "(= lifecycle 2)" },
      { name: "stale_ignored", sort: "Bool", expression: model.effectLifecycle.staleResponsePolicy === "IGNORE_AFTER_CANCEL" ? `(and (= network_result 3) ${canceled})` : "false" },
    ];
    case "form-binding-validation": return [
      { name: "valid", sort: "Bool", expression: valid },
      { name: "validated", sort: "Bool", expression: validated },
      { name: "error", sort: "String", expression: `(ite (and ${validated} (not ${valid})) ${smtString(model.formBindingValidation.invalidCode)} ${smtString("")})` },
    ];
    case "api-network": return [
      { name: "called", sort: "Bool", expression: apiCalled },
      { name: "canceled", sort: "Bool", expression: canceled },
      { name: "outcome", sort: "Int", expression: `(ite (not ${apiCalled}) 0 (ite ${canceled} 1 (ite (= network_result 1) 2 (ite (= network_result 2) 3 4))))` },
      { name: "cache_key", sort: "String", expression: model.apiNetwork.cacheScope === "TENANT_QUERY" ? `(str.++ tenant_id ${smtString(":")} ${boundQuery})` : boundQuery },
    ];
    case "identity-permission": return [
      { name: "tenant_match", sort: "Bool", expression: tenantMatch },
      { name: "authorized", sort: "Bool", expression: authorized },
      { name: "role", sort: "String", expression: `(ite authenticated ${smtString(model.identityPermission.authenticatedRole)} ${smtString(model.identityPermission.anonymousRole)})` },
    ];
    case "rendering-hydration": return [
      { name: "status", sort: "Int", expression: model.renderingHydration.hydrationPolicy === "REQUIRE_MATCH" ? "(ite (= hydration 2) 2 (ite (= hydration 1) 1 0))" : "(ite (= hydration 1) 1 0)" },
      { name: "duplicate", sort: "Bool", expression: model.renderingHydration.duplicateEffectsAllowed ? "(= hydration 2)" : "false" },
    ];
    case "accessibility-focus": return [
      { name: "focus_query", sort: "Bool", expression: `(and ${validated} (not ${valid}))` },
      { name: "error_live", sort: "Bool", expression: `(and ${validated} (not ${valid}) ${model.accessibilityFocus.liveRegion === "polite" ? "true" : "false"})` },
      { name: "keyboard_submit", sort: "Bool", expression: "keyboard_submit" },
    ];
    case "i18n-theme-responsive": {
      let locale = smtString(model.i18nThemeResponsive.fallbackLocale);
      for (const value of [...model.i18nThemeResponsive.supportedLocales].reverse()) locale = `(ite (= locale_input ${smtString(value)}) ${smtString(value)} ${locale})`;
      let theme = smtString(model.i18nThemeResponsive.defaultTheme);
      for (const value of [...model.i18nThemeResponsive.themes].reverse()) theme = `(ite (= theme_input ${smtString(value)}) ${smtString(value)} ${theme})`;
      return [
        { name: "locale_supported", sort: "Bool", expression: `(or ${model.i18nThemeResponsive.supportedLocales.map(value => `(= locale_input ${smtString(value)})`).join(" ")})` },
        { name: "locale", sort: "String", expression: locale },
        { name: "theme_supported", sort: "Bool", expression: `(or ${model.i18nThemeResponsive.themes.map(value => `(= theme_input ${smtString(value)})`).join(" ")})` },
        { name: "theme", sort: "String", expression: theme },
        { name: "columns", sort: "Int", expression: `(ite (<= viewport_width ${model.i18nThemeResponsive.compactBreakpoint}) ${model.i18nThemeResponsive.compactColumns} ${model.i18nThemeResponsive.wideColumns})` },
      ];
    }
    case "native-platform": return [
      { name: "attempted", sort: "Bool", expression: nativeAttempted },
      { name: "allowed", sort: "Bool", expression: nativeAllowed },
      { name: "outcome", sort: "Int", expression: `(ite (not ${nativeAttempted}) 0 (ite ${nativeAllowed} 1 2))` },
    ];
  }
}

function smtDeclarations(): readonly string[] {
  return [
    "(declare-const route_path String)", "(declare-const deep_link_path String)", "(declare-const has_deep_link Bool)",
    "(declare-const event Int)", "(declare-const counter_before Int)", "(declare-const increment_count Int)",
    "(declare-const lifecycle Int)", "(declare-const query String)", "(declare-const keyboard_submit Bool)",
    "(declare-const authenticated Bool)", "(declare-const permission_granted Bool)", "(declare-const tenant_match Bool)",
    "(declare-const tenant_id String)", "(declare-const network_result Int)", "(declare-const hydration Int)",
    "(declare-const locale_input String)", "(declare-const theme_input String)", "(declare-const viewport_width Int)",
    "(declare-const native_foreground Bool)", "(declare-const native_permission_granted Bool)", "(declare-const native_available Bool)",
    "(assert (and (>= event 0) (<= event 7)))", "(assert (and (>= counter_before 0) (<= counter_before 2)))",
    "(assert (and (>= increment_count 0) (<= increment_count 3)))", "(assert (and (>= lifecycle 0) (<= lifecycle 2)))",
    "(assert (and (>= network_result 0) (<= network_result 3)))", "(assert (and (>= hydration 0) (<= hydration 2)))",
    "(assert (and (>= viewport_width 0) (<= viewport_width 4096)))",
  ];
}

export function buildInteractionSmt2(
  canonicalModel: BoundedFrontendInteractionModel,
  sourceModel: BoundedFrontendInteractionModel,
  targetModel: BoundedFrontendInteractionModel,
  referenceModel: BoundedFrontendInteractionModel,
  formalInputDigest = "UNBOUND_FORMAL_INPUT",
): string {
  const models = [canonicalModel, sourceModel, targetModel, referenceModel] as const;
  const prefixes = ["canonical", "source", "target", "reference"] as const;
  const lines = [
    "; ELMOS bounded-frontend-interaction-v1 symbolic block equivalence",
    `; formal-input-bytes-digest: ${formalInputDigest}`,
    "; Same-engine self-consistency only; framework/runtime/native soundness is outside this formula.",
    "(set-logic ALL)", ...smtDeclarations(),
  ];
  const blockDiffs: string[] = [];
  for (const blockId of interactionBlockIds) {
    const symbol = interactionBlockSymbolMap[blockId];
    const outputs = models.map(model => interactionSymbolicOutputs(model, blockId));
    if (new Set(outputs[0]!.map(output => output.name)).size !== outputs[0]!.length) throw new Error(`duplicate SMT output name for ${blockId}`);
    const behaviorDiffs: string[] = [];
    for (const [index, output] of outputs[0]!.entries()) {
      for (const [modelIndex, prefix] of prefixes.entries()) {
        const current = outputs[modelIndex]![index]!;
        if (current.name !== output.name || current.sort !== output.sort) throw new Error(`SMT output shape diverged for ${blockId}`);
        lines.push(`(define-fun ${prefix}_${symbol}_${output.name} () ${output.sort} ${current.expression})`);
      }
      behaviorDiffs.push(`(not (= canonical_${symbol}_${output.name} source_${symbol}_${output.name}))`);
      behaviorDiffs.push(`(not (= canonical_${symbol}_${output.name} target_${symbol}_${output.name}))`);
      behaviorDiffs.push(`(not (= canonical_${symbol}_${output.name} reference_${symbol}_${output.name}))`);
    }
    const semanticDigests = models.map(model => frontendFormalDigest(model[blockModelKeys[blockId]]));
    lines.push(`(define-fun behavior_diff_${symbol} () Bool (or ${behaviorDiffs.join(" ")}))`);
    lines.push(`(define-fun semantic_diff_${symbol} () Bool (or (not (= ${smtString(semanticDigests[0]!)} ${smtString(semanticDigests[1]!)})) (not (= ${smtString(semanticDigests[0]!)} ${smtString(semanticDigests[2]!)})) (not (= ${smtString(semanticDigests[0]!)} ${smtString(semanticDigests[3]!)}))))`);
    lines.push(`(define-fun diff_${symbol} () Bool (or semantic_diff_${symbol} behavior_diff_${symbol}))`);
    blockDiffs.push(`diff_${symbol}`);
  }
  lines.push(`(assert (or ${blockDiffs.join(" ")}))`, "(check-sat)", "(exit)", "");
  return lines.join("\n");
}

export function buildInteractionVacuitySmt2(formalInputDigest = "UNBOUND_FORMAL_INPUT"): string {
  const lines = [
    "; ELMOS bounded-frontend-interaction-v1 per-block assumption/vacuity precheck",
    `; formal-input-bytes-digest: ${formalInputDigest}`,
    "(set-logic ALL)", ...smtDeclarations(),
  ];
  for (const blockId of interactionBlockIds) {
    const symbol = interactionBlockSymbolMap[blockId];
    lines.push(`(define-fun assumption_${symbol} () Bool true)`);
    lines.push(`(assert assumption_${symbol})`);
  }
  lines.push("(check-sat)", "(exit)", "");
  return lines.join("\n");
}

function primitiveLeafPointers(value: unknown): readonly string[] {
  return collectPointers(value).filter(pointer => {
    if (pointer === "" || pointer === "/schemaVersion" || pointer === "/profile" || pointer === "/projectTitle") return false;
    const item = resolvePointer(value, pointer);
    return item === null || typeof item !== "object";
  });
}

function alternateLeaf(pointer: string, value: unknown): unknown {
  if (typeof value === "boolean") return !value;
  if (typeof value === "number") return value === 0 ? 1 : value + 1;
  if (typeof value === "string") {
    if (pointer.endsWith("/path")) return value === "/" ? "/mutant" : `${value}-mutant`;
    if (value === "LIGHT") return "DARK";
    if (value === "DARK") return "LIGHT";
    if (value === "FOREGROUND") return "BACKGROUND";
    if (value === "BACKGROUND") return "FOREGROUND";
    return `${value}__MUTANT`;
  }
  return "__MUTANT";
}

export function mutateInteractionModelAtPointer(
  model: BoundedFrontendInteractionModel,
  pointer: string,
): BoundedFrontendInteractionModel {
  if (!primitiveLeafPointers(model).includes(pointer)) throw new Error(`interaction mutation pointer is not a primitive semantic leaf: ${pointer}`);
  const clone = JSON.parse(JSON.stringify(model)) as Record<string, unknown>;
  const parts = pointer.slice(1).split("/").map(value => value.replaceAll("~1", "/").replaceAll("~0", "~"));
  let current: unknown = clone;
  for (const part of parts.slice(0, -1)) current = Array.isArray(current) ? current[Number(part)] : (current as Record<string, unknown>)[part];
  const leaf = parts.at(-1)!;
  if (Array.isArray(current)) current[Number(leaf)] = alternateLeaf(pointer, current[Number(leaf)]);
  else (current as Record<string, unknown>)[leaf] = alternateLeaf(pointer, (current as Record<string, unknown>)[leaf]);
  return clone as unknown as BoundedFrontendInteractionModel;
}

export interface InteractionCounterexample {
  readonly block_id: InteractionBlockId;
  readonly pointer: string;
  readonly influence_class: string;
  readonly scenario_id: string | null;
  readonly semantic_mutant_detected: boolean;
  readonly behavior_mutant_detected: boolean;
  readonly canonical_observation: unknown;
  readonly mutant_observation: unknown;
}

function pointerBlock(pointer: string): InteractionBlockId | undefined {
  if (/^\/navigation\/routes\/[0-9]+\/(?:title|text)$/.test(pointer)) return "component-template-view";
  return interactionBlockIds.find(blockId => pointer === `/${String(blockModelKeys[blockId])}` || pointer.startsWith(`/${String(blockModelKeys[blockId])}/`));
}

const mutationVariantKinds = ["SOURCE_ONLY", "TARGET_ONLY", "REFERENCE_ONLY"] as const;
type MutationVariantKind = (typeof mutationVariantKinds)[number];

function selectMutationWitness(
  counterexamples: readonly InteractionCounterexample[],
  blockId: InteractionBlockId,
): InteractionCounterexample {
  const blockRoot = `/${String(blockModelKeys[blockId])}`;
  const candidate = counterexamples.find(row => row.block_id === blockId
    && row.influence_class !== "DECLARATION_ECHO"
    && row.behavior_mutant_detected
    && (row.pointer === blockRoot || row.pointer.startsWith(`${blockRoot}/`)));
  if (!candidate) throw new Error(`bounded interaction block lacks an owned behavior mutant witness: ${blockId}`);
  if (pointerBlock(candidate.pointer) !== blockId) throw new Error(`bounded interaction mutation pointer is outside its block: ${blockId}`);
  return candidate;
}

function mutationModels(
  canonicalModel: BoundedFrontendInteractionModel,
  mutant: BoundedFrontendInteractionModel,
  variant: MutationVariantKind,
): readonly [BoundedFrontendInteractionModel, BoundedFrontendInteractionModel, BoundedFrontendInteractionModel, BoundedFrontendInteractionModel] {
  if (variant === "SOURCE_ONLY") return [canonicalModel, mutant, canonicalModel, canonicalModel];
  if (variant === "TARGET_ONLY") return [canonicalModel, canonicalModel, mutant, canonicalModel];
  return [canonicalModel, canonicalModel, canonicalModel, mutant];
}

function mutationFormalInput(
  canonicalModel: BoundedFrontendInteractionModel,
  mutant: BoundedFrontendInteractionModel,
  blockId: InteractionBlockId,
  variant: MutationVariantKind,
  candidate: InteractionCounterexample,
): Readonly<Record<string, unknown>> {
  return {
    schema_version: "1.0",
    kind: "bounded-interaction-seeded-mutation-formal-input",
    proof_profile: "bounded-frontend-interaction-v1",
    block_id: blockId,
    obligation_symbol: `diff_${interactionBlockSymbolMap[blockId]}`,
    variant,
    pointer: candidate.pointer,
    canonical_model_digest: frontendFormalDigest(canonicalModel),
    mutant_model_digest: frontendFormalDigest(mutant),
    canonical_block_digest: frontendFormalDigest(canonicalModel[blockModelKeys[blockId]]),
    mutant_block_digest: frontendFormalDigest(mutant[blockModelKeys[blockId]]),
    counterexample_replay: candidate,
    expected_solver_outcome: "SAT",
    oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE",
  };
}

export function interactionLeafCounterexamples(
  model: BoundedFrontendInteractionModel,
): readonly InteractionCounterexample[] {
  const scenarios = boundedInteractionScenarios(model);
  return primitiveLeafPointers(model).flatMap(pointer => {
    const blockId = pointerBlock(pointer);
    if (!blockId) return [];
    const mutant = mutateInteractionModelAtPointer(model, pointer);
    const routeCopy = /^\/navigation\/routes\/[0-9]+\/(?:title|text)$/.test(pointer);
    const classified = Object.entries(interactionInfluenceMatrix[blockId]).find(([root]) => pointer === root || pointer.startsWith(`${root}/`));
    const influence = routeCopy ? "TRANSITION" : classified?.[1] ?? "DECLARATION_ECHO";
    const found = influence === "DECLARATION_ECHO" ? undefined : scenarios.map(scenario => ({
      scenario,
      canonical: observeBoundedFrontendInteraction(model, scenario).blocks[blockId],
      mutant: observeBoundedFrontendInteraction(mutant, scenario).blocks[blockId],
    })).find(row => canonical(row.canonical) !== canonical(row.mutant));
    return [{
      block_id: blockId,
      pointer,
      influence_class: influence,
      scenario_id: found?.scenario.scenarioId ?? null,
      semantic_mutant_detected: frontendFormalDigest(model) !== frontendFormalDigest(mutant),
      behavior_mutant_detected: found !== undefined,
      canonical_observation: found?.canonical ?? null,
      mutant_observation: found?.mutant ?? null,
    }];
  });
}

interface InteractionProfileBundle {
  readonly project: ReturnType<typeof generateBoundedInteractionProject>;
  readonly relift: ReliftedBoundedFrontendInteraction;
  readonly canonical_model: BoundedFrontendInteractionModel;
  readonly project_digest: string;
  readonly source_fixture_bytes: string;
  readonly source_fixture_digest: string;
}

function projectDigest(files: Readonly<Record<string, string>>): string {
  return frontendFormalDigest(Object.fromEntries(Object.entries(files).sort(([left], [right]) => codePointCompare(left, right))));
}

function makeInteractionBundles(options: InteractionCampaignOptions): ReadonlyMap<UiFrameworkId, InteractionProfileBundle> {
  const bundles = new Map<UiFrameworkId, InteractionProfileBundle>();
  for (const profile of uiTargetProfiles()) {
    const request = boundedInteractionFixtureRequest(profile.id);
    const generated = generateBoundedInteractionProject(request);
    const files = { ...generated.files };
    if (options.tamper?.profile_id === profile.id) {
      const current = files[options.tamper.path];
      if (current === undefined || !current.includes(options.tamper.find)) throw new Error("requested interaction tamper target was not found");
      files[options.tamper.path] = current.replace(options.tamper.find, options.tamper.replace);
    }
    const project = { ...generated, files };
    const sourceBytes = boundedInteractionSourceFixtureBytes(request);
    bundles.set(profile.id, {
      project,
      relift: reliftBoundedInteractionProject(profile.id, files),
      canonical_model: canonicalBoundedFrontendInteractionModel(request),
      project_digest: projectDigest(files),
      source_fixture_bytes: sourceBytes,
      source_fixture_digest: bytesDigest(sourceBytes),
    });
  }
  return bundles;
}

function assertSafeRelative(path: string): void {
  if (!path || path.startsWith("/") || path.includes("\\") || path.split("/").includes("..")) throw new Error(`unsafe generated path: ${path}`);
}

function materializeProject(root: string, files: Readonly<Record<string, string>>): void {
  for (const [path, content] of Object.entries(files)) {
    assertSafeRelative(path);
    const destination = join(root, ...path.split("/"));
    mkdirSync(dirname(destination), { recursive: true }); writeFileSync(destination, content, "utf8");
  }
}

function writeArtifact(root: string, relativePath: string, value: unknown): string {
  assertSafeRelative(relativePath);
  const destination = join(root, ...relativePath.split("/")); mkdirSync(dirname(destination), { recursive: true });
  const content = artifactBytes(value); writeFileSync(destination, content, "utf8"); return bytesDigest(content);
}

function runtimeDriverContract(profile: UiFrameworkId, model: BoundedFrontendInteractionModel): Readonly<Record<string, unknown>> {
  const channels = requiredRuntimeChannels(profile);
  const browserDom = !["flutter", "harmony-arkui"].includes(profile);
  const binding = profile === "react" ? "REACT_HOOKS_COMPONENT" : profile === "vue2" ? "VUE2_OPTIONS_COMPONENT"
    : profile === "vue3" ? "VUE3_COMPOSITION_COMPONENT" : profile === "angular" ? "ANGULAR_SIGNAL_COMPONENT"
      : profile === "svelte" ? "SVELTE_COMPONENT_STATE" : profile === "jquery" ? "JQUERY_NAMESPACED_EVENTS_DATA"
        : profile === "react-native" ? "REACT_NATIVE_HOOKS_COMPONENT" : profile === "flutter" ? "FLUTTER_STATEFUL_WIDGET_INTEGRATION_SEMANTICS"
          : "ARKUI_STATE_COMPONENT_UITEST_SEMANTICS";
  const projectionBase = {
    schema_version: "1.0",
    kind: "bounded-interaction-channel-projection-contract",
    projection: "STRICT_RUNTIME_OBSERVATION_V1",
    model_digest: frontendFormalDigest(model),
    block_actual_keys: boundedFrontendRuntimeActualKeys,
    scenario_ids: interactionScenarioIds,
    channels: Object.fromEntries(channels.map(channel => [channel, {
      status: "NOT_RUN",
      native_execution_allowed: channel !== "browser",
      scenarios: boundedInteractionScenarios(model).map(scenario => {
        const full = reduceBoundedFrontendRuntime(model, scenario);
        const blocks = projectBoundedFrontendRuntimeObservation(full, channel);
        return {
          scenario_id: scenario.scenarioId,
          blocks,
          block_digests: Object.fromEntries(Object.entries(blocks).map(([blockId, value]) => [blockId, frontendFormalDigest(value)])),
        };
      }),
    }])),
    oracle_provenance: "SAME_PRODUCER_CHANNEL_PROJECTION_NOT_INDEPENDENT",
    arbitrary_customer_runtime: "NOT_PROVED",
  };
  return {
    schema_version: "1.0",
    kind: browserDom ? "bounded-interaction-framework-browser-driver-contract" : "bounded-interaction-native-semantics-driver-contract",
    framework_binding: binding,
    runtime_evidence_eligibility: "ELIGIBLE_LOCAL_ACTUAL_RUNTIME_EXECUTION",
    runtime_status: "NOT_RUN",
    independent_runtime_oracle: "NOT_RUN",
    customer_runtime_evidence: "NOT_RUN",
    certification: "NOT_CERTIFIED",
    required_runtime_channels: channels,
    observer_protocol: "block-specific-runtime-observation-v1",
    actual_source: "BLOCK_SPECIFIC_RUNTIME_OBSERVED",
    self_reported_reducer_json_allowed: false,
    legacy_runtime_observed_allowed: false,
    declaration_payload_allowed_keys: ["schema_version", "kind", "block_id", "status", "observer_kind", "measurement_surface", "reason"],
    block_observer_contracts: boundedFrontendBlockObserverContracts,
    browser_required_not_run_blocks: ["effect-lifecycle", "api-network", "identity-permission", "rendering-hydration", "native-platform"],
    native_required_not_run_blocks: ["api-network"],
    native_route_without_real_device_channel_status: "NOT_RUN",
    root_selector: browserDom ? '#elmos-interaction[data-proof-profile="bounded-frontend-interaction-v1"][data-observer-protocol="block-specific-runtime-observation-v1"]' : "NOT_APPLICABLE",
    ready_selector: browserDom ? '#elmos-interaction[data-elmos-ready="true"][data-observer-protocol="block-specific-runtime-observation-v1"]' : "NOT_APPLICABLE",
    scenario_row_selector_template: browserDom ? '[data-scenario-id="${scenario_id}"]' : "NOT_APPLICABLE",
    scenario_action_selector_template: browserDom ? '[data-run-scenario="${scenario_id}"]' : "NOT_APPLICABLE",
    runtime_source_attribute: browserDom ? "data-runtime-source" : "SEMANTICS_LABEL",
    runtime_source_value: "BLOCK_SPECIFIC_RUNTIME_OBSERVED",
    completion_attribute: browserDom ? "data-execution-state" : "SEMANTICS_LABEL",
    completion_value: browserDom ? "PARTIAL" : "PARTIAL_OR_COMPLETE_FROM_BLOCK_STATUSES",
    sequence_attribute: browserDom ? "data-execution-sequence" : "SEMANTICS_LABEL",
    query_selector: browserDom ? "#elmos-query" : "ValueKey(elmos-query)",
    block_selector_template: browserDom ? '[data-semantic-block="${block_id}"]' : "ValueKey(block:${scenario_id}:${block_id})",
    network_intercept_path: channels.includes("browser") ? "/api/search" : "ADAPTER_TRACE",
    channel_projection_contract: projectionBase,
    channel_projection_contract_digest: frontendFormalDigest(projectionBase),
    native_adapter_evidence: "NOT_RUN",
    browser_or_device_evidence: "NOT_RUN",
  };
}

function routeRuntimeChannels(source: UiFrameworkId, target: UiFrameworkId): readonly ("browser" | "android" | "ios" | "harmonyos")[] {
  const present = new Set([...requiredRuntimeChannels(source), ...requiredRuntimeChannels(target)]);
  return (["browser", "android", "ios", "harmonyos"] as const).filter(channel => present.has(channel));
}

function routeChunks(
  source: ReliftedBoundedFrontendInteraction,
  target: ReliftedBoundedFrontendInteraction,
): readonly Readonly<Record<string, unknown>>[] {
  const sourcePointers = collectPointers(source.model).sort(codePointCompare);
  const targetPointers = collectPointers(target.model).sort(codePointCompare);
  if (sourcePointers.join("|") !== targetPointers.join("|")) throw new Error("interaction semantic pointer sets diverged");
  return sourcePointers.map(pointer => ({
    pointer,
    pointer_standard: "RFC6901",
    block_id: pointerBlock(pointer) ?? null,
    source: source.spans[pointer],
    target: target.spans[pointer],
    canonical_subtree_hash: frontendFormalDigest(resolvePointer(source.model, pointer)),
    source_subtree_hash: source.spans[pointer]?.subtree_hash,
    target_subtree_hash: target.spans[pointer]?.subtree_hash,
    equivalent: source.spans[pointer]?.subtree_hash === target.spans[pointer]?.subtree_hash,
  }));
}

function blockBehaviorDigest(observations: readonly InteractionObservation[], blockId: InteractionBlockId): string {
  return frontendFormalDigest(observations.map(observation => ({ scenario_id: observation.scenarioId, observation: observation.blocks[blockId] })));
}

function solverResultWithLinks(
  solver: FrontendSolverResult,
  routeId: string,
  formalInputDigest: string,
  solverInputDigest: string,
): Readonly<Record<string, unknown>> {
  return { ...solver, route_id: routeId, formal_input_digest: formalInputDigest, solver_input_digest: solverInputDigest, smt2_digest: solverInputDigest };
}

export function materializeFrontendInteractionCampaign(
  outputDirectory: string,
  options: InteractionCampaignOptions = {},
): Readonly<Record<string, unknown>> {
  const output = resolve(outputDirectory);
  if (existsSync(output) && readdirSync(output).length > 0) throw new Error("frontend interaction output directory must be absent or empty");
  mkdirSync(output, { recursive: true });
  const bundles = makeInteractionBundles(options);
  const firstBundle = bundles.values().next().value as InteractionProfileBundle | undefined;
  if (!firstBundle) throw new Error("interaction profile bundles are empty");
  const canonicalModel = firstBundle.canonical_model;
  const scenarioCorpus = {
    schema_version: "1.0",
    kind: "bounded-frontend-interaction-scenario-corpus",
    proof_profile: "bounded-frontend-interaction-v1",
    source_kind: "GENERATED_FIXTURE",
    scenarios: boundedInteractionScenarios(canonicalModel),
    arbitrary_customer_source: "NOT_PROVED",
    external_runtime_evidence: "NOT_RUN",
  };
  const scenarioPath = "scenario-corpus.json";
  const scenarioDigest = writeArtifact(output, scenarioPath, scenarioCorpus);
  const scenarioBytes = artifactBytes(scenarioCorpus);

  const profileRecords: Record<string, unknown>[] = [];
  for (const profile of uiTargetProfiles()) {
    const bundle = bundles.get(profile.id)!;
    const profileRoot = join(output, "profiles", profile.id);
    materializeProject(join(profileRoot, "project"), bundle.project.files);
    const sourceFixturePath = `generated-fixtures/${profile.id}/typed-ui-interaction-ir.json`;
    writeArtifact(output, sourceFixturePath, bundle.source_fixture_bytes);
    const files = Object.entries(bundle.project.files).sort(([left], [right]) => codePointCompare(left, right)).map(([path, content]) => ({
      path, sha256: bytesDigest(content), byte_count: Buffer.byteLength(content, "utf8"),
    }));
    const spec = interactionSourceSpec(profile.id);
    const driver = runtimeDriverContract(profile.id, bundle.relift.model);
    const manifestBase = {
      schema_version: "1.0", kind: "frontend-interaction-formal-profile-project",
      proof_profile: "bounded-frontend-interaction-v1", profile_id: profile.id,
      framework_version: profile.frameworkVersion, platforms: profile.platforms,
      required_runtime_channels: requiredRuntimeChannels(profile.id), project_path: "project",
      project_digest: bundle.project_digest, digest_scope: "sorted UTF-8 project files keyed by POSIX relative path",
      file_count: files.length, files,
      source_kind: "GENERATED_FIXTURE", source_fixture_path: sourceFixturePath,
      source_fixture_digest: bundle.source_fixture_digest, source_fixture_byte_count: Buffer.byteLength(bundle.source_fixture_bytes, "utf8"),
      interaction_source_path: spec.sourcePath, navigation_compatibility_path: spec.compatibilityPath,
      relift_model_digest: bundle.relift.model_digest, relift_block_digests: bundle.relift.block_digests,
      runtime_driver_contract: driver, target_build: "NOT_RUN", target_runtime: "NOT_RUN",
    };
    const manifest = { ...manifestBase, manifest_digest: frontendFormalDigest(manifestBase) };
    writeArtifact(output, `profiles/${profile.id}/manifest.json`, manifest);
    profileRecords.push({
      profile_id: profile.id, framework_version: profile.frameworkVersion, platforms: profile.platforms,
      required_runtime_channels: requiredRuntimeChannels(profile.id), project_path: `profiles/${profile.id}/project`,
      project_digest: bundle.project_digest, manifest_path: `profiles/${profile.id}/manifest.json`, manifest_digest: manifest.manifest_digest,
      source_kind: "GENERATED_FIXTURE", source_fixture_path: sourceFixturePath,
      source_fixture_digest: bundle.source_fixture_digest, source_fixture_byte_count: Buffer.byteLength(bundle.source_fixture_bytes, "utf8"),
      interaction_source_path: spec.sourcePath, navigation_compatibility_path: spec.compatibilityPath,
      relift_model_digest: bundle.relift.model_digest, relift_block_digests: bundle.relift.block_digests,
      runtime_driver_contract: driver, target_build: "NOT_RUN", target_runtime: "NOT_RUN",
    });
  }

  const counterexamples = interactionLeafCounterexamples(canonicalModel);
  const mutationRows: Record<string, unknown>[] = [];
  for (const blockId of interactionBlockIds) {
    const candidate = selectMutationWitness(counterexamples, blockId);
    const mutant = mutateInteractionModelAtPointer(canonicalModel, candidate.pointer);
    const variants = mutationVariantKinds.map(variant => {
      const root = `mutations/${blockId}/${variant.toLowerCase().replaceAll("_", "-")}`;
      const formalInput = mutationFormalInput(canonicalModel, mutant, blockId, variant, candidate);
      const formalInputPath = `${root}/formal-input.json`;
      const formalInputDigest = artifactDigest(formalInput);
      const models = mutationModels(canonicalModel, mutant, variant);
      const smt2 = buildInteractionSmt2(...models, formalInputDigest);
      const solver = runFrontendSolver(smt2, options.solver);
      const smtPath = `${root}/proof.smt2`; const solverPath = `${root}/solver-result.json`;
      const smtDigest = bytesDigest(smt2);
      const solverArtifact = {
        ...solverResultWithLinks(solver, `mutation:${blockId}:${variant}`, formalInputDigest, smtDigest),
        mutation_formal_input_path: formalInputPath, mutation_solver_input_path: smtPath,
        expected_outcome: "SAT", replay_status: solver.outcome === "SAT" ? "PASSED" : "FAILED",
      };
      const solverDigest = artifactDigest(solverArtifact);
      writeArtifact(output, formalInputPath, formalInput); writeArtifact(output, smtPath, smt2); writeArtifact(output, solverPath, solverArtifact);
      return { variant, formal_input_path: formalInputPath, formal_input_digest: formalInputDigest,
        smt2_path: smtPath, smt2_digest: smtDigest, solver_result_path: solverPath, solver_result_digest: solverDigest,
        solver_outcome: solver.outcome, replay_status: solver.outcome === "SAT" ? "PASSED" : "FAILED" };
    });
    mutationRows.push({ block_id: blockId, obligation_symbol: `diff_${interactionBlockSymbolMap[blockId]}`, pointer: candidate.pointer,
      scenario_id: candidate.scenario_id, counterexample_replay: candidate, variants,
      status: variants.every(variant => variant.solver_outcome === "SAT" && variant.replay_status === "PASSED") ? "REFUTED_AS_EXPECTED" : "NOT_PROVED" });
  }
  const mutationCampaign = { schema_version: "1.0", kind: "bounded-interaction-seeded-mutation-campaign", proof_profile: "bounded-frontend-interaction-v1", mutations: mutationRows,
    status: mutationRows.every(row => row.status === "REFUTED_AS_EXPECTED") ? "PASSED" : "FAILED" };
  const mutationCampaignPath = "mutation-campaign.json";
  const mutationCampaignDigest = writeArtifact(output, mutationCampaignPath, mutationCampaign);

  const routeRecords: Record<string, unknown>[] = [];
  for (const route of uiConversionRoutes()) {
    const source = bundles.get(route.source)!; const target = bundles.get(route.target)!;
    const canonicalObservations = observeInteractionScenarioSet(canonicalModel, "canonical");
    const referenceObservations = observeInteractionScenarioSet(canonicalModel, "reference");
    const sourceObservations = observeInteractionScenarioSet(source.relift.model, "source");
    const targetObservations = observeInteractionScenarioSet(target.relift.model, "target");
    const semanticEqual = canonical(source.relift.model) === canonical(canonicalModel) && canonical(target.relift.model) === canonical(canonicalModel);
    const behaviorEqual = canonical(behaviorComparable(canonicalObservations)) === canonical(behaviorComparable(referenceObservations))
      && canonical(behaviorComparable(canonicalObservations)) === canonical(behaviorComparable(sourceObservations))
      && canonical(behaviorComparable(canonicalObservations)) === canonical(behaviorComparable(targetObservations));
    const chunks = routeChunks(source.relift, target.relift); const chunkEqual = chunks.every(chunk => chunk.equivalent === true);
    const routeRoot = `routes/${route.routeId}`;
    const behavior = {
      schema_version: "1.0", kind: "bounded-interaction-model-behavior",
      domain: { scenario_manifest_path: scenarioPath, scenario_manifest_digest: scenarioDigest, scenario_count: boundedInteractionScenarios(canonicalModel).length,
        model_reducer: "BOUNDED_PURE_REDUCER", browser_runtime: "NOT_RUN", native_runtime: "NOT_RUN" },
      canonical: { runtime_kind: "AUTHORITATIVE_MODEL_REDUCER", observations: canonicalObservations },
      reference: { runtime_kind: "SAME_ENGINE_SEPARATE_TABLE_REDUCER", observations: referenceObservations },
      source: { runtime_kind: "RELIFTED_EMITTED_SOURCE_MODEL_REDUCER", observations: sourceObservations },
      target: { runtime_kind: "RELIFTED_EMITTED_TARGET_MODEL_REDUCER", observations: targetObservations },
      equivalent: behaviorEqual,
      oracle_provenance: { independence: "NOT_INDEPENDENT_SINGLE_ENGINE", solver_result_used_as_oracle: false, runtime_observation_source: "NOT_RUN" },
      runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER",
    };
    const chunkArtifact = { schema_version: "1.0", kind: "bounded-interaction-rfc6901-chunks", route_id: route.routeId, chunks, equivalent: chunkEqual };
    const formalInput = {
      schema_version: "1.0", kind: "frontend-bounded-interaction-formal-input", corpus_id: "frontend-bounded-interaction-corpus-v1",
      proof_profile: "bounded-frontend-interaction-v1", proof_scope: "typed canonical bounded interaction IR <-> emitted source re-lift <-> emitted target re-lift",
      route_id: route.routeId,
      tuple: { source_profile: route.source, source_framework_version: uiTargetProfile(route.source).frameworkVersion,
        target_profile: route.target, target_framework_version: uiTargetProfile(route.target).frameworkVersion },
      source_project_digest: source.project_digest, target_project_digest: target.project_digest,
      canonical_model: canonicalModel, canonical_model_digest: frontendFormalDigest(canonicalModel),
      canonical_block_digests: Object.fromEntries(interactionBlockIds.map(id => [id, frontendFormalDigest(canonicalModel[blockModelKeys[id]])])),
      source_model_digest: source.relift.model_digest, target_model_digest: target.relift.model_digest,
      source_block_digests: source.relift.block_digests, target_block_digests: target.relift.block_digests,
      source_model_artifact_digest: artifactDigest(source.relift), target_model_artifact_digest: artifactDigest(target.relift),
      semantic_equal: semanticEqual, behavior_digest: artifactDigest(behavior), behavior_equal: behaviorEqual,
      chunk_digest: artifactDigest(chunkArtifact), chunk_equal: chunkEqual,
      scenario_manifest_digest: scenarioDigest, mutation_campaign_digest: mutationCampaignDigest,
      semantic_block_ids: interactionBlockIds, block_symbol_map: interactionBlockSymbolMap,
      influence_classes: { model: interactionInfluenceMatrix, runtime: interactionRuntimeInfluenceMatrix },
      assumptions: proofAssumptions, oracle_provenance: { independence: "NOT_INDEPENDENT_SINGLE_ENGINE", formal_input_from_solver_result: false, oracle_from_solver_result: false },
      arbitrary_customer_source: "NOT_PROVED", compiler_framework_runtime_soundness: "ASSUMED_NOT_PROVED",
      runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER",
    };
    const formalInputDigest = artifactDigest(formalInput);
    const smt2 = buildInteractionSmt2(canonicalModel, source.relift.model, target.relift.model, canonicalModel, formalInputDigest);
    const vacuitySmt2 = buildInteractionVacuitySmt2(formalInputDigest);
    const solver = runFrontendSolver(smt2, options.solver); const vacuitySolver = runFrontendSolver(vacuitySmt2, options.solver);
    const smtDigest = bytesDigest(smt2); const vacuityDigest = bytesDigest(vacuitySmt2);
    const solverResult = solverResultWithLinks(solver, route.routeId, formalInputDigest, smtDigest);
    const vacuitySolverResult = { ...solverResultWithLinks(vacuitySolver, route.routeId, formalInputDigest, vacuityDigest), precheck_status: vacuitySolver.outcome === "SAT" ? "PASSED" : "FAILED" };
    const solverResultDigest = artifactDigest(solverResult); const vacuitySolverResultDigest = artifactDigest(vacuitySolverResult);
    const status: InteractionFormalStatus = !semanticEqual || !behaviorEqual || !chunkEqual ? "REFUTED"
      : vacuitySolver.outcome !== "SAT" ? "NOT_PROVED" : solver.proof_status;
    const blockResults = interactionBlockIds.map(blockId => {
      const blockChunks = chunks.filter(chunk => chunk.block_id === blockId);
      const blockWitnesses = counterexamples.filter(row => row.block_id === blockId);
      const behaviorDenominator = blockWitnesses.filter(row => row.influence_class !== "DECLARATION_ECHO");
      const semanticMutantDetected = blockWitnesses.every(row => row.semantic_mutant_detected);
      const behaviorMutantDetected = behaviorDenominator.length > 0 && behaviorDenominator.every(row => row.behavior_mutant_detected);
      const blockBehaviorEqual = blockBehaviorDigest(canonicalObservations, blockId) === blockBehaviorDigest(referenceObservations, blockId)
        && blockBehaviorDigest(canonicalObservations, blockId) === blockBehaviorDigest(sourceObservations, blockId)
        && blockBehaviorDigest(canonicalObservations, blockId) === blockBehaviorDigest(targetObservations, blockId);
      const seededMutationPassed = mutationRows.find(row => row.block_id === blockId)?.status === "REFUTED_AS_EXPECTED";
      const blockStatus: InteractionFormalStatus = status === "PROVED_UNDER_ASSUMPTIONS" && semanticMutantDetected && behaviorMutantDetected && seededMutationPassed
        ? "PROVED_UNDER_ASSUMPTIONS" : status === "REFUTED" ? "REFUTED" : "NOT_PROVED";
      return {
        block_id: blockId, obligation_symbol: `diff_${interactionBlockSymbolMap[blockId]}`,
        influence_classes: { model: interactionInfluenceMatrix[blockId], runtime: interactionRuntimeInfluenceMatrix[blockId] },
        model_influence_max: aggregateModelInfluence(blockId), runtime_influence_max: aggregateRuntimeInfluence(blockId),
        canonical_block_digest: frontendFormalDigest(canonicalModel[blockModelKeys[blockId]]),
        source_block_digest: source.relift.block_digests[blockId], target_block_digest: target.relift.block_digests[blockId],
        behavior_block_digest: blockBehaviorDigest(canonicalObservations, blockId), chunk_block_digest: frontendFormalDigest(blockChunks),
        formal_input_digest: formalInputDigest, solver_input_digest: smtDigest, solver_result_digest: solverResultDigest,
        vacuity_input_digest: vacuityDigest, vacuity_solver_result_digest: vacuitySolverResultDigest,
        mutation_campaign_digest: mutationCampaignDigest,
        semantic_status: semanticEqual ? "PASSED" : "FAILED", chunk_status: blockChunks.every(chunk => chunk.equivalent === true) ? "PASSED" : "FAILED",
        model_behavior_status: blockBehaviorEqual ? "PASSED" : "FAILED", raw_solver_status: solver.proof_status, formal_status: blockStatus,
        assumption_precheck: vacuitySolver.outcome === "SAT" ? "SAT_NON_VACUOUS_DOMAIN" : "FAILED",
        semantic_mutant_detected: semanticMutantDetected, behavior_mutant_detected: behaviorMutantDetected,
        declaration_echo_excluded_from_behavior_denominator: true,
        runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER", runtime_status: "NOT_RUN",
        oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE", status: blockStatus,
      };
    });
    const composition = {
      schema_version: "1.0", kind: "bounded-interaction-route-composition", route_id: route.routeId,
      source_lifting: { profile_id: route.source, project_digest: source.project_digest, model_digest: source.relift.model_digest },
      target_lowering_relift: { profile_id: route.target, project_digest: target.project_digest, model_digest: target.relift.model_digest },
      canonical_model_digest: frontendFormalDigest(canonicalModel), semantic_equal: semanticEqual, chunk_equal: chunkEqual,
      model_behavior_equal: behaviorEqual, solver_outcome: solver.outcome, vacuity_outcome: vacuitySolver.outcome,
      cross_channel_equivalence: Object.fromEntries(routeRuntimeChannels(route.source, route.target).map(channel => [channel, "NOT_RUN"])),
      oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE", status,
    };
    const paths = {
      source_model_path: `${routeRoot}/source-model.json`, target_model_path: `${routeRoot}/target-model.json`,
      behavior_path: `${routeRoot}/behavior.json`, chunks_path: `${routeRoot}/chunks.json`, formal_input_path: `${routeRoot}/formal-input.json`,
      smt2_path: `${routeRoot}/proof.smt2`, solver_result_path: `${routeRoot}/solver-result.json`,
      vacuity_input_path: `${routeRoot}/vacuity-precheck.smt2`, vacuity_solver_result_path: `${routeRoot}/vacuity-solver-result.json`,
      block_results_path: `${routeRoot}/block-results.json`, composition_path: `${routeRoot}/composition.json`, layered_result_path: `${routeRoot}/layered-result.json`,
    };
    const fixedPaths = paths;
    const links = {
      ...fixedPaths,
      source_model_digest: artifactDigest(source.relift), target_model_digest: artifactDigest(target.relift),
      behavior_digest: artifactDigest(behavior), chunks_digest: artifactDigest(chunkArtifact), formal_input_digest: formalInputDigest,
      smt2_digest: smtDigest, solver_result_digest: solverResultDigest,
      vacuity_input_digest: vacuityDigest, vacuity_solver_result_digest: vacuitySolverResultDigest,
      block_results_digest: artifactDigest({ schema_version: "1.0", kind: "bounded-interaction-block-results", route_id: route.routeId, blocks: blockResults }),
      composition_digest: artifactDigest(composition), mutation_campaign_digest: mutationCampaignDigest,
    };
    const blockArtifact = { schema_version: "1.0", kind: "bounded-interaction-block-results", route_id: route.routeId, blocks: blockResults };
    const layered = {
      schema_version: "1.0", kind: "bounded-interaction-layered-result", route_id: route.routeId,
      proof_profile: "bounded-frontend-interaction-v1", links,
      layers: { emitted_source_relift: "PASSED", emitted_target_relift: "PASSED", semantic: semanticEqual ? "PASSED" : "FAILED",
        chunk: chunkEqual ? "PASSED" : "FAILED", model_behavior: behaviorEqual ? "PASSED" : "FAILED",
        assumption_vacuity_precheck: vacuitySolver.outcome, smt_solver: solver.outcome,
        framework_native_build: "NOT_RUN", framework_browser_or_device_runtime: "NOT_RUN", independent_external_verification: "NOT_RUN" },
      oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE", runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER",
      status, unconditional_proof: false, certification: "NOT_CERTIFIED", assumptions: proofAssumptions,
    };
    writeArtifact(output, fixedPaths.source_model_path, source.relift); writeArtifact(output, fixedPaths.target_model_path, target.relift);
    writeArtifact(output, fixedPaths.behavior_path, behavior); writeArtifact(output, fixedPaths.chunks_path, chunkArtifact);
    writeArtifact(output, fixedPaths.formal_input_path, formalInput); writeArtifact(output, fixedPaths.smt2_path, smt2);
    writeArtifact(output, fixedPaths.solver_result_path, solverResult); writeArtifact(output, fixedPaths.vacuity_input_path, vacuitySmt2);
    writeArtifact(output, fixedPaths.vacuity_solver_result_path, vacuitySolverResult); writeArtifact(output, fixedPaths.block_results_path, blockArtifact);
    writeArtifact(output, fixedPaths.composition_path, composition); const layeredDigest = writeArtifact(output, fixedPaths.layered_result_path, layered);
    routeRecords.push({
      route_id: route.routeId, source_profile: route.source, target_profile: route.target,
      source_project_digest: source.project_digest, target_project_digest: target.project_digest,
      evidence_path: fixedPaths.layered_result_path, evidence_digest: layeredDigest,
      formal_input_path: fixedPaths.formal_input_path, formal_input_digest: formalInputDigest,
      behavior_path: fixedPaths.behavior_path, behavior_digest: links.behavior_digest,
      chunks_path: fixedPaths.chunks_path, chunks_digest: links.chunks_digest,
      solver_input_path: fixedPaths.smt2_path, solver_input_digest: smtDigest,
      solver_result_path: fixedPaths.solver_result_path, solver_result_digest: solverResultDigest,
      vacuity_input_path: fixedPaths.vacuity_input_path, vacuity_input_digest: vacuityDigest,
      vacuity_solver_result_path: fixedPaths.vacuity_solver_result_path, vacuity_solver_result_digest: vacuitySolverResultDigest,
      block_results_path: fixedPaths.block_results_path, block_results_digest: links.block_results_digest,
      composition_path: fixedPaths.composition_path, composition_digest: links.composition_digest,
      layered_result: status, status,
    });
  }
  const counts = Object.fromEntries(["PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"].map(status => [status, routeRecords.filter(route => route.status === status).length]));
  const blockCounts = Object.fromEntries(interactionBlockIds.map(blockId => [blockId, Object.fromEntries(["PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"].map(status => [status, routeRecords.filter(route => {
    const artifact = JSON.parse(readFileSync(join(output, ...(route.block_results_path as string).split("/")), "utf8")) as { blocks: readonly { block_id: string; status: string }[] };
    return artifact.blocks.find(block => block.block_id === blockId)?.status === status;
  }).length]))]));
  const campaign = {
    schema_version: "1.0", kind: "frontend-interaction-formal-route-campaign", proof_profile: "bounded-frontend-interaction-v1",
    corpus_id: "frontend-bounded-interaction-corpus-v1", semantic_block_ids: interactionBlockIds, block_symbol_map: interactionBlockSymbolMap,
    scenario_manifest: { schema_version: "1.0", kind: "bounded-interaction-scenario-manifest", source_kind: "GENERATED_FIXTURE",
      source_path: scenarioPath, source_sha256: scenarioDigest, source_byte_count: Buffer.byteLength(scenarioBytes, "utf8"),
      scenario_ids: interactionScenarioIds, scenario_count: interactionScenarioIds.length,
      input_schema: "InteractionInput@bounded-frontend-interaction-v1", runtime_driver_contract: "profiles[].runtime_driver_contract" },
    mutation_campaign: { path: mutationCampaignPath, digest: mutationCampaignDigest, status: mutationCampaign.status },
    profile_count: profileRecords.length, route_count: routeRecords.length, block_count: interactionBlockIds.length,
    profiles: profileRecords, routes: routeRecords, counts, block_counts: blockCounts,
    source_liftings: profileRecords.map(profile => ({ profile_id: profile.profile_id, project_digest: profile.project_digest, relift_model_digest: profile.relift_model_digest, source_kind: "GENERATED_FIXTURE", arbitrary_customer_source: "NOT_PROVED", status: "PASSED" })),
    target_lowerings: profileRecords.map(profile => ({ profile_id: profile.profile_id, project_digest: profile.project_digest, emitted_project: "PASSED", relift: "PASSED" })),
    assumptions: proofAssumptions,
    oracle_provenance: { independence: "NOT_INDEPENDENT_SINGLE_ENGINE", authoritative_spec: "SAME_ENGINE", reference_reducer: "SAME_ENGINE_SEPARATE_IMPLEMENTATION", solver_result_used_as_input_or_oracle: false },
    arbitrary_customer_source: "NOT_PROVED", unconditional_proof: false, native_build_and_runtime: "NOT_RUN",
    independent_external_verification: "NOT_RUN", certification: "NOT_CERTIFIED",
  };
  writeArtifact(output, "frontend-interaction-formal-campaign.json", campaign);
  return campaign;
}

function exactObjectKeys(value: Record<string, unknown>, expected: readonly string[], name: string): void {
  const actual = Object.keys(value).sort(codePointCompare); const wanted = [...expected].sort(codePointCompare);
  if (actual.join("|") !== wanted.join("|")) throw new Error(`${name} exact keys drifted`);
}

function safeCampaignFile(root: string, relativePath: unknown, name: string): string {
  if (typeof relativePath !== "string") throw new Error(`${name} path is not a string`);
  assertSafeRelative(relativePath);
  const destination = resolve(root, ...relativePath.split("/"));
  if (!destination.startsWith(`${root}/`)) throw new Error(`${name} path escapes campaign root`);
  const metadata = lstatSync(destination);
  if (metadata.isSymbolicLink() || !metadata.isFile()) throw new Error(`${name} is not a regular artifact file`);
  return destination;
}

function filesBelow(root: string, prefix = ""): readonly string[] {
  const result: string[] = [];
  for (const name of readdirSync(join(root, ...prefix.split("/").filter(Boolean))).sort(codePointCompare)) {
    const path = prefix ? `${prefix}/${name}` : name; const absolute = join(root, ...path.split("/")); const stat = lstatSync(absolute);
    if (stat.isSymbolicLink()) throw new Error(`symbolic link is forbidden in project bundle: ${path}`);
    if (stat.isDirectory()) result.push(...filesBelow(root, path)); else if (stat.isFile()) result.push(path); else throw new Error(`non-regular project entry: ${path}`);
  }
  return result;
}

function readJsonArtifact(root: string, path: unknown, digestValue: unknown, name: string): { readonly bytes: string; readonly value: Record<string, unknown> } {
  const bytes = readFileSync(safeCampaignFile(root, path, name), "utf8");
  if (bytesDigest(bytes) !== digestValue) throw new Error(`${name} bytes digest drifted`);
  const value = JSON.parse(bytes) as Record<string, unknown>;
  if (artifactBytes(value) !== bytes) throw new Error(`${name} JSON bytes are non-canonical`);
  return { bytes, value };
}

function verifySolverArtifact(
  value: Record<string, unknown>,
  smt2: string,
  formalInputDigest: string,
  smtDigest: string,
  expectedOutcome?: "UNSAT" | "SAT",
  solverOverride?: string,
  replayCache?: Map<string, FrontendSolverResult>,
): FrontendSolverResult | undefined {
  if (value.formal_input_digest !== formalInputDigest || value.solver_input_digest !== smtDigest || value.smt2_digest !== smtDigest
    || value.unconditional_proof !== false) throw new Error("solver linkage drifted");
  if (expectedOutcome !== undefined && value.outcome !== expectedOutcome) throw new Error(`solver outcome is not ${expectedOutcome}`);
  if (value.identity_status === "VERIFIED") {
    const recordedRealpath = value.solver_binary_realpath;
    if (typeof recordedRealpath !== "string" || resolve(recordedRealpath) !== recordedRealpath
      || value.solver !== recordedRealpath
      || canonical(value.invocation) !== canonical([recordedRealpath, "-in"])) throw new Error("verified solver recorded path/invocation is malformed");
    const recordedOptions = value.options as Record<string, unknown> | undefined;
    if (!recordedOptions || canonical(recordedOptions.args) !== canonical(["-in"])
      || typeof recordedOptions.timeout_ms !== "number" || !Number.isInteger(recordedOptions.timeout_ms)
      || recordedOptions.timeout_ms <= 0) throw new Error("verified solver recorded options are malformed");
    const command = solverOverride ?? recordedRealpath;
    const normalizedSmt = smt2.replace(/^; formal-input-bytes-digest: .*$/m, "; formal-input-bytes-digest: <bound-separately>");
    let resolvedCommand = resolve(command);
    try { resolvedCommand = realpathSync(resolvedCommand); } catch { /* runFrontendSolver emits the fail-closed missing identity */ }
    const replayKey = canonical({
      resolved_command: resolvedCommand,
      recorded_binary_sha256: value.solver_binary_sha256,
      recorded_version: value.solver_version,
      recorded_options: recordedOptions,
      timeout_ms: recordedOptions.timeout_ms,
      semantic_smt_digest: bytesDigest(normalizedSmt),
      expected_outcome: expectedOutcome ?? "ARTIFACT_BOUND",
    });
    const replay = replayCache?.get(replayKey) ?? runFrontendSolver(smt2, { command, timeout_ms: recordedOptions.timeout_ms });
    if (replay.identity_status !== "VERIFIED") throw new Error("solver override does not match the locked solver identity");
    const normalizedReplay: FrontendSolverResult = {
      ...replay,
      solver: recordedRealpath,
      solver_binary_realpath: recordedRealpath,
      invocation: [recordedRealpath, "-in"],
    };
    const coreKeys = Object.keys(normalizedReplay) as (keyof FrontendSolverResult)[];
    const recordedCore = Object.fromEntries(coreKeys.map(key => [key, value[key]]));
    if (canonical(recordedCore) !== canonical(normalizedReplay)) throw new Error("solver replay or locked identity/options/output diverged");
    replayCache?.set(replayKey, replay);
    return normalizedReplay;
  } else if (value.outcome === "UNSAT" || value.outcome === "SAT") throw new Error("unverified solver cannot support a solver decision");
  return undefined;
}

export function verifyFrontendInteractionCampaign(
  outputDirectory: string,
  options: InteractionCampaignVerificationOptions = {},
): readonly string[] {
  const errors: string[] = []; const output = resolve(outputDirectory);
  const solverReplayCache = new Map<string, FrontendSolverResult>();
  try {
    const campaignBytes = readFileSync(safeCampaignFile(output, "frontend-interaction-formal-campaign.json", "campaign"), "utf8");
    const campaign = JSON.parse(campaignBytes) as Record<string, unknown>;
    if (artifactBytes(campaign) !== campaignBytes) throw new Error("campaign JSON bytes are non-canonical");
    exactObjectKeys(campaign, ["schema_version", "kind", "proof_profile", "corpus_id", "semantic_block_ids", "block_symbol_map", "scenario_manifest", "mutation_campaign", "profile_count", "route_count", "block_count", "profiles", "routes", "counts", "block_counts", "source_liftings", "target_lowerings", "assumptions", "oracle_provenance", "arbitrary_customer_source", "unconditional_proof", "native_build_and_runtime", "independent_external_verification", "certification"], "campaign");
    if (campaign.schema_version !== "1.0" || campaign.kind !== "frontend-interaction-formal-route-campaign"
      || campaign.proof_profile !== "bounded-frontend-interaction-v1" || campaign.profile_count !== 9 || campaign.route_count !== 72
      || campaign.block_count !== 12 || canonical(campaign.semantic_block_ids) !== canonical(interactionBlockIds)
      || canonical(campaign.block_symbol_map) !== canonical(interactionBlockSymbolMap)
      || campaign.arbitrary_customer_source !== "NOT_PROVED" || campaign.unconditional_proof !== false
      || campaign.native_build_and_runtime !== "NOT_RUN" || campaign.independent_external_verification !== "NOT_RUN"
      || campaign.certification !== "NOT_CERTIFIED" || canonical(campaign.assumptions) !== canonical(proofAssumptions)) throw new Error("campaign identity/boundary drifted");

    const canonicalModel = canonicalBoundedFrontendInteractionModel(boundedInteractionFixtureRequest("react"));
    const scenarioManifest = campaign.scenario_manifest as Record<string, unknown>;
    exactObjectKeys(scenarioManifest, ["schema_version", "kind", "source_kind", "source_path", "source_sha256", "source_byte_count", "scenario_ids", "scenario_count", "input_schema", "runtime_driver_contract"], "scenario manifest");
    const scenarioArtifact = readJsonArtifact(output, scenarioManifest.source_path, scenarioManifest.source_sha256, "scenario corpus");
    const expectedScenario = { schema_version: "1.0", kind: "bounded-frontend-interaction-scenario-corpus", proof_profile: "bounded-frontend-interaction-v1",
      source_kind: "GENERATED_FIXTURE", scenarios: boundedInteractionScenarios(canonicalModel), arbitrary_customer_source: "NOT_PROVED", external_runtime_evidence: "NOT_RUN" };
    if (canonical(scenarioArtifact.value) !== canonical(expectedScenario) || scenarioManifest.source_byte_count !== Buffer.byteLength(scenarioArtifact.bytes, "utf8")
      || canonical(scenarioManifest.scenario_ids) !== canonical(interactionScenarioIds) || scenarioManifest.scenario_count !== interactionScenarioIds.length) throw new Error("scenario corpus/manifest drifted");

    const mutationLink = campaign.mutation_campaign as Record<string, unknown>;
    exactObjectKeys(mutationLink, ["path", "digest", "status"], "mutation campaign link");
    const mutationArtifact = readJsonArtifact(output, mutationLink.path, mutationLink.digest, "mutation campaign").value;
    exactObjectKeys(mutationArtifact, ["schema_version", "kind", "proof_profile", "mutations", "status"], "mutation campaign");
    if (mutationArtifact.schema_version !== "1.0" || mutationArtifact.kind !== "bounded-interaction-seeded-mutation-campaign"
      || mutationArtifact.proof_profile !== "bounded-frontend-interaction-v1" || mutationArtifact.status !== "PASSED" || mutationLink.status !== "PASSED") throw new Error("mutation campaign identity/status drifted");
    const mutations = mutationArtifact.mutations;
    if (!Array.isArray(mutations) || mutations.length !== interactionBlockIds.length) throw new Error("mutation campaign block closure drifted");
    const mutationBlockIds = mutations.map(item => (item as Record<string, unknown>).block_id);
    if (new Set(mutationBlockIds).size !== interactionBlockIds.length
      || interactionBlockIds.some(blockId => !mutationBlockIds.includes(blockId))) throw new Error("mutation campaign block identity is duplicated or incomplete");
    const expectedCounterexamples = interactionLeafCounterexamples(canonicalModel);
    for (const blockId of interactionBlockIds) {
      const rows = mutations.filter(item => (item as Record<string, unknown>).block_id === blockId) as Record<string, unknown>[];
      if (rows.length !== 1) throw new Error(`mutation row identity is not unique: ${blockId}`);
      const row = rows[0]!;
      exactObjectKeys(row, ["block_id", "obligation_symbol", "pointer", "scenario_id", "counterexample_replay", "variants", "status"], `${blockId}.mutation-row`);
      const candidate = selectMutationWitness(expectedCounterexamples, blockId);
      const pointer = String(row.pointer);
      if (pointerBlock(pointer) !== blockId || pointer !== candidate.pointer
        || row.obligation_symbol !== `diff_${interactionBlockSymbolMap[blockId]}`
        || row.scenario_id !== candidate.scenario_id
        || canonical(row.counterexample_replay) !== canonical(candidate)) throw new Error(`mutation pointer/witness/symbol drifted: ${blockId}`);
      const mutant = mutateInteractionModelAtPointer(canonicalModel, pointer);
      if (frontendFormalDigest(canonicalModel[blockModelKeys[blockId]]) === frontendFormalDigest(mutant[blockModelKeys[blockId]])) {
        throw new Error(`mutation does not alter its owned block: ${blockId}`);
      }
      const variants = row.variants;
      if (!Array.isArray(variants) || variants.length !== 3) throw new Error(`mutation variants drifted: ${blockId}`);
      const actualKinds = variants.map(value => (value as Record<string, unknown>).variant);
      if (new Set(actualKinds).size !== mutationVariantKinds.length
        || mutationVariantKinds.some(kind => !actualKinds.includes(kind))) throw new Error(`mutation variant identity is duplicated or incomplete: ${blockId}`);
      for (const kind of mutationVariantKinds) {
        const matching = variants.filter(value => (value as Record<string, unknown>).variant === kind) as Record<string, unknown>[];
        if (matching.length !== 1) throw new Error(`mutation variant is not unique: ${blockId}.${kind}`);
        const variant = matching[0]!;
        exactObjectKeys(variant, ["variant", "formal_input_path", "formal_input_digest", "smt2_path", "smt2_digest", "solver_result_path", "solver_result_digest", "solver_outcome", "replay_status"], `${blockId}.${kind}.variant`);
        const variantRoot = `mutations/${blockId}/${kind.toLowerCase().replaceAll("_", "-")}`;
        if (variant.formal_input_path !== `${variantRoot}/formal-input.json` || variant.smt2_path !== `${variantRoot}/proof.smt2`
          || variant.solver_result_path !== `${variantRoot}/solver-result.json`) throw new Error(`mutation variant path drifted: ${blockId}.${kind}`);
        const formal = readJsonArtifact(output, variant.formal_input_path, variant.formal_input_digest, `${blockId}.${String(kind)}.formal`).value;
        exactObjectKeys(formal, ["schema_version", "kind", "proof_profile", "block_id", "obligation_symbol", "variant", "pointer", "canonical_model_digest", "mutant_model_digest", "canonical_block_digest", "mutant_block_digest", "counterexample_replay", "expected_solver_outcome", "oracle_provenance"], `${blockId}.${kind}.formal`);
        const expectedFormal = mutationFormalInput(canonicalModel, mutant, blockId, kind, candidate);
        if (canonical(formal) !== canonical(expectedFormal) || variant.formal_input_digest !== artifactDigest(expectedFormal)) throw new Error(`mutation formal input reconstruction drifted: ${blockId}.${String(kind)}`);
        const smtPath = safeCampaignFile(output, variant.smt2_path, `${blockId}.${String(kind)}.smt`); const smt2 = readFileSync(smtPath, "utf8");
        if (bytesDigest(smt2) !== variant.smt2_digest) throw new Error(`mutation SMT digest drifted: ${blockId}.${String(kind)}`);
        const models = mutationModels(canonicalModel, mutant, kind);
        if (smt2 !== buildInteractionSmt2(...models, String(variant.formal_input_digest))) throw new Error(`mutation SMT reconstruction drifted: ${blockId}.${String(kind)}`);
        const solver = readJsonArtifact(output, variant.solver_result_path, variant.solver_result_digest, `${blockId}.${String(kind)}.solver`).value;
        exactObjectKeys(solver, ["schema_version", "solver", "solver_binary_realpath", "solver_binary_sha256", "solver_version", "identity_status", "invocation", "options", "environment", "exit_code", "stdout", "stderr", "outcome", "proof_status", "unconditional_proof", "route_id", "formal_input_digest", "solver_input_digest", "smt2_digest", "mutation_formal_input_path", "mutation_solver_input_path", "expected_outcome", "replay_status"], `${blockId}.${kind}.solver`);
        const replay = verifySolverArtifact(solver, smt2, String(variant.formal_input_digest), String(variant.smt2_digest), "SAT", options.solver?.command, solverReplayCache);
        if (!replay) throw new Error(`mutation solver is not replayable: ${blockId}.${kind}`);
        const expectedSolver = {
          ...solverResultWithLinks(replay, `mutation:${blockId}:${kind}`, String(variant.formal_input_digest), String(variant.smt2_digest)),
          mutation_formal_input_path: variant.formal_input_path,
          mutation_solver_input_path: variant.smt2_path,
          expected_outcome: "SAT",
          replay_status: "PASSED",
        };
        if (canonical(solver) !== canonical(expectedSolver) || variant.solver_result_digest !== artifactDigest(expectedSolver)
          || variant.solver_outcome !== "SAT" || variant.replay_status !== "PASSED") throw new Error(`mutation solver/result/status reconstruction drifted: ${blockId}.${kind}`);
      }
      const expectedRowStatus = mutationVariantKinds.every(kind => {
        const variant = variants.find(value => (value as Record<string, unknown>).variant === kind) as Record<string, unknown>;
        return variant.solver_outcome === "SAT" && variant.replay_status === "PASSED";
      }) ? "REFUTED_AS_EXPECTED" : "NOT_PROVED";
      if (row.status !== expectedRowStatus) throw new Error(`mutation row status drifted: ${blockId}`);
    }

    const verifiedProfiles = new Map<UiFrameworkId, InteractionProfileBundle>();
    const profiles = campaign.profiles;
    if (!Array.isArray(profiles) || profiles.length !== 9) throw new Error("campaign profile closure is not nine");
    for (const raw of profiles) {
      const profile = raw as Record<string, unknown>; const id = profile.profile_id as UiFrameworkId;
      try {
        exactObjectKeys(profile, ["profile_id", "framework_version", "platforms", "required_runtime_channels", "project_path", "project_digest", "manifest_path", "manifest_digest", "source_kind", "source_fixture_path", "source_fixture_digest", "source_fixture_byte_count", "interaction_source_path", "navigation_compatibility_path", "relift_model_digest", "relift_block_digests", "runtime_driver_contract", "target_build", "target_runtime"], `${id}.profile`);
        if (verifiedProfiles.has(id) || !uiTargetProfiles().some(candidate => candidate.id === id)) throw new Error("profile id is invalid or duplicated");
        const exact = uiTargetProfile(id); const request = boundedInteractionFixtureRequest(id);
        if (profile.framework_version !== exact.frameworkVersion || canonical(profile.platforms) !== canonical(exact.platforms)
          || canonical(profile.required_runtime_channels) !== canonical(requiredRuntimeChannels(id))
          || profile.project_path !== `profiles/${id}/project` || profile.manifest_path !== `profiles/${id}/manifest.json`
          || profile.source_fixture_path !== `generated-fixtures/${id}/typed-ui-interaction-ir.json`
          || profile.source_kind !== "GENERATED_FIXTURE" || profile.target_build !== "NOT_RUN" || profile.target_runtime !== "NOT_RUN") throw new Error("exact profile tuple/path/boundary drifted");
        const sourceBytes = readFileSync(safeCampaignFile(output, profile.source_fixture_path, `${id}.source-fixture`), "utf8");
        if (sourceBytes !== boundedInteractionSourceFixtureBytes(request) || bytesDigest(sourceBytes) !== profile.source_fixture_digest
          || Buffer.byteLength(sourceBytes, "utf8") !== profile.source_fixture_byte_count
          || request.uiIr.sourceSnapshotDigest !== profile.source_fixture_digest) throw new Error("generated source fixture provenance drifted");
        const projectRoot = resolve(output, ...(String(profile.project_path).split("/")));
        const projectStat = lstatSync(projectRoot); if (!projectStat.isDirectory() || projectStat.isSymbolicLink()) throw new Error("project root is not a real directory");
        const diskFiles = Object.fromEntries(filesBelow(projectRoot).map(path => [path, readFileSync(join(projectRoot, ...path.split("/")), "utf8")]));
        const computedDigest = projectDigest(diskFiles); if (computedDigest !== profile.project_digest) throw new Error("profile project digest drifted");
        const relift = reliftBoundedInteractionProject(id, diskFiles);
        if (relift.model_digest !== profile.relift_model_digest || canonical(relift.block_digests) !== canonical(profile.relift_block_digests)) throw new Error("profile relift digests drifted");
        const expectedDriver = runtimeDriverContract(id, relift.model);
        if (canonical(profile.runtime_driver_contract) !== canonical(expectedDriver)) throw new Error("runtime driver/projection contract drifted");
        const manifestArtifact = readJsonArtifact(output, profile.manifest_path, artifactDigest(JSON.parse(readFileSync(safeCampaignFile(output, profile.manifest_path, `${id}.manifest-path`), "utf8"))), `${id}.manifest`).value;
        const manifestDigest = manifestArtifact.manifest_digest; const { manifest_digest: _ignored, ...manifestBase } = manifestArtifact;
        if (frontendFormalDigest(manifestBase) !== manifestDigest || manifestDigest !== profile.manifest_digest
          || manifestArtifact.project_digest !== computedDigest || manifestArtifact.source_fixture_digest !== profile.source_fixture_digest
          || canonical(manifestArtifact.runtime_driver_contract) !== canonical(expectedDriver)) throw new Error("profile manifest linkage drifted");
        verifiedProfiles.set(id, { project: generateBoundedInteractionProject(request), relift, canonical_model: canonicalBoundedFrontendInteractionModel(request), project_digest: computedDigest, source_fixture_bytes: sourceBytes, source_fixture_digest: bytesDigest(sourceBytes) });
      } catch (error) { errors.push(`${id}: ${error instanceof Error ? error.message : String(error)}`); }
    }
    if (verifiedProfiles.size !== 9) throw new Error("verified profile closure is incomplete");

    const routes = campaign.routes;
    if (!Array.isArray(routes) || routes.length !== 72) throw new Error("campaign route closure is not 72");
    const seenRoutes = new Set<string>();
    const expectedBlockCounts = Object.fromEntries(interactionBlockIds.map(blockId => [blockId, {
      PROVED_UNDER_ASSUMPTIONS: 0,
      REFUTED: 0,
      NOT_PROVED: 0,
    }])) as Record<InteractionBlockId, Record<InteractionFormalStatus, number>>;
    for (const raw of routes) {
      const route = raw as Record<string, unknown>; const routeId = String(route.route_id);
      try {
        exactObjectKeys(route, ["route_id", "source_profile", "target_profile", "source_project_digest", "target_project_digest", "evidence_path", "evidence_digest", "formal_input_path", "formal_input_digest", "behavior_path", "behavior_digest", "chunks_path", "chunks_digest", "solver_input_path", "solver_input_digest", "solver_result_path", "solver_result_digest", "vacuity_input_path", "vacuity_input_digest", "vacuity_solver_result_path", "vacuity_solver_result_digest", "block_results_path", "block_results_digest", "composition_path", "composition_digest", "layered_result", "status"], `${routeId}.route`);
        const sourceId = route.source_profile as UiFrameworkId; const targetId = route.target_profile as UiFrameworkId;
        if (routeId !== `${sourceId}--to--${targetId}` || sourceId === targetId || seenRoutes.has(routeId)) throw new Error("route identity is invalid or duplicated");
        seenRoutes.add(routeId); const source = verifiedProfiles.get(sourceId)!; const target = verifiedProfiles.get(targetId)!;
        if (!source || !target || route.source_project_digest !== source.project_digest || route.target_project_digest !== target.project_digest) throw new Error("route project links drifted");
        const routeRoot = `routes/${routeId}`;
        const fixedPaths = {
          source_model_path: `${routeRoot}/source-model.json`, target_model_path: `${routeRoot}/target-model.json`,
          behavior_path: `${routeRoot}/behavior.json`, chunks_path: `${routeRoot}/chunks.json`, formal_input_path: `${routeRoot}/formal-input.json`,
          smt2_path: `${routeRoot}/proof.smt2`, solver_result_path: `${routeRoot}/solver-result.json`,
          vacuity_input_path: `${routeRoot}/vacuity-precheck.smt2`, vacuity_solver_result_path: `${routeRoot}/vacuity-solver-result.json`,
          block_results_path: `${routeRoot}/block-results.json`, composition_path: `${routeRoot}/composition.json`, layered_result_path: `${routeRoot}/layered-result.json`,
        };
        const sourceModelArtifact = readJsonArtifact(output, fixedPaths.source_model_path, artifactDigest(source.relift), `${routeId}.source-model`).value;
        const targetModelArtifact = readJsonArtifact(output, fixedPaths.target_model_path, artifactDigest(target.relift), `${routeId}.target-model`).value;
        if (canonical(sourceModelArtifact) !== canonical(source.relift) || canonical(targetModelArtifact) !== canonical(target.relift)) throw new Error("route source/target model artifact drifted");
        const formal = readJsonArtifact(output, route.formal_input_path, route.formal_input_digest, `${routeId}.formal`).value;
        const behaviorArtifact = readJsonArtifact(output, route.behavior_path, route.behavior_digest, `${routeId}.behavior`).value;
        const chunkArtifact = readJsonArtifact(output, route.chunks_path, route.chunks_digest, `${routeId}.chunks`).value;
        const blockArtifact = readJsonArtifact(output, route.block_results_path, route.block_results_digest, `${routeId}.blocks`).value;
        const composition = readJsonArtifact(output, route.composition_path, route.composition_digest, `${routeId}.composition`).value;
        const layered = readJsonArtifact(output, route.evidence_path, route.evidence_digest, `${routeId}.layered`).value;
        const canonicalObservations = observeInteractionScenarioSet(canonicalModel, "canonical");
        const referenceObservations = observeInteractionScenarioSet(canonicalModel, "reference");
        const sourceObservations = observeInteractionScenarioSet(source.relift.model, "source"); const targetObservations = observeInteractionScenarioSet(target.relift.model, "target");
        const semanticEqual = canonical(source.relift.model) === canonical(canonicalModel) && canonical(target.relift.model) === canonical(canonicalModel);
        const behaviorEqual = canonical(behaviorComparable(canonicalObservations)) === canonical(behaviorComparable(referenceObservations))
          && canonical(behaviorComparable(canonicalObservations)) === canonical(behaviorComparable(sourceObservations))
          && canonical(behaviorComparable(canonicalObservations)) === canonical(behaviorComparable(targetObservations));
        const expectedBehavior = { schema_version: "1.0", kind: "bounded-interaction-model-behavior",
          domain: { scenario_manifest_path: "scenario-corpus.json", scenario_manifest_digest: scenarioManifest.source_sha256, scenario_count: interactionScenarioIds.length, model_reducer: "BOUNDED_PURE_REDUCER", browser_runtime: "NOT_RUN", native_runtime: "NOT_RUN" },
          canonical: { runtime_kind: "AUTHORITATIVE_MODEL_REDUCER", observations: canonicalObservations }, reference: { runtime_kind: "SAME_ENGINE_SEPARATE_TABLE_REDUCER", observations: referenceObservations },
          source: { runtime_kind: "RELIFTED_EMITTED_SOURCE_MODEL_REDUCER", observations: sourceObservations }, target: { runtime_kind: "RELIFTED_EMITTED_TARGET_MODEL_REDUCER", observations: targetObservations },
          equivalent: behaviorEqual, oracle_provenance: { independence: "NOT_INDEPENDENT_SINGLE_ENGINE", solver_result_used_as_oracle: false, runtime_observation_source: "NOT_RUN" }, runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER" };
        if (canonical(behaviorArtifact) !== canonical(expectedBehavior) || route.behavior_path !== fixedPaths.behavior_path
          || route.behavior_digest !== artifactDigest(expectedBehavior)) throw new Error("route behavior evidence reconstruction drifted");
        const expectedChunks = routeChunks(source.relift, target.relift);
        const chunkEqual = expectedChunks.every(chunk => chunk.equivalent === true);
        const expectedChunkArtifact = { schema_version: "1.0", kind: "bounded-interaction-rfc6901-chunks", route_id: routeId, chunks: expectedChunks, equivalent: chunkEqual };
        if (canonical(chunkArtifact) !== canonical(expectedChunkArtifact) || route.chunks_path !== fixedPaths.chunks_path
          || route.chunks_digest !== artifactDigest(expectedChunkArtifact)) throw new Error("route chunk evidence reconstruction drifted");
        const expectedFormal = {
          schema_version: "1.0", kind: "frontend-bounded-interaction-formal-input", corpus_id: "frontend-bounded-interaction-corpus-v1",
          proof_profile: "bounded-frontend-interaction-v1", proof_scope: "typed canonical bounded interaction IR <-> emitted source re-lift <-> emitted target re-lift",
          route_id: routeId,
          tuple: { source_profile: sourceId, source_framework_version: uiTargetProfile(sourceId).frameworkVersion,
            target_profile: targetId, target_framework_version: uiTargetProfile(targetId).frameworkVersion },
          source_project_digest: source.project_digest, target_project_digest: target.project_digest,
          canonical_model: canonicalModel, canonical_model_digest: frontendFormalDigest(canonicalModel),
          canonical_block_digests: Object.fromEntries(interactionBlockIds.map(id => [id, frontendFormalDigest(canonicalModel[blockModelKeys[id]])])),
          source_model_digest: source.relift.model_digest, target_model_digest: target.relift.model_digest,
          source_block_digests: source.relift.block_digests, target_block_digests: target.relift.block_digests,
          source_model_artifact_digest: artifactDigest(source.relift), target_model_artifact_digest: artifactDigest(target.relift),
          semantic_equal: semanticEqual, behavior_digest: artifactDigest(expectedBehavior), behavior_equal: behaviorEqual,
          chunk_digest: artifactDigest(expectedChunkArtifact), chunk_equal: chunkEqual,
          scenario_manifest_digest: scenarioManifest.source_sha256, mutation_campaign_digest: mutationLink.digest,
          semantic_block_ids: interactionBlockIds, block_symbol_map: interactionBlockSymbolMap,
          influence_classes: { model: interactionInfluenceMatrix, runtime: interactionRuntimeInfluenceMatrix },
          assumptions: proofAssumptions, oracle_provenance: { independence: "NOT_INDEPENDENT_SINGLE_ENGINE", formal_input_from_solver_result: false, oracle_from_solver_result: false },
          arbitrary_customer_source: "NOT_PROVED", compiler_framework_runtime_soundness: "ASSUMED_NOT_PROVED",
          runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER",
        };
        const expectedFormalDigest = artifactDigest(expectedFormal);
        if (canonical(formal) !== canonical(expectedFormal) || route.formal_input_path !== fixedPaths.formal_input_path
          || route.formal_input_digest !== expectedFormalDigest) throw new Error("route formal input reconstruction drifted");
        const smt2 = readFileSync(safeCampaignFile(output, route.solver_input_path, `${routeId}.smt`), "utf8");
        const expectedSmt2 = buildInteractionSmt2(canonicalModel, source.relift.model, target.relift.model, canonicalModel, expectedFormalDigest);
        const expectedSmtDigest = bytesDigest(expectedSmt2);
        if (route.solver_input_path !== fixedPaths.smt2_path || bytesDigest(smt2) !== route.solver_input_digest
          || smt2 !== expectedSmt2 || route.solver_input_digest !== expectedSmtDigest) throw new Error("route symbolic SMT reconstruction drifted");
        const solver = readJsonArtifact(output, route.solver_result_path, route.solver_result_digest, `${routeId}.solver`).value;
        exactObjectKeys(solver, ["schema_version", "solver", "solver_binary_realpath", "solver_binary_sha256", "solver_version", "identity_status", "invocation", "options", "environment", "exit_code", "stdout", "stderr", "outcome", "proof_status", "unconditional_proof", "route_id", "formal_input_digest", "solver_input_digest", "smt2_digest"], `${routeId}.solver`);
        const solverReplay = verifySolverArtifact(solver, smt2, expectedFormalDigest, expectedSmtDigest, undefined, options.solver?.command, solverReplayCache);
        if (!solverReplay) throw new Error("route solver result is not replayable");
        const expectedSolver = solverResultWithLinks(solverReplay, routeId, expectedFormalDigest, expectedSmtDigest);
        const expectedSolverDigest = artifactDigest(expectedSolver);
        if (canonical(solver) !== canonical(expectedSolver) || route.solver_result_path !== fixedPaths.solver_result_path
          || route.solver_result_digest !== expectedSolverDigest) throw new Error("route solver result reconstruction drifted");
        const vacuity = readFileSync(safeCampaignFile(output, route.vacuity_input_path, `${routeId}.vacuity`), "utf8");
        const expectedVacuity = buildInteractionVacuitySmt2(expectedFormalDigest); const expectedVacuityDigest = bytesDigest(expectedVacuity);
        if (route.vacuity_input_path !== fixedPaths.vacuity_input_path || bytesDigest(vacuity) !== route.vacuity_input_digest
          || vacuity !== expectedVacuity || route.vacuity_input_digest !== expectedVacuityDigest) throw new Error("route vacuity SMT reconstruction drifted");
        const vacuitySolver = readJsonArtifact(output, route.vacuity_solver_result_path, route.vacuity_solver_result_digest, `${routeId}.vacuity-solver`).value;
        exactObjectKeys(vacuitySolver, ["schema_version", "solver", "solver_binary_realpath", "solver_binary_sha256", "solver_version", "identity_status", "invocation", "options", "environment", "exit_code", "stdout", "stderr", "outcome", "proof_status", "unconditional_proof", "route_id", "formal_input_digest", "solver_input_digest", "smt2_digest", "precheck_status"], `${routeId}.vacuity-solver`);
        const vacuityReplay = verifySolverArtifact(vacuitySolver, vacuity, expectedFormalDigest, expectedVacuityDigest, "SAT", options.solver?.command, solverReplayCache);
        if (!vacuityReplay) throw new Error("route vacuity solver result is not replayable");
        const expectedVacuitySolver = { ...solverResultWithLinks(vacuityReplay, routeId, expectedFormalDigest, expectedVacuityDigest), precheck_status: "PASSED" };
        const expectedVacuitySolverDigest = artifactDigest(expectedVacuitySolver);
        if (canonical(vacuitySolver) !== canonical(expectedVacuitySolver) || route.vacuity_solver_result_path !== fixedPaths.vacuity_solver_result_path
          || route.vacuity_solver_result_digest !== expectedVacuitySolverDigest) throw new Error("route vacuity solver result reconstruction drifted");
        const expectedStatus: InteractionFormalStatus = !semanticEqual || !behaviorEqual || !chunkEqual ? "REFUTED"
          : vacuityReplay.outcome !== "SAT" ? "NOT_PROVED" : solverReplay.proof_status;
        const expectedBlockResults = interactionBlockIds.map(blockId => {
          const blockChunks = expectedChunks.filter(chunk => chunk.block_id === blockId);
          const blockWitnesses = expectedCounterexamples.filter(row => row.block_id === blockId);
          const behaviorDenominator = blockWitnesses.filter(row => row.influence_class !== "DECLARATION_ECHO");
          const semanticMutantDetected = blockWitnesses.every(row => row.semantic_mutant_detected);
          const behaviorMutantDetected = behaviorDenominator.length > 0 && behaviorDenominator.every(row => row.behavior_mutant_detected);
          const blockBehaviorEqual = blockBehaviorDigest(canonicalObservations, blockId) === blockBehaviorDigest(referenceObservations, blockId)
            && blockBehaviorDigest(canonicalObservations, blockId) === blockBehaviorDigest(sourceObservations, blockId)
            && blockBehaviorDigest(canonicalObservations, blockId) === blockBehaviorDigest(targetObservations, blockId);
          const seededMutationPassed = (mutations as readonly Record<string, unknown>[]).find(row => row.block_id === blockId)?.status === "REFUTED_AS_EXPECTED";
          const blockStatus: InteractionFormalStatus = expectedStatus === "PROVED_UNDER_ASSUMPTIONS" && semanticMutantDetected && behaviorMutantDetected && seededMutationPassed
            ? "PROVED_UNDER_ASSUMPTIONS" : expectedStatus === "REFUTED" ? "REFUTED" : "NOT_PROVED";
          expectedBlockCounts[blockId][blockStatus] += 1;
          return {
            block_id: blockId, obligation_symbol: `diff_${interactionBlockSymbolMap[blockId]}`,
            influence_classes: { model: interactionInfluenceMatrix[blockId], runtime: interactionRuntimeInfluenceMatrix[blockId] },
            model_influence_max: aggregateModelInfluence(blockId), runtime_influence_max: aggregateRuntimeInfluence(blockId),
            canonical_block_digest: frontendFormalDigest(canonicalModel[blockModelKeys[blockId]]),
            source_block_digest: source.relift.block_digests[blockId], target_block_digest: target.relift.block_digests[blockId],
            behavior_block_digest: blockBehaviorDigest(canonicalObservations, blockId), chunk_block_digest: frontendFormalDigest(blockChunks),
            formal_input_digest: expectedFormalDigest, solver_input_digest: expectedSmtDigest, solver_result_digest: expectedSolverDigest,
            vacuity_input_digest: expectedVacuityDigest, vacuity_solver_result_digest: expectedVacuitySolverDigest,
            mutation_campaign_digest: mutationLink.digest,
            semantic_status: semanticEqual ? "PASSED" : "FAILED", chunk_status: blockChunks.every(chunk => chunk.equivalent === true) ? "PASSED" : "FAILED",
            model_behavior_status: blockBehaviorEqual ? "PASSED" : "FAILED", raw_solver_status: solverReplay.proof_status, formal_status: blockStatus,
            assumption_precheck: vacuityReplay.outcome === "SAT" ? "SAT_NON_VACUOUS_DOMAIN" : "FAILED",
            semantic_mutant_detected: semanticMutantDetected, behavior_mutant_detected: behaviorMutantDetected,
            declaration_echo_excluded_from_behavior_denominator: true,
            runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER", runtime_status: "NOT_RUN",
            oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE", status: blockStatus,
          };
        });
        const expectedBlockArtifact = { schema_version: "1.0", kind: "bounded-interaction-block-results", route_id: routeId, blocks: expectedBlockResults };
        const expectedComposition = {
          schema_version: "1.0", kind: "bounded-interaction-route-composition", route_id: routeId,
          source_lifting: { profile_id: sourceId, project_digest: source.project_digest, model_digest: source.relift.model_digest },
          target_lowering_relift: { profile_id: targetId, project_digest: target.project_digest, model_digest: target.relift.model_digest },
          canonical_model_digest: frontendFormalDigest(canonicalModel), semantic_equal: semanticEqual, chunk_equal: chunkEqual,
          model_behavior_equal: behaviorEqual, solver_outcome: solverReplay.outcome, vacuity_outcome: vacuityReplay.outcome,
          cross_channel_equivalence: Object.fromEntries(routeRuntimeChannels(sourceId, targetId).map(channel => [channel, "NOT_RUN"])),
          oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE", status: expectedStatus,
        };
        const expectedLinks = {
          ...fixedPaths,
          source_model_digest: artifactDigest(source.relift), target_model_digest: artifactDigest(target.relift),
          behavior_digest: artifactDigest(expectedBehavior), chunks_digest: artifactDigest(expectedChunkArtifact), formal_input_digest: expectedFormalDigest,
          smt2_digest: expectedSmtDigest, solver_result_digest: expectedSolverDigest,
          vacuity_input_digest: expectedVacuityDigest, vacuity_solver_result_digest: expectedVacuitySolverDigest,
          block_results_digest: artifactDigest(expectedBlockArtifact), composition_digest: artifactDigest(expectedComposition), mutation_campaign_digest: mutationLink.digest,
        };
        const expectedLayered = {
          schema_version: "1.0", kind: "bounded-interaction-layered-result", route_id: routeId,
          proof_profile: "bounded-frontend-interaction-v1", links: expectedLinks,
          layers: { emitted_source_relift: "PASSED", emitted_target_relift: "PASSED", semantic: semanticEqual ? "PASSED" : "FAILED",
            chunk: chunkEqual ? "PASSED" : "FAILED", model_behavior: behaviorEqual ? "PASSED" : "FAILED",
            assumption_vacuity_precheck: vacuityReplay.outcome, smt_solver: solverReplay.outcome,
            framework_native_build: "NOT_RUN", framework_browser_or_device_runtime: "NOT_RUN", independent_external_verification: "NOT_RUN" },
          oracle_provenance: "NOT_INDEPENDENT_SINGLE_ENGINE", runtime_evidence_eligibility: "INELIGIBLE_SAME_PRODUCER",
          status: expectedStatus, unconditional_proof: false, certification: "NOT_CERTIFIED", assumptions: proofAssumptions,
        };
        const expectedRoute = {
          route_id: routeId, source_profile: sourceId, target_profile: targetId,
          source_project_digest: source.project_digest, target_project_digest: target.project_digest,
          evidence_path: fixedPaths.layered_result_path, evidence_digest: artifactDigest(expectedLayered),
          formal_input_path: fixedPaths.formal_input_path, formal_input_digest: expectedFormalDigest,
          behavior_path: fixedPaths.behavior_path, behavior_digest: artifactDigest(expectedBehavior),
          chunks_path: fixedPaths.chunks_path, chunks_digest: artifactDigest(expectedChunkArtifact),
          solver_input_path: fixedPaths.smt2_path, solver_input_digest: expectedSmtDigest,
          solver_result_path: fixedPaths.solver_result_path, solver_result_digest: expectedSolverDigest,
          vacuity_input_path: fixedPaths.vacuity_input_path, vacuity_input_digest: expectedVacuityDigest,
          vacuity_solver_result_path: fixedPaths.vacuity_solver_result_path, vacuity_solver_result_digest: expectedVacuitySolverDigest,
          block_results_path: fixedPaths.block_results_path, block_results_digest: artifactDigest(expectedBlockArtifact),
          composition_path: fixedPaths.composition_path, composition_digest: artifactDigest(expectedComposition),
          layered_result: expectedStatus, status: expectedStatus,
        };
        if (canonical(blockArtifact) !== canonical(expectedBlockArtifact)) throw new Error("route block results reconstruction drifted");
        if (canonical(composition) !== canonical(expectedComposition)) throw new Error("route composition reconstruction drifted");
        if (canonical(layered) !== canonical(expectedLayered)) throw new Error("route layered result reconstruction drifted");
        if (canonical(route) !== canonical(expectedRoute)) throw new Error("campaign route row reconstruction drifted");
      } catch (error) { errors.push(`${routeId}: ${error instanceof Error ? error.message : String(error)}`); }
    }
    if (seenRoutes.size !== 72 || uiConversionRoutes().some(route => !seenRoutes.has(route.routeId))) errors.push("campaign directed route closure is incomplete");
    const expectedCounts = Object.fromEntries(["PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"].map(status => [status, routes.filter(route => (route as Record<string, unknown>).status === status).length]));
    if (canonical(campaign.counts) !== canonical(expectedCounts)) errors.push("campaign route counts drifted");
    if (canonical(campaign.block_counts) !== canonical(expectedBlockCounts)) errors.push("campaign block counts drifted");
  } catch (error) { errors.push(error instanceof Error ? error.message : String(error)); }
  return errors;
}
