#!/usr/bin/env node
"use strict";

// This helper is intentionally repository-owned and content-addressed by
// run_frontend_formal_toolchains.py. It extracts actual browser observations;
// expected semantic block values are never accepted in its input protocol.

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const SHA256 = /^sha256:[0-9a-f]{64}$/;
const BLOCK_IDS = [
  "route-navigation-deeplink-404",
  "component-template-view",
  "state-management",
  "action-event",
  "effect-lifecycle",
  "form-binding-validation",
  "api-network",
  "identity-permission",
  "rendering-hydration",
  "accessibility-focus",
  "i18n-theme-responsive",
  "native-platform",
];
const OBSERVER_CONTRACT = "block-specific-runtime-observation-v1";
const PARTIAL_REASON = "BLOCK_SPECIFIC_RUNTIME_PARTIAL_CLOSURE";
const ROOT_SELECTOR = '#elmos-interaction[data-proof-profile="bounded-frontend-interaction-v1"][data-elmos-ready="true"][data-observer-protocol="block-specific-runtime-observation-v1"]';
const WEB_REQUIRED_NOT_RUN_BLOCKS = new Set([
  "effect-lifecycle",
  "api-network",
  "identity-permission",
  "rendering-hydration",
  "native-platform",
]);
const OBSERVER_SPECS = {
  "route-navigation-deeplink-404": {
    observer_kind: "ROUTER_DOM_URL_OBSERVER",
    measurement_surface: "page.url+[data-elmos-active-route] attrs",
  },
  "component-template-view": {
    observer_kind: "RENDERED_COMPONENT_DOM_OBSERVER",
    measurement_surface: "active route heading/text/visibility attrs",
  },
  "state-management": {
    observer_kind: "FRAMEWORK_STATE_TRANSITION_OBSERVER",
    measurement_surface: "[data-elmos-state-measurement] before/after/saturated",
  },
  "action-event": {
    observer_kind: "NATIVE_EVENT_OUTCOME_OBSERVER",
    measurement_surface: "captured click/keydown/submit + [data-elmos-action-outcome]",
  },
  "effect-lifecycle": {
    observer_kind: "FRAMEWORK_LIFECYCLE_TRACE_OBSERVER",
    measurement_surface: "ordered [data-elmos-lifecycle-event]",
  },
  "form-binding-validation": {
    observer_kind: "FORM_CONTROL_VALIDITY_OBSERVER",
    measurement_surface: "control value+ValidityState+error DOM+focus",
  },
  "api-network": {
    observer_kind: "BROWSER_NETWORK_OBSERVER",
    measurement_surface: "Playwright request/response/requestfailed + app abort/stale marker",
  },
  "identity-permission": {
    observer_kind: "AUTHORITY_ADAPTER_OBSERVER",
    measurement_surface: "[data-elmos-auth-decision] only if real adapter trace",
  },
  "rendering-hydration": {
    observer_kind: "SSR_HYDRATION_OBSERVER",
    measurement_surface: "server markup digest+hydration warnings/mutations/effect count",
  },
  "accessibility-focus": {
    observer_kind: "ACCESSIBILITY_TREE_FOCUS_OBSERVER",
    measurement_surface: "aria snapshot+axe+active element+keyboard",
  },
  "i18n-theme-responsive": {
    observer_kind: "COMPUTED_LAYOUT_I18N_THEME_OBSERVER",
    measurement_surface: "html lang+rendered translated text+computed theme tokens+measured layout",
  },
  "native-platform": {
    observer_kind: "NATIVE_ADAPTER_DEVICE_OBSERVER",
    measurement_surface: "native semantics+lifecycle+permission+adapter trace",
  },
};

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function digestBytes(value) {
  return `sha256:${crypto.createHash("sha256").update(value).digest("hex")}`;
}

function digestJson(value) {
  return digestBytes(Buffer.from(canonical(value), "utf8"));
}

function exactKeys(value, keys, name) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (canonical(actual) !== canonical(expected)) {
    throw new Error(`${name} keys drifted: ${canonical(actual)}`);
  }
  return value;
}

