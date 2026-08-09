import { createHash } from "node:crypto";

import {
  boundedInteractionScenarios,
  canonicalBoundedFrontendInteractionModel,
  interactionBlockIds,
  interactionContractSource,
  interactionSourceSpec,
  navigationCompatibilitySource,
  type BoundedFrontendInteractionModel,
  type InteractionObservation,
  type InteractionScenario,
} from "./bounded-interaction-source.js";
import { generateUiProject, validateUiProjectGenerationRequest } from "./project-generation.js";
import { uiTargetProfile, uiTargetProfiles } from "./project-profiles.js";
import type {
  GeneratedUiProject,
  UiFrameworkId,
  UiInteractionBindingV2,
  UiIrNode,
  UiProjectGenerationRequest,
  UiProjectGenerationRequestV2,
} from "./project-types.js";

const sha256 = /^sha256:[a-f0-9]{64}$/;
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

function digest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value), "utf8").digest("hex")}`;
}

function exactKeys(value: object, expected: readonly string[], name: string): void {
  const actual = Object.keys(value).sort(codePointCompare);
  const wanted = [...expected].sort(codePointCompare);
  if (actual.join("|") !== wanted.join("|")) throw new Error(`${name} shape drifted`);
}

function requireBinding(value: UiInteractionBindingV2, name: string): void {
  if (!value || typeof value !== "object" || typeof value.id !== "string" || value.id.length === 0) {
    throw new Error(`${name}.id is required`);
  }
  if (!Array.isArray(value.references) || !Array.isArray(value.sourceRefs) || value.sourceRefs.length === 0) {
    throw new Error(`${name} references/sourceRefs are required`);
  }
}

function validateExactBlock(
  name: string,
  value: UiInteractionBindingV2 & Readonly<Record<string, unknown>>,
  fields: readonly string[],
  expected: Readonly<Record<string, unknown>>,
): void {
  requireBinding(value, name);
  exactKeys(value, ["id", "references", "sourceRefs", ...fields], name);
  const semantic = Object.fromEntries(fields.map(field => [field, value[field]]));
  if (canonical(semantic) !== canonical(expected)) throw new Error(`${name} literal contract drifted`);
}

function blockBindings(request: UiProjectGenerationRequestV2): readonly [string, UiInteractionBindingV2][] {
  const ir = request.uiIr;
  return [
    ["componentTemplate", ir.componentTemplate],
    ["stateManagement", ir.stateManagement],
    ["actionEvent", ir.actionEvent],
    ["effectLifecycle", ir.effectLifecycle],
    ["formBindingValidation", ir.formBindingValidation],
    ["apiNetwork", ir.apiNetwork],
    ["identityPermission", ir.identityPermission],
    ["renderingHydration", ir.renderingHydration],
    ["accessibilityFocus", ir.accessibilityFocus],
    ["i18nThemeResponsive", ir.i18nThemeResponsive],
    ["nativePlatform", ir.nativePlatform],
  ];
}

export type BoundedFrontendInteractionBlockId = (typeof interactionBlockIds)[number];

export interface BoundedFrontendBlockObserverContract {
  readonly observer_kind: string;
  readonly measurement_surface: string;
  readonly browser_status: "PASSED" | "NOT_RUN";
  readonly browser_reason: string;
  readonly native_status: "PASSED" | "NOT_RUN";
  readonly native_reason: string;
}

/**
 * Frozen block-specific runtime observer interface.  The strings in this
 * table are part of the runner/pack wire contract and therefore deliberately
 * remain exact rather than being presentation copy.
 */
export const boundedFrontendBlockObserverContracts: Readonly<Record<BoundedFrontendInteractionBlockId, BoundedFrontendBlockObserverContract>> = {
  "route-navigation-deeplink-404": {
    observer_kind: "ROUTER_DOM_URL_OBSERVER",
    measurement_surface: "page.url+[data-elmos-active-route] attrs",
    browser_status: "PASSED",
    browser_reason: "history and rendered route DOM are independently captured",
    native_status: "PASSED",
    native_reason: "eligible only when native navigation semantics are captured on a real runtime channel",
  },
  "component-template-view": {
    observer_kind: "RENDERED_COMPONENT_DOM_OBSERVER",
    measurement_surface: "active route heading/text/visibility attrs",
    browser_status: "PASSED",
    browser_reason: "rendered heading, text, visibility, and route attributes are captured",
    native_status: "PASSED",
    native_reason: "eligible only when the rendered native component semantics are captured on a real runtime channel",
  },
  "state-management": {
    observer_kind: "FRAMEWORK_STATE_TRANSITION_OBSERVER",
    measurement_surface: "[data-elmos-state-measurement] before/after/saturated",
    browser_status: "PASSED",
    browser_reason: "framework state transition is rendered as raw attributes",
    native_status: "PASSED",
    native_reason: "eligible only when native framework state before, after, and saturation are captured",
  },
  "action-event": {
    observer_kind: "NATIVE_EVENT_OUTCOME_OBSERVER",
    measurement_surface: "captured click/keydown/submit + [data-elmos-action-outcome]",
    browser_status: "PASSED",
    browser_reason: "native browser events and rendered handler outcome are captured",
    native_status: "PASSED",
    native_reason: "eligible only when the native input event and handler outcome are captured",
  },
  "effect-lifecycle": {
    observer_kind: "FRAMEWORK_LIFECYCLE_TRACE_OBSERVER",
    measurement_surface: "ordered [data-elmos-lifecycle-event]",
    browser_status: "NOT_RUN",
    browser_reason: "the bounded browser driver does not remount and dispose the framework component per scenario",
    native_status: "PASSED",
    native_reason: "eligible only when ordered native mount, background, foreground, and dispose events are captured",
  },
  "form-binding-validation": {
    observer_kind: "FORM_CONTROL_VALIDITY_OBSERVER",
    measurement_surface: "control value+ValidityState+error DOM+focus",
    browser_status: "PASSED",
    browser_reason: "live form control, browser ValidityState, error DOM, and active element are captured",
    native_status: "PASSED",
    native_reason: "eligible only when native control value, validation, error semantics, and focus are captured",
  },
  "api-network": {
    observer_kind: "BROWSER_NETWORK_OBSERVER",
    measurement_surface: "Playwright request/response/requestfailed + app abort/stale marker",
    browser_status: "NOT_RUN",
    browser_reason: "the bounded browser diagnostic does not yet prove timeout, retry, tenant cache, and unmount cancellation as one complete API contract",
    native_status: "NOT_RUN",
    native_reason: "a single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation",
  },
  "identity-permission": {
    observer_kind: "AUTHORITY_ADAPTER_OBSERVER",
    measurement_surface: "[data-elmos-auth-decision] only if real adapter trace",
    browser_status: "NOT_RUN",
    browser_reason: "no real authority adapter is installed in the bounded local browser profile",
    native_status: "PASSED",
    native_reason: "eligible only when a real native authority adapter decision trace is captured",
  },
  "rendering-hydration": {
    observer_kind: "SSR_HYDRATION_OBSERVER",
    measurement_surface: "server markup digest+hydration warnings/mutations/effect count",
    browser_status: "NOT_RUN",
    browser_reason: "the generated browser profiles are client rendered and expose no SSR hydration boundary",
    native_status: "PASSED",
    native_reason: "eligible only when the applicable native rendering lifecycle and mutation surface is captured",
  },
  "accessibility-focus": {
    observer_kind: "ACCESSIBILITY_TREE_FOCUS_OBSERVER",
    measurement_surface: "aria snapshot+axe+active element+keyboard",
    browser_status: "PASSED",
    browser_reason: "accessibility tree, axe, focus, and keyboard events are captured by the browser driver",
    native_status: "PASSED",
    native_reason: "eligible only when native accessibility semantics, focus, and input events are captured",
  },
  "i18n-theme-responsive": {
    observer_kind: "COMPUTED_LAYOUT_I18N_THEME_OBSERVER",
    measurement_surface: "html lang+rendered translated text+computed theme tokens+measured layout",
    browser_status: "PASSED",
    browser_reason: "document language, rendered text, computed styles, and element geometry are captured",
    native_status: "PASSED",
    native_reason: "eligible only when native locale, rendered text, theme tokens, and measured layout are captured",
  },
  "native-platform": {
    observer_kind: "NATIVE_ADAPTER_DEVICE_OBSERVER",
    measurement_surface: "native semantics+lifecycle+permission+adapter trace",
    browser_status: "NOT_RUN",
    browser_reason: "a browser channel cannot supply device identity or a native adapter trace",
    native_status: "PASSED",
    native_reason: "eligible only when real device semantics, lifecycle, permission, and adapter traces are captured",
  },
};

/**
 * Legacy bounded reducer retained only for model-level comparison and channel
 * expectation fixtures.  Generated runtime consumers do not import or execute
 * it: actual runtime evidence must come from the block-specific observer
 * surfaces declared below.
 */
export function reduceBoundedFrontendRuntime(
  model: BoundedFrontendInteractionModel,
  scenario: InteractionScenario,
): InteractionObservation {
  const input = scenario.input;
  const routes = model.navigation.routes.slice();
  const first = routes[0];
  if (!first) throw new Error("runtime interaction reducer requires a route");
  let requested = first;
  for (const route of routes) if (route.path === input.routePath) requested = route;
  const exactTenant = model.identityPermission.tenantIsolation === "EXACT_TENANT_MATCH"
    && input.tenantId === input.resourceTenantId;
  const canOpen = (route: typeof first): boolean => !route.requiresAuth
    || (input.authenticated && input.permissionGranted && exactTenant);
  const authorized = canOpen(requested);
  const selected = authorized ? requested : first;
  const query = input.query === "" ? model.formBindingValidation.initialValue : input.query;
  const submitted = input.event === "SUBMIT" || input.keyboardKey === model.actionEvent.keyboardSubmit;
  const validated = model.formBindingValidation.validation !== "ON_SUBMIT" || submitted;
  const valid = (!model.formBindingValidation.required || query.length > 0)
    && query.length >= model.formBindingValidation.minimumLength;
  const apiCalled = validated && valid && authorized;
  const canceled = input.event === "CANCEL"
    || (model.apiNetwork.cancelOnUnmount && input.lifecycle === "UNMOUNT");
  const staleIgnored = canceled && input.networkResult === "STALE"
    && model.effectLifecycle.staleResponsePolicy === "IGNORE_AFTER_CANCEL";
  const rawCounter = Math.max(input.counterBefore, model.stateManagement.initial) + input.incrementCount;
  const counterAfter = model.stateManagement.transition === "SATURATING_INCREMENT"
    ? Math.max(model.stateManagement.minimum, Math.min(model.stateManagement.maximum, rawCounter))
    : Math.max(input.counterBefore, model.stateManagement.initial);
  const errorCode = validated && !valid ? model.formBindingValidation.invalidCode : null;
  const focusTarget = errorCode === null ? (submitted ? "result" : null) : model.accessibilityFocus.invalidFocusTarget;
  const localeSupported = model.i18nThemeResponsive.supportedLocales.some(value => value === input.locale);
  const themeSupported = model.i18nThemeResponsive.themes.some(value => value === input.theme);
  const locale = localeSupported ? input.locale : model.i18nThemeResponsive.fallbackLocale;
  const theme = themeSupported ? input.theme : model.i18nThemeResponsive.defaultTheme;
  let nativeTarget: typeof first | null = null;
  if (input.deepLinkPath !== null) {
    nativeTarget = first;
    for (const route of routes) if (route.path === input.deepLinkPath) nativeTarget = route;
  }
  const nativeTargetAuthorized = nativeTarget === null || canOpen(nativeTarget);
  const nativeAttempted = input.event === "NATIVE_DEEPLINK" && input.deepLinkPath !== null
    && model.nativePlatform.capability === "OPEN_DEEP_LINK";
  const nativeLifecycleKnown = model.nativePlatform.lifecycleStates.some(value => value === input.nativeLifecycle);
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
    after: { counter: counterAfter, selectedRouteId: selected.id, authorized, apiCalled, focusTarget, nativeAllowed },
    blocks: {
      "route-navigation-deeplink-404": {
        requestedPath: input.routePath, selectedRouteId: selected.id, selectedPath: selected.path, resolution,
        navigationLabel: model.navigation.label, fallback: model.navigation.fallback,
        deepLink: selected.deepLink, requiresAuth: selected.requiresAuth,
      },
      "component-template-view": {
        componentId: model.componentTemplate.componentId, templateKind: model.componentTemplate.templateKind,
        keyedBy: model.componentTemplate.keyedBy, titleBinding: model.componentTemplate.titleBinding,
        textBinding: model.componentTemplate.textBinding,
        key: model.componentTemplate.keyedBy === "route.id" ? selected.id : "",
        title: model.componentTemplate.titleBinding === "route.title" ? selected.title : "",
        text: model.componentTemplate.textBinding === "route.text" ? selected.text : "", visible: true,
      },
      "state-management": {
        stateId: model.stateManagement.stateId, initial: model.stateManagement.initial,
        minimum: model.stateManagement.minimum, maximum: model.stateManagement.maximum,
        transition: model.stateManagement.transition, before: input.counterBefore, after: counterAfter,
        saturated: rawCounter > model.stateManagement.maximum,
      },
      "action-event": {
        event: input.event, keyboardKey: input.keyboardKey,
        handled: model.actionEvent.acceptedEvents.some(value => value === input.event),
        action: submitted ? (valid && authorized ? "SUBMIT_ACCEPTED" : model.actionEvent.deniedAction) : input.event,
      },
      "effect-lifecycle": {
        lifecycle: input.lifecycle, mountEffect: input.lifecycle === "MOUNT" ? model.effectLifecycle.mountEffect : "NONE",
        cleanupEffect: input.lifecycle === "UNMOUNT" ? model.effectLifecycle.cleanupEffect : "NONE",
        maxExecutionsPerMount: model.effectLifecycle.maxExecutionsPerMount,
        staleResponsePolicy: model.effectLifecycle.staleResponsePolicy,
        executions: input.lifecycle === "MOUNT" ? model.effectLifecycle.maxExecutionsPerMount : 0,
        cleanup: input.lifecycle === "UNMOUNT", staleResponseIgnored: staleIgnored,
      },
      "form-binding-validation": {
        formId: model.formBindingValidation.formId, fieldId: model.formBindingValidation.fieldId,
        initialValue: model.formBindingValidation.initialValue, required: model.formBindingValidation.required,
        minimumLength: model.formBindingValidation.minimumLength, validation: model.formBindingValidation.validation,
        value: query, submitted, validated, valid, errorCode,
      },
      "api-network": {
        operationId: model.apiNetwork.operationId, called: apiCalled, method: model.apiNetwork.method,
        path: model.apiNetwork.path, timeoutMs: model.apiNetwork.timeoutMs, retry: model.apiNetwork.retry,
        cacheScope: model.apiNetwork.cacheScope, cancelOnUnmount: model.apiNetwork.cancelOnUnmount,
        outcome: networkOutcome, canceled, staleIgnored,
        cacheKey: model.apiNetwork.cacheScope === "TENANT_QUERY" ? `${input.tenantId}:${query}` : query,
      },
      "identity-permission": {
        role: input.authenticated ? model.identityPermission.authenticatedRole : model.identityPermission.anonymousRole,
        permission: model.identityPermission.requiredPermission, permissionGranted: input.permissionGranted,
        deniedBehavior: model.identityPermission.deniedBehavior, tenantIsolation: model.identityPermission.tenantIsolation,
        tenantMatch: exactTenant, authorized, serverAuthorityRequired: model.identityPermission.serverAuthorityRequired,
      },
      "rendering-hydration": {
        mode: model.renderingHydration.mode, hydrationPolicy: model.renderingHydration.hydrationPolicy,
        requested: input.hydration, status: hydrationStatus,
        duplicateEffectsAllowed: model.renderingHydration.duplicateEffectsAllowed,
        duplicateEffects: model.renderingHydration.duplicateEffectsAllowed && input.hydration === "MISMATCH",
        mismatchVisible: input.hydration === "MISMATCH",
      },
      "accessibility-focus": {
        mainRole: model.accessibilityFocus.mainRole, headingLevel: model.accessibilityFocus.headingLevel,
        formLabel: model.accessibilityFocus.formLabel,
        errorRole: errorCode === null ? null : model.accessibilityFocus.errorRole,
        liveRegion: model.accessibilityFocus.liveRegion,
        keyboardSubmit: input.keyboardKey === model.accessibilityFocus.keyboardSubmit, focusTarget,
      },
      "i18n-theme-responsive": {
        requestedLocale: input.locale, localeSupported, locale,
        requestedTheme: input.theme, themeSupported, theme, viewportWidth: input.viewportWidth,
        columns: input.viewportWidth <= model.i18nThemeResponsive.compactBreakpoint
          ? model.i18nThemeResponsive.compactColumns : model.i18nThemeResponsive.wideColumns,
      },
      "native-platform": {
        boundary: model.nativePlatform.boundary, capability: model.nativePlatform.capability,
        lifecycleStates: model.nativePlatform.lifecycleStates.join("|"), lifecycle: input.nativeLifecycle,
        lifecycleKnown: nativeLifecycleKnown, deepLinkPath: input.deepLinkPath,
        targetRouteId: nativeTarget?.id ?? null, targetAuthorized: nativeTargetAuthorized, attempted: nativeAttempted,
        permissionContract: model.nativePlatform.permission, permission: input.nativePermission,
        available: input.nativeAvailable, deniedBehavior: model.nativePlatform.deniedBehavior,
        outcome: !nativeAttempted ? "NOT_ATTEMPTED" : nativeAllowed ? "OPENED" : model.nativePlatform.deniedBehavior,
        recovery: nativeAllowed ? "NOT_REQUIRED" : model.nativePlatform.recovery,
      },
    },
  };
}

export type BoundedFrontendRuntimeChannel = "browser" | "android" | "ios" | "harmonyos";

export const boundedFrontendRuntimeActualKeys = {
  "route-navigation-deeplink-404": ["requestedPath", "selectedRouteId", "selectedPath", "resolution", "deepLink", "requiresAuth"],
  "component-template-view": ["componentId", "key", "title", "text", "visible"],
  "state-management": ["stateId", "before", "after", "saturated"],
  "action-event": ["event", "keyboardKey", "handled", "action"],
  "effect-lifecycle": ["lifecycle", "effect", "executions", "cleanup", "staleResponseIgnored"],
  "form-binding-validation": ["formId", "fieldId", "value", "submitted", "valid", "errorCode"],
  "api-network": ["operationId", "called", "method", "path", "outcome", "canceled", "staleIgnored", "cacheKey"],
  "identity-permission": ["role", "permission", "permissionGranted", "tenantMatch", "authorized", "serverAuthorityRequired"],
  "rendering-hydration": ["mode", "requested", "status", "duplicateEffects", "mismatchVisible"],
  "accessibility-focus": ["mainRole", "headingLevel", "formLabel", "errorRole", "liveRegion", "keyboardSubmit", "focusTarget"],
  "i18n-theme-responsive": ["requestedLocale", "locale", "requestedTheme", "theme", "viewportWidth", "columns"],
  "native-platform": ["boundary", "lifecycle", "attempted", "permission", "available", "outcome", "recovery"],
} as const;

/** Strict runtime-evidence projection; declaration-only fields remain in the formal model. */
export function projectBoundedFrontendRuntimeObservation(
  observation: InteractionObservation,
  channel: BoundedFrontendRuntimeChannel,
): Readonly<Record<string, Readonly<Record<string, unknown>>>> {
  const blocks = observation.blocks;
  const navigation = blocks["route-navigation-deeplink-404"];
  const component = blocks["component-template-view"];
  const state = blocks["state-management"];
  const action = blocks["action-event"];
  const effect = blocks["effect-lifecycle"];
  const form = blocks["form-binding-validation"];
  const api = blocks["api-network"];
  const identity = blocks["identity-permission"];
  const rendering = blocks["rendering-hydration"];
  const a11y = blocks["accessibility-focus"];
  const display = blocks["i18n-theme-responsive"];
  const native = blocks["native-platform"];
  const browser = channel === "browser";
  return {
    "route-navigation-deeplink-404": {
      requestedPath: navigation.requestedPath, selectedRouteId: navigation.selectedRouteId,
      selectedPath: navigation.selectedPath, resolution: navigation.resolution,
      deepLink: navigation.deepLink, requiresAuth: navigation.requiresAuth,
    },
    "component-template-view": {
      componentId: component.componentId, key: component.key, title: component.title,
      text: component.text, visible: component.visible,
    },
    "state-management": { stateId: state.stateId, before: state.before, after: state.after, saturated: state.saturated },
    "action-event": { event: action.event, keyboardKey: action.keyboardKey, handled: action.handled, action: action.action },
    "effect-lifecycle": {
      lifecycle: effect.lifecycle,
      effect: effect.lifecycle === "MOUNT" ? effect.mountEffect : effect.lifecycle === "UNMOUNT" ? effect.cleanupEffect : "NONE",
      executions: effect.executions, cleanup: effect.cleanup, staleResponseIgnored: effect.staleResponseIgnored,
    },
    "form-binding-validation": {
      formId: form.formId, fieldId: form.fieldId, value: form.value, submitted: form.submitted,
      valid: form.valid, errorCode: form.errorCode,
    },
    "api-network": {
      operationId: api.operationId, called: api.called, method: api.method, path: api.path,
      outcome: api.outcome, canceled: api.canceled, staleIgnored: api.staleIgnored, cacheKey: api.cacheKey,
    },
    "identity-permission": {
      role: identity.role, permission: identity.permission, permissionGranted: identity.permissionGranted,
      tenantMatch: identity.tenantMatch, authorized: identity.authorized,
      serverAuthorityRequired: identity.serverAuthorityRequired,
    },
    "rendering-hydration": {
      mode: rendering.mode, requested: rendering.requested, status: rendering.status,
      duplicateEffects: rendering.duplicateEffects, mismatchVisible: rendering.mismatchVisible,
    },
    "accessibility-focus": {
      mainRole: a11y.mainRole, headingLevel: a11y.headingLevel, formLabel: a11y.formLabel,
      errorRole: a11y.errorRole, liveRegion: a11y.liveRegion,
      keyboardSubmit: a11y.keyboardSubmit, focusTarget: a11y.focusTarget,
    },
    "i18n-theme-responsive": {
      requestedLocale: display.requestedLocale, locale: display.locale,
      requestedTheme: display.requestedTheme, theme: display.theme,
      viewportWidth: display.viewportWidth, columns: display.columns,
    },
    "native-platform": {
      boundary: native.boundary, lifecycle: native.lifecycle,
      attempted: browser ? false : native.attempted, permission: native.permission,
      available: browser ? false : native.available,
      outcome: browser ? "NOT_ATTEMPTED" : native.outcome,
      recovery: native.recovery,
    },
  };
}

function nodeFromBinding(name: string, value: UiInteractionBindingV2): UiIrNode {
  return { id: value.id, name, kind: `bounded-interaction-${name}`, references: value.references, sourceRefs: value.sourceRefs };
}

export function interactionV2ToV1Request(request: UiProjectGenerationRequestV2): UiProjectGenerationRequest {
  const byName = Object.fromEntries(blockBindings(request).map(([name, value]) => [name, nodeFromBinding(name, value)])) as Record<string, UiIrNode>;
  return {
    schemaVersion: "1.0",
    projectName: request.projectName,
    applicationId: request.applicationId,
    title: request.title,
    source: request.source,
    targetFramework: request.targetFramework,
    packageName: request.packageName,
    bundleId: request.bundleId,
    uiIr: {
      schemaVersion: "1.0",
      sourceSnapshotDigest: request.uiIr.sourceSnapshotDigest,
      routes: request.uiIr.routes,
      views: request.uiIr.views,
      components: request.uiIr.components,
      states: [byName.stateManagement!],
      actions: [byName.actionEvent!],
      effects: [byName.effectLifecycle!],
      forms: [byName.formBindingValidation!],
      bindings: [byName.componentTemplate!],
      permissions: [byName.identityPermission!],
      resources: [byName.apiNetwork!, byName.renderingHydration!],
      designTokens: [byName.i18nThemeResponsive!],
      accessibility: [byName.accessibilityFocus!],
      nativeBoundaries: [byName.nativePlatform!],
      unknowns: request.uiIr.unknowns,
    },
  };
}

export function validateUiProjectGenerationRequestV2(
  request: UiProjectGenerationRequestV2,
): UiProjectGenerationRequestV2 {
  if (!request || typeof request !== "object" || request.schemaVersion !== "2.0") throw new Error("interaction request schemaVersion 2.0 is required");
  exactKeys(request, ["schemaVersion", "projectName", "applicationId", "title", "source", "targetFramework", "packageName", "bundleId", "uiIr"], "interaction request");
  exactKeys(request.source, ["framework", "version", "platform"], "interaction source tuple");
  if (!request.uiIr || request.uiIr.schemaVersion !== "2.0" || request.uiIr.profile !== "bounded-frontend-interaction-v1") {
    throw new Error("bounded frontend interaction UI IR v2 identity is required");
  }
  exactKeys(request.uiIr, [
    "schemaVersion", "profile", "sourceSnapshotDigest", "routes", "views", "components", "componentTemplate",
    "stateManagement", "actionEvent", "effectLifecycle", "formBindingValidation", "apiNetwork", "identityPermission",
    "renderingHydration", "accessibilityFocus", "i18nThemeResponsive", "nativePlatform", "unknowns",
  ], "uiIr v2");
  if (!sha256.test(request.uiIr.sourceSnapshotDigest)) throw new Error("uiIr v2 sourceSnapshotDigest is invalid");
  for (const [index, route] of request.uiIr.routes.entries()) {
    exactKeys(route, ["id", "name", "kind", "references", "sourceRefs", "path", "componentId", "requiresAuth", "deepLink"], `uiIr.routes[${index}]`);
  }
  for (const [index, view] of request.uiIr.views.entries()) exactKeys(view, ["id", "name", "kind", "references", "sourceRefs"], `uiIr.views[${index}]`);
  for (const [index, component] of request.uiIr.components.entries()) {
    exactKeys(component, ["id", "name", "kind", "references", "sourceRefs", "text", "accessibilityRole"], `uiIr.components[${index}]`);
  }
  const ir = request.uiIr;
  validateExactBlock("componentTemplate", ir.componentTemplate as typeof ir.componentTemplate & Readonly<Record<string, unknown>>,
    ["componentId", "templateKind", "keyedBy", "titleBinding", "textBinding"],
    { componentId: "interaction.shell", templateKind: "ROUTE_DETAIL_WITH_INTERACTION_MATRIX", keyedBy: "route.id", titleBinding: "route.title", textBinding: "route.text" });
  validateExactBlock("stateManagement", ir.stateManagement as typeof ir.stateManagement & Readonly<Record<string, unknown>>,
    ["stateId", "initial", "minimum", "maximum", "transition"],
    { stateId: "bounded.counter", initial: 0, minimum: 0, maximum: 2, transition: "SATURATING_INCREMENT" });
  validateExactBlock("actionEvent", ir.actionEvent as typeof ir.actionEvent & Readonly<Record<string, unknown>>,
    ["acceptedEvents", "deniedAction", "keyboardSubmit"],
    { acceptedEvents: ["BOOT", "NAVIGATE", "AUTHENTICATE", "SUBMIT", "CANCEL", "HYDRATE", "DISPLAY_CHANGE", "NATIVE_DEEPLINK"], deniedAction: "BLOCK", keyboardSubmit: "Enter" });
  validateExactBlock("effectLifecycle", ir.effectLifecycle as typeof ir.effectLifecycle & Readonly<Record<string, unknown>>,
    ["mountEffect", "cleanupEffect", "maxExecutionsPerMount", "staleResponsePolicy"],
    { mountEffect: "LOAD_ON_MOUNT", cleanupEffect: "CANCEL_ON_UNMOUNT", maxExecutionsPerMount: 1, staleResponsePolicy: "IGNORE_AFTER_CANCEL" });
  validateExactBlock("formBindingValidation", ir.formBindingValidation as typeof ir.formBindingValidation & Readonly<Record<string, unknown>>,
    ["formId", "fieldId", "initialValue", "required", "minimumLength", "validation", "invalidCode"],
    { formId: "search", fieldId: "query", initialValue: "", required: true, minimumLength: 2, validation: "ON_SUBMIT", invalidCode: "QUERY_TOO_SHORT" });
  validateExactBlock("apiNetwork", ir.apiNetwork as typeof ir.apiNetwork & Readonly<Record<string, unknown>>,
    ["operationId", "method", "path", "timeoutMs", "retry", "cacheScope", "cancelOnUnmount"],
    { operationId: "search", method: "POST", path: "/api/search", timeoutMs: 1000, retry: "NEVER", cacheScope: "TENANT_QUERY", cancelOnUnmount: true });
  validateExactBlock("identityPermission", ir.identityPermission as typeof ir.identityPermission & Readonly<Record<string, unknown>>,
    ["anonymousRole", "authenticatedRole", "requiredPermission", "deniedBehavior", "tenantIsolation", "serverAuthorityRequired"],
    { anonymousRole: "ANONYMOUS", authenticatedRole: "MEMBER", requiredPermission: "search:execute", deniedBehavior: "HIDE_AND_BLOCK", tenantIsolation: "EXACT_TENANT_MATCH", serverAuthorityRequired: true });
  validateExactBlock("renderingHydration", ir.renderingHydration as typeof ir.renderingHydration & Readonly<Record<string, unknown>>,
    ["mode", "hydrationPolicy", "mismatchBehavior", "duplicateEffectsAllowed"],
    { mode: "HYDRATABLE_CSR", hydrationPolicy: "REQUIRE_MATCH", mismatchBehavior: "RENDER_ERROR", duplicateEffectsAllowed: false });
  validateExactBlock("accessibilityFocus", ir.accessibilityFocus as typeof ir.accessibilityFocus & Readonly<Record<string, unknown>>,
    ["navigationLabel", "mainRole", "headingLevel", "formLabel", "errorRole", "liveRegion", "invalidFocusTarget", "keyboardSubmit"],
    { navigationLabel: "主要导航", mainRole: "main", headingLevel: 1, formLabel: "搜索", errorRole: "alert", liveRegion: "polite", invalidFocusTarget: "query", keyboardSubmit: "Enter" });
  validateExactBlock("i18nThemeResponsive", ir.i18nThemeResponsive as typeof ir.i18nThemeResponsive & Readonly<Record<string, unknown>>,
    ["supportedLocales", "fallbackLocale", "themes", "defaultTheme", "compactBreakpoint", "compactColumns", "wideColumns"],
    { supportedLocales: ["zh-CN", "en-US"], fallbackLocale: "en-US", themes: ["LIGHT", "DARK"], defaultTheme: "LIGHT", compactBreakpoint: 720, compactColumns: 1, wideColumns: 2 });
  validateExactBlock("nativePlatform", ir.nativePlatform as typeof ir.nativePlatform & Readonly<Record<string, unknown>>,
    ["boundary", "capability", "lifecycleStates", "permission", "deniedBehavior", "recovery"],
    { boundary: "ADAPTER", capability: "OPEN_DEEP_LINK", lifecycleStates: ["FOREGROUND", "BACKGROUND"], permission: "DEEPLINK_OPEN", deniedBehavior: "NO_OP_REPORTED", recovery: "FOREGROUND_RETRY" });
  validateUiProjectGenerationRequest(interactionV2ToV1Request(request));

  const ids = new Set<string>();
  for (const node of [...request.uiIr.routes, ...request.uiIr.views, ...request.uiIr.components]) {
    if (ids.has(node.id)) throw new Error(`duplicate UI interaction id: ${node.id}`);
    ids.add(node.id);
  }
  for (const [name, binding] of blockBindings(request)) {
    requireBinding(binding, name);
    if (ids.has(binding.id)) throw new Error(`duplicate UI interaction id: ${binding.id}`);
    ids.add(binding.id);
  }
  for (const node of [
    ...request.uiIr.routes, ...request.uiIr.views, ...request.uiIr.components,
    ...blockBindings(request).map(([, binding]) => binding),
  ]) {
    for (const reference of node.references) if (!ids.has(reference)) throw new Error(`UI interaction reference is unresolved: ${reference}`);
    for (const sourceRef of node.sourceRefs) {
      if (typeof sourceRef !== "string" || sourceRef.startsWith("/") || sourceRef.includes("..")
        || !/^[A-Za-z0-9._/-]+:[1-9][0-9]*$/.test(sourceRef)) throw new Error(`UI interaction sourceRef is unsafe or non-canonical: ${sourceRef}`);
    }
  }
  const exactReferences = (name: string, actual: readonly string[], expected: readonly string[]): void => {
    if (canonical(actual) !== canonical(expected)) throw new Error(`${name} role dependency graph drifted`);
  };
  for (const route of request.uiIr.routes) exactReferences(`route ${route.id}`, route.references, [route.componentId, ir.identityPermission.id]);
  for (const component of request.uiIr.components) exactReferences(`component ${component.id}`, component.references, [ir.componentTemplate.id, ir.accessibilityFocus.id, ir.i18nThemeResponsive.id]);
  exactReferences("view shell", request.uiIr.views[0]?.references ?? [], [ir.componentTemplate.id]);
  exactReferences("componentTemplate", ir.componentTemplate.references, request.uiIr.routes.map(route => route.id));
  exactReferences("stateManagement", ir.stateManagement.references, [ir.componentTemplate.id]);
  exactReferences("actionEvent", ir.actionEvent.references, [ir.stateManagement.id, ir.formBindingValidation.id]);
  exactReferences("effectLifecycle", ir.effectLifecycle.references, [ir.actionEvent.id, ir.apiNetwork.id]);
  exactReferences("formBindingValidation", ir.formBindingValidation.references, [ir.accessibilityFocus.id]);
  exactReferences("apiNetwork", ir.apiNetwork.references, [ir.formBindingValidation.id, ir.identityPermission.id, ir.effectLifecycle.id]);
  exactReferences("identityPermission", ir.identityPermission.references, [ir.actionEvent.id]);
  exactReferences("renderingHydration", ir.renderingHydration.references, [ir.componentTemplate.id, ir.effectLifecycle.id]);
  exactReferences("accessibilityFocus", ir.accessibilityFocus.references, [ir.componentTemplate.id, ir.formBindingValidation.id, ir.actionEvent.id]);
  exactReferences("i18nThemeResponsive", ir.i18nThemeResponsive.references, [ir.componentTemplate.id]);
  exactReferences("nativePlatform", ir.nativePlatform.references, [ir.identityPermission.id, ir.effectLifecycle.id]);

  // Materializing the typed IR through the canonical builder also narrows all
  // literal unions at runtime; the source emitter never substitutes defaults.
  const model = canonicalBoundedFrontendInteractionModel(request);
  if (model.actionEvent.acceptedEvents.join("|") !== "BOOT|NAVIGATE|AUTHENTICATE|SUBMIT|CANCEL|HYDRATE|DISPLAY_CHANGE|NATIVE_DEEPLINK"
    || model.stateManagement.minimum !== 0 || model.stateManagement.maximum !== 2
    || model.formBindingValidation.minimumLength !== 2 || model.apiNetwork.cacheScope !== "TENANT_QUERY"
    || model.identityPermission.tenantIsolation !== "EXACT_TENANT_MATCH"
    || model.renderingHydration.hydrationPolicy !== "REQUIRE_MATCH"
    || model.accessibilityFocus.liveRegion !== "polite"
    || model.i18nThemeResponsive.compactBreakpoint !== 720
    || model.nativePlatform.recovery !== "FOREGROUND_RETRY") {
    throw new Error("bounded frontend interaction literal profile drifted");
  }
  return request;
}

function runtimeReducerDeclaration(profile: UiFrameworkId): string {
  const raw = reduceBoundedFrontendRuntime.toString();
  const untyped = "function reduceBoundedFrontendRuntime(model, scenario)";
  if (!raw.includes(untyped)) throw new Error("runtime reducer source header drifted");
  const header = profile === "vue2"
    ? "function elmosReduceRuntime(model, scenario)"
    : "export function elmosReduceRuntime(model: typeof ELMOS_FRONTEND_INTERACTION, scenario: ElmosRuntimeScenario)";
  const types = profile === "vue2" ? "" : [
    "export interface ElmosRuntimeInput {",
    "  readonly routePath: string; readonly event: 'BOOT' | 'NAVIGATE' | 'AUTHENTICATE' | 'SUBMIT' | 'CANCEL' | 'HYDRATE' | 'DISPLAY_CHANGE' | 'NATIVE_DEEPLINK';",
    "  readonly keyboardKey: string | null; readonly counterBefore: number; readonly incrementCount: number; readonly lifecycle: 'MOUNT' | 'ACTIVE' | 'UNMOUNT';",
    "  readonly query: string; readonly networkResult: 'NONE' | 'SUCCESS' | 'ERROR' | 'STALE'; readonly authenticated: boolean; readonly permissionGranted: boolean;",
    "  readonly tenantId: string; readonly resourceTenantId: string; readonly hydration: 'NONE' | 'MATCH' | 'MISMATCH'; readonly locale: string; readonly theme: string;",
    "  readonly viewportWidth: number; readonly nativeLifecycle: 'FOREGROUND' | 'BACKGROUND'; readonly nativePermission: 'GRANTED' | 'DENIED';",
    "  readonly nativeAvailable: boolean; readonly deepLinkPath: string | null;",
    "}",
    "export interface ElmosRuntimeScenario { readonly scenarioId: string; readonly input: ElmosRuntimeInput; }",
    "",
  ].join("\n");
  const typedRaw = profile === "vue2" ? raw : raw.replace("const canOpen = (route) =>", "const canOpen = (route: (typeof routes)[number]) =>");
  return `${types}${typedRaw.replace(untyped, header)}`;
}

function runtimeProjectionDeclaration(profile: UiFrameworkId): string {
  const raw = projectBoundedFrontendRuntimeObservation.toString();
  const untyped = "function projectBoundedFrontendRuntimeObservation(observation, channel)";
  if (!raw.includes(untyped)) throw new Error("runtime projection source header drifted");
  const header = profile === "vue2"
    ? "export function elmosProjectRuntimeObservation(observation, channel)"
    : "export function elmosProjectRuntimeObservation(observation: ReturnType<typeof elmosReduceRuntime>, channel: ElmosRuntimeChannel)";
  const type = profile === "vue2" ? "" : "export type ElmosRuntimeChannel = 'browser' | 'android' | 'ios' | 'harmonyos';\n";
  return `${type}${raw.replace(untyped, header)}`;
}

function tsRuntimeModule(profile: UiFrameworkId): string {
  const exported = profile === "vue2" ? runtimeReducerDeclaration(profile).replace("function elmosReduceRuntime", "export function elmosReduceRuntime") : runtimeReducerDeclaration(profile);
  return [
    "// Independent generated runtime reducer. It consumes the typed contract and runtime event input only.",
    'import { ELMOS_FRONTEND_INTERACTION } from "./elmos-bounded-interaction";',
    exported,
    runtimeProjectionDeclaration(profile),
    "",
  ].join("\n");
}

function dartRuntimeModule(): string {
  return [
    "// Independent runtime reducer; no canonical observer or expected observation is imported.",
    "import 'elmos_bounded_interaction.dart' show elmosFrontendInteraction, elmosMap, elmosList;",
    `const List<String> elmosRuntimeBlockIds = ${JSON.stringify(interactionBlockIds)};`,
    `const Map<String, List<String>> elmosRuntimeActualKeys = ${JSON.stringify(boundedFrontendRuntimeActualKeys)};`,
    "Map<String, Object?> elmosReduceRuntime(Object? rawScenario) {",
    "  final model = elmosFrontendInteraction; final scenario = elmosMap(rawScenario); final input = elmosMap(scenario['input']); final navigation = elmosMap(model['navigation']); final routes = elmosList(navigation['routes']).map(elmosMap).toList(growable: false); final first = routes.first;",
    "  final requested = routes.firstWhere((route) => route['path'] == input['routePath'], orElse: () => first); final identity = elmosMap(model['identityPermission']); final tenantMatch = identity['tenantIsolation'] == 'EXACT_TENANT_MATCH' && input['tenantId'] == input['resourceTenantId'];",
    "  bool canOpen(Map<String, Object?> route) => route['requiresAuth'] != true || (input['authenticated'] == true && input['permissionGranted'] == true && tenantMatch); final authorized = canOpen(requested); final selected = authorized ? requested : first;",
    "  final form = elmosMap(model['formBindingValidation']); final rawQuery = input['query']! as String; final query = rawQuery.isEmpty ? form['initialValue']! as String : rawQuery; final action = elmosMap(model['actionEvent']); final submitted = input['event'] == 'SUBMIT' || input['keyboardKey'] == action['keyboardSubmit']; final validated = form['validation'] != 'ON_SUBMIT' || submitted; final valid = (form['required'] != true || query.isNotEmpty) && query.length >= (form['minimumLength']! as num); final apiCalled = validated && valid && authorized;",
    "  final api = elmosMap(model['apiNetwork']); final canceled = input['event'] == 'CANCEL' || (api['cancelOnUnmount'] == true && input['lifecycle'] == 'UNMOUNT'); final effect = elmosMap(model['effectLifecycle']); final staleIgnored = canceled && input['networkResult'] == 'STALE' && effect['staleResponsePolicy'] == 'IGNORE_AFTER_CANCEL';",
    "  final state = elmosMap(model['stateManagement']); final rawCounter = (input['counterBefore']! as num).clamp(state['initial']! as num, double.infinity) + (input['incrementCount']! as num); final counterAfter = state['transition'] == 'SATURATING_INCREMENT' ? rawCounter.clamp(state['minimum']! as num, state['maximum']! as num) : (input['counterBefore']! as num).clamp(state['initial']! as num, double.infinity);",
    "  final a11y = elmosMap(model['accessibilityFocus']); final errorCode = validated && !valid ? form['invalidCode'] : null; final focusTarget = errorCode == null ? (submitted ? 'result' : null) : a11y['invalidFocusTarget']; final display = elmosMap(model['i18nThemeResponsive']); final localeSupported = elmosList(display['supportedLocales']).contains(input['locale']); final themeSupported = elmosList(display['themes']).contains(input['theme']); final locale = localeSupported ? input['locale'] : display['fallbackLocale']; final theme = themeSupported ? input['theme'] : display['defaultTheme'];",
    "  final native = elmosMap(model['nativePlatform']); final nativeTarget = input['deepLinkPath'] == null ? null : routes.firstWhere((route) => route['path'] == input['deepLinkPath'], orElse: () => first); final nativeTargetAuthorized = nativeTarget == null || canOpen(nativeTarget); final nativeAttempted = input['event'] == 'NATIVE_DEEPLINK' && input['deepLinkPath'] != null && native['capability'] == 'OPEN_DEEP_LINK'; final nativeLifecycleKnown = elmosList(native['lifecycleStates']).contains(input['nativeLifecycle']); final nativeAllowed = nativeAttempted && nativeTargetAuthorized && input['nativeAvailable'] == true && input['nativePermission'] == 'GRANTED' && input['nativeLifecycle'] == 'FOREGROUND' && nativeLifecycleKnown;",
    "  final rendering = elmosMap(model['renderingHydration']); final hydrationStatus = input['hydration'] == 'MISMATCH' && rendering['hydrationPolicy'] == 'REQUIRE_MATCH' ? rendering['mismatchBehavior'] : input['hydration'] == 'MATCH' ? 'MATCHED' : 'NOT_ATTEMPTED'; final networkOutcome = !apiCalled ? 'NOT_CALLED' : canceled ? 'CANCELED' : input['networkResult'] == 'SUCCESS' ? 'SUCCESS' : input['networkResult'] == 'ERROR' ? 'ERROR' : 'PENDING'; final component = elmosMap(model['componentTemplate']);",
    "  return <String, Object?>{'scenarioId': scenario['scenarioId'], 'before': <String, Object?>{'counter': input['counterBefore'], 'lifecycle': input['lifecycle'], 'query': input['query'], 'authenticated': input['authenticated']}, 'after': <String, Object?>{'counter': counterAfter, 'selectedRouteId': selected['id'], 'authorized': authorized, 'apiCalled': apiCalled, 'focusTarget': focusTarget, 'nativeAllowed': nativeAllowed}, 'blocks': <String, Object?>{",
    "    'route-navigation-deeplink-404': <String, Object?>{'requestedPath': input['routePath'], 'selectedRouteId': selected['id'], 'selectedPath': selected['path'], 'resolution': identical(requested, first) && input['routePath'] != first['path'] ? 'FIRST_DECLARED_FALLBACK' : authorized ? 'DECLARED' : 'AUTH_DENIED_FALLBACK', 'navigationLabel': navigation['label'], 'fallback': navigation['fallback'], 'deepLink': selected['deepLink'], 'requiresAuth': selected['requiresAuth']},",
    "    'component-template-view': <String, Object?>{'componentId': component['componentId'], 'templateKind': component['templateKind'], 'keyedBy': component['keyedBy'], 'titleBinding': component['titleBinding'], 'textBinding': component['textBinding'], 'key': component['keyedBy'] == 'route.id' ? selected['id'] : '', 'title': component['titleBinding'] == 'route.title' ? selected['title'] : '', 'text': component['textBinding'] == 'route.text' ? selected['text'] : '', 'visible': true},",
    "    'state-management': <String, Object?>{'stateId': state['stateId'], 'initial': state['initial'], 'minimum': state['minimum'], 'maximum': state['maximum'], 'transition': state['transition'], 'before': input['counterBefore'], 'after': counterAfter, 'saturated': rawCounter > (state['maximum']! as num)},",
    "    'action-event': <String, Object?>{'event': input['event'], 'keyboardKey': input['keyboardKey'], 'handled': elmosList(action['acceptedEvents']).contains(input['event']), 'action': submitted ? (valid && authorized ? 'SUBMIT_ACCEPTED' : action['deniedAction']) : input['event']},",
    "    'effect-lifecycle': <String, Object?>{'lifecycle': input['lifecycle'], 'mountEffect': input['lifecycle'] == 'MOUNT' ? effect['mountEffect'] : 'NONE', 'cleanupEffect': input['lifecycle'] == 'UNMOUNT' ? effect['cleanupEffect'] : 'NONE', 'maxExecutionsPerMount': effect['maxExecutionsPerMount'], 'staleResponsePolicy': effect['staleResponsePolicy'], 'executions': input['lifecycle'] == 'MOUNT' ? effect['maxExecutionsPerMount'] : 0, 'cleanup': input['lifecycle'] == 'UNMOUNT', 'staleResponseIgnored': staleIgnored},",
    "    'form-binding-validation': <String, Object?>{'formId': form['formId'], 'fieldId': form['fieldId'], 'initialValue': form['initialValue'], 'required': form['required'], 'minimumLength': form['minimumLength'], 'validation': form['validation'], 'value': query, 'submitted': submitted, 'validated': validated, 'valid': valid, 'errorCode': errorCode},",
    "    'api-network': <String, Object?>{'operationId': api['operationId'], 'called': apiCalled, 'method': api['method'], 'path': api['path'], 'timeoutMs': api['timeoutMs'], 'retry': api['retry'], 'cacheScope': api['cacheScope'], 'cancelOnUnmount': api['cancelOnUnmount'], 'outcome': networkOutcome, 'canceled': canceled, 'staleIgnored': staleIgnored, 'cacheKey': api['cacheScope'] == 'TENANT_QUERY' ? '${input['tenantId']}:$query' : query},",
    "    'identity-permission': <String, Object?>{'role': input['authenticated'] == true ? identity['authenticatedRole'] : identity['anonymousRole'], 'permission': identity['requiredPermission'], 'permissionGranted': input['permissionGranted'], 'deniedBehavior': identity['deniedBehavior'], 'tenantIsolation': identity['tenantIsolation'], 'tenantMatch': tenantMatch, 'authorized': authorized, 'serverAuthorityRequired': identity['serverAuthorityRequired']},",
    "    'rendering-hydration': <String, Object?>{'mode': rendering['mode'], 'hydrationPolicy': rendering['hydrationPolicy'], 'requested': input['hydration'], 'status': hydrationStatus, 'duplicateEffectsAllowed': rendering['duplicateEffectsAllowed'], 'duplicateEffects': rendering['duplicateEffectsAllowed'] == true && input['hydration'] == 'MISMATCH', 'mismatchVisible': input['hydration'] == 'MISMATCH'},",
    "    'accessibility-focus': <String, Object?>{'mainRole': a11y['mainRole'], 'headingLevel': a11y['headingLevel'], 'formLabel': a11y['formLabel'], 'errorRole': errorCode == null ? null : a11y['errorRole'], 'liveRegion': a11y['liveRegion'], 'keyboardSubmit': input['keyboardKey'] == a11y['keyboardSubmit'], 'focusTarget': focusTarget},",
    "    'i18n-theme-responsive': <String, Object?>{'requestedLocale': input['locale'], 'localeSupported': localeSupported, 'locale': locale, 'requestedTheme': input['theme'], 'themeSupported': themeSupported, 'theme': theme, 'viewportWidth': input['viewportWidth'], 'columns': (input['viewportWidth']! as num) <= (display['compactBreakpoint']! as num) ? display['compactColumns'] : display['wideColumns']},",
    "    'native-platform': <String, Object?>{'boundary': native['boundary'], 'capability': native['capability'], 'lifecycleStates': elmosList(native['lifecycleStates']).join('|'), 'lifecycle': input['nativeLifecycle'], 'lifecycleKnown': nativeLifecycleKnown, 'deepLinkPath': input['deepLinkPath'], 'targetRouteId': nativeTarget?['id'], 'targetAuthorized': nativeTargetAuthorized, 'attempted': nativeAttempted, 'permissionContract': native['permission'], 'permission': input['nativePermission'], 'available': input['nativeAvailable'], 'deniedBehavior': native['deniedBehavior'], 'outcome': !nativeAttempted ? 'NOT_ATTEMPTED' : nativeAllowed ? 'OPENED' : native['deniedBehavior'], 'recovery': nativeAllowed ? 'NOT_REQUIRED' : native['recovery']},",
    "  }};",
    "}",
    "Map<String, Object?> elmosProjectRuntimeObservation(Map<String, Object?> observation, String channel) { final blocks = elmosMap(observation['blocks']); final navigation = elmosMap(blocks['route-navigation-deeplink-404']); final component = elmosMap(blocks['component-template-view']); final state = elmosMap(blocks['state-management']); final action = elmosMap(blocks['action-event']); final effect = elmosMap(blocks['effect-lifecycle']); final form = elmosMap(blocks['form-binding-validation']); final api = elmosMap(blocks['api-network']); final identity = elmosMap(blocks['identity-permission']); final rendering = elmosMap(blocks['rendering-hydration']); final a11y = elmosMap(blocks['accessibility-focus']); final display = elmosMap(blocks['i18n-theme-responsive']); final native = elmosMap(blocks['native-platform']); final browser = channel == 'browser'; return <String, Object?>{",
    "  'route-navigation-deeplink-404': <String, Object?>{'requestedPath': navigation['requestedPath'], 'selectedRouteId': navigation['selectedRouteId'], 'selectedPath': navigation['selectedPath'], 'resolution': navigation['resolution'], 'deepLink': navigation['deepLink'], 'requiresAuth': navigation['requiresAuth']}, 'component-template-view': <String, Object?>{'componentId': component['componentId'], 'key': component['key'], 'title': component['title'], 'text': component['text'], 'visible': component['visible']}, 'state-management': <String, Object?>{'stateId': state['stateId'], 'before': state['before'], 'after': state['after'], 'saturated': state['saturated']}, 'action-event': <String, Object?>{'event': action['event'], 'keyboardKey': action['keyboardKey'], 'handled': action['handled'], 'action': action['action']},",
    "  'effect-lifecycle': <String, Object?>{'lifecycle': effect['lifecycle'], 'effect': effect['lifecycle'] == 'MOUNT' ? effect['mountEffect'] : effect['lifecycle'] == 'UNMOUNT' ? effect['cleanupEffect'] : 'NONE', 'executions': effect['executions'], 'cleanup': effect['cleanup'], 'staleResponseIgnored': effect['staleResponseIgnored']}, 'form-binding-validation': <String, Object?>{'formId': form['formId'], 'fieldId': form['fieldId'], 'value': form['value'], 'submitted': form['submitted'], 'valid': form['valid'], 'errorCode': form['errorCode']}, 'api-network': <String, Object?>{'operationId': api['operationId'], 'called': api['called'], 'method': api['method'], 'path': api['path'], 'outcome': api['outcome'], 'canceled': api['canceled'], 'staleIgnored': api['staleIgnored'], 'cacheKey': api['cacheKey']},",
    "  'identity-permission': <String, Object?>{'role': identity['role'], 'permission': identity['permission'], 'permissionGranted': identity['permissionGranted'], 'tenantMatch': identity['tenantMatch'], 'authorized': identity['authorized'], 'serverAuthorityRequired': identity['serverAuthorityRequired']}, 'rendering-hydration': <String, Object?>{'mode': rendering['mode'], 'requested': rendering['requested'], 'status': rendering['status'], 'duplicateEffects': rendering['duplicateEffects'], 'mismatchVisible': rendering['mismatchVisible']}, 'accessibility-focus': <String, Object?>{'mainRole': a11y['mainRole'], 'headingLevel': a11y['headingLevel'], 'formLabel': a11y['formLabel'], 'errorRole': a11y['errorRole'], 'liveRegion': a11y['liveRegion'], 'keyboardSubmit': a11y['keyboardSubmit'], 'focusTarget': a11y['focusTarget']},",
    "  'i18n-theme-responsive': <String, Object?>{'requestedLocale': display['requestedLocale'], 'locale': display['locale'], 'requestedTheme': display['requestedTheme'], 'theme': display['theme'], 'viewportWidth': display['viewportWidth'], 'columns': display['columns']}, 'native-platform': <String, Object?>{'boundary': native['boundary'], 'lifecycle': native['lifecycle'], 'attempted': browser ? false : native['attempted'], 'permission': native['permission'], 'available': browser ? false : native['available'], 'outcome': browser ? 'NOT_ATTEMPTED' : native['outcome'], 'recovery': native['recovery']}, }; }",
    "",
  ].join("\n");
}

function reactWebConsumer(): string {
  return [
    'import { FormEvent, useEffect, useRef, useState } from "react";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime, type ElmosRuntimeInput, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "type RuntimeObservation = ReturnType<typeof elmosReduceRuntime>;",
    "interface RuntimeRow { readonly observation: RuntimeObservation; readonly sequence: number; }",
    "export function ElmosInteractionPanel() {",
    "  const [rows, setRows] = useState<Readonly<Record<string, RuntimeRow>>>({});",
    "  const [sequence, setSequence] = useState(0);",
    "  const pending = useRef<ElmosRuntimeScenario | null>(null); const controller = useRef<AbortController | null>(null);",
    "  const query = useRef<HTMLInputElement>(null); const locale = useRef<HTMLSelectElement>(null); const theme = useRef<HTMLSelectElement>(null);",
    "  const authenticated = useRef<HTMLInputElement>(null); const permission = useRef<HTMLInputElement>(null); const tenant = useRef<HTMLInputElement>(null); const resourceTenant = useRef<HTMLInputElement>(null);",
    "  function dispatchValue(element: HTMLInputElement | HTMLSelectElement | null, value: string, kind: 'input' | 'change') { if (!element) return; element.value = value; element.dispatchEvent(new Event(kind, { bubbles: true })); }",
    "  function applyScenario(scenario: ElmosRuntimeScenario): ElmosRuntimeInput {",
    "    dispatchValue(query.current, scenario.input.query, 'input'); dispatchValue(locale.current, scenario.input.locale, 'change'); dispatchValue(theme.current, scenario.input.theme, 'change');",
    "    if (authenticated.current) { authenticated.current.checked = scenario.input.authenticated; authenticated.current.dispatchEvent(new Event('change', { bubbles: true })); }",
    "    if (permission.current) { permission.current.checked = scenario.input.permissionGranted; permission.current.dispatchEvent(new Event('change', { bubbles: true })); }",
    "    dispatchValue(tenant.current, scenario.input.tenantId, 'input'); dispatchValue(resourceTenant.current, scenario.input.resourceTenantId, 'input');",
    "    return { ...scenario.input, query: query.current?.value ?? scenario.input.query, locale: locale.current?.value ?? scenario.input.locale, theme: theme.current?.value ?? scenario.input.theme, authenticated: authenticated.current?.checked ?? scenario.input.authenticated, permissionGranted: permission.current?.checked ?? scenario.input.permissionGranted, tenantId: tenant.current?.value ?? scenario.input.tenantId, resourceTenantId: resourceTenant.current?.value ?? scenario.input.resourceTenantId, viewportWidth: window.innerWidth };",
    "  }",
    "  async function execute(scenario: ElmosRuntimeScenario) {",
    "    let input = applyScenario(scenario); let observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = observation.blocks['api-network'];",
    "    if (api.canceled) { controller.current?.abort(); controller.current = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.current.signal }).catch(() => undefined); controller.current.abort(); await request; controller.current = null; }",
    "    else if (api.called) { controller.current = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.current.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) input = { ...input, networkResult: 'ERROR' }; } finally { controller.current = null; } observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); }",
    "    const next = sequence + 1; setSequence(next); setRows(previous => ({ ...previous, [scenario.scenarioId]: { observation, sequence: next } }));",
    "    if (observation.blocks['accessibility-focus'].focusTarget === 'query') queueMicrotask(() => query.current?.focus());",
    "  }",
    "  function trigger(scenario: ElmosRuntimeScenario) { if (scenario.input.event === 'SUBMIT') pending.current = scenario; else void execute(scenario); }",
    "  function submitForm(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const scenario = pending.current ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending.current = null; if (scenario) void execute(scenario); }",
    "  useEffect(() => { const abort = () => controller.current?.abort(); window.addEventListener('beforeunload', abort); return () => { window.removeEventListener('beforeunload', abort); abort(); }; }, []);",
    "  return <section id=\"elmos-interaction\" data-proof-profile=\"bounded-frontend-interaction-v1\" data-runtime-scope=\"REACT_COMPONENT_ACTUAL_EVENTS\" data-elmos-ready=\"true\" data-completion={sequence > 0 ? 'COMPLETE' : 'IDLE'} data-run-id={sequence} aria-label=\"ELMOS bounded interaction runtime\">",
    "    <form data-elmos-control=\"form\" aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} onSubmit={submitForm}>",
    "      <input ref={query} id=\"elmos-query\" name=\"query\" aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} /><select ref={locale} id=\"elmos-locale\" aria-label=\"locale\"><option>zh-CN</option><option>en-US</option><option>fr-FR</option><option>de-DE</option></select><select ref={theme} id=\"elmos-theme\" aria-label=\"theme\"><option>LIGHT</option><option>DARK</option><option>SEPIA</option></select>",
    "      <input ref={authenticated} id=\"elmos-authenticated\" type=\"checkbox\" aria-label=\"authenticated\" /><input ref={permission} id=\"elmos-permission\" type=\"checkbox\" aria-label=\"permission granted\" /><input ref={tenant} id=\"elmos-tenant\" aria-label=\"tenant\" /><input ref={resourceTenant} id=\"elmos-resource-tenant\" aria-label=\"resource tenant\" />",
    "      {ELMOS_INTERACTION_SCENARIOS.map(scenario => { const row = rows[scenario.scenarioId]; const projected = row ? elmosProjectRuntimeObservation(row.observation, 'browser') : null; return <article key={scenario.scenarioId} data-scenario-id={scenario.scenarioId} data-runtime-source={row ? 'framework-events' : 'unexecuted'} data-execution-state={row ? 'PARTIAL' : 'IDLE'} data-execution-sequence={row?.sequence ?? 0}><button type={scenario.input.event === 'SUBMIT' ? 'submit' : 'button'} data-run-scenario={scenario.scenarioId} data-scenario-action={scenario.scenarioId} data-elmos-event={scenario.input.event} onClick={() => trigger(scenario)}>{scenario.scenarioId}</button>{projected && Object.entries(projected).map(([blockId, block]) => <pre key={blockId} data-semantic-block={blockId}>{JSON.stringify(block)}</pre>)}</article>; })}",
    "    </form><output data-command-log=\"true\" aria-live={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion}></output>",
    "  </section>;",
    "}",
    "",
  ].join("\n");
}

function vue3WebConsumer(): string {
  return [
    '<script setup lang="ts">',
    'import { onBeforeUnmount, ref } from "vue";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime, type ElmosRuntimeInput, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "type RuntimeObservation = ReturnType<typeof elmosReduceRuntime>; interface RuntimeRow { readonly observation: RuntimeObservation; readonly sequence: number; }",
    "const rows = ref<Readonly<Record<string, RuntimeRow>>>({}); const sequence = ref(0); const pending = ref<ElmosRuntimeScenario | null>(null); let controller: AbortController | null = null;",
    "const query = ref<HTMLInputElement | null>(null); const locale = ref<HTMLSelectElement | null>(null); const theme = ref<HTMLSelectElement | null>(null); const authenticated = ref<HTMLInputElement | null>(null); const permission = ref<HTMLInputElement | null>(null); const tenant = ref<HTMLInputElement | null>(null); const resourceTenant = ref<HTMLInputElement | null>(null);",
    "function dispatchValue(element: HTMLInputElement | HTMLSelectElement | null, value: string, kind: 'input' | 'change') { if (!element) return; element.value = value; element.dispatchEvent(new Event(kind, { bubbles: true })); }",
    "function applyScenario(scenario: ElmosRuntimeScenario): ElmosRuntimeInput { dispatchValue(query.value, scenario.input.query, 'input'); dispatchValue(locale.value, scenario.input.locale, 'change'); dispatchValue(theme.value, scenario.input.theme, 'change'); if (authenticated.value) { authenticated.value.checked = scenario.input.authenticated; authenticated.value.dispatchEvent(new Event('change', { bubbles: true })); } if (permission.value) { permission.value.checked = scenario.input.permissionGranted; permission.value.dispatchEvent(new Event('change', { bubbles: true })); } dispatchValue(tenant.value, scenario.input.tenantId, 'input'); dispatchValue(resourceTenant.value, scenario.input.resourceTenantId, 'input'); return { ...scenario.input, query: query.value?.value ?? scenario.input.query, locale: locale.value?.value ?? scenario.input.locale, theme: theme.value?.value ?? scenario.input.theme, authenticated: authenticated.value?.checked ?? scenario.input.authenticated, permissionGranted: permission.value?.checked ?? scenario.input.permissionGranted, tenantId: tenant.value?.value ?? scenario.input.tenantId, resourceTenantId: resourceTenant.value?.value ?? scenario.input.resourceTenantId, viewportWidth: window.innerWidth }; }",
    "async function execute(scenario: ElmosRuntimeScenario) { let input = applyScenario(scenario); let observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = observation.blocks['api-network']; if (api.canceled) { controller?.abort(); controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }).catch(() => undefined); controller.abort(); await request; controller = null; } else if (api.called) { controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) input = { ...input, networkResult: 'ERROR' }; } finally { controller = null; } observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); } const next = sequence.value + 1; sequence.value = next; rows.value = { ...rows.value, [scenario.scenarioId]: { observation, sequence: next } }; if (observation.blocks['accessibility-focus'].focusTarget === 'query') queueMicrotask(() => query.value?.focus()); }",
    "function trigger(scenario: ElmosRuntimeScenario) { if (scenario.input.event === 'SUBMIT') pending.value = scenario; else void execute(scenario); } function submitForm(event: SubmitEvent) { event.preventDefault(); const scenario = pending.value ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending.value = null; if (scenario) void execute(scenario); }",
    "onBeforeUnmount(() => { controller?.abort(); controller = null; });",
    "</script>",
    '<template><section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-runtime-scope="VUE3_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" :data-completion="sequence > 0 ? \'COMPLETE\' : \'IDLE\'" :data-run-id="sequence" aria-label="ELMOS bounded interaction runtime">',
    '<form data-elmos-control="form" :aria-label="ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel" @submit="submitForm"><input ref="query" id="elmos-query" name="query" :aria-label="ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel"><select ref="locale" id="elmos-locale" aria-label="locale"><option>zh-CN</option><option>en-US</option><option>fr-FR</option><option>de-DE</option></select><select ref="theme" id="elmos-theme" aria-label="theme"><option>LIGHT</option><option>DARK</option><option>SEPIA</option></select><input ref="authenticated" id="elmos-authenticated" type="checkbox" aria-label="authenticated"><input ref="permission" id="elmos-permission" type="checkbox" aria-label="permission granted"><input ref="tenant" id="elmos-tenant" aria-label="tenant"><input ref="resourceTenant" id="elmos-resource-tenant" aria-label="resource tenant">',
    '<article v-for="scenario in ELMOS_INTERACTION_SCENARIOS" :key="scenario.scenarioId" :data-scenario-id="scenario.scenarioId" :data-runtime-source="rows[scenario.scenarioId] ? \'framework-events\' : \'unexecuted\'" :data-execution-state="rows[scenario.scenarioId] ? \'COMPLETE\' : \'IDLE\'" :data-execution-sequence="rows[scenario.scenarioId]?.sequence ?? 0"><button :type="scenario.input.event === \'SUBMIT\' ? \'submit\' : \'button\'" :data-run-scenario="scenario.scenarioId" :data-scenario-action="scenario.scenarioId" :data-elmos-event="scenario.input.event" @click="trigger(scenario)">{{ scenario.scenarioId }}</button><template v-if="rows[scenario.scenarioId]"><pre v-for="(block, blockId) in elmosProjectRuntimeObservation(rows[scenario.scenarioId]!.observation, \'browser\')" :key="blockId" :data-semantic-block="blockId">{{ JSON.stringify(block) }}</pre></template></article>',
    '</form><output data-command-log="true" :aria-live="ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion"></output></section></template>',
    "",
  ].join("\n");
}

function vue2WebConsumer(): string {
  return [
    '<script>',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime } from "./elmos-interaction-runtime";',
    "export default {",
    "  data: () => ({ rows: {}, sequence: 0, pending: null, controller: null, scenarios: ELMOS_INTERACTION_SCENARIOS, model: ELMOS_FRONTEND_INTERACTION }),",
    "  beforeDestroy() { if (this.controller) this.controller.abort(); this.controller = null; },",
    "  methods: {",
    "    dispatchValue(element, value, kind) { if (!element) return; element.value = value; element.dispatchEvent(new Event(kind, { bubbles: true })); },",
    "    applyScenario(scenario) { const refs = this.$refs; this.dispatchValue(refs.query, scenario.input.query, 'input'); this.dispatchValue(refs.locale, scenario.input.locale, 'change'); this.dispatchValue(refs.theme, scenario.input.theme, 'change'); refs.authenticated.checked = scenario.input.authenticated; refs.authenticated.dispatchEvent(new Event('change', { bubbles: true })); refs.permission.checked = scenario.input.permissionGranted; refs.permission.dispatchEvent(new Event('change', { bubbles: true })); this.dispatchValue(refs.tenant, scenario.input.tenantId, 'input'); this.dispatchValue(refs.resourceTenant, scenario.input.resourceTenantId, 'input'); return { ...scenario.input, query: refs.query.value, locale: refs.locale.value, theme: refs.theme.value, authenticated: refs.authenticated.checked, permissionGranted: refs.permission.checked, tenantId: refs.tenant.value, resourceTenantId: refs.resourceTenant.value, viewportWidth: window.innerWidth }; },",
    "    async execute(scenario) { let input = this.applyScenario(scenario); let observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = observation.blocks['api-network']; if (api.canceled) { if (this.controller) this.controller.abort(); this.controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: this.controller.signal }).catch(() => undefined); this.controller.abort(); await request; this.controller = null; } else if (api.called) { this.controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: this.controller.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) input = { ...input, networkResult: 'ERROR' }; } finally { this.controller = null; } observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); } this.sequence += 1; this.$set(this.rows, scenario.scenarioId, { observation, sequence: this.sequence }); if (observation.blocks['accessibility-focus'].focusTarget === 'query') this.$nextTick(() => this.$refs.query.focus()); },",
    "    trigger(scenario) { if (scenario.input.event === 'SUBMIT') this.pending = scenario; else this.execute(scenario); }, submitForm(event) { event.preventDefault(); const scenario = this.pending || this.scenarios.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS'); this.pending = null; if (scenario) this.execute(scenario); }, blockEntries(observation) { return Object.entries(elmosProjectRuntimeObservation(observation, 'browser')); },",
    "  },",
    "};",
    "</script>",
    '<template><section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-runtime-scope="VUE2_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" :data-completion="sequence > 0 ? \'COMPLETE\' : \'IDLE\'" :data-run-id="sequence" aria-label="ELMOS bounded interaction runtime"><form data-elmos-control="form" :aria-label="model.accessibilityFocus.formLabel" @submit="submitForm"><input ref="query" id="elmos-query" name="query" :aria-label="model.accessibilityFocus.formLabel"><select ref="locale" id="elmos-locale" aria-label="locale"><option>zh-CN</option><option>en-US</option><option>fr-FR</option><option>de-DE</option></select><select ref="theme" id="elmos-theme" aria-label="theme"><option>LIGHT</option><option>DARK</option><option>SEPIA</option></select><input ref="authenticated" id="elmos-authenticated" type="checkbox" aria-label="authenticated"><input ref="permission" id="elmos-permission" type="checkbox" aria-label="permission granted"><input ref="tenant" id="elmos-tenant" aria-label="tenant"><input ref="resourceTenant" id="elmos-resource-tenant" aria-label="resource tenant"><article v-for="scenario in scenarios" :key="scenario.scenarioId" :data-scenario-id="scenario.scenarioId" :data-runtime-source="rows[scenario.scenarioId] ? \'framework-events\' : \'unexecuted\'" :data-execution-state="rows[scenario.scenarioId] ? \'COMPLETE\' : \'IDLE\'" :data-execution-sequence="rows[scenario.scenarioId] ? rows[scenario.scenarioId].sequence : 0"><button :type="scenario.input.event === \'SUBMIT\' ? \'submit\' : \'button\'" :data-run-scenario="scenario.scenarioId" :data-scenario-action="scenario.scenarioId" :data-elmos-event="scenario.input.event" @click="trigger(scenario)">{{ scenario.scenarioId }}</button><template v-if="rows[scenario.scenarioId]"><pre v-for="entry in blockEntries(rows[scenario.scenarioId].observation)" :key="entry[0]" :data-semantic-block="entry[0]">{{ JSON.stringify(entry[1]) }}</pre></template></article></form><output data-command-log="true" :aria-live="model.accessibilityFocus.liveRegion"></output></section></template>',
    "",
  ].join("\n");
}

function svelteWebConsumer(): string {
  return [
    '<script lang="ts">',
    'import { onDestroy } from "svelte";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime, type ElmosRuntimeInput, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "type RuntimeObservation = ReturnType<typeof elmosReduceRuntime>; interface RuntimeRow { readonly observation: RuntimeObservation; readonly sequence: number; }",
    "let rows: Readonly<Record<string, RuntimeRow>> = {}; let sequence = 0; let pending: ElmosRuntimeScenario | null = null; let controller: AbortController | null = null;",
    "let query: HTMLInputElement; let locale: HTMLSelectElement; let theme: HTMLSelectElement; let authenticated: HTMLInputElement; let permission: HTMLInputElement; let tenant: HTMLInputElement; let resourceTenant: HTMLInputElement;",
    "function dispatchValue(element: HTMLInputElement | HTMLSelectElement, value: string, kind: 'input' | 'change') { element.value = value; element.dispatchEvent(new Event(kind, { bubbles: true })); }",
    "function applyScenario(scenario: ElmosRuntimeScenario): ElmosRuntimeInput { dispatchValue(query, scenario.input.query, 'input'); dispatchValue(locale, scenario.input.locale, 'change'); dispatchValue(theme, scenario.input.theme, 'change'); authenticated.checked = scenario.input.authenticated; authenticated.dispatchEvent(new Event('change', { bubbles: true })); permission.checked = scenario.input.permissionGranted; permission.dispatchEvent(new Event('change', { bubbles: true })); dispatchValue(tenant, scenario.input.tenantId, 'input'); dispatchValue(resourceTenant, scenario.input.resourceTenantId, 'input'); return { ...scenario.input, query: query.value, locale: locale.value, theme: theme.value, authenticated: authenticated.checked, permissionGranted: permission.checked, tenantId: tenant.value, resourceTenantId: resourceTenant.value, viewportWidth: window.innerWidth }; }",
    "async function execute(scenario: ElmosRuntimeScenario) { let input = applyScenario(scenario); let observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = observation.blocks['api-network']; if (api.canceled) { controller?.abort(); controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }).catch(() => undefined); controller.abort(); await request; controller = null; } else if (api.called) { controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) input = { ...input, networkResult: 'ERROR' }; } finally { controller = null; } observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); } sequence += 1; rows = { ...rows, [scenario.scenarioId]: { observation, sequence } }; if (observation.blocks['accessibility-focus'].focusTarget === 'query') queueMicrotask(() => query.focus()); }",
    "function trigger(scenario: ElmosRuntimeScenario) { if (scenario.input.event === 'SUBMIT') pending = scenario; else void execute(scenario); } function submitForm(event: SubmitEvent) { event.preventDefault(); const scenario = pending ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending = null; if (scenario) void execute(scenario); } function blockEntries(observation: RuntimeObservation) { return Object.entries(elmosProjectRuntimeObservation(observation, 'browser')); }",
    "onDestroy(() => { controller?.abort(); controller = null; });",
    "</script>",
    '<section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-runtime-scope="SVELTE_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" data-completion={sequence > 0 ? "PARTIAL" : "IDLE"} data-run-id={sequence} aria-label="ELMOS bounded interaction runtime"><form data-elmos-control="form" aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} onsubmit={submitForm}><input bind:this={query} id="elmos-query" name="query" aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel}><select bind:this={locale} id="elmos-locale" aria-label="locale"><option>zh-CN</option><option>en-US</option><option>fr-FR</option><option>de-DE</option></select><select bind:this={theme} id="elmos-theme" aria-label="theme"><option>LIGHT</option><option>DARK</option><option>SEPIA</option></select><input bind:this={authenticated} id="elmos-authenticated" type="checkbox" aria-label="authenticated"><input bind:this={permission} id="elmos-permission" type="checkbox" aria-label="permission granted"><input bind:this={tenant} id="elmos-tenant" aria-label="tenant"><input bind:this={resourceTenant} id="elmos-resource-tenant" aria-label="resource tenant">',
    '{#each ELMOS_INTERACTION_SCENARIOS as scenario (scenario.scenarioId)}{@const row = rows[scenario.scenarioId]}<article data-scenario-id={scenario.scenarioId} data-runtime-source={row ? "framework-events" : "unexecuted"} data-execution-state={row ? "PARTIAL" : "IDLE"} data-execution-sequence={row?.sequence ?? 0}><button type={scenario.input.event === "SUBMIT" ? "submit" : "button"} data-run-scenario={scenario.scenarioId} data-scenario-action={scenario.scenarioId} data-elmos-event={scenario.input.event} onclick={() => trigger(scenario)}>{scenario.scenarioId}</button>{#if row}{#each blockEntries(row.observation) as entry (entry[0])}<pre data-semantic-block={entry[0]}>{JSON.stringify(entry[1])}</pre>{/each}{/if}</article>{/each}</form><output data-command-log="true" aria-live={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion}></output></section>',
    "",
  ].join("\n");
}

function angularWebConsumer(): string {
  return [
    'import { Component, ElementRef, OnDestroy, ViewChild, signal } from "@angular/core";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime, type ElmosRuntimeInput, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "type RuntimeObservation = ReturnType<typeof elmosReduceRuntime>; interface RuntimeRow { readonly observation: RuntimeObservation; readonly sequence: number; }",
    "@Component({ standalone: true, selector: 'elmos-interaction', template: `",
    '<section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-runtime-scope="ANGULAR_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" [attr.data-completion]="sequence() > 0 ? \'COMPLETE\' : \'IDLE\'" [attr.data-run-id]="sequence()" aria-label="ELMOS bounded interaction runtime"><form data-elmos-control="form" [attr.aria-label]="model.accessibilityFocus.formLabel" (submit)="submitForm($event)"><input #query id="elmos-query" name="query" [attr.aria-label]="model.accessibilityFocus.formLabel"><select #locale id="elmos-locale" aria-label="locale"><option>zh-CN</option><option>en-US</option><option>fr-FR</option><option>de-DE</option></select><select #theme id="elmos-theme" aria-label="theme"><option>LIGHT</option><option>DARK</option><option>SEPIA</option></select><input #authenticated id="elmos-authenticated" type="checkbox" aria-label="authenticated"><input #permission id="elmos-permission" type="checkbox" aria-label="permission granted"><input #tenant id="elmos-tenant" aria-label="tenant"><input #resourceTenant id="elmos-resource-tenant" aria-label="resource tenant">',
    "@for (scenario of scenarios; track scenario.scenarioId) { @let row = rowFor(scenario.scenarioId); <article [attr.data-scenario-id]=\"scenario.scenarioId\" [attr.data-runtime-source]=\"row ? 'framework-events' : 'unexecuted'\" [attr.data-execution-state]=\"row ? 'COMPLETE' : 'IDLE'\" [attr.data-execution-sequence]=\"row?.sequence ?? 0\"><button [type]=\"scenario.input.event === 'SUBMIT' ? 'submit' : 'button'\" [attr.data-run-scenario]=\"scenario.scenarioId\" [attr.data-scenario-action]=\"scenario.scenarioId\" [attr.data-elmos-event]=\"scenario.input.event\" (click)=\"trigger(scenario)\">{{ scenario.scenarioId }}</button>@if (row) { @for (entry of blockEntries(row.observation); track entry[0]) { <pre [attr.data-semantic-block]=\"entry[0]\">{{ stringify(entry[1]) }}</pre> } }</article> }</form><output data-command-log=\"true\" [attr.aria-live]=\"model.accessibilityFocus.liveRegion\"></output></section>",
    "  ` })",
    "export class ElmosInteractionComponent implements OnDestroy {",
    "  readonly model = ELMOS_FRONTEND_INTERACTION; readonly scenarios = ELMOS_INTERACTION_SCENARIOS; readonly rows = signal<Readonly<Record<string, RuntimeRow>>>({}); readonly sequence = signal(0); private pending: ElmosRuntimeScenario | null = null; private controller: AbortController | null = null;",
    "  @ViewChild('query', { static: true }) private query!: ElementRef<HTMLInputElement>; @ViewChild('locale', { static: true }) private locale!: ElementRef<HTMLSelectElement>; @ViewChild('theme', { static: true }) private theme!: ElementRef<HTMLSelectElement>; @ViewChild('authenticated', { static: true }) private authenticated!: ElementRef<HTMLInputElement>; @ViewChild('permission', { static: true }) private permission!: ElementRef<HTMLInputElement>; @ViewChild('tenant', { static: true }) private tenant!: ElementRef<HTMLInputElement>; @ViewChild('resourceTenant', { static: true }) private resourceTenant!: ElementRef<HTMLInputElement>;",
    "  rowFor(id: string): RuntimeRow | undefined { return this.rows()[id]; } blockEntries(observation: RuntimeObservation): readonly (readonly [string, unknown])[] { return Object.entries(elmosProjectRuntimeObservation(observation, 'browser')); } stringify(value: unknown): string { return JSON.stringify(value); }",
    "  private dispatchValue(element: HTMLInputElement | HTMLSelectElement, value: string, kind: 'input' | 'change'): void { element.value = value; element.dispatchEvent(new Event(kind, { bubbles: true })); }",
    "  private applyScenario(scenario: ElmosRuntimeScenario): ElmosRuntimeInput { const query = this.query.nativeElement; const locale = this.locale.nativeElement; const theme = this.theme.nativeElement; const authenticated = this.authenticated.nativeElement; const permission = this.permission.nativeElement; const tenant = this.tenant.nativeElement; const resourceTenant = this.resourceTenant.nativeElement; this.dispatchValue(query, scenario.input.query, 'input'); this.dispatchValue(locale, scenario.input.locale, 'change'); this.dispatchValue(theme, scenario.input.theme, 'change'); authenticated.checked = scenario.input.authenticated; authenticated.dispatchEvent(new Event('change', { bubbles: true })); permission.checked = scenario.input.permissionGranted; permission.dispatchEvent(new Event('change', { bubbles: true })); this.dispatchValue(tenant, scenario.input.tenantId, 'input'); this.dispatchValue(resourceTenant, scenario.input.resourceTenantId, 'input'); return { ...scenario.input, query: query.value, locale: locale.value, theme: theme.value, authenticated: authenticated.checked, permissionGranted: permission.checked, tenantId: tenant.value, resourceTenantId: resourceTenant.value, viewportWidth: window.innerWidth }; }",
    "  async execute(scenario: ElmosRuntimeScenario): Promise<void> { let input = this.applyScenario(scenario); let observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = observation.blocks['api-network']; if (api.canceled) { this.controller?.abort(); this.controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: this.controller.signal }).catch(() => undefined); this.controller.abort(); await request; this.controller = null; } else if (api.called) { this.controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: this.controller.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) input = { ...input, networkResult: 'ERROR' }; } finally { this.controller = null; } observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); } const next = this.sequence() + 1; this.sequence.set(next); this.rows.update(previous => ({ ...previous, [scenario.scenarioId]: { observation, sequence: next } })); if (observation.blocks['accessibility-focus'].focusTarget === 'query') queueMicrotask(() => this.query.nativeElement.focus()); }",
    "  trigger(scenario: ElmosRuntimeScenario): void { if (scenario.input.event === 'SUBMIT') this.pending = scenario; else void this.execute(scenario); } submitForm(event: SubmitEvent): void { event.preventDefault(); const scenario = this.pending ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; this.pending = null; if (scenario) void this.execute(scenario); } ngOnDestroy(): void { this.controller?.abort(); this.controller = null; }",
    "}",
    "",
  ].join("\n");
}

function jqueryWebConsumer(): string {
  return [
    'import $ from "jquery";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime, type ElmosRuntimeInput, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "type RuntimeObservation = ReturnType<typeof elmosReduceRuntime>; let controller: AbortController | null = null; let sequence = 0; let pending: ElmosRuntimeScenario | null = null;",
    "function applyScenario(scenario: ElmosRuntimeScenario): ElmosRuntimeInput { const set = (selector: string, value: string, kind: 'input' | 'change') => { $(selector).val(value).trigger(kind); }; set('#elmos-query', scenario.input.query, 'input'); set('#elmos-locale', scenario.input.locale, 'change'); set('#elmos-theme', scenario.input.theme, 'change'); $('#elmos-authenticated').prop('checked', scenario.input.authenticated).trigger('change'); $('#elmos-permission').prop('checked', scenario.input.permissionGranted).trigger('change'); set('#elmos-tenant', scenario.input.tenantId, 'input'); set('#elmos-resource-tenant', scenario.input.resourceTenantId, 'input'); return { ...scenario.input, query: String($('#elmos-query').val() ?? ''), locale: String($('#elmos-locale').val() ?? ''), theme: String($('#elmos-theme').val() ?? ''), authenticated: Boolean($('#elmos-authenticated').prop('checked')), permissionGranted: Boolean($('#elmos-permission').prop('checked')), tenantId: String($('#elmos-tenant').val() ?? ''), resourceTenantId: String($('#elmos-resource-tenant').val() ?? ''), viewportWidth: window.innerWidth }; }",
    "function render(scenario: ElmosRuntimeScenario, observation: RuntimeObservation): void { const row = $(`[data-scenario-id=\"${scenario.scenarioId}\"]`); row.find('[data-runtime-blocks]').remove(); const blocks = $('<div>', { 'data-runtime-blocks': 'true' }); for (const [blockId, block] of Object.entries(elmosProjectRuntimeObservation(observation, 'browser'))) blocks.append($('<pre>', { 'data-semantic-block': blockId, text: JSON.stringify(block) })); sequence += 1; row.append(blocks).attr({ 'data-runtime-source': 'framework-events', 'data-execution-state': 'PARTIAL', 'data-execution-sequence': String(sequence) }); $('#elmos-interaction').attr({ 'data-completion': 'PARTIAL', 'data-run-id': String(sequence) }); if (observation.blocks['accessibility-focus'].focusTarget === 'query') $('#elmos-query').trigger('focus'); }",
    "async function execute(scenario: ElmosRuntimeScenario): Promise<void> { let input = applyScenario(scenario); let observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = observation.blocks['api-network']; if (api.canceled) { controller?.abort(); controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }).catch(() => undefined); controller.abort(); await request; controller = null; } else if (api.called) { controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) input = { ...input, networkResult: 'ERROR' }; } finally { controller = null; } observation = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); } render(scenario, observation); }",
    "export function mountElmosInteraction(root: HTMLElement): () => void { const section = $('<section>', { id: 'elmos-interaction', 'data-proof-profile': 'bounded-frontend-interaction-v1', 'data-runtime-scope': 'JQUERY_EVENTS_AND_DATA', 'data-elmos-ready': 'true', 'data-completion': 'IDLE', 'data-run-id': '0', 'aria-label': 'ELMOS bounded interaction runtime' }); const form = $('<form>', { 'data-elmos-control': 'form', 'aria-label': ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel }); form.append($('<input>', { id: 'elmos-query', name: 'query', 'aria-label': ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel }), $('<select>', { id: 'elmos-locale', 'aria-label': 'locale' }).append(...['zh-CN','en-US','fr-FR','de-DE'].map(value => $('<option>', { value, text: value }))), $('<select>', { id: 'elmos-theme', 'aria-label': 'theme' }).append(...['LIGHT','DARK','SEPIA'].map(value => $('<option>', { value, text: value }))), $('<input>', { id: 'elmos-authenticated', type: 'checkbox', 'aria-label': 'authenticated' }), $('<input>', { id: 'elmos-permission', type: 'checkbox', 'aria-label': 'permission granted' }), $('<input>', { id: 'elmos-tenant', 'aria-label': 'tenant' }), $('<input>', { id: 'elmos-resource-tenant', 'aria-label': 'resource tenant' })); for (const scenario of ELMOS_INTERACTION_SCENARIOS) { const row = $('<article>', { 'data-scenario-id': scenario.scenarioId, 'data-runtime-source': 'unexecuted', 'data-execution-state': 'IDLE', 'data-execution-sequence': '0' }); const button = $('<button>', { type: scenario.input.event === 'SUBMIT' ? 'submit' : 'button', 'data-run-scenario': scenario.scenarioId, 'data-scenario-action': scenario.scenarioId, 'data-elmos-event': scenario.input.event, text: scenario.scenarioId }); button.data('elmosScenario', scenario).on('click.elmos', () => { if (scenario.input.event === 'SUBMIT') pending = scenario; else void execute(scenario); }); row.append(button); form.append(row); } form.on('submit.elmos', event => { event.preventDefault(); const scenario = pending ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending = null; if (scenario) void execute(scenario); }); section.append(form, $('<output>', { 'data-command-log': 'true', 'aria-live': ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion })); $(root).append(section); const cleanup = () => { controller?.abort(); controller = null; form.off('.elmos'); form.find('button').off('.elmos'); }; $(window).one('beforeunload.elmos', cleanup); return cleanup; }",
    "",
  ].join("\n");
}