function readConfig(configPath) {
  const config = exactKeys(
    JSON.parse(fs.readFileSync(configPath, "utf8")),
    [
      "schema_version",
      "kind",
      "profile_id",
      "project_digest",
      "proof_profile",
      "base_url",
      "scenario_manifest",
      "semantic_block_ids",
      "block_observer_contracts",
      "playwright_package_root",
      "axe_package_root",
      "browsers",
      "timeout_ms",
    ],
    "probe config",
  );
  if (
    config.schema_version !== "1.0" ||
    config.kind !== "frontend-interaction-playwright-probe-config" ||
    config.proof_profile !== "bounded-frontend-interaction-v1" ||
    !SHA256.test(config.project_digest) ||
    !Number.isInteger(config.timeout_ms) ||
    config.timeout_ms < 1 ||
    canonical(config.semantic_block_ids) !== canonical(BLOCK_IDS)
  ) {
    throw new Error("probe config identity is invalid");
  }
  if (!Array.isArray(config.scenario_manifest) || config.scenario_manifest.length !== 18) {
    throw new Error("scenario manifest must contain the exact 18 locked scenarios");
  }
  const seen = new Set();
  for (const [index, raw] of config.scenario_manifest.entries()) {
    const scenario = exactKeys(raw, ["scenario_id", "input"], `scenario_manifest[${index}]`);
    if (typeof scenario.scenario_id !== "string" || scenario.scenario_id.length === 0 || seen.has(scenario.scenario_id)) {
      throw new Error(`scenario_manifest[${index}].scenario_id is invalid or duplicate`);
    }
    if (scenario.input === null || typeof scenario.input !== "object" || Array.isArray(scenario.input)) {
      throw new Error(`scenario_manifest[${index}].input is invalid`);
    }
    seen.add(scenario.scenario_id);
  }
  const contractIds = Object.keys(config.block_observer_contracts || {});
  if (canonical([...contractIds].sort()) !== canonical([...BLOCK_IDS].sort())) {
    throw new Error("block observer contract closure drifted");
  }
  const browserNotRun = [];
  const nativeNotRun = [];
  for (const blockId of BLOCK_IDS) {
    const row = exactKeys(
      config.block_observer_contracts[blockId],
      ["observer_kind", "measurement_surface", "browser_status", "browser_reason", "native_status", "native_reason"],
      `${blockId} block observer contract`,
    );
    const spec = OBSERVER_SPECS[blockId];
    if (
      row.observer_kind !== spec.observer_kind ||
      row.measurement_surface !== spec.measurement_surface ||
      !["PASSED", "NOT_RUN"].includes(row.browser_status) ||
      !["PASSED", "NOT_RUN"].includes(row.native_status) ||
      typeof row.browser_reason !== "string" || row.browser_reason.length === 0 ||
      typeof row.native_reason !== "string" || row.native_reason.length === 0
    ) {
      throw new Error(`${blockId} block observer contract drifted`);
    }
    if (row.browser_status === "NOT_RUN") browserNotRun.push(blockId);
    if (row.native_status === "NOT_RUN") nativeNotRun.push(blockId);
  }
  if (
    canonical(browserNotRun) !== canonical([...WEB_REQUIRED_NOT_RUN_BLOCKS]) ||
    canonical(nativeNotRun) !== canonical(["api-network"]) ||
    config.block_observer_contracts["api-network"].native_reason !==
      "a single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation"
  ) {
    throw new Error("browser/native block observer ceiling drifted");
  }
  if (!Array.isArray(config.browsers) || config.browsers.length !== 2) {
    throw new Error("browser matrix must contain exact Chromium and Firefox rows");
  }
  for (const [index, raw] of config.browsers.entries()) {
    const browser = exactKeys(
      raw,
      ["browser_id", "engine", "executable_path", "executable_sha256", "executable_byte_count"],
      `browsers[${index}]`,
    );
    if (
      !["chromium", "firefox"].includes(browser.engine) ||
      typeof browser.browser_id !== "string" ||
      !path.isAbsolute(browser.executable_path) ||
      !SHA256.test(browser.executable_sha256) ||
      !Number.isInteger(browser.executable_byte_count) ||
      browser.executable_byte_count < 1
    ) {
      throw new Error(`browsers[${index}] identity is invalid`);
    }
  }
  if (
    canonical(config.browsers.map(row => [row.browser_id, row.engine])) !==
    canonical([["google-chrome", "chromium"], ["mozilla-firefox", "firefox"]])
  ) {
    throw new Error("browser matrix identity/order drifted");
  }
  return config;
}

function targetDescription(value) {
  if (!value || typeof value !== "object") return null;
  const attributes = {};
  for (const name of [
    "id",
    "name",
    "role",
    "type",
    "data-elmos-control",
    "data-elmos-event",
    "data-field-id",
    "data-run-scenario",
  ]) {
    const attribute = value.getAttribute && value.getAttribute(name);
    if (attribute !== null && attribute !== undefined) attributes[name] = attribute;
  }
  return {
    tag: value.tagName ? value.tagName.toLowerCase() : null,
    attributes,
    value: "value" in value && typeof value.value === "string" ? value.value : null,
  };
}

async function installActualEventCapture(context) {
  await context.addInitScript(() => {
    const events = [];
    Object.defineProperty(window, "__ELMOS_ACTUAL_BROWSER_EVENTS__", {
      value: events,
      configurable: false,
      enumerable: false,
      writable: false,
    });
    const describe = target => {
      if (!target || typeof target !== "object") return null;
      const attributes = {};
      for (const name of ["id", "name", "role", "type", "data-elmos-control", "data-elmos-event", "data-field-id", "data-run-scenario"]) {
        const attribute = target.getAttribute && target.getAttribute(name);
        if (attribute !== null && attribute !== undefined) attributes[name] = attribute;
      }
      return {
        tag: target.tagName ? target.tagName.toLowerCase() : null,
        attributes,
        value: "value" in target && typeof target.value === "string" ? target.value : null,
      };
    };
    for (const type of ["click", "input", "change", "invalid", "submit", "keydown", "focusin", "popstate", "hashchange"]) {
      addEventListener(type, event => {
        events.push({
          type,
          key: typeof event.key === "string" ? event.key : null,
          target: describe(event.target),
          defaultPrevented: event.defaultPrevented,
          timestamp: Date.now(),
        });
      }, true);
    }
  });
}