function nativeReactConsumer(): string {
  return [
    'import { useEffect, useRef, useState } from "react";',
    'import { Pressable, ScrollView, Text, TextInput, View } from "react-native";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosProjectRuntimeObservation, elmosReduceRuntime, type ElmosRuntimeInput, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "type RuntimeObservation = ReturnType<typeof elmosReduceRuntime>; interface RuntimeRow { readonly observation: RuntimeObservation; readonly sequence: number; }",
    "export interface ElmosNativeAdapter { readonly openDeepLink: (path: string) => Promise<boolean>; }",
    "const deniedAdapter: ElmosNativeAdapter = { openDeepLink: async () => false };",
    "export function ElmosInteractionPanel({ nativeAdapter = deniedAdapter }: { readonly nativeAdapter?: ElmosNativeAdapter }) {",
    "  const [query, setQuery] = useState(''); const [rows, setRows] = useState<Readonly<Record<string, RuntimeRow>>>({}); const [sequence, setSequence] = useState(0); const abortRef = useRef<AbortController | null>(null);",
    "  async function dispatch(scenario: ElmosRuntimeScenario) {",
    "    let input: ElmosRuntimeInput = { ...scenario.input, query: query === '' ? scenario.input.query : query }; let next = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); const api = next.blocks['api-network']; const native = next.blocks['native-platform'];",
    "    if (api.canceled) { abortRef.current?.abort(); abortRef.current = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, body: JSON.stringify({ query: input.query }), signal: abortRef.current.signal }).catch(() => undefined); abortRef.current.abort(); await request; abortRef.current = null; }",
    "    else if (api.called) { abortRef.current = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, body: JSON.stringify({ query: input.query }), signal: abortRef.current.signal }); input = { ...input, networkResult: response.ok ? 'SUCCESS' : 'ERROR' }; } catch { input = { ...input, networkResult: 'ERROR' }; } finally { abortRef.current = null; } next = elmosReduceRuntime(ELMOS_FRONTEND_INTERACTION, { ...scenario, input }); }",
    "    if (native.attempted && native.outcome === 'OPENED' && scenario.input.deepLinkPath) await nativeAdapter.openDeepLink(scenario.input.deepLinkPath); const current = sequence + 1; setSequence(current); setRows(previous => ({ ...previous, [scenario.scenarioId]: { observation: next, sequence: current } }));",
    "  }",
    "  useEffect(() => () => { abortRef.current?.abort(); }, []);",
    '  return <ScrollView nativeID="elmos-interaction" testID="elmos-interaction" dataSet={{ proofProfile: "bounded-frontend-interaction-v1", runtimeScope: "REACT_NATIVE_COMPONENT_ACTUAL_EVENTS", elmosReady: "true", completion: sequence > 0 ? "COMPLETE" : "IDLE", runId: String(sequence) }} accessibilityLabel="ELMOS bounded interaction observations">',
    '    <TextInput testID="elmos-query" accessibilityLabel={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} value={query} onChangeText={setQuery} />',
    "    {ELMOS_INTERACTION_SCENARIOS.map(scenario => { const row = rows[scenario.scenarioId]; const projected = row ? elmosProjectRuntimeObservation(row.observation, 'browser') : null; return <View key={scenario.scenarioId} testID={`scenario:${scenario.scenarioId}`} dataSet={{ scenarioId: scenario.scenarioId, runtimeSource: row ? 'framework-events' : 'unexecuted', executionState: row ? 'COMPLETE' : 'IDLE', executionSequence: String(row?.sequence ?? 0) }}><Pressable testID={`action:${scenario.scenarioId}`} dataSet={{ runScenario: scenario.scenarioId, scenarioAction: scenario.scenarioId, elmosEvent: scenario.input.event }} accessibilityRole=\"button\" onPress={() => { void dispatch(scenario); }}><Text>{scenario.scenarioId}</Text></Pressable>{projected && Object.entries(projected).map(([blockId, block]) => <Text key={blockId} testID={`block:${scenario.scenarioId}:${blockId}`} dataSet={{ semanticBlock: blockId }}>{JSON.stringify(block)}</Text>)}</View>; })}",
    "  </ScrollView>;",
    "}",
    "",
  ].join("\n");
}