function eventAdequacy(input, events, network, activeElement, ariaSnapshot, axeResults) {
  const types = new Set(events.map(item => item.type));
  const checks = {
    framework_click_observed: types.has("click"),
    accessibility_tree_observed: typeof ariaSnapshot === "string" && ariaSnapshot.trim().length > 0,
    focus_observed: activeElement !== null && activeElement.tag !== null,
    axe_executed: axeResults !== null,
    axe_no_serious_or_critical: axeResults !== null && !axeResults.violations.some(
      violation => violation.impact === "serious" || violation.impact === "critical",
    ),
  };
  if (input.keyboardKey === "Enter") {
    checks.keyboard_trigger_observed = events.some(item =>
      item.type === "keydown" && item.key === "Enter" && item.target &&
      item.target.attributes && typeof item.target.attributes["data-run-scenario"] === "string"
    );
  }
  if (input.event === "SUBMIT") {
    checks.form_input_event_observed = types.has("input") || types.has("change");
    checks.form_constraint_outcome_observed = types.has("submit") || types.has("invalid");
  }
  if (input.event === "CANCEL") {
    checks.cancel_event_observed = events.some(item => item.target && item.target.attributes["data-elmos-event"] === "CANCEL");
  }
  if (input.event === "DISPLAY_CHANGE") {
    checks.display_control_event_observed = types.has("change") || types.has("input");
  }
  return checks;
}

function formSubmissionAttemptObserved(events, scenarioId, associatedForm) {
  return associatedForm === true && Array.isArray(events) &&
    typeof scenarioId === "string" && events.some(event => {
    const target = event && event.target;
    const attributes = target && target.attributes;
    if (!attributes || typeof attributes !== "object") return false;
    if (event.type === "submit") {
      return target.tag === "form" && attributes["data-elmos-control"] === "form";
    }
    if (
      !["button", "input"].includes(target.tag) ||
      attributes["data-run-scenario"] !== scenarioId ||
      attributes.type !== "submit"
    ) {
      return false;
    }
    if (event.type === "click") return true;
    return event.type === "keydown" && ["Enter", " ", "Spacebar"].includes(event.key);
    });
}

async function exactAttributes(locator, names, name) {
  if (await locator.count() !== 1) throw new Error(`${name} is absent or duplicated`);
  const attributes = {};
  for (const attributeName of names) {
    const value = await locator.getAttribute(attributeName);
    if (value === null) throw new Error(`${name}.${attributeName} is absent`);
    attributes[attributeName] = value;
  }
  return attributes;
}

async function validateExactRootAndRows(page, config) {
  const root = page.locator(ROOT_SELECTOR);
  if (await root.count() !== 1) throw new Error("exact ready observer root is absent or duplicated");
  const allRows = page.locator("[data-scenario-id]");
  if (await allRows.count() !== config.scenario_manifest.length) {
    throw new Error("global scenario row closure contains missing or extra rows");
  }
  const rowIds = await allRows.evaluateAll(rows => rows.map(row => row.getAttribute("data-scenario-id")));
  const expectedIds = config.scenario_manifest.map(item => item.scenario_id);
  if (canonical(rowIds) !== canonical(expectedIds)) throw new Error("global scenario row order/identity drifted");
  for (const scenarioId of expectedIds) {
    const row = root.locator(`[data-scenario-id=${JSON.stringify(scenarioId)}]`);
    if (await row.count() !== 1 || await row.locator("[data-run-scenario]").count() !== 1) {
      throw new Error(`${scenarioId} row/action closure drifted`);
    }
  }
  return root;
}

async function applyScenarioControls(page, input) {
  const fillIfPresent = async (selector, value) => {
    const locator = page.locator(selector);
    if (await locator.count() === 1 && typeof value === "string") await locator.fill(value);
  };
  await fillIfPresent("#elmos-query", input.query);
  await fillIfPresent("#elmos-tenant", input.tenantId);
  await fillIfPresent("#elmos-resource-tenant", input.resourceTenantId);
  for (const [selector, value] of [["#elmos-locale", input.locale], ["#elmos-theme", input.theme]]) {
    const locator = page.locator(selector);
    if (await locator.count() === 1 && typeof value === "string") {
      const optionCount = await locator.locator(`option[value=${JSON.stringify(value)}]`).count();
      if (optionCount !== 1) throw new Error(`${selector} lacks exact scenario option ${value}`);
      await locator.selectOption(value);
    }
  }
  for (const [selector, value] of [["#elmos-authenticated", input.authenticated], ["#elmos-permission", input.permissionGranted]]) {
    const locator = page.locator(selector);
    if (await locator.count() === 1 && typeof value === "boolean") await locator.setChecked(value);
  }
}