function reactNativePlatformScaffoldContract(): string {
  return `${JSON.stringify({
    schema_version: "1.0",
    kind: "expo-react-native-platform-scaffold-materialization-contract",
    expo_version: "57.0.8",
    react_native_version: "0.86.0",
    node_version: "24.12.0",
    package_manager: "npm",
    ordered_commands: [
      ["npm", "install", "--package-lock-only", "--ignore-scripts"],
      ["npm", "ci", "--ignore-scripts"],
      ["npx", "--no-install", "expo", "prebuild", "--platform", "android", "--no-install"],
      ["npx", "--no-install", "expo", "prebuild", "--platform", "ios", "--no-install"],
    ],
    protected_source_paths: ["App.tsx", "src", "app.json", "index.ts", "package.json", "tsconfig.json"],
    required_captured_outputs: ["package-lock.json", "android", "ios"],
    browser_runtime_command: ["npm", "run", "web"],
    browser_export_command: ["npm", "run", "export:web"],
    native_driver_contract: {
      scenario_test_id_prefix: "action:",
      block_test_id_prefix: "block:",
      scenario_count: 18,
      block_count: 12,
      runtime_source: "REACT_NATIVE_COMPONENT_ACTUAL_EVENTS",
      precomputed_observations_allowed: false,
    },
    dependency_lock_status: "NOT_RUN",
    materialization_status: "NOT_RUN",
    android_build_status: "NOT_RUN",
    ios_simulator_build_status: "NOT_RUN",
    android_runtime_status: "NOT_RUN",
    ios_runtime_status: "NOT_RUN",
    arbitrary_environment: "NOT_PROVED",
  }, null, 2)}\n`;
}

function flutterConsumer(): string {
  return [
    "import 'dart:convert';",
    "import 'package:flutter/foundation.dart';",
    "import 'package:flutter/material.dart';",
    "import 'elmos_bounded_interaction.dart';",
    "import 'elmos_interaction_runtime.dart';",
    "typedef ElmosApiAdapter = Future<String> Function(String path, String method, String query, bool cancel);",
    "typedef ElmosNativeAdapter = Future<bool> Function(String path);",
    "class ElmosInteractionPanel extends StatefulWidget {",
    "  const ElmosInteractionPanel({this.apiAdapter, this.nativeAdapter, super.key});",
    "  final ElmosApiAdapter? apiAdapter; final ElmosNativeAdapter? nativeAdapter;",
    "  @override State<ElmosInteractionPanel> createState() => _ElmosInteractionPanelState();",
    "}",
    "class _ElmosInteractionPanelState extends State<ElmosInteractionPanel> {",
    "  final TextEditingController query = TextEditingController(); final FocusNode queryFocus = FocusNode(); final Map<String, Map<String, Object?>> observations = <String, Map<String, Object?>>{}; final Map<String, int> sequences = <String, int>{}; int sequence = 0; bool canceled = false;",
    "  String get runtimeChannel { if (kIsWeb) return 'browser'; return switch (defaultTargetPlatform) { TargetPlatform.android => 'android', TargetPlatform.iOS => 'ios', _ => 'browser' }; }",
    "  Future<void> dispatch(Object? raw) async {",
    "    final scenario = Map<String, Object?>.from(elmosMap(raw)); final input = Map<String, Object?>.from(elmosMap(scenario['input'])); input['query'] = query.text.isEmpty ? input['query'] : query.text; scenario['input'] = input;",
    "    var next = elmosReduceRuntime(scenario);",
    "    final blocks = elmosMap(next['blocks']); final api = elmosMap(blocks['api-network']); final native = elmosMap(blocks['native-platform']); final a11y = elmosMap(blocks['accessibility-focus']);",
    "    if (api['canceled'] == true) canceled = true;",
    "    if ((api['called'] == true || api['canceled'] == true) && widget.apiAdapter != null) { final outcome = await widget.apiAdapter!.call(api['path']! as String, api['method']! as String, input['query']! as String, api['canceled'] == true); input['networkResult'] = outcome; scenario['input'] = input; next = elmosReduceRuntime(scenario); }",
    "    if (runtimeChannel != 'browser' && native['attempted'] == true && native['outcome'] == 'OPENED' && input['deepLinkPath'] is String) await widget.nativeAdapter?.call(input['deepLinkPath']! as String);",
    "    if (!mounted) return; final scenarioId = scenario['scenarioId']! as String; setState(() { sequence += 1; observations[scenarioId] = next; sequences[scenarioId] = sequence; });",
    "    if (a11y['focusTarget'] == 'query') queryFocus.requestFocus();",
    "  }",
    "  @override void dispose() { canceled = true; query.dispose(); queryFocus.dispose(); super.dispose(); }",
    "  @override",
    "  Widget build(BuildContext context) => Semantics(",
    "    label: 'ELMOS bounded interaction observations',",
    "    child: Column(children: [",
    "      TextField(key: const ValueKey<String>('elmos-query'), controller: query, focusNode: queryFocus, decoration: InputDecoration(labelText: elmosMap(elmosFrontendInteraction['accessibilityFocus'])['formLabel']! as String)),",
    "      Expanded(child: SingleChildScrollView(key: const ValueKey<String>('elmos-interaction'), child: Column(children: [",
    "      for (final scenario in elmosInteractionScenarios) Builder(builder: (context) { final scenarioId = elmosMap(scenario)['scenarioId']! as String; final observation = observations[scenarioId]; return Semantics(container: true, label: 'scenario:$scenarioId:${observation == null ? 'IDLE' : 'COMPLETE'}:sequence:${sequences[scenarioId] ?? 0}', child: Column(key: ValueKey<String>('scenario:$scenarioId'), children: [FilledButton(key: ValueKey<String>('action:$scenarioId'), onPressed: () async { await dispatch(scenario); }, child: Text(scenarioId)), if (observation != null) for (final entry in elmosProjectRuntimeObservation(observation, runtimeChannel).entries) Text(jsonEncode(entry.value), key: ValueKey<String>('block:$scenarioId:${entry.key}'), semanticsLabel: 'block:${entry.key}:${jsonEncode(entry.value)}')])); }),",
    "      ]))),",
    "    ]),",
    "  );",
    "}",
    "",
  ].join("\n");
}

function flutterPlatformScaffold(projectName: string): Readonly<Record<string, string>> {
  return {
    ".metadata": [
      "# Managed Web scaffold for Flutter 3.44.1; native scaffolds are materialized by the pinned contract below.",
      "version:", "  revision: 924134a44c", "  channel: stable", "project_type: app",
      "migration:", "  platforms:", "    - platform: root", "      create_revision: 924134a44c", "      base_revision: 924134a44c",
      "    - platform: web", "      create_revision: 924134a44c", "      base_revision: 924134a44c",
      "",
    ].join("\n"),
    "web/index.html": [
      "<!DOCTYPE html>", '<html><head><base href="$FLUTTER_BASE_HREF"><meta charset="UTF-8">',
      '<meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="description" content="ELMOS bounded frontend interaction runtime">',
      `<title>${projectName}</title><link rel="manifest" href="manifest.json"></head>`,
      '<body><script src="flutter_bootstrap.js" async></script></body></html>', "",
    ].join("\n"),
    "web/manifest.json": `${JSON.stringify({ name: projectName, short_name: projectName, start_url: ".", display: "standalone", background_color: "#ffffff", theme_color: "#15223d", description: "ELMOS bounded frontend interaction runtime", icons: [] }, null, 2)}\n`,
    "platform-scaffold-contract.json": `${JSON.stringify({
      schema_version: "1.0",
      kind: "flutter-platform-scaffold-materialization-contract",
      flutter_version: "3.44.1",
      dart_version: "3.12.1",
      flutter_revision: "924134a44c",
      command: ["flutter", "create", ".", `--project-name=${projectName}`, "--org=io.elmos", "--platforms=android,ios", "--no-pub"],
      protected_source_paths: ["lib", "integration_test", "test_driver", "test", "web", "pubspec.yaml", "analysis_options.yaml"],
      required_captured_outputs: ["android", "ios", ".metadata"],
      materialization_status: "NOT_RUN",
      android_build_status: "NOT_RUN",
      ios_simulator_build_status: "NOT_RUN",
      arbitrary_environment: "NOT_PROVED",
    }, null, 2)}\n`,
  };
}

function flutterIntegrationTest(projectName: string): string {
  return [
    "import 'dart:convert';",
    "import 'package:flutter/foundation.dart';",
    "import 'package:flutter/material.dart';",
    "import 'package:flutter_test/flutter_test.dart';",
    "import 'package:integration_test/integration_test.dart';",
    `import 'package:${projectName}/elmos_bounded_interaction.dart';`,
    `import 'package:${projectName}/elmos_interaction_runtime.dart';`,
    `import 'package:${projectName}/main.dart' as app;`,
    "void main() {",
    "  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();",
    "  testWidgets('executes 18 by 12 bounded interaction semantics with adapter and focus traces', (tester) async {",
    "    final runtimeChannel = kIsWeb ? 'browser' : switch (defaultTargetPlatform) { TargetPlatform.android => 'android', TargetPlatform.iOS => 'ios', _ => throw UnsupportedError('bounded interaction integration channel is unsupported') }; final scenarios = <Map<String, Object?>>[]; final networkEvents = <String, List<Map<String, Object?>>>{}; final platformEvents = <String, List<Map<String, Object?>>>{}; var activeScenarioId = '';",
    "    await tester.pumpWidget(app.GeneratedApp(interactionApiAdapter: (path, method, query, cancel) async { final events = networkEvents.putIfAbsent(activeScenarioId, () => <Map<String, Object?>>[]); final outcome = cancel ? 'STALE' : query == 'fail' ? 'ERROR' : 'SUCCESS'; events.add(<String, Object?>{'method': method, 'path': path, 'query': query, 'cancel': cancel, 'outcome': outcome}); return outcome; }, interactionNativeAdapter: (path) async { platformEvents.putIfAbsent(activeScenarioId, () => <Map<String, Object?>>[]).add(<String, Object?>{'operation': 'OPEN_DEEP_LINK', 'path': path, 'result': true}); return true; })); await tester.pumpAndSettle();",
    "    var priorSequence = 0; var networkEventCount = 0; var platformEventCount = 0;",
    "    for (final raw in elmosInteractionScenarios) {",
    "      final id = elmosMap(raw)['scenarioId']! as String; activeScenarioId = id; final action = find.byKey(ValueKey<String>('action:$id')); await tester.ensureVisible(action); await tester.tap(action); await tester.pumpAndSettle(); expect(find.byKey(ValueKey<String>('scenario:$id')), findsOneWidget); final blocks = <String, Object?>{};",
    "      for (final blockId in elmosRuntimeBlockIds) { final finder = find.byKey(ValueKey<String>('block:$id:$blockId')); expect(finder, findsOneWidget, reason: '$id:$blockId'); final text = tester.widget<Text>(finder).data; expect(text, isNotNull); final decoded = jsonDecode(text!) as Map<String, Object?>; expect(decoded.keys.toSet(), elmosRuntimeActualKeys[blockId]!.toSet(), reason: '$id:$blockId keys'); blocks[blockId] = decoded; }",
    "      final semantics = tester.getSemantics(find.byKey(ValueKey<String>('scenario:$id'))).label; final match = RegExp(r'sequence:(\\d+)').firstMatch(semantics); expect(match, isNotNull); final current = int.parse(match!.group(1)!); expect(current, greaterThan(priorSequence)); priorSequence = current;",
    "      final fieldFinder = find.byKey(const ValueKey<String>('elmos-query')); await tester.ensureVisible(fieldFinder); await tester.pumpAndSettle(); final field = tester.widget<TextField>(fieldFinder); final focus = <String, Object?>{'target': field.focusNode?.hasFocus == true ? 'query' : null, 'query_has_focus': field.focusNode?.hasFocus == true}; if (id == 'FORM_INVALID_SUBMIT_FOCUS_ERROR') expect(field.focusNode?.hasFocus, isTrue); final network = networkEvents[id] ?? const <Map<String, Object?>>[]; final platform = platformEvents[id] ?? const <Map<String, Object?>>[]; networkEventCount += network.length; platformEventCount += platform.length; scenarios.add(<String, Object?>{'scenario_id': id, 'execution_sequence': current, 'execution_state': 'COMPLETE', 'runtime_source': 'flutter-framework-events', 'framework_events': <Map<String, Object?>>[<String, Object?>{'kind': 'TAP', 'target_key': 'action:$id'}], 'semantics_label': semantics, 'focus': focus, 'network_adapter_events': network, 'platform_adapter_events': platform, 'evidence_refs': <String, Object?>{'semantics': 'INLINE_INTEGRATION_BINDING', 'network': network.isEmpty ? null : 'INLINE_API_ADAPTER_TRACE', 'platform': platform.isEmpty ? null : 'INLINE_NATIVE_ADAPTER_TRACE'}, 'blocks': blocks});",
    "    }",
    "    expect(networkEventCount, greaterThan(0)); if (runtimeChannel == 'browser') { expect(platformEventCount, 0); } else { expect(platformEventCount, greaterThan(0)); } binding.reportData = <String, Object?>{'runtime_channel': runtimeChannel, 'runtime_source': 'FLUTTER_INTEGRATION_SEMANTICS', 'model_or_precomputed_values_used': false, 'scenarios': scenarios, 'summary': <String, Object?>{'scenario_count': scenarios.length, 'block_count': elmosRuntimeBlockIds.length, 'all_complete': scenarios.every((row) => row['execution_state'] == 'COMPLETE'), 'network_adapter_event_count': networkEventCount, 'platform_adapter_event_count': platformEventCount}};",
    "  });",
    "}",
    "",
  ].join("\n");
}

function flutterIntegrationDriver(): string {
  return [
    "import 'dart:convert';",
    "import 'dart:io';",
    "import 'package:integration_test/integration_test_driver.dart';",
    "String requiredEnvironment(String name) { final value = Platform.environment[name]; if (value == null || value.isEmpty) throw StateError('$name is required'); return value; }",
    "String requiredDigest(String name) { final value = requiredEnvironment(name); if (!RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(value)) throw StateError('$name must be a sha256 digest'); return value; }",
    "Future<void> main() async {",
    "  final tracePath = requiredEnvironment('ELMOS_FLUTTER_TRACE_PATH'); final channel = requiredEnvironment('ELMOS_FLUTTER_RUNTIME_CHANNEL'); if (!const <String>{'browser', 'android', 'ios'}.contains(channel)) throw StateError('ELMOS_FLUTTER_RUNTIME_CHANNEL is invalid'); final projectDigest = requiredDigest('ELMOS_FLUTTER_PROJECT_DIGEST'); final profileManifestDigest = requiredDigest('ELMOS_FLUTTER_PROFILE_MANIFEST_DIGEST'); final scenarioManifestDigest = requiredDigest('ELMOS_FLUTTER_SCENARIO_MANIFEST_DIGEST');",
    "  await integrationDriver(responseDataCallback: (data) async { if (data == null || data.length != 5 || !const <String>['runtime_channel', 'runtime_source', 'model_or_precomputed_values_used', 'scenarios', 'summary'].every(data.containsKey)) throw StateError('Flutter integration response shape drifted'); if (data['runtime_channel'] != channel) throw StateError('Flutter integration target channel does not match ELMOS_FLUTTER_RUNTIME_CHANNEL'); if (data['runtime_source'] != 'FLUTTER_INTEGRATION_SEMANTICS' || data['model_or_precomputed_values_used'] != false || data['scenarios'] is! List<Object?> || data['summary'] is! Map<String, Object?>) throw StateError('Flutter integration response provenance drifted'); final payload = <String, Object?>{'schema_version': '1.0', 'kind': 'bounded-frontend-interaction-flutter-runtime-trace', 'proof_profile': 'bounded-frontend-interaction-v1', 'profile_id': 'flutter', 'channel': channel, 'project_digest': projectDigest, 'profile_manifest_digest': profileManifestDigest, 'scenario_manifest_digest': scenarioManifestDigest, 'runtime_source': data['runtime_source'], 'model_or_precomputed_values_used': data['model_or_precomputed_values_used'], 'scenarios': data['scenarios'], 'summary': data['summary']}; final destination = File(tracePath); if (destination.existsSync()) throw StateError('ELMOS_FLUTTER_TRACE_PATH already exists'); destination.parent.createSync(recursive: true); final temporary = File('$tracePath.tmp.$pid'); await temporary.writeAsString('${jsonEncode(payload)}\\n', flush: true); await temporary.rename(tracePath); }, writeResponseOnFailure: false);",
    "}",
    "",
  ].join("\n");
}

function generatedObserverContractLiteral(): string {
  return JSON.stringify(interactionBlockIds.map(blockId => ({
    block_id: blockId,
    ...boundedFrontendBlockObserverContracts[blockId],
  })));
}