async function readObserverDeclarations(row, expectedContracts) {
  const nodes = row.locator("[data-semantic-block]");
  if (await nodes.count() !== BLOCK_IDS.length) throw new Error("semantic observer declaration closure drifted");
  const declarations = {};
  const order = [];
  for (let index = 0; index < BLOCK_IDS.length; index += 1) {
    const node = nodes.nth(index);
    const blockId = await node.getAttribute("data-semantic-block");
    if (!BLOCK_IDS.includes(blockId) || Object.hasOwn(declarations, blockId)) {
      throw new Error("unknown or duplicate semantic observer declaration");
    }
    order.push(blockId);
    const spec = OBSERVER_SPECS[blockId];
    const expected = expectedContracts[blockId];
    const declaration = exactKeys(
      JSON.parse((await node.textContent()) || ""),
      ["schema_version", "kind", "block_id", "status", "observer_kind", "measurement_surface", "reason"],
      `${blockId} observer declaration`,
    );
    const attributes = await exactAttributes(
      node,
      ["data-observer-kind", "data-observation-status", "data-measurement-surface", "data-model-values-used"],
      `${blockId} observer declaration attributes`,
    );
    if (
      declaration.schema_version !== "1.0" ||
      declaration.kind !== "frontend-block-observer-declaration" ||
      declaration.block_id !== blockId ||
      !["PASSED", "NOT_RUN"].includes(declaration.status) ||
      declaration.observer_kind !== spec.observer_kind ||
      declaration.measurement_surface !== spec.measurement_surface ||
      declaration.status !== expected.browser_status ||
      declaration.reason !== expected.browser_reason ||
      typeof declaration.reason !== "string" || declaration.reason.length === 0 ||
      attributes["data-observer-kind"] !== spec.observer_kind ||
      attributes["data-observation-status"] !== declaration.status ||
      attributes["data-measurement-surface"] !== spec.measurement_surface ||
      attributes["data-model-values-used"] !== "false" ||
      (WEB_REQUIRED_NOT_RUN_BLOCKS.has(blockId) && declaration.status !== "NOT_RUN")
    ) {
      throw new Error(`${blockId} observer declaration identity/status drifted`);
    }
    declarations[blockId] = declaration;
  }
  if (canonical(order) !== canonical(BLOCK_IDS)) throw new Error("semantic observer declaration order drifted");
  return declarations;
}

async function captureBlockMeasurement({blockId, page, root, row, scenario, eventLog, network, ariaSnapshot, axeResults, activeElement}) {
  if (blockId === "route-navigation-deeplink-404") {
    const active = page.locator('#main[data-elmos-active-route="true"]');
    const declared = page.locator("nav [data-route-id]");
    const declared_routes = [];
    for (let index = 0; index < await declared.count(); index += 1) {
      const route = declared.nth(index);
      const attributes = await exactAttributes(
        route,
        ["data-route-id", "data-requires-auth", "data-deep-link"],
        `declared route ${index}`,
      );
      const href = await route.getAttribute("href");
      if (href === null) throw new Error(`declared route ${index}.href is absent`);
      declared_routes.push({
        route_id: attributes["data-route-id"],
        route_path: new URL(href, page.url()).pathname,
        requires_auth: attributes["data-requires-auth"] === "true",
        deep_link: attributes["data-deep-link"] === "true",
      });
    }
    if (declared_routes.length === 0) throw new Error("declared route DOM is empty");
    return {
      page_url: page.url(),
      active_route_attributes: await exactAttributes(active, [
        "data-route-id", "data-route-path", "data-deep-link", "data-requires-auth",
      ], "active route"),
      declared_routes,
    };
  }
  if (blockId === "component-template-view") {
    const active = page.locator('#main[data-elmos-active-route="true"]');
    const heading = active.locator("article.card > h1");
    const text = active.locator("article.card > p:not(.status)");
    if (await heading.count() !== 1 || await text.count() !== 1) throw new Error("active component heading/text surface is incomplete");
    return {
      heading: (await heading.textContent()) || "",
      text: (await text.textContent()) || "",
      visibility: await active.isVisible(),
      attributes: await exactAttributes(active, [
        "id", "data-route-id", "data-elmos-active-component",
        "data-elmos-component-id", "data-elmos-component-key",
      ], "active component"),
    };
  }
  if (blockId === "state-management") {
    return {state_measurement: await exactAttributes(row.locator("[data-elmos-state-measurement]"), [
      "data-elmos-state-id", "data-elmos-before", "data-elmos-after", "data-elmos-saturated",
    ], "state measurement")};
  }
  if (blockId === "action-event") {
    return {
      captured_events: eventLog.filter(event => ["click", "keydown", "submit"].includes(event.type)),
      outcome_attributes: await exactAttributes(row.locator("[data-elmos-action-outcome]"), [
        "data-elmos-event-outcome", "data-elmos-keyboard-key", "data-elmos-handled", "data-elmos-action",
      ], "action outcome"),
    };
  }
  if (blockId === "effect-lifecycle") {
    const nodes = row.locator("[data-elmos-lifecycle-event]");
    const ordered_events = [];
    for (let index = 0; index < await nodes.count(); index += 1) {
      const attributes = await exactAttributes(nodes.nth(index), [
        "data-elmos-lifecycle", "data-elmos-effect", "data-elmos-executions",
        "data-elmos-cleanup", "data-elmos-stale-response-ignored",
      ], `lifecycle event ${index}`);
      ordered_events.push({
        lifecycle: attributes["data-elmos-lifecycle"], effect: attributes["data-elmos-effect"],
        executions: attributes["data-elmos-executions"], cleanup: attributes["data-elmos-cleanup"],
        stale_response_ignored: attributes["data-elmos-stale-response-ignored"],
      });
    }
    if (ordered_events.length === 0) throw new Error("lifecycle trace is empty");
    return {ordered_events};
  }
  if (blockId === "form-binding-validation") {
    const query = page.locator("#elmos-query");
    if (await query.count() !== 1) throw new Error("live form control is absent or duplicated");
    const controlSurface = await query.evaluate(control => ({
      associated_form: Boolean(
        control.form &&
        control.form.tagName.toLowerCase() === "form" &&
        control.form.getAttribute("data-elmos-control") === "form"
      ),
      field_binding: control.getAttribute("data-field-id"),
      value: control.value,
      valid: control.validity.valid,
    }));
    if (typeof controlSurface.field_binding !== "string" || !/^[^.]+\.[^.]+$/.test(controlSurface.field_binding)) {
      throw new Error("live form control field binding is invalid");
    }
    const [formId, fieldId] = controlSurface.field_binding.split(".");
    const error = row.locator('[data-elmos-form-error="true"]');
    if (await error.count() > 1) throw new Error("form error DOM is duplicated");
    let errorCode = null;
    if (await error.count() === 1) {
      if (await error.getAttribute("role") !== "alert") throw new Error("form error DOM lacks alert role");
      errorCode = ((await error.textContent()) || "").trim();
      if (errorCode.length === 0) throw new Error("form error DOM is empty");
    }
    const focusTarget = activeElement && activeElement.attributes
      ? activeElement.attributes.id === "elmos-query" ? "query"
        : activeElement.attributes.id === "elmos-result" ? "result" : null
      : null;
    return {
      control: {form_id: formId, field_id: fieldId, value: controlSurface.value},
      validity_state: {
        submitted: formSubmissionAttemptObserved(
          eventLog, scenario.scenario_id, controlSurface.associated_form
        ),
        valid: controlSurface.valid,
      },
      error_dom: {error_code: errorCode},
      active_element: {focus_target: focusTarget},
    };
  }
  if (blockId === "api-network") {
    throw new Error("bounded browser network diagnostic does not prove the complete API contract");
  }
  if (blockId === "identity-permission") {
    throw new Error("browser authority adapter observer is NOT_RUN");
  }
  if (blockId === "rendering-hydration") {
    throw new Error("client-rendered browser hydration observer is NOT_RUN");
  }
  if (blockId === "accessibility-focus") {
    if (typeof ariaSnapshot !== "string" || ariaSnapshot.trim().length === 0) {
      throw new Error("accessibility tree snapshot is absent");
    }
    if (axeResults === null || typeof axeResults !== "object" || !Array.isArray(axeResults.violations)) {
      throw new Error("axe result is absent or invalid");
    }
    const main = page.locator('#main[data-elmos-active-route="true"]');
    const heading = main.locator("article.card > h1");
    const form = root.locator('form[data-elmos-control="form"]');
    const output = root.locator('output#elmos-result[data-elmos-result="true"]');
    if (await main.count() !== 1 || await heading.count() !== 1 || await form.count() !== 1 || await output.count() !== 1) {
      throw new Error("actual accessibility DOM surface is absent or duplicated");
    }
    const mainRole = await main.evaluate(element => element.getAttribute("role") || (element.tagName === "MAIN" ? "main" : ""));
    const headingLevel = await heading.evaluate(element => {
      const match = /^H([1-6])$/.exec(element.tagName);
      return match ? Number(match[1]) : 0;
    });
    const formLabel = (await form.getAttribute("aria-label")) || "";
    const liveRegion = (await output.getAttribute("aria-live")) || "";
    if (!mainRole || headingLevel === 0 || !formLabel || !["off", "polite", "assertive"].includes(liveRegion)) {
      throw new Error("actual accessibility DOM semantics are incomplete");
    }
    const errors = row.locator('[data-elmos-form-error="true"]');
    if (await errors.count() > 1) throw new Error("accessibility error role surface is duplicated");
    const errorRole = await errors.count() === 1 ? await errors.getAttribute("role") : null;
    if (errorRole !== null && errorRole !== "alert") throw new Error("actual form error role is invalid");
    const focusTarget = activeElement && activeElement.attributes
      ? activeElement.attributes.id === "elmos-query" ? "query"
        : activeElement.attributes.id === "elmos-result" ? "result" : null
      : null;
    const keyboardEvents = eventLog.filter(event => event.type === "keydown");
    const keyboardSubmit = keyboardEvents.some(event =>
      event.key === "Enter" && event.target && event.target.attributes &&
      event.target.attributes["data-run-scenario"] === scenario.scenario_id
    );
    const roleSnapshot = ariaSnapshot.toLowerCase();
    if (!roleSnapshot.includes("main") || !roleSnapshot.includes("heading")) {
      throw new Error("accessibility tree does not contain the actual main/heading surface");
    }
    return {
      aria_snapshot: ariaSnapshot,
      axe_results: axeResults,
      active_element: activeElement,
      keyboard_events: keyboardEvents,
      accessibility_state: {
        main_role: mainRole, heading_level: headingLevel,
        form_label: formLabel, error_role: errorRole,
        live_region: liveRegion, focus_target: focusTarget,
        keyboard_submit: keyboardSubmit,
      },
    };
  }
  if (blockId === "i18n-theme-responsive") {
    const marker = row.locator("[data-elmos-i18n-measurement]");
    if (await marker.count() !== 1) throw new Error("rendered translated text surface is absent or duplicated");
    const rect = await marker.boundingBox();
    if (rect === null) throw new Error("i18n/theme/layout measurement is not rendered");
    const computed = await marker.evaluate(element => {
      const rootStyle = getComputedStyle(document.documentElement);
      const elementStyle = getComputedStyle(element);
      const rawGrid = elementStyle.gridTemplateColumns.trim();
      const tracks = rawGrid === "none" || rawGrid === "" ? [] : rawGrid.split(/\s+/);
      return {
        theme: rootStyle.getPropertyValue("--elmos-theme").trim(),
        grid_template_columns: rawGrid,
        columns: tracks.length,
        window_inner_width: window.innerWidth,
      };
    });
    if (!computed.theme || computed.columns < 1 || computed.grid_template_columns === "none") {
      throw new Error("computed theme/grid surface is incomplete");
    }
    const viewport = page.viewportSize();
    if (viewport === null || viewport.width !== computed.window_inner_width) {
      throw new Error("browser viewport and rendered layout width drifted");
    }
    const text = ((await marker.textContent()) || "").trim();
    if (!text) throw new Error("rendered translated text is empty");
    return {
      html_lang: await page.locator("html").getAttribute("lang"),
      translated_text: {requested_locale: scenario.input.locale, text},
      computed_theme_tokens: {requested_theme: scenario.input.theme, theme: computed.theme},
      layout_measurement: {
        viewport_width: viewport.width,
        columns: computed.columns,
        computed_grid_template_columns: computed.grid_template_columns,
        bounding_box: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      },
    };
  }
  if (blockId === "native-platform") throw new Error("browser native adapter/device observer is NOT_RUN");
  throw new Error(`unsupported block observer: ${blockId}`);
}