function blockSpecificBrowserRuntimeModule(profile: UiFrameworkId): string {
  const contracts = generatedObserverContractLiteral();
  if (profile === "vue2") {
    return [
      "// Block-specific runtime actions and declaration-only observer metadata; no observation JSON is emitted.",
      'import { ELMOS_FRONTEND_INTERACTION } from "./elmos-bounded-interaction";',
      `export const ELMOS_BLOCK_OBSERVERS = Object.freeze(${contracts});`,
      "export function elmosBrowserObserverDeclarations() { return ELMOS_BLOCK_OBSERVERS.map(spec => ({ schema_version: '1.0', kind: 'frontend-block-observer-declaration', block_id: spec.block_id, status: spec.browser_status, observer_kind: spec.observer_kind, measurement_surface: spec.measurement_surface, reason: spec.browser_reason })); }",
      "export function elmosDeclarationJson(value) { return JSON.stringify(value); }",
      "export function elmosCreateBrowserRuntimeSession() { let controller = null; return { async execute(scenario, queryElement) { const input = { ...scenario.input, query: queryElement.value === '' ? scenario.input.query : queryElement.value, viewportWidth: window.innerWidth }; queryElement.value = input.query; queryElement.required = ELMOS_FRONTEND_INTERACTION.formBindingValidation.required; queryElement.minLength = ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength; queryElement.setCustomValidity(input.query.length < ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''); queryElement.dispatchEvent(new Event('input', { bubbles: true })); const routes = ELMOS_FRONTEND_INTERACTION.navigation.routes; const first = routes[0]; const requested = routes.find(route => route.path === input.routePath) || first; const tenantMatch = input.tenantId === input.resourceTenantId; const authorized = !requested.requiresAuth || (input.authenticated && input.permissionGranted && tenantMatch); const selected = authorized ? requested : first; const resolution = requested === first && input.routePath !== first.path ? 'FIRST_DECLARED_FALLBACK' : authorized ? 'DECLARED' : 'AUTH_DENIED_FALLBACK'; history.pushState({}, '', selected.path); window.dispatchEvent(new PopStateEvent('popstate')); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); const submitted = input.event === 'SUBMIT' || input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; const valid = queryElement.validity.valid; const rawCounter = Math.max(input.counterBefore, ELMOS_FRONTEND_INTERACTION.stateManagement.initial) + input.incrementCount; const counterAfter = Math.max(ELMOS_FRONTEND_INTERACTION.stateManagement.minimum, Math.min(ELMOS_FRONTEND_INTERACTION.stateManagement.maximum, rawCounter)); const canceled = input.event === 'CANCEL' || (ELMOS_FRONTEND_INTERACTION.apiNetwork.cancelOnUnmount && input.lifecycle === 'UNMOUNT'); const apiCalled = submitted && valid && authorized; let networkOutcome = 'NOT_CALLED'; if (canceled) { controller?.abort(); controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }).catch(() => undefined); controller.abort(); await request; controller = null; networkOutcome = 'CANCELED'; } else if (apiCalled) { controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }); networkOutcome = response.ok ? 'SUCCESS' : 'ERROR'; } catch (error) { networkOutcome = error instanceof DOMException && error.name === 'AbortError' ? 'CANCELED' : 'ERROR'; } finally { controller = null; } } const locale = ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.supportedLocales.includes(input.locale) ? input.locale : ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.fallbackLocale; const theme = ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.themes.includes(input.theme) ? input.theme : ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.defaultTheme; document.documentElement.lang = locale; document.documentElement.setAttribute('data-elmos-theme', theme); document.documentElement.style.setProperty('--elmos-theme', theme); const columns = matchMedia(`(max-width: ${ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.compactBreakpoint}px)`).matches ? ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.compactColumns : ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.wideColumns; document.documentElement.style.setProperty('--elmos-grid-columns', 'repeat(' + String(columns) + ', minmax(0, 1fr))'); const errorCode = submitted && !valid ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''; const focusTarget = errorCode ? 'query' : submitted ? 'result' : ''; const action = submitted ? valid && authorized ? 'SUBMIT_ACCEPTED' : ELMOS_FRONTEND_INTERACTION.actionEvent.deniedAction : input.event; queryElement.setAttribute('data-elmos-form-id', ELMOS_FRONTEND_INTERACTION.formBindingValidation.formId); queryElement.setAttribute('data-elmos-field-id', ELMOS_FRONTEND_INTERACTION.formBindingValidation.fieldId); queryElement.setAttribute('data-elmos-value', input.query); queryElement.setAttribute('data-elmos-submitted', String(submitted)); queryElement.setAttribute('data-elmos-valid', String(valid)); queryElement.setAttribute('data-elmos-error-code', errorCode); queryElement.setAttribute('data-elmos-focus-target', focusTarget); return { requestedPath: input.routePath, selectedRouteId: selected.id, selectedPath: selected.path, resolution, stateId: ELMOS_FRONTEND_INTERACTION.stateManagement.stateId, counterBefore: input.counterBefore, counterAfter, saturated: rawCounter > ELMOS_FRONTEND_INTERACTION.stateManagement.maximum, event: input.event, keyboardKey: input.keyboardKey || '', handled: ELMOS_FRONTEND_INTERACTION.actionEvent.acceptedEvents.includes(input.event), action, query: input.query, submitted, valid, errorCode, apiCalled, operationId: ELMOS_FRONTEND_INTERACTION.apiNetwork.operationId, method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, path: ELMOS_FRONTEND_INTERACTION.apiNetwork.path, networkOutcome, canceled, staleIgnored: canceled && input.networkResult === 'STALE', cacheKey: `${input.tenantId}:${input.query}`, requestedLocale: input.locale, locale, requestedTheme: input.theme, theme, columns, viewportWidth: window.innerWidth, translatedText: locale === 'en-US' ? 'Search results' : '搜索结果', focusTarget, mainRole: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.mainRole, headingLevel: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.headingLevel, formLabel: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel, errorRole: errorCode ? ELMOS_FRONTEND_INTERACTION.accessibilityFocus.errorRole : '', liveRegion: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion, keyboardSubmit: input.keyboardKey === ELMOS_FRONTEND_INTERACTION.accessibilityFocus.keyboardSubmit }; }, dispose() { controller?.abort(); controller = null; } }; }",
      "",
    ].join("\n");
  }
  return [
    "// Block-specific runtime actions and declaration-only observer metadata; no observation JSON is emitted.",
    'import { ELMOS_FRONTEND_INTERACTION } from "./elmos-bounded-interaction";',
    "export interface ElmosRuntimeInput { readonly routePath: string; readonly event: string; readonly keyboardKey: string | null; readonly counterBefore: number; readonly incrementCount: number; readonly lifecycle: string; readonly query: string; readonly networkResult: string; readonly authenticated: boolean; readonly permissionGranted: boolean; readonly tenantId: string; readonly resourceTenantId: string; readonly hydration: string; readonly locale: string; readonly theme: string; readonly viewportWidth: number; readonly nativeLifecycle: string; readonly nativePermission: string; readonly nativeAvailable: boolean; readonly deepLinkPath: string | null; }",
    "export interface ElmosRuntimeScenario { readonly scenarioId: string; readonly input: ElmosRuntimeInput; }",
    "export interface ElmosObserverDeclaration { readonly schema_version: '1.0'; readonly kind: 'frontend-block-observer-declaration'; readonly block_id: string; readonly status: 'PASSED' | 'NOT_RUN'; readonly observer_kind: string; readonly measurement_surface: string; readonly reason: string; }",
    "export interface ElmosBrowserMeasurement { readonly requestedPath: string; readonly selectedRouteId: string; readonly selectedPath: string; readonly resolution: string; readonly stateId: string; readonly counterBefore: number; readonly counterAfter: number; readonly saturated: boolean; readonly event: string; readonly keyboardKey: string; readonly handled: boolean; readonly action: string; readonly query: string; readonly submitted: boolean; readonly valid: boolean; readonly errorCode: string; readonly apiCalled: boolean; readonly operationId: string; readonly method: string; readonly path: string; readonly networkOutcome: string; readonly canceled: boolean; readonly staleIgnored: boolean; readonly cacheKey: string; readonly requestedLocale: string; readonly locale: string; readonly requestedTheme: string; readonly theme: string; readonly columns: number; readonly viewportWidth: number; readonly translatedText: string; readonly focusTarget: string; readonly mainRole: string; readonly headingLevel: number; readonly formLabel: string; readonly errorRole: string; readonly liveRegion: string; readonly keyboardSubmit: boolean; }",
    `export const ELMOS_BLOCK_OBSERVERS = Object.freeze(${contracts} as const);`,
    "export function elmosBrowserObserverDeclarations(): readonly ElmosObserverDeclaration[] { return ELMOS_BLOCK_OBSERVERS.map(spec => ({ schema_version: '1.0', kind: 'frontend-block-observer-declaration', block_id: spec.block_id, status: spec.browser_status, observer_kind: spec.observer_kind, measurement_surface: spec.measurement_surface, reason: spec.browser_reason })); }",
    "export function elmosDeclarationJson(value: ElmosObserverDeclaration): string { return JSON.stringify(value); }",
    "export interface ElmosBrowserRuntimeSession { readonly execute: (scenario: ElmosRuntimeScenario, queryElement: HTMLInputElement) => Promise<ElmosBrowserMeasurement>; readonly dispose: () => void; }",
    "export function elmosCreateBrowserRuntimeSession(): ElmosBrowserRuntimeSession {",
    "  let controller: AbortController | null = null;",
    "  return {",
    "    async execute(scenario, queryElement) {",
    "      const input: ElmosRuntimeInput = { ...scenario.input, query: queryElement.value === '' ? scenario.input.query : queryElement.value, viewportWidth: window.innerWidth };",
    "      queryElement.value = input.query; queryElement.required = ELMOS_FRONTEND_INTERACTION.formBindingValidation.required; queryElement.minLength = ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength; queryElement.setCustomValidity(input.query.length < ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''); queryElement.dispatchEvent(new Event('input', { bubbles: true }));",
    "      const routes = ELMOS_FRONTEND_INTERACTION.navigation.routes; const first = routes[0]!; const requested = routes.find(route => route.path === input.routePath) ?? first; const tenantMatch = input.tenantId === input.resourceTenantId; const authorized = !requested.requiresAuth || (input.authenticated && input.permissionGranted && tenantMatch); const selected = authorized ? requested : first;",
    "      const resolution = requested === first && input.routePath !== first.path ? 'FIRST_DECLARED_FALLBACK' : authorized ? 'DECLARED' : 'AUTH_DENIED_FALLBACK'; history.pushState({}, '', selected.path); window.dispatchEvent(new PopStateEvent('popstate')); await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));",
    "      const submitted = input.event === 'SUBMIT' || input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; const valid = queryElement.validity.valid; const rawCounter = Math.max(input.counterBefore, ELMOS_FRONTEND_INTERACTION.stateManagement.initial) + input.incrementCount; const counterAfter = Math.max(ELMOS_FRONTEND_INTERACTION.stateManagement.minimum, Math.min(ELMOS_FRONTEND_INTERACTION.stateManagement.maximum, rawCounter)); const canceled = input.event === 'CANCEL' || (ELMOS_FRONTEND_INTERACTION.apiNetwork.cancelOnUnmount && input.lifecycle === 'UNMOUNT'); const apiCalled = submitted && valid && authorized;",
    "      let networkOutcome = 'NOT_CALLED'; if (canceled) { controller?.abort(); controller = new AbortController(); const request = fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }).catch(() => undefined); controller.abort(); await request; controller = null; networkOutcome = 'CANCELED'; } else if (apiCalled) { controller = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, headers: { 'content-type': 'application/json', 'x-elmos-tenant': input.tenantId }, body: JSON.stringify({ query: input.query }), signal: controller.signal }); networkOutcome = response.ok ? 'SUCCESS' : 'ERROR'; } catch (error) { networkOutcome = error instanceof DOMException && error.name === 'AbortError' ? 'CANCELED' : 'ERROR'; } finally { controller = null; } }",
    "      const locale = (ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.supportedLocales as readonly string[]).includes(input.locale) ? input.locale : ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.fallbackLocale; const theme = (ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.themes as readonly string[]).includes(input.theme) ? input.theme : ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.defaultTheme; document.documentElement.lang = locale; document.documentElement.setAttribute('data-elmos-theme', theme); document.documentElement.style.setProperty('--elmos-theme', theme); const columns = matchMedia(`(max-width: ${ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.compactBreakpoint}px)`).matches ? ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.compactColumns : ELMOS_FRONTEND_INTERACTION.i18nThemeResponsive.wideColumns;",
    "      document.documentElement.style.setProperty('--elmos-grid-columns', 'repeat(' + String(columns) + ', minmax(0, 1fr))'); const errorCode = submitted && !valid ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''; const focusTarget = errorCode ? 'query' : submitted ? 'result' : ''; const action = submitted ? valid && authorized ? 'SUBMIT_ACCEPTED' : ELMOS_FRONTEND_INTERACTION.actionEvent.deniedAction : input.event; queryElement.setAttribute('data-elmos-form-id', ELMOS_FRONTEND_INTERACTION.formBindingValidation.formId); queryElement.setAttribute('data-elmos-field-id', ELMOS_FRONTEND_INTERACTION.formBindingValidation.fieldId); queryElement.setAttribute('data-elmos-value', input.query); queryElement.setAttribute('data-elmos-submitted', String(submitted)); queryElement.setAttribute('data-elmos-valid', String(valid)); queryElement.setAttribute('data-elmos-error-code', errorCode); queryElement.setAttribute('data-elmos-focus-target', focusTarget);",
    "      return { requestedPath: input.routePath, selectedRouteId: selected.id, selectedPath: selected.path, resolution, stateId: ELMOS_FRONTEND_INTERACTION.stateManagement.stateId, counterBefore: input.counterBefore, counterAfter, saturated: rawCounter > ELMOS_FRONTEND_INTERACTION.stateManagement.maximum, event: input.event, keyboardKey: input.keyboardKey ?? '', handled: (ELMOS_FRONTEND_INTERACTION.actionEvent.acceptedEvents as readonly string[]).includes(input.event), action, query: input.query, submitted, valid, errorCode, apiCalled, operationId: ELMOS_FRONTEND_INTERACTION.apiNetwork.operationId, method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, path: ELMOS_FRONTEND_INTERACTION.apiNetwork.path, networkOutcome, canceled, staleIgnored: canceled && input.networkResult === 'STALE', cacheKey: `${input.tenantId}:${input.query}`, requestedLocale: input.locale, locale, requestedTheme: input.theme, theme, columns, viewportWidth: window.innerWidth, translatedText: locale === 'en-US' ? 'Search results' : '搜索结果', focusTarget, mainRole: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.mainRole, headingLevel: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.headingLevel, formLabel: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel, errorRole: errorCode ? ELMOS_FRONTEND_INTERACTION.accessibilityFocus.errorRole : '', liveRegion: ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion, keyboardSubmit: input.keyboardKey === ELMOS_FRONTEND_INTERACTION.accessibilityFocus.keyboardSubmit };",
    "    },",
    "    dispose() { controller?.abort(); controller = null; },",
    "  };",
    "}",
    "",
  ].join("\n");
}

function blockSpecificReactWebConsumer(): string {
  return [
    'import { FormEvent, useEffect, useRef, useState } from "react";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosBrowserObserverDeclarations, elmosCreateBrowserRuntimeSession, elmosDeclarationJson, type ElmosBrowserMeasurement, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "interface RuntimeRow { readonly measurement: ElmosBrowserMeasurement; readonly sequence: number; }",
    "const declarations = elmosBrowserObserverDeclarations();",
    "export function ElmosInteractionPanel() {",
    "  const [rows, setRows] = useState<Readonly<Record<string, RuntimeRow>>>({}); const [sequence, setSequence] = useState(0); const session = useRef(elmosCreateBrowserRuntimeSession()); const pending = useRef<ElmosRuntimeScenario | null>(null); const query = useRef<HTMLInputElement>(null); const result = useRef<HTMLOutputElement>(null);",
    "  async function execute(scenario: ElmosRuntimeScenario) { if (!query.current) return; const measurement = await session.current.execute(scenario, query.current); const next = sequence + 1; setSequence(next); setRows(previous => ({ ...previous, [scenario.scenarioId]: { measurement, sequence: next } })); queueMicrotask(() => measurement.focusTarget === 'query' ? query.current?.focus() : measurement.focusTarget === 'result' ? result.current?.focus() : undefined); }",
    "  function syncValidity(event: FormEvent<HTMLInputElement>) { const element = event.currentTarget; element.setCustomValidity(element.value.length < ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''); } function invalidForm(event: FormEvent<HTMLInputElement>) { const scenario = pending.current; event.currentTarget.setAttribute('data-elmos-invalid-event', 'captured'); pending.current = null; if (scenario) void execute(scenario); } function isSubmitScenario(scenario: ElmosRuntimeScenario) { return scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; } function trigger(scenario: ElmosRuntimeScenario) { if (isSubmitScenario(scenario)) pending.current = scenario; else void execute(scenario); } function submitForm(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const scenario = pending.current ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending.current = null; if (scenario) void execute(scenario); }",
    "  useEffect(() => () => session.current.dispose(), []);",
    '  return <section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-observer-protocol="block-specific-runtime-observation-v1" data-runtime-scope="REACT_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" data-completion={sequence > 0 ? "PARTIAL" : "IDLE"} data-run-id={sequence} aria-label="ELMOS bounded interaction runtime">',
    '    <span hidden data-elmos-lifecycle-event="MOUNT" data-lifecycle-sequence="1"></span><form data-elmos-control="form" aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} onSubmit={submitForm}><input ref={query} id="elmos-query" name="query" data-elmos-control="query" data-field-id="search.query" required minLength={ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength} aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} onInput={syncValidity} onInvalid={invalidForm} />',
    `    {ELMOS_INTERACTION_SCENARIOS.map(scenario => { const row = rows[scenario.scenarioId]; const value = row?.measurement; return <article key={scenario.scenarioId} data-scenario-id={scenario.scenarioId} data-runtime-source={row ? 'BLOCK_SPECIFIC_RUNTIME_OBSERVED' : 'NOT_RUN'} data-execution-state={row ? 'PARTIAL' : 'IDLE'} data-execution-sequence={row?.sequence ?? 0}><button type={isSubmitScenario(scenario) ? 'submit' : 'button'} data-run-scenario={scenario.scenarioId} data-scenario-action={scenario.scenarioId} data-elmos-event={scenario.input.event} onClick={() => trigger(scenario)}>{scenario.scenarioId}</button>{value && <div data-elmos-raw-measurements="true"><span data-elmos-state-measurement="true" data-elmos-state-id={value.stateId} data-elmos-before={value.counterBefore} data-elmos-after={value.counterAfter} data-elmos-saturated={String(value.saturated)}></span><span data-elmos-action-outcome="true" data-elmos-event-outcome={value.event} data-elmos-keyboard-key={value.keyboardKey} data-elmos-handled={String(value.handled)} data-elmos-action={value.action}></span><span data-elmos-form-measurement="true" data-elmos-form-id={ELMOS_FRONTEND_INTERACTION.formBindingValidation.formId} data-elmos-field-id={ELMOS_FRONTEND_INTERACTION.formBindingValidation.fieldId} data-elmos-submitted={String(value.submitted)} data-elmos-valid={String(value.valid)} data-elmos-error-code={value.errorCode} data-elmos-focus-target={value.focusTarget}></span><span data-elmos-api-measurement="true" data-elmos-operation-id={value.operationId} data-elmos-called={String(value.apiCalled)} data-elmos-method={value.method} data-elmos-path={value.path} data-elmos-outcome={value.networkOutcome} data-elmos-canceled={String(value.canceled)} data-elmos-stale-ignored={String(value.staleIgnored)} data-elmos-cache-key={value.cacheKey}></span><span data-elmos-accessibility-measurement="true" data-elmos-main-role={value.mainRole} data-elmos-heading-level={value.headingLevel} data-elmos-form-label={value.formLabel} data-elmos-error-role={value.errorRole} data-elmos-live-region={value.liveRegion} data-elmos-focus-target={value.focusTarget} data-elmos-keyboard-submit={String(value.keyboardSubmit)}></span><span data-elmos-i18n-measurement="true" style={{ display: 'grid', gridTemplateColumns: 'var(--elmos-grid-columns)' }} data-elmos-requested-locale={value.requestedLocale} data-elmos-requested-theme={value.requestedTheme} data-elmos-theme={value.theme} data-elmos-columns={value.columns} data-elmos-viewport-width={value.viewportWidth}>{value.translatedText}</span><span data-elmos-auth-decision="NOT_RUN" data-authority-adapter-trace="NOT_RUN"></span><span data-elmos-hydration-measurement="NOT_RUN"></span><span data-elmos-native-measurement="NOT_RUN"></span>{value.errorCode && <span data-elmos-form-error="true" role="alert">{value.errorCode}</span>}</div>}{row && declarations.map(declaration => <pre key={declaration.block_id} data-semantic-block={declaration.block_id} data-observer-kind={declaration.observer_kind} data-observation-status={declaration.status} data-measurement-surface={declaration.measurement_surface} data-model-values-used="false">{elmosDeclarationJson(declaration)}</pre>)}</article>; })}`,
    '    </form><output ref={result} id="elmos-result" data-elmos-result="true" tabIndex={-1} aria-live={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion}></output>',
    "  </section>;",
    "}",
    "",
  ].join("\n");
}

function blockSpecificVue3WebConsumer(): string {
  return [
    '<script setup lang="ts">',
    'import { onBeforeUnmount, ref } from "vue";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosBrowserObserverDeclarations, elmosCreateBrowserRuntimeSession, elmosDeclarationJson, type ElmosBrowserMeasurement, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "interface RuntimeRow { readonly measurement: ElmosBrowserMeasurement; readonly sequence: number; }",
    "const declarations = elmosBrowserObserverDeclarations(); const rows = ref<Readonly<Record<string, RuntimeRow>>>({}); const sequence = ref(0); const pending = ref<ElmosRuntimeScenario | null>(null); const query = ref<HTMLInputElement | null>(null); const result = ref<HTMLOutputElement | null>(null); const session = elmosCreateBrowserRuntimeSession();",
    "async function execute(scenario: ElmosRuntimeScenario) { if (!query.value) return; const measurement = await session.execute(scenario, query.value); const next = sequence.value + 1; sequence.value = next; rows.value = { ...rows.value, [scenario.scenarioId]: { measurement, sequence: next } }; queueMicrotask(() => measurement.focusTarget === 'query' ? query.value?.focus() : measurement.focusTarget === 'result' ? result.value?.focus() : undefined); }",
    "function syncValidity(event: Event) { const element = event.currentTarget as HTMLInputElement; element.setCustomValidity(element.value.length < ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''); } function invalidForm(event: Event) { const element = event.currentTarget as HTMLInputElement; const scenario = pending.value; element.setAttribute('data-elmos-invalid-event', 'captured'); pending.value = null; if (scenario) void execute(scenario); } function isSubmitScenario(scenario: ElmosRuntimeScenario) { return scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; } function trigger(scenario: ElmosRuntimeScenario) { if (isSubmitScenario(scenario)) pending.value = scenario; else void execute(scenario); } function submitForm(event: SubmitEvent) { event.preventDefault(); const scenario = pending.value ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending.value = null; if (scenario) void execute(scenario); } onBeforeUnmount(() => session.dispose());",
    "</script>",
    '<template><section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-observer-protocol="block-specific-runtime-observation-v1" data-runtime-scope="VUE3_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" :data-completion="sequence > 0 ? \'PARTIAL\' : \'IDLE\'" :data-run-id="sequence" aria-label="ELMOS bounded interaction runtime"><span hidden data-elmos-lifecycle-event="MOUNT" data-lifecycle-sequence="1"></span><form data-elmos-control="form" :aria-label="ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel" @submit="submitForm"><input ref="query" id="elmos-query" name="query" data-elmos-control="query" data-field-id="search.query" required :minlength="ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength" :aria-label="ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel" @input="syncValidity" @invalid="invalidForm">',
    '<article v-for="scenario in ELMOS_INTERACTION_SCENARIOS" :key="scenario.scenarioId" :data-scenario-id="scenario.scenarioId" :data-runtime-source="rows[scenario.scenarioId] ? \'BLOCK_SPECIFIC_RUNTIME_OBSERVED\' : \'NOT_RUN\'" :data-execution-state="rows[scenario.scenarioId] ? \'PARTIAL\' : \'IDLE\'" :data-execution-sequence="rows[scenario.scenarioId]?.sequence ?? 0"><button :type="isSubmitScenario(scenario) ? \'submit\' : \'button\'" :data-run-scenario="scenario.scenarioId" :data-scenario-action="scenario.scenarioId" :data-elmos-event="scenario.input.event" @click="trigger(scenario)">{{ scenario.scenarioId }}</button><template v-if="rows[scenario.scenarioId]"><span data-elmos-state-measurement="true" :data-elmos-state-id="rows[scenario.scenarioId]!.measurement.stateId" :data-elmos-before="rows[scenario.scenarioId]!.measurement.counterBefore" :data-elmos-after="rows[scenario.scenarioId]!.measurement.counterAfter" :data-elmos-saturated="String(rows[scenario.scenarioId]!.measurement.saturated)"></span><span data-elmos-action-outcome="true" :data-elmos-event-outcome="rows[scenario.scenarioId]!.measurement.event" :data-elmos-keyboard-key="rows[scenario.scenarioId]!.measurement.keyboardKey" :data-elmos-handled="String(rows[scenario.scenarioId]!.measurement.handled)" :data-elmos-action="rows[scenario.scenarioId]!.measurement.action"></span><span data-elmos-form-measurement="true" :data-elmos-form-id="ELMOS_FRONTEND_INTERACTION.formBindingValidation.formId" :data-elmos-field-id="ELMOS_FRONTEND_INTERACTION.formBindingValidation.fieldId" :data-elmos-submitted="String(rows[scenario.scenarioId]!.measurement.submitted)" :data-elmos-valid="String(rows[scenario.scenarioId]!.measurement.valid)" :data-elmos-error-code="rows[scenario.scenarioId]!.measurement.errorCode" :data-elmos-focus-target="rows[scenario.scenarioId]!.measurement.focusTarget"></span><span data-elmos-api-measurement="true" :data-elmos-operation-id="rows[scenario.scenarioId]!.measurement.operationId" :data-elmos-called="String(rows[scenario.scenarioId]!.measurement.apiCalled)" :data-elmos-method="rows[scenario.scenarioId]!.measurement.method" :data-elmos-path="rows[scenario.scenarioId]!.measurement.path" :data-elmos-outcome="rows[scenario.scenarioId]!.measurement.networkOutcome" :data-elmos-canceled="String(rows[scenario.scenarioId]!.measurement.canceled)" :data-elmos-stale-ignored="String(rows[scenario.scenarioId]!.measurement.staleIgnored)" :data-elmos-cache-key="rows[scenario.scenarioId]!.measurement.cacheKey"></span><span data-elmos-accessibility-measurement="true" :data-elmos-main-role="rows[scenario.scenarioId]!.measurement.mainRole" :data-elmos-heading-level="rows[scenario.scenarioId]!.measurement.headingLevel" :data-elmos-form-label="rows[scenario.scenarioId]!.measurement.formLabel" :data-elmos-error-role="rows[scenario.scenarioId]!.measurement.errorRole" :data-elmos-live-region="rows[scenario.scenarioId]!.measurement.liveRegion" :data-elmos-focus-target="rows[scenario.scenarioId]!.measurement.focusTarget" :data-elmos-keyboard-submit="String(rows[scenario.scenarioId]!.measurement.keyboardSubmit)"></span><span data-elmos-i18n-measurement="true" style="display:grid;grid-template-columns:var(--elmos-grid-columns)" :data-elmos-requested-locale="rows[scenario.scenarioId]!.measurement.requestedLocale" :data-elmos-requested-theme="rows[scenario.scenarioId]!.measurement.requestedTheme" :data-elmos-theme="rows[scenario.scenarioId]!.measurement.theme" :data-elmos-columns="rows[scenario.scenarioId]!.measurement.columns" :data-elmos-viewport-width="rows[scenario.scenarioId]!.measurement.viewportWidth">{{ rows[scenario.scenarioId]!.measurement.translatedText }}</span><span data-elmos-auth-decision="NOT_RUN" data-authority-adapter-trace="NOT_RUN"></span><span data-elmos-hydration-measurement="NOT_RUN"></span><span data-elmos-native-measurement="NOT_RUN"></span><span v-if="rows[scenario.scenarioId]!.measurement.errorCode" data-elmos-form-error="true" role="alert">{{ rows[scenario.scenarioId]!.measurement.errorCode }}</span><pre v-for="declaration in declarations" :key="declaration.block_id" :data-semantic-block="declaration.block_id" :data-observer-kind="declaration.observer_kind" :data-observation-status="declaration.status" :data-measurement-surface="declaration.measurement_surface" data-model-values-used="false">{{ elmosDeclarationJson(declaration) }}</pre></template></article>',
    '</form><output ref="result" id="elmos-result" data-elmos-result="true" tabindex="-1" :aria-live="ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion"></output></section></template>',
    "",
  ].join("\n");
}