async function runScenario(page, AxeBuilder, config, scenario) {
  const network = [];
  const consoleEvents = [];
  const pageErrors = [];
  const requestListener = request => network.push({
    kind: "request",
    method: request.method(),
    url: request.url(),
    post_data: request.postData(),
    resource_type: request.resourceType(),
  });
  const responseListener = response => network.push({
    kind: "response",
    method: response.request().method(),
    url: response.url(),
    status: response.status(),
  });
  const failedListener = request => network.push({
    kind: "requestfailed",
    method: request.method(),
    url: request.url(),
    failure: request.failure(),
  });
  const consoleListener = message => consoleEvents.push({type: message.type(), text: message.text()});
  const errorListener = error => pageErrors.push({name: error.name, message: error.message});
  page.on("request", requestListener);
  page.on("response", responseListener);
  page.on("requestfailed", failedListener);
  page.on("console", consoleListener);
  page.on("pageerror", errorListener);

  try {
    if (Number.isInteger(scenario.input.viewportWidth) && scenario.input.viewportWidth > 0) {
      await page.setViewportSize({width: scenario.input.viewportWidth, height: 900});
    }
    await page.goto(config.base_url, {waitUntil: "networkidle", timeout: config.timeout_ms});
    const root = await validateExactRootAndRows(page, config);
    const row = root.locator(`[data-scenario-id=${JSON.stringify(scenario.scenario_id)}]`);
    const trigger = row.locator("[data-run-scenario]");
    await applyScenarioControls(page, scenario.input);
    const beforeSequence = await row.getAttribute("data-execution-sequence");
    if (!/^(?:0|[1-9][0-9]*)$/.test(beforeSequence || "")) throw new Error("scenario sequence is not an integer");
    if (scenario.input.keyboardKey === "Enter") {
      await trigger.focus();
      await page.keyboard.press("Enter");
    } else {
      await trigger.click();
    }
    await page.waitForFunction(
      ({scenarioId, previous}) => {
        const candidate = document.querySelector(`#elmos-interaction [data-scenario-id=${JSON.stringify(scenarioId)}]`);
        const sequence = candidate && candidate.getAttribute("data-execution-sequence");
        return candidate !== null &&
          candidate.getAttribute("data-runtime-source") === "BLOCK_SPECIFIC_RUNTIME_OBSERVED" &&
          ["COMPLETE", "PARTIAL"].includes(candidate.getAttribute("data-execution-state")) &&
          /^(?:0|[1-9][0-9]*)$/.test(sequence || "") && Number(sequence) > Number(previous);
      },
      {scenarioId: scenario.scenario_id, previous: beforeSequence},
      {timeout: config.timeout_ms},
    );
    const declarations = await readObserverDeclarations(row, config.block_observer_contracts);
    const eventLog = await page.evaluate(() => window.__ELMOS_ACTUAL_BROWSER_EVENTS__ || []);
    const activeElement = await page.evaluate(() => {
      const value = document.activeElement;
      if (!value) return null;
      const attributes = {};
      for (const name of ["id", "name", "role", "type", "data-elmos-control", "data-field-id"]) {
        const attribute = value.getAttribute && value.getAttribute(name);
        if (attribute !== null && attribute !== undefined) attributes[name] = attribute;
      }
      return {tag: value.tagName ? value.tagName.toLowerCase() : null, attributes};
    });
    let ariaSnapshot = null;
    let ariaError = null;
    try {
      ariaSnapshot = await page.locator("body").ariaSnapshot({timeout: config.timeout_ms});
    } catch (error) {
      ariaError = String(error);
    }
    let axeResults = null;
    let axeError = null;
    try {
      axeResults = await new AxeBuilder({page}).analyze();
    } catch (error) {
      axeError = String(error);
    }
    const html = await page.locator("body").evaluate(element => element.outerHTML);
    const actualRuntimeMetadata = await row.evaluate(element => ({
      execution_state: element.getAttribute("data-execution-state"),
      execution_sequence: element.getAttribute("data-execution-sequence"),
      runtime_source: element.getAttribute("data-runtime-source"),
    }));
    const unexpectedConsoleErrors = consoleEvents.filter(event => {
      if (event.type !== "error") return false;
      return !(
        scenario.input.networkResult === "ERROR" &&
        /(?:500|failed to load resource)/i.test(event.text)
      );
    });
    const blocks = {};
    const captureErrors = [];
    for (const blockId of BLOCK_IDS) {
      const declaration = declarations[blockId];
      if (declaration.status === "NOT_RUN") {
        blocks[blockId] = {
          status: "NOT_RUN",
          actual_source: "NOT_RUN",
          observer_kind: declaration.observer_kind,
          measurement_surface: declaration.measurement_surface,
          measurement: null,
          measurement_digest: null,
          model_values_used_as_actual: false,
          reason: declaration.reason,
        };
        continue;
      }
      try {
        const measurement = await captureBlockMeasurement({
          blockId, page, root, row, scenario, eventLog, network, ariaSnapshot,
          axeResults, activeElement,
        });
        blocks[blockId] = {
          status: "PASSED",
          actual_source: "BLOCK_SPECIFIC_RUNTIME_OBSERVED",
          observer_kind: declaration.observer_kind,
          measurement_surface: declaration.measurement_surface,
          measurement,
          measurement_digest: digestJson(measurement),
          model_values_used_as_actual: false,
          reason: null,
        };
      } catch (error) {
        captureErrors.push({block_id: blockId, error: String(error)});
        blocks[blockId] = {
          status: "FAILED",
          actual_source: "NOT_RUN",
          observer_kind: declaration.observer_kind,
          measurement_surface: declaration.measurement_surface,
          measurement: null,
          measurement_digest: null,
          model_values_used_as_actual: false,
          reason: String(error),
        };
      }
    }
    const partial = Object.values(blocks).some(block => block.status === "NOT_RUN");
    const failed = Object.values(blocks).some(block => block.status === "FAILED");
    const expectedExecutionState = partial ? "PARTIAL" : "COMPLETE";
    const checks = {
      root_ready_and_protocol_exact: await page.locator(ROOT_SELECTOR).count() === 1,
      runtime_source: actualRuntimeMetadata.runtime_source === "BLOCK_SPECIFIC_RUNTIME_OBSERVED",
      execution_state_exact: actualRuntimeMetadata.execution_state === expectedExecutionState,
      execution_sequence_monotonic: Number(actualRuntimeMetadata.execution_sequence) > Number(beforeSequence),
      semantic_block_order_and_closure: canonical(Object.keys(blocks)) === canonical(BLOCK_IDS),
      block_specific_capture_complete: captureErrors.length === 0,
      no_self_reported_actual: Object.values(blocks).every(block =>
        !["SELF_REPORTED_REDUCER_JSON", "RUNTIME_OBSERVED"].includes(block.actual_source) &&
        block.model_values_used_as_actual === false
      ),
      no_page_errors: pageErrors.length === 0,
      no_unexpected_console_errors: unexpectedConsoleErrors.length === 0,
      ...eventAdequacy(scenario.input, eventLog, network, activeElement, ariaSnapshot, axeResults),
    };
    const checksPassed = Object.values(checks).every(Boolean);
    return {
      scenario_id: scenario.scenario_id,
      status: !checksPassed || failed ? "FAILED" : partial ? "PARTIAL" : "PASSED",
      reason: !checksPassed || failed ? "BLOCK_SPECIFIC_CAPTURE_FAILED" : partial ? PARTIAL_REASON : null,
      checks,
      runtime_metadata: actualRuntimeMetadata,
      block_observations: blocks,
      browser_events: eventLog,
      network_events: network,
      console_events: consoleEvents,
      page_errors: pageErrors,
      active_element: activeElement,
      aria_snapshot: ariaSnapshot,
      aria_error: ariaError,
      axe: axeResults,
      axe_error: axeError,
      raw_dom: html,
      raw_dom_sha256: digestBytes(Buffer.from(html, "utf8")),
      capture_errors: captureErrors,
    };
  } finally {
    page.off("request", requestListener);
    page.off("response", responseListener);
    page.off("requestfailed", failedListener);
    page.off("console", consoleListener);
    page.off("pageerror", errorListener);
  }
}

async function runBrowser(browserSpec, playwright, AxeBuilder, config) {
  const executable = fs.readFileSync(browserSpec.executable_path);
  if (
    executable.length !== browserSpec.executable_byte_count ||
    digestBytes(executable) !== browserSpec.executable_sha256
  ) {
    throw new Error(`${browserSpec.browser_id} executable identity drift`);
  }
  const browserType = playwright[browserSpec.engine];
  if (!browserType) throw new Error(`${browserSpec.engine} Playwright engine is unavailable`);
  const browser = await browserType.launch({
    executablePath: browserSpec.executable_path,
    headless: true,
  });
  try {
    const context = await browser.newContext({
      locale: "zh-CN",
      viewport: {width: 1024, height: 900},
      serviceWorkers: "block",
    });
    await installActualEventCapture(context);
    const page = await context.newPage();
    await page.route("**/*", async route => {
      const url = new URL(route.request().url());
      if (![
        "127.0.0.1",
        "localhost",
        "::1",
      ].includes(url.hostname)) {
        await route.abort("blockedbyclient");
        return;
      }
      if (url.pathname === "/api/search") {
        const postData = route.request().postData() || "";
        let query = "";
        try {
          const parsed = JSON.parse(postData);
          query = typeof parsed.query === "string" ? parsed.query : "";
        } catch {
          query = new URLSearchParams(postData).get("query") || "";
        }
        const status = query === "fail" ? 500 : 200;
        await route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify({query, status: status === 200 ? "ok" : "error"}),
        });
        return;
      }
      await route.continue();
    });
    const scenarios = [];
    for (const scenario of config.scenario_manifest) {
      try {
        scenarios.push(await runScenario(page, AxeBuilder, config, scenario));
      } catch (error) {
        scenarios.push({
          scenario_id: scenario.scenario_id,
          status: "FAILED",
          error: {name: error.name || "Error", message: String(error.message || error)},
          block_observations: {},
        });
      }
    }
    await context.close();
    const status = scenarios.some(item => item.status === "FAILED")
      ? "FAILED"
      : scenarios.every(item => item.status === "PASSED") ? "PASSED" : "NOT_RUN";
    return {
      browser_id: browserSpec.browser_id,
      engine: browserSpec.engine,
      executable: browserSpec,
      browser_version: browser.version(),
      status,
      reason: status === "NOT_RUN" ? PARTIAL_REASON : null,
      scenario_count: scenarios.length,
      scenarios,
    };
  } finally {
    await browser.close();
  }
}