function blockSpecificVue2WebConsumer(): string {
  return [
    "<script>",
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosBrowserObserverDeclarations, elmosCreateBrowserRuntimeSession, elmosDeclarationJson } from "./elmos-interaction-runtime";',
    "export default {",
    "  data: () => ({ model: ELMOS_FRONTEND_INTERACTION, scenarios: ELMOS_INTERACTION_SCENARIOS, declarations: elmosBrowserObserverDeclarations(), rows: {}, sequence: 0, pending: null, session: elmosCreateBrowserRuntimeSession() }),",
    "  mounted() { const query = this.$refs.query; query.addEventListener('input', this.syncValidity); query.addEventListener('invalid', this.invalidForm); }, beforeDestroy() { const query = this.$refs.query; query.removeEventListener('input', this.syncValidity); query.removeEventListener('invalid', this.invalidForm); this.session.dispose(); },",
    "  methods: { declarationJson: elmosDeclarationJson, async execute(scenario) { const query = this.$refs.query; if (!query) return; const measurement = await this.session.execute(scenario, query); this.sequence += 1; this.$set(this.rows, scenario.scenarioId, { measurement, sequence: this.sequence }); this.$nextTick(() => measurement.focusTarget === 'query' ? query.focus() : measurement.focusTarget === 'result' ? this.$refs.result.focus() : undefined); }, syncValidity(event) { const element = event.currentTarget; element.setCustomValidity(element.value.length < this.model.formBindingValidation.minimumLength ? this.model.formBindingValidation.invalidCode : ''); }, invalidForm(event) { const scenario = this.pending; event.currentTarget.setAttribute('data-elmos-invalid-event', 'captured'); this.pending = null; if (scenario) this.execute(scenario); }, isSubmitScenario(scenario) { return scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === this.model.actionEvent.keyboardSubmit; }, trigger(scenario) { if (this.isSubmitScenario(scenario)) this.pending = scenario; else this.execute(scenario); }, submitForm(event) { event.preventDefault(); const scenario = this.pending || this.scenarios.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS'); this.pending = null; if (scenario) this.execute(scenario); } },",
    "};",
    "</script>",
    '<template><section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-observer-protocol="block-specific-runtime-observation-v1" data-runtime-scope="VUE2_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" :data-completion="sequence > 0 ? \'PARTIAL\' : \'IDLE\'" :data-run-id="sequence" aria-label="ELMOS bounded interaction runtime"><span hidden data-elmos-lifecycle-event="MOUNT" data-lifecycle-sequence="1"></span><form data-elmos-control="form" :aria-label="model.accessibilityFocus.formLabel" @submit="submitForm"><input ref="query" id="elmos-query" name="query" data-elmos-control="query" data-field-id="search.query" required :minlength="model.formBindingValidation.minimumLength" :aria-label="model.accessibilityFocus.formLabel"><article v-for="scenario in scenarios" :key="scenario.scenarioId" :data-scenario-id="scenario.scenarioId" :data-runtime-source="rows[scenario.scenarioId] ? \'BLOCK_SPECIFIC_RUNTIME_OBSERVED\' : \'NOT_RUN\'" :data-execution-state="rows[scenario.scenarioId] ? \'PARTIAL\' : \'IDLE\'" :data-execution-sequence="rows[scenario.scenarioId] ? rows[scenario.scenarioId].sequence : 0"><button :type="isSubmitScenario(scenario) ? \'submit\' : \'button\'" :data-run-scenario="scenario.scenarioId" :data-scenario-action="scenario.scenarioId" :data-elmos-event="scenario.input.event" @click="trigger(scenario)">{{ scenario.scenarioId }}</button><template v-if="rows[scenario.scenarioId]"><span data-elmos-state-measurement="true" :data-elmos-state-id="rows[scenario.scenarioId].measurement.stateId" :data-elmos-before="rows[scenario.scenarioId].measurement.counterBefore" :data-elmos-after="rows[scenario.scenarioId].measurement.counterAfter" :data-elmos-saturated="String(rows[scenario.scenarioId].measurement.saturated)"></span><span data-elmos-action-outcome="true" :data-elmos-event-outcome="rows[scenario.scenarioId].measurement.event" :data-elmos-keyboard-key="rows[scenario.scenarioId].measurement.keyboardKey" :data-elmos-handled="String(rows[scenario.scenarioId].measurement.handled)" :data-elmos-action="rows[scenario.scenarioId].measurement.action"></span><span data-elmos-form-measurement="true" :data-elmos-form-id="model.formBindingValidation.formId" :data-elmos-field-id="model.formBindingValidation.fieldId" :data-elmos-submitted="String(rows[scenario.scenarioId].measurement.submitted)" :data-elmos-valid="String(rows[scenario.scenarioId].measurement.valid)" :data-elmos-error-code="rows[scenario.scenarioId].measurement.errorCode" :data-elmos-focus-target="rows[scenario.scenarioId].measurement.focusTarget"></span><span data-elmos-api-measurement="true" :data-elmos-operation-id="rows[scenario.scenarioId].measurement.operationId" :data-elmos-called="String(rows[scenario.scenarioId].measurement.apiCalled)" :data-elmos-method="rows[scenario.scenarioId].measurement.method" :data-elmos-path="rows[scenario.scenarioId].measurement.path" :data-elmos-outcome="rows[scenario.scenarioId].measurement.networkOutcome" :data-elmos-canceled="String(rows[scenario.scenarioId].measurement.canceled)" :data-elmos-stale-ignored="String(rows[scenario.scenarioId].measurement.staleIgnored)" :data-elmos-cache-key="rows[scenario.scenarioId].measurement.cacheKey"></span><span data-elmos-accessibility-measurement="true" :data-elmos-main-role="rows[scenario.scenarioId].measurement.mainRole" :data-elmos-heading-level="rows[scenario.scenarioId].measurement.headingLevel" :data-elmos-form-label="rows[scenario.scenarioId].measurement.formLabel" :data-elmos-error-role="rows[scenario.scenarioId].measurement.errorRole" :data-elmos-live-region="rows[scenario.scenarioId].measurement.liveRegion" :data-elmos-focus-target="rows[scenario.scenarioId].measurement.focusTarget" :data-elmos-keyboard-submit="String(rows[scenario.scenarioId].measurement.keyboardSubmit)"></span><span data-elmos-i18n-measurement="true" style="display:grid;grid-template-columns:var(--elmos-grid-columns)" :data-elmos-requested-locale="rows[scenario.scenarioId].measurement.requestedLocale" :data-elmos-requested-theme="rows[scenario.scenarioId].measurement.requestedTheme" :data-elmos-theme="rows[scenario.scenarioId].measurement.theme" :data-elmos-columns="rows[scenario.scenarioId].measurement.columns" :data-elmos-viewport-width="rows[scenario.scenarioId].measurement.viewportWidth">{{ rows[scenario.scenarioId].measurement.translatedText }}</span><span data-elmos-auth-decision="NOT_RUN" data-authority-adapter-trace="NOT_RUN"></span><span data-elmos-hydration-measurement="NOT_RUN"></span><span data-elmos-native-measurement="NOT_RUN"></span><span v-if="rows[scenario.scenarioId].measurement.errorCode" data-elmos-form-error="true" role="alert">{{ rows[scenario.scenarioId].measurement.errorCode }}</span><pre v-for="declaration in declarations" :key="declaration.block_id" :data-semantic-block="declaration.block_id" :data-observer-kind="declaration.observer_kind" :data-observation-status="declaration.status" :data-measurement-surface="declaration.measurement_surface" data-model-values-used="false">{{ declarationJson(declaration) }}</pre></template></article></form><output ref="result" id="elmos-result" data-elmos-result="true" tabindex="-1" :aria-live="model.accessibilityFocus.liveRegion"></output></section></template>',
    "",
  ].join("\n");
}

function blockSpecificSvelteWebConsumer(): string {
  return [
    '<script lang="ts">',
    'import { onDestroy } from "svelte";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosBrowserObserverDeclarations, elmosCreateBrowserRuntimeSession, elmosDeclarationJson, type ElmosBrowserMeasurement, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "interface RuntimeRow { readonly measurement: ElmosBrowserMeasurement; readonly sequence: number; }",
    "const declarations = elmosBrowserObserverDeclarations(); const session = elmosCreateBrowserRuntimeSession(); let rows: Readonly<Record<string, RuntimeRow>> = {}; let sequence = 0; let pending: ElmosRuntimeScenario | null = null; let query: HTMLInputElement; let result: HTMLOutputElement;",
    "async function execute(scenario: ElmosRuntimeScenario) { const measurement = await session.execute(scenario, query); sequence += 1; rows = { ...rows, [scenario.scenarioId]: { measurement, sequence } }; queueMicrotask(() => measurement.focusTarget === 'query' ? query.focus() : measurement.focusTarget === 'result' ? result.focus() : undefined); } function syncValidity(event: Event) { const element = event.currentTarget as HTMLInputElement; element.setCustomValidity(element.value.length < ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''); } function invalidForm(event: Event) { const element = event.currentTarget as HTMLInputElement; const scenario = pending; element.setAttribute('data-elmos-invalid-event', 'captured'); pending = null; if (scenario) void execute(scenario); } function isSubmitScenario(scenario: ElmosRuntimeScenario) { return scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; } function trigger(scenario: ElmosRuntimeScenario) { if (isSubmitScenario(scenario)) pending = scenario; else void execute(scenario); } function submitForm(event: SubmitEvent) { event.preventDefault(); const scenario = pending ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending = null; if (scenario) void execute(scenario); } onDestroy(() => session.dispose());",
    "</script>",
    '<section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-observer-protocol="block-specific-runtime-observation-v1" data-runtime-scope="SVELTE_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" data-completion={sequence > 0 ? "PARTIAL" : "IDLE"} data-run-id={sequence} aria-label="ELMOS bounded interaction runtime"><span hidden data-elmos-lifecycle-event="MOUNT" data-lifecycle-sequence="1"></span><form data-elmos-control="form" aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} onsubmit={submitForm}><input bind:this={query} id="elmos-query" name="query" data-elmos-control="query" data-field-id="search.query" required minlength={ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength} aria-label={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} oninput={syncValidity} oninvalid={invalidForm}>',
    '{#each ELMOS_INTERACTION_SCENARIOS as scenario (scenario.scenarioId)}{@const row = rows[scenario.scenarioId]}<article data-scenario-id={scenario.scenarioId} data-runtime-source={row ? "BLOCK_SPECIFIC_RUNTIME_OBSERVED" : "NOT_RUN"} data-execution-state={row ? "PARTIAL" : "IDLE"} data-execution-sequence={row?.sequence ?? 0}><button type={isSubmitScenario(scenario) ? "submit" : "button"} data-run-scenario={scenario.scenarioId} data-scenario-action={scenario.scenarioId} data-elmos-event={scenario.input.event} onclick={() => trigger(scenario)}>{scenario.scenarioId}</button>{#if row}<span data-elmos-state-measurement="true" data-elmos-state-id={row.measurement.stateId} data-elmos-before={row.measurement.counterBefore} data-elmos-after={row.measurement.counterAfter} data-elmos-saturated={String(row.measurement.saturated)}></span><span data-elmos-action-outcome="true" data-elmos-event-outcome={row.measurement.event} data-elmos-keyboard-key={row.measurement.keyboardKey} data-elmos-handled={String(row.measurement.handled)} data-elmos-action={row.measurement.action}></span><span data-elmos-form-measurement="true" data-elmos-form-id={ELMOS_FRONTEND_INTERACTION.formBindingValidation.formId} data-elmos-field-id={ELMOS_FRONTEND_INTERACTION.formBindingValidation.fieldId} data-elmos-submitted={String(row.measurement.submitted)} data-elmos-valid={String(row.measurement.valid)} data-elmos-error-code={row.measurement.errorCode} data-elmos-focus-target={row.measurement.focusTarget}></span><span data-elmos-api-measurement="true" data-elmos-operation-id={row.measurement.operationId} data-elmos-called={String(row.measurement.apiCalled)} data-elmos-method={row.measurement.method} data-elmos-path={row.measurement.path} data-elmos-outcome={row.measurement.networkOutcome} data-elmos-canceled={String(row.measurement.canceled)} data-elmos-stale-ignored={String(row.measurement.staleIgnored)} data-elmos-cache-key={row.measurement.cacheKey}></span><span data-elmos-accessibility-measurement="true" data-elmos-main-role={row.measurement.mainRole} data-elmos-heading-level={row.measurement.headingLevel} data-elmos-form-label={row.measurement.formLabel} data-elmos-error-role={row.measurement.errorRole} data-elmos-live-region={row.measurement.liveRegion} data-elmos-focus-target={row.measurement.focusTarget} data-elmos-keyboard-submit={String(row.measurement.keyboardSubmit)}></span><span data-elmos-i18n-measurement="true" style="display:grid;grid-template-columns:var(--elmos-grid-columns)" data-elmos-requested-locale={row.measurement.requestedLocale} data-elmos-requested-theme={row.measurement.requestedTheme} data-elmos-theme={row.measurement.theme} data-elmos-columns={row.measurement.columns} data-elmos-viewport-width={row.measurement.viewportWidth}>{row.measurement.translatedText}</span><span data-elmos-auth-decision="NOT_RUN" data-authority-adapter-trace="NOT_RUN"></span><span data-elmos-hydration-measurement="NOT_RUN"></span><span data-elmos-native-measurement="NOT_RUN"></span>{#if row.measurement.errorCode}<span data-elmos-form-error="true" role="alert">{row.measurement.errorCode}</span>{/if}{#each declarations as declaration (declaration.block_id)}<pre data-semantic-block={declaration.block_id} data-observer-kind={declaration.observer_kind} data-observation-status={declaration.status} data-measurement-surface={declaration.measurement_surface} data-model-values-used="false">{elmosDeclarationJson(declaration)}</pre>{/each}{/if}</article>{/each}</form><output bind:this={result} id="elmos-result" data-elmos-result="true" tabindex="-1" aria-live={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion}></output></section>',
    "",
  ].join("\n");
}

function blockSpecificAngularWebConsumer(): string {
  return [
    'import { Component, ElementRef, OnDestroy, ViewChild, signal } from "@angular/core";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosBrowserObserverDeclarations, elmosCreateBrowserRuntimeSession, elmosDeclarationJson, type ElmosBrowserMeasurement, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "interface RuntimeRow { readonly measurement: ElmosBrowserMeasurement; readonly sequence: number; }",
    "@Component({ standalone: true, selector: 'elmos-interaction', template: `",
    '<section id="elmos-interaction" data-proof-profile="bounded-frontend-interaction-v1" data-observer-protocol="block-specific-runtime-observation-v1" data-runtime-scope="ANGULAR_COMPONENT_ACTUAL_EVENTS" data-elmos-ready="true" [attr.data-completion]="sequence() > 0 ? \'PARTIAL\' : \'IDLE\'" [attr.data-run-id]="sequence()" aria-label="ELMOS bounded interaction runtime"><span hidden data-elmos-lifecycle-event="MOUNT" data-lifecycle-sequence="1"></span><form data-elmos-control="form" [attr.aria-label]="model.accessibilityFocus.formLabel" (submit)="submitForm($event)"><input #query id="elmos-query" name="query" data-elmos-control="query" data-field-id="search.query" required [attr.minlength]="model.formBindingValidation.minimumLength" [attr.aria-label]="model.accessibilityFocus.formLabel" (input)="syncValidity($event)" (invalid)="invalidForm($event)">',
    "@for (scenario of scenarios; track scenario.scenarioId) { @let row = rowFor(scenario.scenarioId); <article [attr.data-scenario-id]=\"scenario.scenarioId\" [attr.data-runtime-source]=\"row ? 'BLOCK_SPECIFIC_RUNTIME_OBSERVED' : 'NOT_RUN'\" [attr.data-execution-state]=\"row ? 'PARTIAL' : 'IDLE'\" [attr.data-execution-sequence]=\"row?.sequence ?? 0\"><button [type]=\"isSubmitScenario(scenario) ? 'submit' : 'button'\" [attr.data-run-scenario]=\"scenario.scenarioId\" [attr.data-scenario-action]=\"scenario.scenarioId\" [attr.data-elmos-event]=\"scenario.input.event\" (click)=\"trigger(scenario)\">{{ scenario.scenarioId }}</button>@if (row) { <span data-elmos-state-measurement=\"true\" [attr.data-elmos-state-id]=\"row.measurement.stateId\" [attr.data-elmos-before]=\"row.measurement.counterBefore\" [attr.data-elmos-after]=\"row.measurement.counterAfter\" [attr.data-elmos-saturated]=\"row.measurement.saturated\"></span><span data-elmos-action-outcome=\"true\" [attr.data-elmos-event-outcome]=\"row.measurement.event\" [attr.data-elmos-keyboard-key]=\"row.measurement.keyboardKey\" [attr.data-elmos-handled]=\"row.measurement.handled\" [attr.data-elmos-action]=\"row.measurement.action\"></span><span data-elmos-form-measurement=\"true\" [attr.data-elmos-form-id]=\"model.formBindingValidation.formId\" [attr.data-elmos-field-id]=\"model.formBindingValidation.fieldId\" [attr.data-elmos-submitted]=\"row.measurement.submitted\" [attr.data-elmos-focus-target]=\"row.measurement.focusTarget\" [attr.data-value]=\"row.measurement.query\" [attr.data-elmos-valid]=\"row.measurement.valid\" [attr.data-elmos-error-code]=\"row.measurement.errorCode\"></span><span data-elmos-api-measurement=\"true\" [attr.data-elmos-operation-id]=\"row.measurement.operationId\" [attr.data-elmos-called]=\"row.measurement.apiCalled\" [attr.data-elmos-method]=\"row.measurement.method\" [attr.data-elmos-path]=\"row.measurement.path\" [attr.data-elmos-outcome]=\"row.measurement.networkOutcome\" [attr.data-elmos-canceled]=\"row.measurement.canceled\" [attr.data-elmos-stale-ignored]=\"row.measurement.staleIgnored\" [attr.data-elmos-cache-key]=\"row.measurement.cacheKey\"></span><span data-elmos-accessibility-measurement=\"true\" [attr.data-elmos-main-role]=\"row.measurement.mainRole\" [attr.data-elmos-heading-level]=\"row.measurement.headingLevel\" [attr.data-elmos-form-label]=\"row.measurement.formLabel\" [attr.data-elmos-error-role]=\"row.measurement.errorRole\" [attr.data-elmos-live-region]=\"row.measurement.liveRegion\" [attr.data-elmos-focus-target]=\"row.measurement.focusTarget\" [attr.data-elmos-keyboard-submit]=\"row.measurement.keyboardSubmit\"></span><span data-elmos-i18n-measurement=\"true\" style=\"display:grid;grid-template-columns:var(--elmos-grid-columns)\" [attr.data-elmos-requested-locale]=\"row.measurement.requestedLocale\" [attr.data-elmos-requested-theme]=\"row.measurement.requestedTheme\" [attr.data-elmos-theme]=\"row.measurement.theme\" [attr.data-elmos-locale]=\"row.measurement.locale\" [attr.data-elmos-theme-value]=\"row.measurement.theme\" [attr.data-elmos-columns]=\"row.measurement.columns\" [attr.data-elmos-viewport-width]=\"row.measurement.viewportWidth\">{{ row.measurement.translatedText }}</span><span data-elmos-auth-decision=\"NOT_RUN\" data-authority-adapter-trace=\"NOT_RUN\"></span><span data-elmos-hydration-measurement=\"NOT_RUN\"></span><span data-elmos-native-measurement=\"NOT_RUN\"></span>@if (row.measurement.errorCode) { <span data-elmos-form-error=\"true\" role=\"alert\">{{ row.measurement.errorCode }}</span> } @for (declaration of declarations; track declaration.block_id) { <pre [attr.data-semantic-block]=\"declaration.block_id\" [attr.data-observer-kind]=\"declaration.observer_kind\" [attr.data-observation-status]=\"declaration.status\" [attr.data-measurement-surface]=\"declaration.measurement_surface\" data-model-values-used=\"false\">{{ declarationJson(declaration) }}</pre> } }</article> }</form><output #result id=\"elmos-result\" data-elmos-result=\"true\" tabindex=\"-1\" [attr.aria-live]=\"model.accessibilityFocus.liveRegion\"></output></section>",
    "  ` })",
    "export class ElmosInteractionComponent implements OnDestroy {",
    "  readonly model = ELMOS_FRONTEND_INTERACTION; readonly scenarios = ELMOS_INTERACTION_SCENARIOS; readonly declarations = elmosBrowserObserverDeclarations(); readonly rows = signal<Readonly<Record<string, RuntimeRow>>>({}); readonly sequence = signal(0); readonly declarationJson = elmosDeclarationJson; private readonly session = elmosCreateBrowserRuntimeSession(); private pending: ElmosRuntimeScenario | null = null; @ViewChild('query', { static: true }) private query!: ElementRef<HTMLInputElement>; @ViewChild('result', { static: true }) private result!: ElementRef<HTMLOutputElement>;",
    "  rowFor(id: string): RuntimeRow | undefined { return this.rows()[id]; } async execute(scenario: ElmosRuntimeScenario): Promise<void> { const measurement = await this.session.execute(scenario, this.query.nativeElement); const next = this.sequence() + 1; this.sequence.set(next); this.rows.update(previous => ({ ...previous, [scenario.scenarioId]: { measurement, sequence: next } })); queueMicrotask(() => measurement.focusTarget === 'query' ? this.query.nativeElement.focus() : measurement.focusTarget === 'result' ? this.result.nativeElement.focus() : undefined); } syncValidity(event: Event): void { const element = event.currentTarget as HTMLInputElement; element.setCustomValidity(element.value.length < this.model.formBindingValidation.minimumLength ? this.model.formBindingValidation.invalidCode : ''); } invalidForm(event: Event): void { const element = event.currentTarget as HTMLInputElement; const scenario = this.pending; element.setAttribute('data-elmos-invalid-event', 'captured'); this.pending = null; if (scenario) void this.execute(scenario); } isSubmitScenario(scenario: ElmosRuntimeScenario): boolean { return scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === this.model.actionEvent.keyboardSubmit; } trigger(scenario: ElmosRuntimeScenario): void { if (this.isSubmitScenario(scenario)) this.pending = scenario; else void this.execute(scenario); } submitForm(event: SubmitEvent): void { event.preventDefault(); const scenario = this.pending ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; this.pending = null; if (scenario) void this.execute(scenario); } ngOnDestroy(): void { this.session.dispose(); }",
    "}",
    "",
  ].join("\n");
}

function blockSpecificJqueryWebConsumer(): string {
  return [
    'import $ from "jquery";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosBrowserObserverDeclarations, elmosCreateBrowserRuntimeSession, elmosDeclarationJson, type ElmosBrowserMeasurement, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "const declarations = elmosBrowserObserverDeclarations(); const session = elmosCreateBrowserRuntimeSession(); let sequence = 0; let pending: ElmosRuntimeScenario | null = null;",
    "function raw(tag: string, attributes: Readonly<Record<string, string>>, text = '') { return $(`<${tag}>`, { ...attributes, text }); }",
    "function render(scenario: ElmosRuntimeScenario, value: ElmosBrowserMeasurement): void { const row = $(`[data-scenario-id=\"${scenario.scenarioId}\"]`); row.find('[data-elmos-generated-measurement]').remove(); const generated = $('<div>', { 'data-elmos-generated-measurement': 'true' }); generated.append(raw('span', { 'data-elmos-state-measurement': 'true', 'data-elmos-state-id': value.stateId, 'data-elmos-before': String(value.counterBefore), 'data-elmos-after': String(value.counterAfter), 'data-elmos-saturated': String(value.saturated) }), raw('span', { 'data-elmos-action-outcome': 'true', 'data-elmos-event-outcome': value.event, 'data-elmos-keyboard-key': value.keyboardKey, 'data-elmos-handled': String(value.handled), 'data-elmos-action': value.action }), raw('span', { 'data-elmos-form-measurement': 'true', 'data-elmos-form-id': ELMOS_FRONTEND_INTERACTION.formBindingValidation.formId, 'data-elmos-field-id': ELMOS_FRONTEND_INTERACTION.formBindingValidation.fieldId, 'data-elmos-submitted': String(value.submitted), 'data-elmos-valid': String(value.valid), 'data-elmos-error-code': value.errorCode, 'data-elmos-focus-target': value.focusTarget }), raw('span', { 'data-elmos-api-measurement': 'true', 'data-elmos-operation-id': value.operationId, 'data-elmos-called': String(value.apiCalled), 'data-elmos-method': value.method, 'data-elmos-path': value.path, 'data-elmos-outcome': value.networkOutcome, 'data-elmos-canceled': String(value.canceled), 'data-elmos-stale-ignored': String(value.staleIgnored), 'data-elmos-cache-key': value.cacheKey }), raw('span', { 'data-elmos-accessibility-measurement': 'true', 'data-elmos-main-role': value.mainRole, 'data-elmos-heading-level': String(value.headingLevel), 'data-elmos-form-label': value.formLabel, 'data-elmos-error-role': value.errorRole, 'data-elmos-live-region': value.liveRegion, 'data-elmos-focus-target': value.focusTarget, 'data-elmos-keyboard-submit': String(value.keyboardSubmit) }), raw('span', { 'data-elmos-i18n-measurement': 'true', style: 'display:grid;grid-template-columns:var(--elmos-grid-columns)', 'data-elmos-requested-locale': value.requestedLocale, 'data-elmos-requested-theme': value.requestedTheme, 'data-elmos-theme': value.theme, 'data-elmos-columns': String(value.columns), 'data-elmos-viewport-width': String(value.viewportWidth) }, value.translatedText), raw('span', { 'data-elmos-auth-decision': 'NOT_RUN', 'data-authority-adapter-trace': 'NOT_RUN' }), raw('span', { 'data-elmos-hydration-measurement': 'NOT_RUN' }), raw('span', { 'data-elmos-native-measurement': 'NOT_RUN' })); if (value.errorCode) generated.append(raw('span', { 'data-elmos-form-error': 'true', role: 'alert' }, value.errorCode)); for (const declaration of declarations) generated.append(raw('pre', { 'data-semantic-block': declaration.block_id, 'data-observer-kind': declaration.observer_kind, 'data-observation-status': declaration.status, 'data-measurement-surface': declaration.measurement_surface, 'data-model-values-used': 'false' }, elmosDeclarationJson(declaration))); sequence += 1; row.append(generated).attr({ 'data-runtime-source': 'BLOCK_SPECIFIC_RUNTIME_OBSERVED', 'data-execution-state': 'PARTIAL', 'data-execution-sequence': String(sequence) }); $('#elmos-interaction').attr({ 'data-completion': 'PARTIAL', 'data-run-id': String(sequence) }); if (value.focusTarget === 'query') $('#elmos-query').trigger('focus'); else if (value.focusTarget === 'result') $('#elmos-result').trigger('focus'); }",
    "async function execute(scenario: ElmosRuntimeScenario): Promise<void> { const query = document.querySelector<HTMLInputElement>('#elmos-query'); if (!query) return; render(scenario, await session.execute(scenario, query)); }",
    "function syncValidity(event: Event): void { const element = event.target; if (!(element instanceof HTMLInputElement) || element.id !== 'elmos-query') return; element.setCustomValidity(element.value.length < ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength ? ELMOS_FRONTEND_INTERACTION.formBindingValidation.invalidCode : ''); }",
    "function invalidForm(event: Event): void { const element = event.target; if (!(element instanceof HTMLInputElement) || element.id !== 'elmos-query') return; const scenario = pending; element.setAttribute('data-elmos-invalid-event', 'captured'); pending = null; if (scenario) void execute(scenario); }",
    "function isSubmitScenario(scenario: ElmosRuntimeScenario): boolean { return scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; }",
    "export function mountElmosInteraction(root: HTMLElement): () => void { const section = $('<section>', { id: 'elmos-interaction', 'data-proof-profile': 'bounded-frontend-interaction-v1', 'data-observer-protocol': 'block-specific-runtime-observation-v1', 'data-runtime-scope': 'JQUERY_EVENTS_AND_DATA', 'data-elmos-ready': 'true', 'data-completion': 'IDLE', 'data-run-id': '0', 'aria-label': 'ELMOS bounded interaction runtime' }); const form = $('<form>', { 'data-elmos-control': 'form', 'aria-label': ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel }); form.append($('<span>', { hidden: true, 'data-elmos-lifecycle-event': 'MOUNT', 'data-lifecycle-sequence': '1' }), $('<input>', { id: 'elmos-query', name: 'query', required: true, minlength: ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength, 'data-elmos-control': 'query', 'data-field-id': 'search.query', 'aria-label': ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel })); for (const scenario of ELMOS_INTERACTION_SCENARIOS) { const row = $('<article>', { 'data-scenario-id': scenario.scenarioId, 'data-runtime-source': 'NOT_RUN', 'data-execution-state': 'IDLE', 'data-execution-sequence': '0' }); const button = $('<button>', { type: isSubmitScenario(scenario) ? 'submit' : 'button', 'data-run-scenario': scenario.scenarioId, 'data-scenario-action': scenario.scenarioId, 'data-elmos-event': scenario.input.event, text: scenario.scenarioId }); button.data('elmosScenario', scenario).on('click.elmos', () => { if (isSubmitScenario(scenario)) pending = scenario; else void execute(scenario); }); row.append(button); form.append(row); } form.on('submit.elmos', event => { event.preventDefault(); const scenario = pending ?? ELMOS_INTERACTION_SCENARIOS.find(item => item.scenarioId === 'FORM_VALID_SUBMIT_API_SUCCESS') ?? null; pending = null; if (scenario) void execute(scenario); }); section.append(form, $('<output>', { id: 'elmos-result', 'data-elmos-result': 'true', tabindex: '-1', 'aria-live': ELMOS_FRONTEND_INTERACTION.accessibilityFocus.liveRegion })); $(root).append(section); const cleanup = () => { session.dispose(); form.off('.elmos'); form.find('button').off('.elmos'); }; $(window).one('beforeunload.elmos', cleanup); return cleanup; }",
    "",
  ].join("\n");
}