async function main() {
  if (process.argv.length !== 4) {
    throw new Error("usage: frontend_formal_playwright_probe.cjs <config.json> <output.json>");
  }
  const configPath = path.resolve(process.argv[2]);
  const outputPath = path.resolve(process.argv[3]);
  const config = readConfig(configPath);
  const playwright = require(path.resolve(config.playwright_package_root));
  const axeModule = require(path.resolve(config.axe_package_root));
  const AxeBuilder = axeModule.default || axeModule.AxeBuilder || axeModule;
  const browserRuns = [];
  for (const browserSpec of config.browsers) {
    try {
      browserRuns.push(await runBrowser(browserSpec, playwright, AxeBuilder, config));
    } catch (error) {
      browserRuns.push({
        browser_id: browserSpec.browser_id,
        engine: browserSpec.engine,
        executable: browserSpec,
        browser_version: null,
          status: "FAILED",
          reason: "BLOCK_SPECIFIC_CAPTURE_FAILED",
        scenario_count: 0,
        scenarios: [],
        error: {name: error.name || "Error", message: String(error.message || error)},
      });
    }
  }
  const status = browserRuns.some(item => item.status === "FAILED")
    ? "FAILED"
    : browserRuns.every(item => item.status === "PASSED") ? "PASSED" : "NOT_RUN";
  const output = {
    schema_version: "1.0",
    kind: "frontend-interaction-playwright-probe-result",
    profile_id: config.profile_id,
    project_digest: config.project_digest,
    proof_profile: config.proof_profile,
    scenario_manifest_digest: digestJson(config.scenario_manifest),
    semantic_block_ids: BLOCK_IDS,
    model_values_accepted_as_actual: false,
    external_network: "BLOCKED",
    status,
    reason: status === "NOT_RUN" ? PARTIAL_REASON : null,
    browser_runs: browserRuns,
  };
  const data = Buffer.from(`${JSON.stringify(output, null, 2)}\n`, "utf8");
  fs.writeFileSync(outputPath, data, {flag: "wx", mode: 0o600});
  process.stdout.write(`${JSON.stringify({output: outputPath, sha256: digestBytes(data), byte_count: data.length, status: output.status})}\n`);
  // NOT_RUN is an expected, fully captured partial closure, not a helper crash.
  process.exitCode = output.status === "FAILED" ? 1 : 0;
}

module.exports = {
  eventAdequacy,
  formSubmissionAttemptObserved,
  readConfig,
  validateExactRootAndRows,
};

if (require.main === module) {
  main().catch(error => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 2;
  });
}