function blockSpecificNativeRuntimeModule(): string {
  const contracts = generatedObserverContractLiteral();
  return [
    "// Native block observer declarations only; actual values come from framework semantics and adapter traces.",
    "export interface ElmosRuntimeInput { readonly routePath: string; readonly event: string; readonly keyboardKey: string | null; readonly counterBefore: number; readonly incrementCount: number; readonly lifecycle: string; readonly query: string; readonly networkResult: string; readonly authenticated: boolean; readonly permissionGranted: boolean; readonly tenantId: string; readonly resourceTenantId: string; readonly hydration: string; readonly locale: string; readonly theme: string; readonly viewportWidth: number; readonly nativeLifecycle: string; readonly nativePermission: string; readonly nativeAvailable: boolean; readonly deepLinkPath: string | null; }",
    "export interface ElmosRuntimeScenario { readonly scenarioId: string; readonly input: ElmosRuntimeInput; }",
    "export interface ElmosObserverDeclaration { readonly schema_version: '1.0'; readonly kind: 'frontend-block-observer-declaration'; readonly block_id: string; readonly status: 'PASSED' | 'NOT_RUN'; readonly observer_kind: string; readonly measurement_surface: string; readonly reason: string; }",
    `export const ELMOS_BLOCK_OBSERVERS = Object.freeze(${contracts} as const);`,
    "export function elmosNativeObserverDeclarations(observedBlockIds: readonly string[]): readonly ElmosObserverDeclaration[] { const observed = new Set(observedBlockIds); return ELMOS_BLOCK_OBSERVERS.map(spec => { const complete = spec.native_status === 'PASSED' && observed.has(spec.block_id); return { schema_version: '1.0', kind: 'frontend-block-observer-declaration', block_id: spec.block_id, status: complete ? 'PASSED' : 'NOT_RUN', observer_kind: spec.observer_kind, measurement_surface: spec.measurement_surface, reason: spec.native_status === 'NOT_RUN' ? spec.native_reason : complete ? 'native framework semantics or adapter trace captured' : 'required native framework, authority, hydration, route, locale, or device surface was not observed' }; }); }",
    "export function elmosDeclarationJson(value: ElmosObserverDeclaration): string { return JSON.stringify(value); }",
    "",
  ].join("\n");
}

function blockSpecificNativeReactConsumer(): string {
  return [
    'import { useEffect, useRef, useState } from "react";',
    'import { Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";',
    'import { ELMOS_FRONTEND_INTERACTION, ELMOS_INTERACTION_SCENARIOS } from "./elmos-bounded-interaction";',
    'import { elmosDeclarationJson, elmosNativeObserverDeclarations, type ElmosRuntimeScenario } from "./elmos-interaction-runtime";',
    "interface NativeMeasurement { readonly stateBefore: number; readonly stateAfter: number; readonly saturated: boolean; readonly event: string; readonly action: string; readonly query: string; readonly valid: boolean; readonly apiOutcome: string; readonly nativeOutcome: string; readonly observedBlocks: readonly string[]; } interface RuntimeRow { readonly measurement: NativeMeasurement; readonly sequence: number; }",
    "export interface ElmosNativeAdapter { readonly openDeepLink: (path: string) => Promise<boolean>; }",
    "export function ElmosInteractionPanel({ nativeAdapter }: { readonly nativeAdapter?: ElmosNativeAdapter }) {",
    "  const [query, setQuery] = useState(''); const [rows, setRows] = useState<Readonly<Record<string, RuntimeRow>>>({}); const [sequence, setSequence] = useState(0); const controller = useRef<AbortController | null>(null); const lifecycle = useRef<readonly string[]>(['MOUNT']);",
    "  async function dispatch(scenario: ElmosRuntimeScenario) { const value = query === '' ? scenario.input.query : query; setQuery(value); const rawCounter = Math.max(scenario.input.counterBefore, ELMOS_FRONTEND_INTERACTION.stateManagement.initial) + scenario.input.incrementCount; const stateAfter = Math.max(ELMOS_FRONTEND_INTERACTION.stateManagement.minimum, Math.min(ELMOS_FRONTEND_INTERACTION.stateManagement.maximum, rawCounter)); const submitted = scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey === ELMOS_FRONTEND_INTERACTION.actionEvent.keyboardSubmit; const valid = value.length >= ELMOS_FRONTEND_INTERACTION.formBindingValidation.minimumLength; const apiCalled = submitted && valid; let apiOutcome = 'NOT_CALLED'; if (apiCalled) { controller.current = new AbortController(); try { const response = await fetch(ELMOS_FRONTEND_INTERACTION.apiNetwork.path, { method: ELMOS_FRONTEND_INTERACTION.apiNetwork.method, body: JSON.stringify({ query: value }), signal: controller.current.signal }); apiOutcome = response.ok ? 'SUCCESS' : 'ERROR'; } catch { apiOutcome = 'ERROR'; } finally { controller.current = null; } } let nativeOutcome = 'NOT_RUN'; let nativeObserved = false; if (Platform.OS !== 'web' && scenario.input.event === 'NATIVE_DEEPLINK' && scenario.input.deepLinkPath && nativeAdapter) { nativeObserved = true; nativeOutcome = await nativeAdapter.openDeepLink(scenario.input.deepLinkPath) ? 'OPENED' : 'DENIED_RECOVERABLE'; } const observedBlocks = ['state-management', 'action-event', 'form-binding-validation', 'accessibility-focus', ...(nativeObserved ? ['native-platform'] : [])]; const action = submitted ? valid ? 'SUBMIT_ACCEPTED' : ELMOS_FRONTEND_INTERACTION.actionEvent.deniedAction : scenario.input.event; const measurement: NativeMeasurement = { stateBefore: scenario.input.counterBefore, stateAfter, saturated: rawCounter > ELMOS_FRONTEND_INTERACTION.stateManagement.maximum, event: scenario.input.event, action, query: value, valid, apiOutcome, nativeOutcome, observedBlocks }; const next = sequence + 1; setSequence(next); setRows(previous => ({ ...previous, [scenario.scenarioId]: { measurement, sequence: next } })); }",
    "  useEffect(() => () => { controller.current?.abort(); lifecycle.current = [...lifecycle.current, 'UNMOUNT']; }, []);",
    '  return <ScrollView nativeID="elmos-interaction" testID="elmos-interaction" accessibilityLabel={`ELMOS:bounded-frontend-interaction-v1:protocol:block-specific-runtime-observation-v1:scope:REACT_NATIVE_COMPONENT_ACTUAL_EVENTS:runtime:BLOCK_SPECIFIC_RUNTIME_OBSERVED:state:${sequence > 0 ? "PARTIAL" : "IDLE"}:sequence:${sequence}`}>',
    '    <TextInput testID="elmos-query" accessibilityLabel={ELMOS_FRONTEND_INTERACTION.accessibilityFocus.formLabel} value={query} onChangeText={setQuery} />',
    "    {ELMOS_INTERACTION_SCENARIOS.map(scenario => { const row = rows[scenario.scenarioId]; const value = row?.measurement; const declarations = value ? elmosNativeObserverDeclarations(value.observedBlocks) : []; return <View key={scenario.scenarioId} testID={`scenario:${scenario.scenarioId}`} accessible accessibilityLabel={`scenario:${scenario.scenarioId}:runtime:${row ? 'BLOCK_SPECIFIC_RUNTIME_OBSERVED' : 'NOT_RUN'}:state:${row ? 'PARTIAL' : 'IDLE'}:sequence:${row?.sequence ?? 0}`}><Pressable testID={`action:${scenario.scenarioId}`} accessibilityLabel={`action:${scenario.scenarioId}:event:${scenario.input.event}`} accessibilityRole=\"button\" onPress={() => { void dispatch(scenario); }}><Text>{scenario.scenarioId}</Text></Pressable>{value && <View testID={`measurements:${scenario.scenarioId}`} accessibilityLabel={`state:${value.stateBefore}:${value.stateAfter}:${value.saturated};action:${value.event}:${value.action};form:${value.query}:${value.valid};api:${value.apiOutcome};native:${value.nativeOutcome}`}>{declarations.map(declaration => <Text key={declaration.block_id} testID={`block:${scenario.scenarioId}:${declaration.block_id}`} accessibilityLabel={`declaration:${declaration.block_id}:${declaration.observer_kind}:${declaration.status}:${declaration.measurement_surface}:model-values-used:false`}>{elmosDeclarationJson(declaration)}</Text>)}</View>}</View>; })}",
    "  </ScrollView>;",
    "}",
    "",
  ].join("\n");
}

function blockSpecificDartRuntimeModule(): string {
  return [
    "// Declaration-only native observer contract. Actual values are captured from Widget semantics and adapters.",
    `const List<String> elmosRuntimeBlockIds = ${JSON.stringify(interactionBlockIds)};`,
    `const List<Map<String, Object>> elmosBlockObservers = <Map<String, Object>>${generatedObserverContractLiteral()};`,
    "List<Map<String, Object>> elmosNativeObserverDeclarations(Set<String> observedBlockIds) => elmosBlockObservers.map((spec) { final blockId = spec['block_id']! as String; final nativeStatus = spec['native_status']! as String; final complete = nativeStatus == 'PASSED' && observedBlockIds.contains(blockId); return <String, Object>{'schema_version': '1.0', 'kind': 'frontend-block-observer-declaration', 'block_id': blockId, 'status': complete ? 'PASSED' : 'NOT_RUN', 'observer_kind': spec['observer_kind']!, 'measurement_surface': spec['measurement_surface']!, 'reason': nativeStatus == 'NOT_RUN' ? spec['native_reason']! : complete ? 'Flutter semantics or adapter trace captured' : 'required native framework, authority, hydration, route, locale, or device surface was not observed'}; }).toList(growable: false);",
    "",
  ].join("\n");
}

function blockSpecificFlutterConsumer(): string {
  return [
    "import 'dart:convert';",
    "import 'package:flutter/foundation.dart';",
    "import 'package:flutter/material.dart';",
    "import 'elmos_bounded_interaction.dart';",
    "import 'elmos_interaction_runtime.dart';",
    "typedef ElmosApiAdapter = Future<String> Function(String path, String method, String query, bool cancel);",
    "typedef ElmosNativeAdapter = Future<bool> Function(String path);",
    "class ElmosInteractionPanel extends StatefulWidget { const ElmosInteractionPanel({this.apiAdapter, this.nativeAdapter, super.key}); final ElmosApiAdapter? apiAdapter; final ElmosNativeAdapter? nativeAdapter; @override State<ElmosInteractionPanel> createState() => _ElmosInteractionPanelState(); }",
    "class _ElmosInteractionPanelState extends State<ElmosInteractionPanel> {",
    "  final TextEditingController query = TextEditingController(); final FocusNode queryFocus = FocusNode(); final FocusNode resultFocus = FocusNode(); final Map<String, Map<String, Object?>> measurements = <String, Map<String, Object?>>{}; final Map<String, int> sequences = <String, int>{}; int sequence = 0; String get runtimeChannel { if (kIsWeb) return 'browser'; return switch (defaultTargetPlatform) { TargetPlatform.android => 'android', TargetPlatform.iOS => 'ios', _ => 'browser' }; }",
    "  Future<void> dispatch(Object? raw) async { final scenario = elmosMap(raw); final input = elmosMap(scenario['input']); final value = query.text.isEmpty ? input['query']! as String : query.text; query.text = value; final model = elmosFrontendInteraction; final state = elmosMap(model['stateManagement']); final rawCounter = (input['counterBefore']! as num).clamp(state['initial']! as num, double.infinity) + (input['incrementCount']! as num); final stateAfter = rawCounter.clamp(state['minimum']! as num, state['maximum']! as num); final form = elmosMap(model['formBindingValidation']); final actionContract = elmosMap(model['actionEvent']); final submitted = input['event'] == 'SUBMIT' || input['keyboardKey'] == actionContract['keyboardSubmit']; final valid = value.length >= (form['minimumLength']! as num); final api = elmosMap(model['apiNetwork']); final canceled = input['event'] == 'CANCEL' || input['lifecycle'] == 'UNMOUNT'; var apiOutcome = 'NOT_CALLED'; if ((submitted && valid || canceled) && widget.apiAdapter != null) { apiOutcome = await widget.apiAdapter!.call(api['path']! as String, api['method']! as String, value, canceled); } var nativeOutcome = 'NOT_RUN'; var nativeObserved = false; if (runtimeChannel != 'browser' && input['event'] == 'NATIVE_DEEPLINK' && input['deepLinkPath'] is String && widget.nativeAdapter != null) { nativeObserved = true; nativeOutcome = await widget.nativeAdapter!.call(input['deepLinkPath']! as String) ? 'OPENED' : 'DENIED_RECOVERABLE'; } final observed = <String>{'state-management', 'action-event', 'form-binding-validation', 'accessibility-focus', if (nativeObserved) 'native-platform'}; final action = submitted ? valid ? 'SUBMIT_ACCEPTED' : actionContract['deniedAction']! as String : input['event']! as String; final measurement = <String, Object?>{'state_before': input['counterBefore'], 'state_after': stateAfter, 'saturated': rawCounter > (state['maximum']! as num), 'event': input['event'], 'action': action, 'query': value, 'valid': valid, 'api_outcome': apiOutcome, 'native_outcome': nativeOutcome, 'observed_blocks': observed}; if (!mounted) return; final id = scenario['scenarioId']! as String; setState(() { sequence += 1; measurements[id] = measurement; sequences[id] = sequence; }); if (submitted && !valid) { queryFocus.requestFocus(); } else if (submitted) { resultFocus.requestFocus(); } }",
    "  @override void dispose() { query.dispose(); queryFocus.dispose(); resultFocus.dispose(); super.dispose(); }",
    "  @override Widget build(BuildContext context) => Semantics(label: 'ELMOS:bounded-frontend-interaction-v1:block-specific-runtime-observation-v1:${sequence > 0 ? 'PARTIAL' : 'IDLE'}', child: Column(children: [TextField(key: const ValueKey<String>('elmos-query'), controller: query, focusNode: queryFocus, decoration: InputDecoration(labelText: elmosMap(elmosFrontendInteraction['accessibilityFocus'])['formLabel']! as String)), Expanded(child: SingleChildScrollView(key: const ValueKey<String>('elmos-interaction'), child: Column(children: [for (final scenario in elmosInteractionScenarios) Builder(builder: (context) { final id = elmosMap(scenario)['scenarioId']! as String; final measurement = measurements[id]; final observed = measurement == null ? <String>{} : Set<String>.from(measurement['observed_blocks']! as Set<String>); final declarations = measurement == null ? const <Map<String, Object>>[] : elmosNativeObserverDeclarations(observed); return Semantics(container: true, label: 'scenario:$id:${measurement == null ? 'IDLE' : 'PARTIAL'}:sequence:${sequences[id] ?? 0}:runtime:BLOCK_SPECIFIC_RUNTIME_OBSERVED:${measurement == null ? '' : jsonEncode(<String, Object?>{'state_before': measurement['state_before'], 'state_after': measurement['state_after'], 'saturated': measurement['saturated'], 'event': measurement['event'], 'action': measurement['action'], 'query': measurement['query'], 'valid': measurement['valid'], 'api_outcome': measurement['api_outcome'], 'native_outcome': measurement['native_outcome']})}', child: Column(key: ValueKey<String>('scenario:$id'), children: [FilledButton(key: ValueKey<String>('action:$id'), onPressed: () async { await dispatch(scenario); }, child: Text(id)), for (final declaration in declarations) Text(jsonEncode(declaration), key: ValueKey<String>('block:$id:${declaration['block_id']}'), semanticsLabel: 'declaration:${declaration['block_id']}:${declaration['observer_kind']}:${declaration['status']}:${declaration['measurement_surface']}:model-values-used:false')])); })]))), Focus(focusNode: resultFocus, child: const Text('', key: ValueKey<String>('elmos-result')))]));",
    "}",
    "",
  ].join("\n");
}

function blockSpecificFlutterIntegrationTest(projectName: string): string {
  return [
    "import 'dart:convert';",
    "import 'package:flutter/foundation.dart';",
    "import 'package:flutter/material.dart';",
    "import 'package:flutter_test/flutter_test.dart';",
    "import 'package:integration_test/integration_test.dart';",
    `import 'package:${projectName}/elmos_bounded_interaction.dart';`,
    `import 'package:${projectName}/elmos_interaction_runtime.dart';`,
    `import 'package:${projectName}/main.dart' as app;`,
    "void main() { final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized(); testWidgets('captures 18 declaration-only block-specific Flutter traces', (tester) async { final runtimeChannel = kIsWeb ? 'browser' : switch (defaultTargetPlatform) { TargetPlatform.android => 'android', TargetPlatform.iOS => 'ios', _ => throw UnsupportedError('unsupported Flutter runtime channel') }; final scenarios = <Map<String, Object?>>[]; final networkEvents = <String, List<Map<String, Object?>>>{}; final platformEvents = <String, List<Map<String, Object?>>>{}; var activeId = ''; await tester.pumpWidget(app.GeneratedApp(interactionApiAdapter: (path, method, query, cancel) async { final outcome = cancel ? 'STALE' : query == 'fail' ? 'ERROR' : 'SUCCESS'; networkEvents.putIfAbsent(activeId, () => <Map<String, Object?>>[]).add(<String, Object?>{'method': method, 'path': path, 'query': query, 'cancel': cancel, 'outcome': outcome}); return outcome; }, interactionNativeAdapter: (path) async { platformEvents.putIfAbsent(activeId, () => <Map<String, Object?>>[]).add(<String, Object?>{'operation': 'OPEN_DEEP_LINK', 'path': path, 'result': true}); return true; })); await tester.pumpAndSettle(); var prior = 0; for (final raw in elmosInteractionScenarios) { final id = elmosMap(raw)['scenarioId']! as String; activeId = id; final action = find.byKey(ValueKey<String>('action:$id')); await tester.ensureVisible(action); await tester.tap(action); await tester.pumpAndSettle(); final declarations = <String, Object?>{}; for (final blockId in elmosRuntimeBlockIds) { final finder = find.byKey(ValueKey<String>('block:$id:$blockId')); expect(finder, findsOneWidget); final decoded = jsonDecode(tester.widget<Text>(finder).data!) as Map<String, Object?>; expect(decoded.keys.toSet(), <String>{'schema_version', 'kind', 'block_id', 'status', 'observer_kind', 'measurement_surface', 'reason'}); expect(decoded['block_id'], blockId); expect(<String>{'PASSED', 'NOT_RUN'}, contains(decoded['status'])); expect(decoded.keys, isNot(contains('actual'))); expect(decoded.keys, isNot(contains('expected'))); expect(decoded.keys, isNot(contains('model'))); expect(decoded.keys, isNot(contains('projection'))); declarations[blockId] = decoded; } final semantics = tester.getSemantics(find.byKey(ValueKey<String>('scenario:$id'))).label; final sequenceMatch = RegExp(r'sequence:(\\d+)').firstMatch(semantics); expect(sequenceMatch, isNotNull); final current = int.parse(sequenceMatch!.group(1)!); expect(current, greaterThan(prior)); prior = current; scenarios.add(<String, Object?>{'scenario_id': id, 'execution_sequence': current, 'execution_state': 'PARTIAL', 'runtime_source': 'BLOCK_SPECIFIC_RUNTIME_OBSERVED', 'semantics_label': semantics, 'block_declarations': declarations, 'network_adapter_events': networkEvents[id] ?? const <Map<String, Object?>>[], 'platform_adapter_events': platformEvents[id] ?? const <Map<String, Object?>>[]}); } binding.reportData = <String, Object?>{'runtime_channel': runtimeChannel, 'runtime_source': 'BLOCK_SPECIFIC_RUNTIME_OBSERVED', 'model_or_precomputed_values_used': false, 'scenarios': scenarios, 'summary': <String, Object?>{'scenario_count': scenarios.length, 'block_count': elmosRuntimeBlockIds.length, 'all_partial_or_complete': scenarios.every((row) => <String>{'PARTIAL', 'COMPLETE'}.contains(row['execution_state']))}}; }); }",
    "",
  ].join("\n");
}

function blockSpecificFlutterIntegrationDriver(): string {
  return [
    "import 'dart:convert';",
    "import 'dart:io';",
    "import 'package:integration_test/integration_test_driver.dart';",
    "String requiredEnvironment(String name) { final value = Platform.environment[name]; if (value == null || value.isEmpty) throw StateError('$name is required'); return value; }",
    "String requiredDigest(String name) { final value = requiredEnvironment(name); if (!RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(value)) throw StateError('$name must be a sha256 digest'); return value; }",
    "Future<void> main() async { final tracePath = requiredEnvironment('ELMOS_FLUTTER_TRACE_PATH'); final channel = requiredEnvironment('ELMOS_FLUTTER_RUNTIME_CHANNEL'); if (!const <String>{'browser', 'android', 'ios'}.contains(channel)) throw StateError('ELMOS_FLUTTER_RUNTIME_CHANNEL is invalid'); final projectDigest = requiredDigest('ELMOS_FLUTTER_PROJECT_DIGEST'); final profileManifestDigest = requiredDigest('ELMOS_FLUTTER_PROFILE_MANIFEST_DIGEST'); final scenarioManifestDigest = requiredDigest('ELMOS_FLUTTER_SCENARIO_MANIFEST_DIGEST'); await integrationDriver(responseDataCallback: (data) async { if (data == null || data.length != 5 || !const <String>['runtime_channel', 'runtime_source', 'model_or_precomputed_values_used', 'scenarios', 'summary'].every(data.containsKey)) throw StateError('Flutter integration response shape drifted'); if (data['runtime_channel'] != channel || data['runtime_source'] != 'BLOCK_SPECIFIC_RUNTIME_OBSERVED' || data['model_or_precomputed_values_used'] != false || data['scenarios'] is! List<Object?> || data['summary'] is! Map<String, Object?>) throw StateError('Flutter block-specific provenance drifted'); final payload = <String, Object?>{'schema_version': '1.0', 'kind': 'bounded-frontend-interaction-flutter-runtime-trace', 'proof_profile': 'bounded-frontend-interaction-v1', 'observer_protocol': 'block-specific-runtime-observation-v1', 'profile_id': 'flutter', 'channel': channel, 'project_digest': projectDigest, 'profile_manifest_digest': profileManifestDigest, 'scenario_manifest_digest': scenarioManifestDigest, 'runtime_source': data['runtime_source'], 'model_or_precomputed_values_used': false, 'scenarios': data['scenarios'], 'summary': data['summary']}; final destination = File(tracePath); if (destination.existsSync()) throw StateError('ELMOS_FLUTTER_TRACE_PATH already exists'); destination.parent.createSync(recursive: true); final temporary = File('$tracePath.tmp.$pid'); await temporary.writeAsString('${jsonEncode(payload)}\\n', flush: true); await temporary.rename(tracePath); }, writeResponseOnFailure: false); }",
    "",
  ].join("\n");
}

function blockSpecificArkRuntimeModule(): string {
  const contracts = generatedObserverContractLiteral();
  return [
    "// ArkUI declaration-only observer contract. UI tests must derive values from Ark semantics and adapters.",
    `export const ELMOS_BLOCK_OBSERVERS = ${contracts};`,
    "export function elmosArkObserverDeclarations(observedBlockIds: string[]): object[] { return ELMOS_BLOCK_OBSERVERS.map((spec) => { const complete = spec.native_status === 'PASSED' && observedBlockIds.indexOf(spec.block_id) >= 0; return { schema_version: '1.0', kind: 'frontend-block-observer-declaration', block_id: spec.block_id, status: complete ? 'PASSED' : 'NOT_RUN', observer_kind: spec.observer_kind, measurement_surface: spec.measurement_surface, reason: spec.native_status === 'NOT_RUN' ? spec.native_reason : complete ? 'ArkUI event semantics captured' : 'required ArkUI authority, hydration, route, state, lifecycle, network, locale, or device surface was not observed' }; }); }",
    "",
  ].join("\n");
}

function replaceExact(source: string, needle: string, replacement: string, path: string): string {
  const first = source.indexOf(needle);
  if (first < 0 || source.indexOf(needle, first + needle.length) >= 0) throw new Error(`interaction integration point drifted: ${path}`);
  return source.replace(needle, replacement);
}

export function augmentBoundedInteractionFiles(
  profile: UiFrameworkId,
  model: BoundedFrontendInteractionModel,
  baseFiles: Readonly<Record<string, string>>,
): Readonly<Record<string, string>> {
  const spec = interactionSourceSpec(profile);
  const files: Record<string, string> = {
    ...baseFiles,
    [spec.sourcePath]: interactionContractSource(profile, model),
    [spec.compatibilityPath]: navigationCompatibilitySource(profile),
  };
  switch (profile) {
    case "react":
      files["src/elmos-interaction-runtime.ts"] = blockSpecificBrowserRuntimeModule(profile);
      files["src/ElmosInteractionPanel.tsx"] = blockSpecificReactWebConsumer();
      files["src/App.tsx"] = replaceExact(files["src/App.tsx"]!, '  return <main className="content" id="main" data-route-id={route.id} data-route-path={route.path} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink}><article className="card">', `  return <main className="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" data-elmos-route-id={route.id} data-elmos-route-path={route.path} data-elmos-requires-auth={route.requiresAuth} data-elmos-deep-link={route.deepLink} data-elmos-component-id=${JSON.stringify(model.componentTemplate.componentId)} data-elmos-component-key={route.id} data-route-id={route.id} data-route-path={route.path} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink}><article className="card">`, "src/App.tsx");
      files["src/App.tsx"] = replaceExact(files["src/App.tsx"]!, 'import { routes, type GeneratedRoute } from "./routes";', 'import { routes, type GeneratedRoute } from "./routes";\nimport { ElmosInteractionPanel } from "./ElmosInteractionPanel";', "src/App.tsx");
      files["src/App.tsx"] = replaceExact(files["src/App.tsx"]!, "    </Routes>\n  </div>;", "    </Routes>\n    <ElmosInteractionPanel />\n  </div>;", "src/App.tsx");
      break;
    case "vue2":
      files["src/elmos-interaction-runtime.js"] = blockSpecificBrowserRuntimeModule(profile);
      files["src/ElmosInteractionPanel.vue"] = blockSpecificVue2WebConsumer();
      files["src/views/GeneratedPage.vue"] = replaceExact(files["src/views/GeneratedPage.vue"]!, `<template><main class="content" id="main" :data-route-id="page && page.id" :data-route-path="page && page.path" :data-requires-auth="page && page.requiresAuth ? 'true' : 'false'" :data-deep-link="page && page.deepLink ? 'true' : 'false'"><article class="card">`, `<template><main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" :data-elmos-route-id="page && page.id" :data-elmos-route-path="page && page.path" :data-elmos-requires-auth="page && page.requiresAuth ? 'true' : 'false'" :data-elmos-deep-link="page && page.deepLink ? 'true' : 'false'" data-elmos-component-id=${JSON.stringify(model.componentTemplate.componentId)} :data-elmos-component-key="page && page.id" :data-route-id="page && page.id" :data-route-path="page && page.path" :data-requires-auth="page && page.requiresAuth ? 'true' : 'false'" :data-deep-link="page && page.deepLink ? 'true' : 'false'"><article class="card">`, "src/views/GeneratedPage.vue");
      files["src/App.vue"] = replaceExact(files["src/App.vue"]!, 'import { routes } from "./routes";\nexport default { data: () => ({ routes }) };', 'import { routes } from "./routes";\nimport ElmosInteractionPanel from "./ElmosInteractionPanel.vue";\nexport default { components: { ElmosInteractionPanel }, data: () => ({ routes }) };', "src/App.vue");
      files["src/App.vue"] = replaceExact(files["src/App.vue"]!, "</nav><RouterView /></div></template>", "</nav><RouterView /><ElmosInteractionPanel /></div></template>", "src/App.vue");
      break;
    case "vue3":
      files["src/elmos-interaction-runtime.ts"] = blockSpecificBrowserRuntimeModule(profile);
      files["src/ElmosInteractionPanel.vue"] = blockSpecificVue3WebConsumer();
      files["src/views/GeneratedPage.vue"] = replaceExact(files["src/views/GeneratedPage.vue"]!, '<template><main class="content" id="main" :data-route-id="page?.id" :data-route-path="page?.path" :data-requires-auth="page?.requiresAuth" :data-deep-link="page?.deepLink"><article class="card">', `<template><main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" :data-elmos-route-id="page?.id" :data-elmos-route-path="page?.path" :data-elmos-requires-auth="page?.requiresAuth" :data-elmos-deep-link="page?.deepLink" data-elmos-component-id=${JSON.stringify(model.componentTemplate.componentId)} :data-elmos-component-key="page?.id" :data-route-id="page?.id" :data-route-path="page?.path" :data-requires-auth="page?.requiresAuth" :data-deep-link="page?.deepLink"><article class="card">`, "src/views/GeneratedPage.vue");
      files["src/App.vue"] = replaceExact(files["src/App.vue"]!, '<script setup lang="ts">import { routes } from "./routes";</script>', '<script setup lang="ts">import { routes } from "./routes"; import ElmosInteractionPanel from "./ElmosInteractionPanel.vue";</script>', "src/App.vue");
      files["src/App.vue"] = replaceExact(files["src/App.vue"]!, "</nav><RouterView /></div></template>", "</nav><RouterView /><ElmosInteractionPanel /></div></template>", "src/App.vue");
      break;
    case "jquery":
      files["src/elmos-interaction-runtime.ts"] = blockSpecificBrowserRuntimeModule(profile);
      files["src/elmos-interaction-consumer.ts"] = blockSpecificJqueryWebConsumer();
      files["src/elmos-interaction-consumer.ts"] = replaceExact(
        files["src/elmos-interaction-consumer.ts"]!,
        ")); for (const scenario of ELMOS_INTERACTION_SCENARIOS) {",
        ")); const formElement = form.get(0); if (!formElement) throw new Error('ELMOS form was not created'); formElement.addEventListener('invalid', invalidForm, true); form.on('input.elmos', '#elmos-query', syncValidity); for (const scenario of ELMOS_INTERACTION_SCENARIOS) {",
        "src/elmos-interaction-consumer.ts",
      );
      files["src/elmos-interaction-consumer.ts"] = replaceExact(
        files["src/elmos-interaction-consumer.ts"]!,
        "const cleanup = () => { session.dispose(); form.off('.elmos'); form.find('button').off('.elmos'); };",
        "const cleanup = () => { formElement.removeEventListener('invalid', invalidForm, true); session.dispose(); form.off('.elmos'); form.find('button').off('.elmos'); };",
        "src/elmos-interaction-consumer.ts",
      );
      files["src/main.ts"] = replaceExact(files["src/main.ts"]!, '  $("#main").attr({ "data-route-id": route.id, "data-route-path": route.path, "data-requires-auth": String(route.requiresAuth), "data-deep-link": String(route.deepLink) }).empty().append(article);', `  $("#main").attr({ "data-elmos-active-route": "true", "data-elmos-active-component": "true", "data-elmos-route-id": route.id, "data-elmos-route-path": route.path, "data-elmos-requires-auth": String(route.requiresAuth), "data-elmos-deep-link": String(route.deepLink), "data-elmos-component-id": ${JSON.stringify(model.componentTemplate.componentId)}, "data-elmos-component-key": route.id, "data-route-id": route.id, "data-route-path": route.path, "data-requires-auth": String(route.requiresAuth), "data-deep-link": String(route.deepLink) }).empty().append(article);`, "src/main.ts");
      files["src/main.ts"] = replaceExact(files["src/main.ts"]!, 'import { routes } from "./routes";', 'import { routes } from "./routes";\nimport { mountElmosInteraction } from "./elmos-interaction-consumer";', "src/main.ts");
      files["src/main.ts"] = `${files["src/main.ts"]}mountElmosInteraction(document.body);\n`;
      break;
    case "angular":
      files["src/elmos-interaction-runtime.ts"] = blockSpecificBrowserRuntimeModule(profile);
      files["src/elmos-interaction.component.ts"] = blockSpecificAngularWebConsumer();
      files["src/app/generated-page.component.ts"] = replaceExact(files["src/app/generated-page.component.ts"]!, '  template: `<main class="content" id="main" [attr.data-route-id]="id" [attr.data-route-path]="path" [attr.data-requires-auth]="requiresAuth" [attr.data-deep-link]="deepLink"><article class="card"><h1>{{ title }}</h1><p>{{ text }}</p><p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p></article></main>`,', `  template: \`<main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" [attr.data-elmos-route-id]="id" [attr.data-elmos-route-path]="path" [attr.data-elmos-requires-auth]="requiresAuth" [attr.data-elmos-deep-link]="deepLink" data-elmos-component-id=${JSON.stringify(model.componentTemplate.componentId)} [attr.data-elmos-component-key]="id" [attr.data-route-id]="id" [attr.data-route-path]="path" [attr.data-requires-auth]="requiresAuth" [attr.data-deep-link]="deepLink"><article class="card"><h1>{{ title }}</h1><p>{{ text }}</p><p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p></article></main>\`,`, "src/app/generated-page.component.ts");
      files["src/app/app.component.ts"] = replaceExact(files["src/app/app.component.ts"]!, 'import { ELMOS_ROUTES } from "../elmos-bounded-navigation";', 'import { ELMOS_ROUTES } from "../elmos-bounded-navigation";\nimport { ElmosInteractionComponent } from "../elmos-interaction.component";', "src/app/app.component.ts");
      files["src/app/app.component.ts"] = replaceExact(files["src/app/app.component.ts"]!, 'imports: [RouterLink, RouterOutlet],', 'imports: [RouterLink, RouterOutlet, ElmosInteractionComponent],', "src/app/app.component.ts");
      files["src/app/app.component.ts"] = replaceExact(files["src/app/app.component.ts"]!, "</nav><router-outlet /></div>`", "</nav><router-outlet /><elmos-interaction /></div>`", "src/app/app.component.ts");
      break;
    case "svelte":
      files["src/elmos-interaction-runtime.ts"] = blockSpecificBrowserRuntimeModule(profile);
      files["src/ElmosInteractionPanel.svelte"] = blockSpecificSvelteWebConsumer();
      files["src/App.svelte"] = replaceExact(files["src/App.svelte"]!, '<nav class="nav" aria-label="主要导航">', '<nav class="nav" aria-label="主要导航">', "src/App.svelte");
      files["src/App.svelte"] = replaceExact(files["src/App.svelte"]!, '</nav><main class="content" id="main" data-route-id={page?.id} data-route-path={page?.path} data-requires-auth={page?.requiresAuth} data-deep-link={page?.deepLink}><article class="card">', `</nav><main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" data-elmos-route-id={page?.id} data-elmos-route-path={page?.path} data-elmos-requires-auth={page?.requiresAuth} data-elmos-deep-link={page?.deepLink} data-elmos-component-id=${JSON.stringify(model.componentTemplate.componentId)} data-elmos-component-key={page?.id} data-route-id={page?.id} data-route-path={page?.path} data-requires-auth={page?.requiresAuth} data-deep-link={page?.deepLink}><article class="card">`, "src/App.svelte");
      files["src/App.svelte"] = replaceExact(files["src/App.svelte"]!, '  import { routes } from "./routes";', '  import { routes } from "./routes";\n  import ElmosInteractionPanel from "./ElmosInteractionPanel.svelte";', "src/App.svelte");
      files["src/App.svelte"] = replaceExact(files["src/App.svelte"]!, "</article></main></div>", "</article></main><ElmosInteractionPanel /></div>", "src/App.svelte");
      break;
    case "react-native":
      files["src/elmos-interaction-runtime.ts"] = blockSpecificNativeRuntimeModule();
      files["src/elmos-interaction-consumer.tsx"] = blockSpecificNativeReactConsumer();
      files["platform-scaffold-contract.json"] = reactNativePlatformScaffoldContract();
      files["App.tsx"] = replaceExact(files["App.tsx"]!, 'import { GeneratedNavigation } from "./src/navigation";', 'import { GeneratedNavigation } from "./src/navigation";\nimport { ElmosInteractionPanel } from "./src/elmos-interaction-consumer";', "App.tsx");
      files["App.tsx"] = replaceExact(files["App.tsx"]!, "<><GeneratedNavigation /><StatusBar", "<><GeneratedNavigation /><ElmosInteractionPanel /><StatusBar", "App.tsx");
      break;
    case "flutter":
      {
        const nameMatch = /^name:\s*([a-z0-9_]+)$/m.exec(files["pubspec.yaml"]!);
        if (!nameMatch?.[1]) throw new Error("Flutter generated package name is missing");
        Object.assign(files, flutterPlatformScaffold(nameMatch[1]));
        files["pubspec.yaml"] = replaceExact(files["pubspec.yaml"]!, "  flutter_test:\n    sdk: flutter", "  flutter_test:\n    sdk: flutter\n  integration_test:\n    sdk: flutter", "pubspec.yaml");
        files["integration_test/bounded_interaction_test.dart"] = blockSpecificFlutterIntegrationTest(nameMatch[1]);
        files["test_driver/integration_test.dart"] = blockSpecificFlutterIntegrationDriver();
      }
      files["lib/elmos_interaction_runtime.dart"] = blockSpecificDartRuntimeModule();
      files["lib/elmos_interaction_consumer.dart"] = blockSpecificFlutterConsumer();
      files["lib/main.dart"] = replaceExact(files["lib/main.dart"]!, "import 'elmos_bounded_navigation.dart';", "import 'elmos_bounded_navigation.dart';\nimport 'elmos_interaction_consumer.dart';", "lib/main.dart");
      files["lib/main.dart"] = replaceExact(files["lib/main.dart"]!,
        "  const GeneratedApp({super.key});",
        "  const GeneratedApp({this.interactionApiAdapter, this.interactionNativeAdapter, super.key});\n  final ElmosApiAdapter? interactionApiAdapter;\n  final ElmosNativeAdapter? interactionNativeAdapter;",
        "lib/main.dart");
      files["lib/main.dart"] = replaceExact(files["lib/main.dart"]!,
        `    return MaterialApp(title: ${JSON.stringify(model.projectTitle)}, initialRoute: elmosFirstRoute.path,`,
        `    return MaterialApp(title: ${JSON.stringify(model.projectTitle)}, initialRoute: elmosFirstRoute.path,\n      builder: (context, child) => Column(children: [Expanded(child: child ?? const SizedBox.shrink()), SizedBox(height: 240, child: Material(child: ElmosInteractionPanel(apiAdapter: interactionApiAdapter, nativeAdapter: interactionNativeAdapter)))]),`,
        "lib/main.dart");
      break;
    case "harmony-arkui":
      files["entry/src/main/ets/elmos-interaction-runtime.ets"] = blockSpecificArkRuntimeModule();
      files["entry/src/main/ets/pages/Index.ets"] = replaceExact(files["entry/src/main/ets/pages/Index.ets"]!,
        "import { ELMOS_ROUTES, elmosSelectBoundedRoute } from '../elmos-bounded-navigation';",
        "import { ELMOS_ROUTES, elmosSelectBoundedRoute } from '../elmos-bounded-navigation';\nimport { ELMOS_INTERACTION_SCENARIOS } from '../elmos-bounded-interaction';\nimport { elmosArkObserverDeclarations } from '../elmos-interaction-runtime';",
        "entry/src/main/ets/pages/Index.ets");
      files["entry/src/main/ets/pages/Index.ets"] = replaceExact(files["entry/src/main/ets/pages/Index.ets"]!,
        "  @State selected: number = 0;",
        "  @State selected: number = 0;\n  @State interactionDeclarations: string[][] = ELMOS_INTERACTION_SCENARIOS.map(() => []);\n  @State interactionSequences: number[] = ELMOS_INTERACTION_SCENARIOS.map(() => 0);\n  private interactionSequence: number = 0;\n  private dispatchInteraction(index: number): void { this.interactionSequence += 1; this.interactionDeclarations[index] = elmosArkObserverDeclarations(['action-event']).map((declaration: object) => JSON.stringify(declaration)); this.interactionSequences[index] = this.interactionSequence; this.interactionDeclarations = [...this.interactionDeclarations]; this.interactionSequences = [...this.interactionSequences]; }",
        "entry/src/main/ets/pages/Index.ets");
      files["entry/src/main/ets/pages/Index.ets"] = replaceExact(files["entry/src/main/ets/pages/Index.ets"]!,
        "          Text('生成状态：等待 HarmonyOS 真机与无障碍验证').fontColor('#6B4F00')",
        "          Text('生成状态：等待 HarmonyOS 真机与无障碍验证').fontColor('#6B4F00')\n          ForEach(ELMOS_INTERACTION_SCENARIOS, (_scenario: object, index: number) => { Column() { Button(String(index)).accessibilityText('action:' + String(index)).onClick(() => { this.dispatchInteraction(index); }); ForEach(this.interactionDeclarations[index], (declaration: string) => { Text(declaration).accessibilityText('scenario:' + String(index) + ':runtime:BLOCK_SPECIFIC_RUNTIME_OBSERVED:state:PARTIAL:sequence:' + String(this.interactionSequences[index]) + ':declaration:' + declaration) }) } })",
        "entry/src/main/ets/pages/Index.ets");
      break;
  }
  return files;
}

export function boundedInteractionConsumerPaths(profile: UiFrameworkId): readonly string[] {
  switch (profile) {
    case "react": return ["src/App.tsx", "src/elmos-interaction-runtime.ts", "src/ElmosInteractionPanel.tsx"];
    case "vue2": return ["src/App.vue", "src/elmos-interaction-runtime.js", "src/ElmosInteractionPanel.vue"];
    case "vue3": return ["src/App.vue", "src/elmos-interaction-runtime.ts", "src/ElmosInteractionPanel.vue"];
    case "jquery": return ["src/main.ts", "src/elmos-interaction-runtime.ts", "src/elmos-interaction-consumer.ts"];
    case "angular": return ["src/app/app.component.ts", "src/elmos-interaction-runtime.ts", "src/elmos-interaction.component.ts"];
    case "svelte": return ["src/App.svelte", "src/elmos-interaction-runtime.ts", "src/ElmosInteractionPanel.svelte"];
    case "react-native": return ["App.tsx", "src/elmos-interaction-runtime.ts", "src/elmos-interaction-consumer.tsx"];
    case "flutter": return ["lib/main.dart", "lib/elmos_interaction_runtime.dart", "lib/elmos_interaction_consumer.dart"];
    case "harmony-arkui": return ["entry/src/main/ets/pages/Index.ets", "entry/src/main/ets/elmos-interaction-runtime.ets"];
  }
}

export interface GeneratedBoundedInteractionProject extends GeneratedUiProject {
  readonly interactionProofProfile: "bounded-frontend-interaction-v1";
  readonly interactionModelDigest: string;
}

export function generateBoundedInteractionProject(
  requestValue: UiProjectGenerationRequestV2,
): GeneratedBoundedInteractionProject {
  const request = validateUiProjectGenerationRequestV2(requestValue);
  const base = generateUiProject(interactionV2ToV1Request(request));
  const model = canonicalBoundedFrontendInteractionModel(request);
  const generated = augmentBoundedInteractionFiles(request.targetFramework, model, base.files);
  const files = { ...generated };
  const metadata = JSON.parse(files["elmos.ui-migration.json"]!) as Record<string, unknown>;
  const { ["elmos.ui-migration.json"]: _ignored, ...scope } = files;
  files["elmos.ui-migration.json"] = `${JSON.stringify({
    ...metadata,
    schemaVersion: "2.0",
    proofProfile: "bounded-frontend-interaction-v1",
    interactionScenarioCount: boundedInteractionScenarios(model).length,
    interactionBlockIds,
    digestScope: "all generated files except elmos.ui-migration.json",
    contentDigest: digest(scope),
  }, null, 2)}\n`;
  const contentDigest = digest(files);
  return {
    ...base,
    contentDigest,
    files,
    obligations: [
      ...base.obligations,
      "The bounded interaction source interpreter and strict generated grammar are same-producer self-consistency evidence, not an independent runtime oracle.",
      "SSR hydration, real network, tenant authority, browser/device channels, and native platform execution remain NOT_RUN until separately replayed.",
    ],
    interactionProofProfile: "bounded-frontend-interaction-v1",
    interactionModelDigest: digest(model),
  };
}

function binding(id: string, references: readonly string[]): UiInteractionBindingV2 {
  return { id, references, sourceRefs: [`fixtures/bounded-interaction/${id}:1`] };
}

export function boundedInteractionFixtureRequest(target: UiFrameworkId): UiProjectGenerationRequestV2 {
  const source = uiTargetProfiles().find(profile => profile.id !== target);
  if (!source) throw new Error("bounded interaction fixture source is unavailable");
  const routeNode = (id: string, componentId: string, path: string, requiresAuth: boolean, deepLink: boolean) => ({
    id, name: id, kind: "bounded-interaction-route", references: [componentId, "block.identity"],
    sourceRefs: [`fixtures/bounded-interaction/${id}:1`], path, componentId, requiresAuth, deepLink,
  });
  const componentNode = (id: string, name: string, text: string) => ({
    id, name, kind: "bounded-interaction-component", references: ["block.component", "block.a11y", "block.display"],
    sourceRefs: [`fixtures/bounded-interaction/${id}:1`], text, accessibilityRole: "main",
  });
  const draft: UiProjectGenerationRequestV2 = {
    schemaVersion: "2.0",
    projectName: `interaction-${target.replaceAll("-", "")}`,
    applicationId: "elmos.formal.frontendinteraction",
    title: "ELMOS 有界前端交互验证",
    source: { framework: source.id, version: source.frameworkVersion, platform: source.platforms[0]! },
    targetFramework: target,
    packageName: "elmos_formal_frontend_interaction",
    bundleId: "io.elmos.frontendinteraction",
    uiIr: {
      schemaVersion: "2.0",
      profile: "bounded-frontend-interaction-v1",
      sourceSnapshotDigest: `sha256:${"c".repeat(64)}`,
      routes: [
        routeNode("route.home", "component.home", "/", false, true),
        routeNode("route.account", "component.account", "/account", true, true),
        routeNode("route.help", "component.help", "/help", false, false),
      ],
      views: [{ id: "view.shell", name: "shell", kind: "bounded-interaction-view", references: ["block.component"], sourceRefs: ["fixtures/bounded-interaction/view.shell:1"] }],
      components: [
        componentNode("component.home", "首页", "首页内容"),
        componentNode("component.account", "账户", "账户内容"),
        componentNode("component.help", "帮助", "帮助内容"),
      ],
      componentTemplate: { ...binding("block.component", ["route.home", "route.account", "route.help"]), componentId: "interaction.shell", templateKind: "ROUTE_DETAIL_WITH_INTERACTION_MATRIX", keyedBy: "route.id", titleBinding: "route.title", textBinding: "route.text" },
      stateManagement: { ...binding("block.state", ["block.component"]), stateId: "bounded.counter", initial: 0, minimum: 0, maximum: 2, transition: "SATURATING_INCREMENT" },
      actionEvent: { ...binding("block.action", ["block.state", "block.form"]), acceptedEvents: ["BOOT", "NAVIGATE", "AUTHENTICATE", "SUBMIT", "CANCEL", "HYDRATE", "DISPLAY_CHANGE", "NATIVE_DEEPLINK"], deniedAction: "BLOCK", keyboardSubmit: "Enter" },
      effectLifecycle: { ...binding("block.effect", ["block.action", "block.api"]), mountEffect: "LOAD_ON_MOUNT", cleanupEffect: "CANCEL_ON_UNMOUNT", maxExecutionsPerMount: 1, staleResponsePolicy: "IGNORE_AFTER_CANCEL" },
      formBindingValidation: { ...binding("block.form", ["block.a11y"]), formId: "search", fieldId: "query", initialValue: "", required: true, minimumLength: 2, validation: "ON_SUBMIT", invalidCode: "QUERY_TOO_SHORT" },
      apiNetwork: { ...binding("block.api", ["block.form", "block.identity", "block.effect"]), operationId: "search", method: "POST", path: "/api/search", timeoutMs: 1000, retry: "NEVER", cacheScope: "TENANT_QUERY", cancelOnUnmount: true },
      identityPermission: { ...binding("block.identity", ["block.action"]), anonymousRole: "ANONYMOUS", authenticatedRole: "MEMBER", requiredPermission: "search:execute", deniedBehavior: "HIDE_AND_BLOCK", tenantIsolation: "EXACT_TENANT_MATCH", serverAuthorityRequired: true },
      renderingHydration: { ...binding("block.render", ["block.component", "block.effect"]), mode: "HYDRATABLE_CSR", hydrationPolicy: "REQUIRE_MATCH", mismatchBehavior: "RENDER_ERROR", duplicateEffectsAllowed: false },
      accessibilityFocus: { ...binding("block.a11y", ["block.component", "block.form", "block.action"]), navigationLabel: "主要导航", mainRole: "main", headingLevel: 1, formLabel: "搜索", errorRole: "alert", liveRegion: "polite", invalidFocusTarget: "query", keyboardSubmit: "Enter" },
      i18nThemeResponsive: { ...binding("block.display", ["block.component"]), supportedLocales: ["zh-CN", "en-US"], fallbackLocale: "en-US", themes: ["LIGHT", "DARK"], defaultTheme: "LIGHT", compactBreakpoint: 720, compactColumns: 1, wideColumns: 2 },
      nativePlatform: { ...binding("block.native", ["block.identity", "block.effect"]), boundary: "ADAPTER", capability: "OPEN_DEEP_LINK", lifecycleStates: ["FOREGROUND", "BACKGROUND"], permission: "DEEPLINK_OPEN", deniedBehavior: "NO_OP_REPORTED", recovery: "FOREGROUND_RETRY" },
      unknowns: [],
    },
  };
  const fixturePath = `generated-fixtures/${target}/typed-ui-interaction-ir.json`;
  const initialBytes = boundedInteractionSourceFixtureBytes(draft);
  const sourceRefsFor = (id: string): readonly string[] => {
    const marker = `"id": ${JSON.stringify(id)}`;
    const offset = initialBytes.indexOf(marker);
    if (offset < 0) throw new Error(`generated fixture source span is missing: ${id}`);
    return [`${fixturePath}:${initialBytes.slice(0, offset).split("\n").length}`];
  };
  const rebind = <T extends { readonly id: string; readonly sourceRefs: readonly string[] }>(value: T): T => ({ ...value, sourceRefs: sourceRefsFor(value.id) });
  const rebound: UiProjectGenerationRequestV2 = {
    ...draft,
    uiIr: {
      ...draft.uiIr,
      routes: draft.uiIr.routes.map(rebind), views: draft.uiIr.views.map(rebind), components: draft.uiIr.components.map(rebind),
      componentTemplate: rebind(draft.uiIr.componentTemplate), stateManagement: rebind(draft.uiIr.stateManagement),
      actionEvent: rebind(draft.uiIr.actionEvent), effectLifecycle: rebind(draft.uiIr.effectLifecycle),
      formBindingValidation: rebind(draft.uiIr.formBindingValidation), apiNetwork: rebind(draft.uiIr.apiNetwork),
      identityPermission: rebind(draft.uiIr.identityPermission), renderingHydration: rebind(draft.uiIr.renderingHydration),
      accessibilityFocus: rebind(draft.uiIr.accessibilityFocus), i18nThemeResponsive: rebind(draft.uiIr.i18nThemeResponsive),
      nativePlatform: rebind(draft.uiIr.nativePlatform),
    },
  };
  const sourceSnapshotDigest = `sha256:${createHash("sha256").update(boundedInteractionSourceFixtureBytes(rebound), "utf8").digest("hex")}`;
  return { ...rebound, uiIr: { ...rebound.uiIr, sourceSnapshotDigest } };
}

export function boundedInteractionSourceFixtureArtifact(request: UiProjectGenerationRequestV2): Readonly<Record<string, unknown>> {
  const { sourceSnapshotDigest: _excluded, ...uiIr } = request.uiIr;
  return {
    schema_version: "1.0",
    kind: "bounded-frontend-interaction-generated-source-fixture",
    source_kind: "GENERATED_FIXTURE",
    proof_profile: "bounded-frontend-interaction-v1",
    target_profile: request.targetFramework,
    ui_ir: uiIr,
    arbitrary_customer_source: "NOT_PROVED",
    external_source_evidence: "NOT_RUN",
  };
}

export function boundedInteractionSourceFixtureBytes(request: UiProjectGenerationRequestV2): string {
  return `${JSON.stringify(boundedInteractionSourceFixtureArtifact(request), null, 2)}\n`;
}

export function requiredRuntimeChannels(profile: UiFrameworkId): readonly ("browser" | "android" | "ios" | "harmonyos")[] {
  if (profile === "react-native" || profile === "flutter") return ["browser", "android", "ios"];
  if (profile === "harmony-arkui") return ["harmonyos"];
  return ["browser"];
}

export function interactionTargetProfile(profile: UiFrameworkId) {
  return uiTargetProfile(profile);
}
