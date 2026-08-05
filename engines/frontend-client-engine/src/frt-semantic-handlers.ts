import { createHash } from "node:crypto";

type JsonRecord = Readonly<Record<string, unknown>>;

export const delegatedFrtSemanticHandlerKinds = [
  "governance",
  "source_generation",
  "build_toolchain",
  "test_automation",
  "delivery_pipeline",
  "design_system",
  "mobile_client",
  "cross_platform",
  "route_orchestration",
  "compatibility",
  "advanced_verification",
  "runtime_operations",
  "product_workflow",
  "administration",
  "performance_capacity",
  "resilience_dr",
  "security_privacy",
  "production_readiness",
] as const;

export type DelegatedFrtSemanticHandlerKind =
  (typeof delegatedFrtSemanticHandlerKinds)[number];

export const implementedFrtHandlerKinds = [
  "estate_discovery",
  "semantic_ir",
  "typed_contract",
  "migration_planning",
  "directional_route",
  ...delegatedFrtSemanticHandlerKinds,
] as const;

export interface FrtSemanticSkillDescriptor {
  readonly id: string;
  readonly name: string;
  readonly title: string;
  readonly batch: string;
  readonly sourceSha256: string;
}

export interface FrtSemanticHandlerDescriptor {
  readonly handlerKind: string;
  readonly surfaceManifestPaths: Readonly<Record<string, string>>;
}

export interface FrtSemanticRouteDescriptor {
  readonly routeId: string;
  readonly skillId: string;
  readonly batch: string;
  readonly source: string;
  readonly target: string;
  readonly certification: string;
}

export interface FrtSemanticHandlerContext {
  readonly skill: FrtSemanticSkillDescriptor;
  readonly handler: FrtSemanticHandlerDescriptor;
  readonly action: "PLAN" | "ANALYZE" | "EXECUTE" | "VERIFY";
  readonly input?: JsonRecord;
  readonly routes: readonly FrtSemanticRouteDescriptor[];
  readonly requiredEvidenceRoles: readonly string[];
  readonly obligations: readonly string[];
}

interface HandlerFinding {
  readonly code: string;
  readonly severity: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  readonly message: string;
  readonly owner: string;
  readonly blocking: boolean;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right, "en-US"))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value)).digest("hex")}`;
}

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireRecord(value: unknown, name: string): JsonRecord {
  if (!isRecord(value)) throw new Error(`${name} must be an object`);
  return value;
}

function recordAt(input: JsonRecord | undefined, key: string): JsonRecord {
  return requireRecord(input?.[key], `input.${key}`);
}

function optionalRecordAt(input: JsonRecord | undefined, key: string): JsonRecord {
  const value = input?.[key];
  return value === undefined ? {} : requireRecord(value, `input.${key}`);
}

function recordsAt(input: JsonRecord | undefined, key: string): readonly JsonRecord[] {
  const value = input?.[key];
  if (!Array.isArray(value)) throw new Error(`input.${key} must be an array`);
  return value.map((item, index) => requireRecord(item, `input.${key}[${index}]`));
}

function optionalRecordsAt(input: JsonRecord | undefined, key: string): readonly JsonRecord[] {
  return input?.[key] === undefined ? [] : recordsAt(input, key);
}

function strings(value: unknown, name: string): readonly string[] {
  if (!Array.isArray(value) || value.some(item => typeof item !== "string" || !item.trim())) {
    throw new Error(`${name} must be an array of non-empty strings`);
  }
  return [...new Set(value)].sort((left, right) => left.localeCompare(right, "en-US"));
}

function optionalStrings(value: unknown, name: string): readonly string[] {
  return value === undefined ? [] : strings(value, name);
}

function text(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function booleanValue(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function finding(
  code: string,
  message: string,
  owner: string,
  blocking = true,
  severity: HandlerFinding["severity"] = "ERROR",
): HandlerFinding {
  return { code, severity, message, owner, blocking };
}

function operationName(skillName: string): string {
  return skillName.replace(/^frt-\d{4}-/, "");
}

function missingFields(input: JsonRecord | undefined, required: readonly string[]): readonly string[] {
  return required.filter(key => input?.[key] === undefined);
}

function envelope(
  context: FrtSemanticHandlerContext,
  required: readonly string[],
  semanticArtifact: JsonRecord,
  domainFindings: readonly HandlerFinding[] = [],
): Readonly<Record<string, unknown>> {
  const missing = missingFields(context.input, required);
  const handlerFindings = [
    ...missing.map(key => finding(
      "FRT_HANDLER_INPUT_REQUIRED",
      `${context.skill.id} requires input.${key} before ${context.action} can execute its typed handler.`,
      "request-owner",
    )),
    ...domainFindings,
  ];
  return {
    handler: context.handler,
    handlerImplementation: "frt-semantic-handlers/v1",
    operation: operationName(context.skill.name),
    inputDigest: digest(context.input ?? {}),
    inputContract: {
      required,
      missing,
      state: missing.length === 0 ? "SATISFIED" : "INPUT_REQUIRED",
    },
    semanticArtifact,
    handlerFindings,
    executionBoundary: {
      localComputation: "EXECUTED",
      externalExecution: "NOT_RUN",
      certification: "NOT_CERTIFIED",
      requiredEvidenceRoles: context.requiredEvidenceRoles,
      obligations: context.obligations,
    },
  };
}

function governanceHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const invariants = context.input?.invariants === undefined ? [] : recordsAt(context.input, "invariants");
  const dependencies = context.input?.dependencies === undefined ? [] : recordsAt(context.input, "dependencies");
  const allowed = new Set(optionalRecordsAt(context.input, "allowedDependencies")
    .map(item => `${text(item.from, "")}>${text(item.to, "")}`));
  const artifacts = optionalRecordsAt(context.input, "artifacts");
  const invariantFailures = invariants
    .filter(item => item.satisfied !== true)
    .map(item => text(item.id, "unnamed-invariant"));
  const boundaryViolations = dependencies
    .filter(item => allowed.size > 0 && !allowed.has(`${text(item.from, "")}>${text(item.to, "")}`))
    .map(item => ({ from: text(item.from, "unknown"), to: text(item.to, "unknown") }));
  const provenanceViolations = artifacts
    .filter(item => !/^sha256:[a-f0-9]{64}$/.test(text(item.digest, "")) || !text(item.provenance, ""))
    .map(item => text(item.name, "unnamed-artifact"));
  const findings: HandlerFinding[] = [
    ...invariantFailures.map(id => finding("FRT_GOVERNANCE_INVARIANT_FAILED", `Invariant ${id} failed.`, "governance-owner", true, "CRITICAL")),
    ...boundaryViolations.map(edge => finding("FRT_MODULE_BOUNDARY_VIOLATION", `${edge.from} may not depend on ${edge.to}.`, "architecture-owner")),
    ...provenanceViolations.map(name => finding("FRT_ARTIFACT_PROVENANCE_INVALID", `${name} lacks a valid digest or provenance.`, "artifact-owner", true, "CRITICAL")),
  ];
  return envelope(context, ["invariants"], {
    kind: "governance-assessment",
    invariantResults: invariants.map(item => ({ id: text(item.id, "unnamed"), satisfied: item.satisfied === true })),
    boundaryViolations,
    provenanceViolations,
    releaseDecision: findings.length === 0 && invariants.length > 0 ? "READY_FOR_EXTERNAL_GATE" : "BLOCKED",
  }, findings);
}

function targetSkeleton(profile: JsonRecord, uiIr: JsonRecord): Readonly<Record<string, string>> {
  const stack = text(profile.stack, "unknown");
  const version = text(profile.version, "exact-version-required");
  const title = text(uiIr.title, "ELMOS Frontend");
  const htmlTitle = title
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
  const normalized = stack.toLocaleLowerCase("en-US");
  if (normalized === "react") return {
    "package.json": JSON.stringify({ private: true, dependencies: { react: version } }, null, 2),
    "src/App.tsx": `export function App(){return <main aria-label={${JSON.stringify(title)}}><h1>{${JSON.stringify(title)}}</h1></main>}\n`,
  };
  if (normalized === "vue 3" || normalized === "vue3") return {
    "package.json": JSON.stringify({ private: true, dependencies: { vue: version } }, null, 2),
    "src/App.vue": `<template><main aria-label="${htmlTitle}"><h1>${htmlTitle}</h1></main></template>\n`,
  };
  if (normalized === "vue 2" || normalized === "vue2") return {
    "package.json": JSON.stringify({ private: true, dependencies: { vue: version } }, null, 2),
    "src/App.vue": `<template><main aria-label="${htmlTitle}"><h1>${htmlTitle}</h1></main></template>\n<script>export default {name:'App'}</script>\n`,
  };
  if (normalized.includes("wechat") || normalized.includes("mini")) return {
    "app.json": JSON.stringify({ pages: ["pages/index/index"] }, null, 2),
    "pages/index/index.wxml": `<view role="main" aria-label="${htmlTitle}"><text>${htmlTitle}</text></view>\n`,
  };
  if (normalized === "arkui") return {
    "entry/src/main/ets/pages/Index.ets": `@Entry @Component struct Index { build(){ Column(){ Text(${JSON.stringify(title)}) }.accessibilityText(${JSON.stringify(title)}) } }\n`,
  };
  if (normalized === "flutter") return {
    "pubspec.yaml": `name: frt_target\nenvironment:\n  sdk: '>=3.10.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n`,
    "lib/main.dart": `import 'package:flutter/material.dart';\nvoid main()=>runApp(const MaterialApp(home:Scaffold(body:Semantics(label:${JSON.stringify(title)},child:Text(${JSON.stringify(title)})))));\n`,
  };
  return {};
}

function sourceGenerationHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const missing = missingFields(context.input, ["targetProfile", "uiIr"]);
  if (missing.length > 0) return envelope(context, ["targetProfile", "uiIr"], {
    kind: "target-architecture",
    generatedFiles: {},
    bootstrap: "NOT_RUN",
  });
  const profile = recordAt(context.input, "targetProfile");
  const uiIr = recordAt(context.input, "uiIr");
  const generatedFiles = targetSkeleton(profile, uiIr);
  const findings = Object.keys(generatedFiles).length === 0
    ? [finding("FRT_TARGET_PROFILE_UNSUPPORTED", `Target stack ${text(profile.stack, "unknown")} is unsupported.`, "target-owner")]
    : [];
  return envelope(context, ["targetProfile", "uiIr"], {
    kind: "target-architecture",
    profile: { stack: text(profile.stack, "unknown"), version: text(profile.version, "missing") },
    modules: optionalStrings(uiIr.modules, "input.uiIr.modules"),
    generatedFiles,
    generatedFileDigest: digest(generatedFiles),
    dependencyResolution: Object.keys(generatedFiles).length > 0 ? "PINNED_PROFILE_GENERATED" : "BLOCKED",
    bootstrap: "READY_FOR_REAL_TOOLCHAIN",
  }, findings);
}

function buildToolchainHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const nodes = context.input?.astNodes === undefined ? [] : recordsAt(context.input, "astNodes");
  const imports = optionalRecordsAt(context.input, "imports");
  const diagnostics = optionalRecordsAt(context.input, "diagnostics");
  const unsupported = optionalRecordsAt(context.input, "unsupportedSemantics");
  const allocations = nodes.map((node, index) => {
    const rawName = text(node.name, `node-${index + 1}`);
    const safeName = rawName.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-|-$/g, "") || `node-${index + 1}`;
    return { nodeId: text(node.id, rawName), path: `src/generated/${safeName}.ts`, kind: text(node.kind, "unknown") };
  });
  const nodeIds = new Set(nodes.map(item => text(item.id, text(item.name, ""))));
  const unresolvedImports = imports
    .filter(item => !nodeIds.has(text(item.to, "")))
    .map(item => ({ from: text(item.from, "unknown"), to: text(item.to, "unknown") }));
  const typedHoles = unsupported.map(item => ({
    code: text(item.code, "FRT_TYPED_HOLE_UNCLASSIFIED"),
    semantic: text(item.semantic, "unknown"),
    blocking: item.blocking !== false,
  }));
  const normalizedDiagnostics = diagnostics.map(item => ({
    code: text(item.code, "UNKNOWN"),
    severity: text(item.severity, "ERROR").toLocaleUpperCase("en-US"),
    file: text(item.file, "unknown"),
    message: text(item.message, "diagnostic message unavailable"),
  }));
  const findings = [
    ...unresolvedImports.map(item => finding("FRT_IMPORT_UNRESOLVED", `${item.from} imports missing node ${item.to}.`, "generation-owner")),
    ...typedHoles.filter(item => item.blocking).map(item => finding(item.code, `${item.semantic} requires a typed implementation.`, "generation-owner")),
  ];
  return envelope(context, ["astNodes"], {
    kind: "build-toolchain-result",
    allocations,
    importGraph: imports,
    unresolvedImports,
    typedHoles,
    normalizedDiagnostics,
    repairLoop: {
      passes: numberValue(context.input?.repairPasses),
      remainingErrors: normalizedDiagnostics.filter(item => item.severity === "ERROR").length,
      converged: normalizedDiagnostics.every(item => item.severity !== "ERROR") && typedHoles.every(item => !item.blocking),
    },
  }, findings);
}

function testAutomationHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const components = context.input?.components === undefined ? [] : recordsAt(context.input, "components");
  const tests = components.flatMap(component => {
    const id = text(component.id, text(component.name, "component"));
    const props = optionalStrings(component.props, `component ${id}.props`);
    const events = optionalStrings(component.events, `component ${id}.events`);
    const slots = optionalStrings(component.slots, `component ${id}.slots`);
    return [
      { id: `${id}:render`, kind: "render", assertion: `${id} preserves its accessible component boundary` },
      ...props.map(prop => ({ id: `${id}:prop:${prop}`, kind: "prop", assertion: `${prop} is bound with its declared type` })),
      ...events.map(event => ({ id: `${id}:event:${event}`, kind: "event", assertion: `${event} is emitted exactly once` })),
      ...slots.map(slot => ({ id: `${id}:slot:${slot}`, kind: "slot", assertion: `${slot} preserves child identity` })),
    ];
  });
  const duplicateIds = components
    .map(item => text(item.id, text(item.name, "")))
    .filter((id, index, ids) => id && ids.indexOf(id) !== index);
  const findings = [...new Set(duplicateIds)].map(id => finding(
    "FRT_COMPONENT_ID_DUPLICATED",
    `Component ${id} is declared more than once.`,
    "component-owner",
  ));
  return envelope(context, ["components"], {
    kind: "component-contract-suite",
    componentContracts: components.map(item => ({
      id: text(item.id, text(item.name, "component")),
      props: optionalStrings(item.props, "component.props"),
      events: optionalStrings(item.events, "component.events"),
      slots: optionalStrings(item.slots, "component.slots"),
      hooks: optionalStrings(item.hooks, "component.hooks"),
    })),
    generatedTests: tests,
    suiteDigest: digest(tests),
  }, findings);
}

function deliveryPipelineHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const states = context.input?.states === undefined ? [] : recordsAt(context.input, "states");
  const effects = optionalRecordsAt(context.input, "effects");
  const asyncOperations = optionalRecordsAt(context.input, "asyncOperations");
  const stateIds = new Set(states.map(item => text(item.id, "")));
  const unknownStateRefs = effects.flatMap(effect => [
    ...optionalStrings(effect.reads, "effect.reads"),
    ...optionalStrings(effect.writes, "effect.writes"),
  ]).filter(id => !stateIds.has(id));
  const missingCleanup = effects
    .filter(effect => booleanValue(effect.ownsResource) && !booleanValue(effect.cleanup))
    .map(effect => text(effect.id, "unnamed-effect"));
  const cancellationGaps = asyncOperations
    .filter(operation => operation.cancelable !== true)
    .map(operation => text(operation.id, "unnamed-async-operation"));
  const findings = [
    ...[...new Set(unknownStateRefs)].map(id => finding("FRT_STATE_REFERENCE_UNKNOWN", `State ${id} is referenced but not declared.`, "state-owner")),
    ...missingCleanup.map(id => finding("FRT_RESOURCE_CLEANUP_MISSING", `Effect ${id} owns a resource without cleanup.`, "runtime-owner", true, "CRITICAL")),
    ...cancellationGaps.map(id => finding("FRT_ASYNC_CANCELLATION_MISSING", `Async operation ${id} has no cancellation contract.`, "runtime-owner")),
  ];
  return envelope(context, ["states"], {
    kind: "runtime-semantics-map",
    stateOwnership: states.map(item => ({
      id: text(item.id, "unnamed"),
      owner: text(item.owner, "UNASSIGNED"),
      persistence: text(item.persistence, "memory"),
    })),
    effectGraph: effects.map(item => ({
      id: text(item.id, "unnamed"),
      reads: optionalStrings(item.reads, "effect.reads"),
      writes: optionalStrings(item.writes, "effect.writes"),
      cleanup: booleanValue(item.cleanup),
    })),
    lifecycleOrder: optionalStrings(context.input?.lifecycleOrder, "input.lifecycleOrder"),
    semanticLosses: findings.map(item => item.code),
  }, findings);
}

function designSystemHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const routes = context.input?.routes === undefined ? [] : recordsAt(context.input, "routes");
  const forms = optionalRecordsAt(context.input, "forms");
  const apis = optionalRecordsAt(context.input, "apis");
  const storage = optionalRecordsAt(context.input, "storage");
  const permissions = optionalRecordsAt(context.input, "permissions");
  const routeIds = new Set(routes.map(item => text(item.id, text(item.path, ""))));
  const unresolvedRedirects = routes
    .filter(item => typeof item.redirectTo === "string" && !routeIds.has(item.redirectTo))
    .map(item => ({ route: text(item.id, text(item.path, "unknown")), redirectTo: text(item.redirectTo, "unknown") }));
  const unboundForms = forms
    .filter(item => !text(item.submitApi, "") || !apis.some(api => text(api.id, "") === item.submitApi))
    .map(item => text(item.id, "unnamed-form"));
  const findings = [
    ...unresolvedRedirects.map(item => finding("FRT_ROUTE_TARGET_UNRESOLVED", `${item.route} redirects to missing ${item.redirectTo}.`, "route-owner")),
    ...unboundForms.map(id => finding("FRT_FORM_API_UNBOUND", `Form ${id} has no declared submit API.`, "application-owner")),
  ];
  return envelope(context, ["routes"], {
    kind: "application-boundary-contract",
    routeGraph: routes,
    formContracts: forms,
    apiContracts: apis,
    storageContracts: storage,
    permissionContracts: permissions,
    unresolvedRedirects,
    unboundForms,
  }, findings);
}

function mobileClientHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const nodes = context.input?.uiNodes === undefined ? [] : recordsAt(context.input, "uiNodes");
  const tokens = optionalRecordAt(context.input, "designTokens");
  const locales = optionalStrings(context.input?.locales, "input.locales");
  const missingLabels = nodes
    .filter(node => booleanValue(node.interactive) && !text(node.accessibleLabel, ""))
    .map(node => text(node.id, "unnamed-ui-node"));
  const fixedDirection = nodes
    .filter(node => node.direction === "ltr" && locales.some(locale => /^(ar|fa|he|ur)(-|$)/i.test(locale)))
    .map(node => text(node.id, "unnamed-ui-node"));
  const ungovernedMotion = nodes
    .filter(node => booleanValue(node.animated) && node.respectsReducedMotion !== true)
    .map(node => text(node.id, "unnamed-ui-node"));
  const findings = [
    ...missingLabels.map(id => finding("FRT_ACCESSIBLE_LABEL_MISSING", `Interactive UI node ${id} lacks an accessible label.`, "accessibility-owner", true, "CRITICAL")),
    ...fixedDirection.map(id => finding("FRT_RTL_LAYOUT_NOT_ADAPTIVE", `UI node ${id} is fixed LTR for an RTL locale.`, "i18n-owner")),
    ...ungovernedMotion.map(id => finding("FRT_REDUCED_MOTION_UNSUPPORTED", `Animated UI node ${id} ignores reduced-motion preferences.`, "accessibility-owner")),
  ];
  return envelope(context, ["uiNodes"], {
    kind: "ui-fidelity-contract",
    designTokens: tokens,
    uiNodes: nodes,
    locales,
    accessibilityGaps: missingLabels,
    rtlGaps: fixedDirection,
    motionGaps: ungovernedMotion,
    semanticBaselineDigest: digest({ nodes, tokens, locales }),
    visualApproval: "NOT_RUN",
  }, findings);
}

function crossPlatformHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const required = context.input?.requiredCapabilities === undefined
    ? [] : strings(context.input.requiredCapabilities, "input.requiredCapabilities");
  const platforms = context.input?.platformCapabilities === undefined
    ? {} : recordAt(context.input, "platformCapabilities");
  const bridges = optionalRecordsAt(context.input, "bridges");
  const capabilityMatrix = Object.entries(platforms).map(([platform, capabilities]) => {
    const available = strings(capabilities, `input.platformCapabilities.${platform}`);
    return {
      platform,
      available,
      missing: required.filter(capability => !available.includes(capability)),
    };
  });
  const gaps = capabilityMatrix.flatMap(item => item.missing.map(capability => ({ platform: item.platform, capability })));
  const unsafeBridges = bridges
    .filter(bridge => !text(bridge.permission, "") || !text(bridge.errorContract, ""))
    .map(bridge => text(bridge.id, "unnamed-bridge"));
  const findings = [
    ...gaps.map(gap => finding("FRT_PLATFORM_CAPABILITY_MISSING", `${gap.platform} lacks ${gap.capability}.`, "platform-owner")),
    ...unsafeBridges.map(id => finding("FRT_NATIVE_BRIDGE_CONTRACT_INCOMPLETE", `Native bridge ${id} lacks permission or error semantics.`, "platform-owner", true, "CRITICAL")),
  ];
  return envelope(context, ["requiredCapabilities", "platformCapabilities"], {
    kind: "platform-capability-map",
    requiredCapabilities: required,
    capabilityMatrix,
    bridges,
    capabilityGaps: gaps,
    nativeExecution: "NOT_RUN",
  }, findings);
}

function routeOrchestrationHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const batchRoutes = context.routes.filter(route => route.batch === context.skill.batch);
  const requestedIds = optionalStrings(context.input?.routeIds, "input.routeIds");
  const selected = requestedIds.length === 0
    ? batchRoutes
    : context.routes.filter(route => requestedIds.includes(route.routeId) || requestedIds.includes(route.skillId));
  const unknown = requestedIds.filter(id => !context.routes.some(route => route.routeId === id || route.skillId === id));
  const corpus = optionalRecordsAt(context.input, "corpus");
  const findings = unknown.map(id => finding("FRT_ROUTE_REGISTRY_ENTRY_UNKNOWN", `Route ${id} is not registered.`, "route-owner"));
  return envelope(context, [], {
    kind: "directed-route-orchestration",
    routeRegistry: selected,
    selectedRouteCount: selected.length,
    differentialCases: corpus.map(item => ({
      id: text(item.id, "unnamed-case"),
      sourceDigest: text(item.sourceDigest, "MISSING"),
      expectedIrDigest: text(item.expectedIrDigest, "MISSING"),
      corpusClass: text(item.corpusClass, "development"),
    })),
    equivalenceGate: corpus.length === 0 ? "INPUT_REQUIRED" : "READY_FOR_RUNNER",
    certificationFragment: { eligible: false, certification: "NOT_CERTIFIED" },
  }, findings);
}

function compatibilityHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const packs = context.input?.packs === undefined ? [] : recordsAt(context.input, "packs");
  const provided = new Map<string, string[]>();
  for (const pack of packs) {
    const id = text(pack.id, "unnamed-pack");
    for (const capability of optionalStrings(pack.provides, `pack ${id}.provides`)) {
      provided.set(capability, [...(provided.get(capability) ?? []), id]);
    }
  }
  const conflicts = [...provided.entries()]
    .filter(([, owners]) => owners.length > 1)
    .map(([capability, owners]) => ({ capability, owners }));
  const missingRequirements = packs.flatMap(pack => {
    const id = text(pack.id, "unnamed-pack");
    return optionalStrings(pack.requires, `pack ${id}.requires`)
      .filter(requirement => !provided.has(requirement))
      .map(requirement => ({ pack: id, requirement }));
  });
  const order = [...packs]
    .sort((left, right) => numberValue(right.priority) - numberValue(left.priority)
      || text(left.id, "").localeCompare(text(right.id, ""), "en-US"))
    .map(pack => text(pack.id, "unnamed-pack"));
  const findings = [
    ...conflicts.map(item => finding("FRT_PACK_CAPABILITY_CONFLICT", `${item.capability} is provided by ${item.owners.join(", ")}.`, "pack-owner")),
    ...missingRequirements.map(item => finding("FRT_PACK_REQUIREMENT_MISSING", `${item.pack} requires missing ${item.requirement}.`, "pack-owner")),
  ];
  return envelope(context, ["packs"], {
    kind: "pack-compatibility-result",
    overlayOrder: order,
    providedCapabilities: Object.fromEntries(provided),
    conflicts,
    missingRequirements,
    compositionDigest: digest(order),
  }, findings);
}

function advancedVerificationHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const properties = context.input?.properties === undefined ? [] : recordsAt(context.input, "properties");
  const tools = optionalRecordAt(context.input, "toolchains");
  const counterexamples = optionalRecordsAt(context.input, "counterexamples");
  const obligations = properties.map(property => ({
    id: text(property.id, "unnamed-property"),
    kind: text(property.kind, "invariant"),
    expression: text(property.expression, "MISSING"),
    assumptions: optionalStrings(property.assumptions, "property.assumptions"),
    bounds: isRecord(property.bounds) ? property.bounds : {},
    status: "NOT_RUN",
  }));
  const malformed = obligations.filter(item => item.expression === "MISSING").map(item => item.id);
  const findings = malformed.map(id => finding("FRT_PROOF_OBLIGATION_INCOMPLETE", `Proof obligation ${id} lacks an expression.`, "verification-owner"));
  return envelope(context, ["properties"], {
    kind: "verification-plan",
    proofObligations: obligations,
    adapters: Object.entries(tools).map(([tool, profile]) => ({ tool, profile, execution: "NOT_RUN" })),
    counterexampleIr: counterexamples.map(item => ({
      propertyId: text(item.propertyId, "unknown"),
      trace: Array.isArray(item.trace) ? item.trace : [],
      replay: "NOT_RUN",
    })),
    proofEvidenceGraph: { nodes: obligations.map(item => item.id), edges: [] },
    formalProof: "NOT_RUN",
  }, findings);
}

function runtimeOperationsHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const resources = context.input?.resources === undefined ? [] : recordsAt(context.input, "resources");
  const roles = optionalRecordsAt(context.input, "roles");
  const jobs = optionalRecordsAt(context.input, "jobs");
  const quotas = optionalRecordAt(context.input, "quotas");
  const resourceIds = new Set(resources.map(item => text(item.id, "")));
  const invalidJobs = jobs
    .filter(job => !resourceIds.has(text(job.resourceId, "")) || !text(job.idempotencyKey, ""))
    .map(job => text(job.id, "unnamed-job"));
  const broadRoles = roles
    .filter(role => optionalStrings(role.permissions, "role.permissions").some(permission => permission === "*" || permission.endsWith(":*")))
    .map(role => text(role.id, "unnamed-role"));
  const findings = [
    ...invalidJobs.map(id => finding("FRT_DURABLE_JOB_CONTRACT_INVALID", `Job ${id} lacks a resource binding or idempotency key.`, "runtime-owner")),
    ...broadRoles.map(id => finding("FRT_RBAC_PERMISSION_OVERBROAD", `Role ${id} contains a wildcard permission.`, "security-owner", true, "CRITICAL")),
  ];
  return envelope(context, ["resources"], {
    kind: "runtime-operations-model",
    registry: resources.map(item => ({
      id: text(item.id, "unnamed-resource"),
      type: text(item.type, "unknown"),
      tenantBound: item.tenantBound === true,
      version: text(item.version, "exact-version-required"),
    })),
    durableJobs: jobs,
    rbac: roles,
    quotas,
    deploymentPlan: { state: findings.length === 0 ? "READY_FOR_EXTERNAL_RUNNER" : "BLOCKED", execution: "NOT_RUN" },
  }, findings);
}

function reachableStates(initial: string, transitions: readonly JsonRecord[]): Set<string> {
  const reached = new Set<string>(initial ? [initial] : []);
  let changed = true;
  while (changed) {
    changed = false;
    for (const transition of transitions) {
      const from = text(transition.from, "");
      const to = text(transition.to, "");
      if (reached.has(from) && to && !reached.has(to)) {
        reached.add(to);
        changed = true;
      }
    }
  }
  return reached;
}

function productWorkflowHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const requirements = context.input?.requirements === undefined ? [] : recordsAt(context.input, "requirements");
  const states = context.input?.states === undefined ? [] : recordsAt(context.input, "states");
  const transitions = context.input?.transitions === undefined ? [] : recordsAt(context.input, "transitions");
  const journeys = optionalRecordsAt(context.input, "journeys");
  const artifacts = optionalRecordsAt(context.input, "artifacts");
  const initial = text(context.input?.initialState, text(states[0]?.id, ""));
  const reached = reachableStates(initial, transitions);
  const unreachable = states.map(item => text(item.id, "")).filter(id => id && !reached.has(id));
  const artifactRequirements = new Set(artifacts.flatMap(item => optionalStrings(item.requirementIds, "artifact.requirementIds")));
  const untraced = requirements.map(item => text(item.id, "")).filter(id => id && !artifactRequirements.has(id));
  const uncompensated = transitions
    .filter(item => booleanValue(item.sideEffect) && !text(item.compensation, ""))
    .map(item => text(item.id, `${text(item.from, "?")}->${text(item.to, "?")}`));
  const journeyRequirements = new Set(journeys.flatMap(item => optionalStrings(item.requirementIds, "journey.requirementIds")));
  const uncovered = requirements.map(item => text(item.id, "")).filter(id => id && !journeyRequirements.has(id));
  const findings = [
    ...unreachable.map(id => finding("FRT_WORKFLOW_STATE_UNREACHABLE", `State ${id} is unreachable from ${initial || "the missing initial state"}.`, "workflow-owner")),
    ...untraced.map(id => finding("FRT_REQUIREMENT_TRACE_MISSING", `Requirement ${id} has no implementation artifact.`, "product-owner")),
    ...uncompensated.map(id => finding("FRT_SIDE_EFFECT_COMPENSATION_MISSING", `Transition ${id} has an uncompensated side effect.`, "workflow-owner", true, "CRITICAL")),
    ...uncovered.map(id => finding("FRT_REQUIREMENT_JOURNEY_UNCOVERED", `Requirement ${id} has no representative journey.`, "quality-owner")),
  ];
  return envelope(context, ["requirements", "states", "transitions"], {
    kind: "product-workflow-model",
    traceability: requirements.map(item => ({ id: text(item.id, "unnamed"), traced: artifactRequirements.has(text(item.id, "")) })),
    stateMachine: { initial, states, transitions, reachable: [...reached].sort(), unreachable },
    uncompensatedTransitions: uncompensated,
    journeyCoverage: { journeys, uncoveredRequirements: uncovered },
    externalJourneyExecution: "NOT_RUN",
  }, findings);
}

function administrationHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const capabilities = context.input?.capabilities === undefined ? [] : recordsAt(context.input, "capabilities");
  const roles = context.input?.roles === undefined ? [] : recordsAt(context.input, "roles");
  const operations = context.input?.operations === undefined ? [] : recordsAt(context.input, "operations");
  const rolePermissions = new Map(roles.map(role => [
    text(role.id, ""),
    new Set(optionalStrings(role.permissions, "role.permissions")),
  ]));
  const unauthorized = operations.filter(operation => {
    const role = rolePermissions.get(text(operation.roleId, ""));
    return !role?.has(text(operation.permission, ""));
  }).map(operation => text(operation.id, "unnamed-operation"));
  const unaudited = operations
    .filter(operation => !text(operation.auditEvent, ""))
    .map(operation => text(operation.id, "unnamed-operation"));
  const irreversibleBulk = operations
    .filter(operation => booleanValue(operation.bulk) && !text(operation.rollback, ""))
    .map(operation => text(operation.id, "unnamed-operation"));
  const findings = [
    ...unauthorized.map(id => finding("FRT_ADMIN_OPERATION_UNAUTHORIZED", `Admin operation ${id} is not granted to its role.`, "security-owner", true, "CRITICAL")),
    ...unaudited.map(id => finding("FRT_ADMIN_AUDIT_EVENT_MISSING", `Admin operation ${id} has no audit event.`, "audit-owner")),
    ...irreversibleBulk.map(id => finding("FRT_ADMIN_BULK_ROLLBACK_MISSING", `Bulk operation ${id} has no rollback contract.`, "operations-owner", true, "CRITICAL")),
  ];
  return envelope(context, ["capabilities", "roles", "operations"], {
    kind: "administration-capability-model",
    capabilityMatrix: capabilities,
    roles,
    operations,
    unauthorizedOperations: unauthorized,
    unauditedOperations: unaudited,
    irreversibleBulkOperations: irreversibleBulk,
    adminJourneyExecution: "NOT_RUN",
  }, findings);
}

function percentile(values: readonly number[], quantile: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(quantile * sorted.length) - 1));
  return sorted[index] ?? null;
}

function performanceCapacityHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const workload = context.input?.workload === undefined ? {} : recordAt(context.input, "workload");
  const budgets = context.input?.budgets === undefined ? {} : recordAt(context.input, "budgets");
  const samples = optionalRecordsAt(context.input, "samples");
  const latencies = samples.map(item => numberValue(item.latencyMs)).filter(value => value >= 0);
  const failures = samples.filter(item => item.success === false).length;
  const metrics = {
    sampleCount: samples.length,
    p95LatencyMs: percentile(latencies, 0.95),
    p99LatencyMs: percentile(latencies, 0.99),
    errorRate: samples.length === 0 ? null : failures / samples.length,
    throughputPerSecond: numberValue(context.input?.throughputPerSecond),
  };
  const violations: string[] = [];
  if (metrics.p95LatencyMs !== null && metrics.p95LatencyMs > numberValue(budgets.p95LatencyMs, Number.POSITIVE_INFINITY)) violations.push("p95LatencyMs");
  if (metrics.p99LatencyMs !== null && metrics.p99LatencyMs > numberValue(budgets.p99LatencyMs, Number.POSITIVE_INFINITY)) violations.push("p99LatencyMs");
  if (metrics.errorRate !== null && metrics.errorRate > numberValue(budgets.maximumErrorRate, Number.POSITIVE_INFINITY)) violations.push("errorRate");
  if (metrics.throughputPerSecond < numberValue(budgets.minimumThroughputPerSecond, 0)) violations.push("throughputPerSecond");
  const findings = violations.map(metric => finding("FRT_PERFORMANCE_BUDGET_EXCEEDED", `${metric} exceeds its declared budget.`, "performance-owner"));
  return envelope(context, ["workload", "budgets"], {
    kind: "performance-capacity-assessment",
    workload,
    budgets,
    candidateMetrics: metrics,
    budgetViolations: violations,
    measurementAuthority: "LOCAL_CANDIDATE_ONLY",
    representativePerformanceRun: "NOT_RUN",
  }, findings);
}

function resilienceDrHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const scenarios = context.input?.scenarios === undefined ? [] : recordsAt(context.input, "scenarios");
  const recoveryObjectives = context.input?.recoveryObjectives === undefined
    ? {} : recordAt(context.input, "recoveryObjectives");
  const observations = optionalRecordsAt(context.input, "observations");
  const observedById = new Map(observations.map(item => [text(item.scenarioId, ""), item]));
  const uncovered = scenarios.filter(item => !observedById.has(text(item.id, ""))).map(item => text(item.id, "unnamed-scenario"));
  const objectiveViolations = observations.filter(item =>
    numberValue(item.rtoSeconds) > numberValue(recoveryObjectives.maximumRtoSeconds, Number.POSITIVE_INFINITY)
      || numberValue(item.rpoSeconds) > numberValue(recoveryObjectives.maximumRpoSeconds, Number.POSITIVE_INFINITY),
  ).map(item => text(item.scenarioId, "unknown-scenario"));
  const unsafe = scenarios
    .filter(item => !text(item.rollback, "") || !text(item.blastRadius, ""))
    .map(item => text(item.id, "unnamed-scenario"));
  const findings = [
    ...unsafe.map(id => finding("FRT_CHAOS_SAFETY_CONTRACT_MISSING", `Scenario ${id} lacks rollback or blast-radius bounds.`, "resilience-owner", true, "CRITICAL")),
    ...objectiveViolations.map(id => finding("FRT_RECOVERY_OBJECTIVE_EXCEEDED", `Scenario ${id} exceeds RTO or RPO.`, "resilience-owner")),
  ];
  return envelope(context, ["scenarios", "recoveryObjectives"], {
    kind: "resilience-dr-plan",
    scenarios,
    recoveryObjectives,
    candidateObservations: observations,
    uncoveredScenarios: uncovered,
    objectiveViolations,
    authorizedChaosExecution: "NOT_RUN",
    restoreAndDrExercise: "NOT_RUN",
  }, findings);
}

function securityPrivacyHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const assets = context.input?.assets === undefined ? [] : recordsAt(context.input, "assets");
  const securityFindings = context.input?.findings === undefined ? [] : recordsAt(context.input, "findings");
  const dataFlows = optionalRecordsAt(context.input, "dataFlows");
  const components = optionalRecordsAt(context.input, "sbomComponents");
  const critical = securityFindings.filter(item => ["CRITICAL", "HIGH"].includes(text(item.severity, "").toLocaleUpperCase("en-US")));
  const unclassifiedAssets = assets.filter(item => !text(item.classification, "")).map(item => text(item.id, "unnamed-asset"));
  const privacyGaps = dataFlows
    .filter(item => booleanValue(item.personalData) && (!text(item.purpose, "") || !text(item.retention, "")))
    .map(item => text(item.id, "unnamed-data-flow"));
  const unpinnedComponents = components
    .filter(item => !text(item.version, "") || /^(latest|current|x)$/i.test(text(item.version, "")))
    .map(item => text(item.name, "unnamed-component"));
  const findings = [
    ...critical.map(item => finding("FRT_SECURITY_ZERO_TOLERANCE_FINDING", `${text(item.id, "finding")} is ${text(item.severity, "HIGH")}.`, "security-owner", true, "CRITICAL")),
    ...unclassifiedAssets.map(id => finding("FRT_ASSET_CLASSIFICATION_MISSING", `Asset ${id} has no security classification.`, "security-owner")),
    ...privacyGaps.map(id => finding("FRT_PRIVACY_PURPOSE_OR_RETENTION_MISSING", `Data flow ${id} lacks purpose or retention.`, "privacy-owner", true, "CRITICAL")),
    ...unpinnedComponents.map(id => finding("FRT_SBOM_VERSION_UNPINNED", `SBOM component ${id} is not exactly versioned.`, "supply-chain-owner")),
  ];
  return envelope(context, ["assets", "findings"], {
    kind: "security-privacy-assessment",
    attackSurface: assets,
    normalizedFindings: securityFindings,
    dataFlows,
    sbomComponents: components,
    zeroToleranceFindingCount: critical.length,
    privacyGaps,
    supplyChainGaps: unpinnedComponents,
    penetrationTest: "NOT_RUN",
  }, findings);
}

function productionReadinessHandler(context: FrtSemanticHandlerContext): Readonly<Record<string, unknown>> {
  const slos = context.input?.slos === undefined ? [] : recordsAt(context.input, "slos");
  const runbooks = context.input?.runbooks === undefined ? [] : recordsAt(context.input, "runbooks");
  const alerts = optionalRecordsAt(context.input, "alerts");
  const releases = optionalRecordsAt(context.input, "releases");
  const runbookServices = new Set(runbooks.map(item => text(item.serviceId, "")));
  const missingRunbooks = slos.map(item => text(item.serviceId, "")).filter(id => id && !runbookServices.has(id));
  const unsafeReleases = releases
    .filter(item => !text(item.canaryPolicy, "") || !text(item.rollback, ""))
    .map(item => text(item.id, "unnamed-release"));
  const unactionableAlerts = alerts
    .filter(item => !text(item.owner, "") || !text(item.runbookId, ""))
    .map(item => text(item.id, "unnamed-alert"));
  const findings = [
    ...missingRunbooks.map(id => finding("FRT_PRODUCTION_RUNBOOK_MISSING", `Service ${id} has an SLO but no runbook.`, "sre-owner")),
    ...unsafeReleases.map(id => finding("FRT_RELEASE_ROLLBACK_CONTRACT_MISSING", `Release ${id} lacks canary or rollback policy.`, "release-owner", true, "CRITICAL")),
    ...unactionableAlerts.map(id => finding("FRT_ALERT_NOT_ACTIONABLE", `Alert ${id} lacks an owner or runbook.`, "sre-owner")),
  ];
  return envelope(context, ["slos", "runbooks"], {
    kind: "production-readiness-model",
    serviceSlos: slos,
    runbooks,
    alerts,
    releaseTrain: releases,
    missingRunbooks,
    unsafeReleases,
    productionObservation: "NOT_RUN",
    customerAcceptance: "NOT_RUN",
    decision: "NOT_CERTIFIED",
  }, findings);
}

const handlers: Readonly<Record<DelegatedFrtSemanticHandlerKind, (
  context: FrtSemanticHandlerContext,
) => Readonly<Record<string, unknown>>>> = {
  governance: governanceHandler,
  source_generation: sourceGenerationHandler,
  build_toolchain: buildToolchainHandler,
  test_automation: testAutomationHandler,
  delivery_pipeline: deliveryPipelineHandler,
  design_system: designSystemHandler,
  mobile_client: mobileClientHandler,
  cross_platform: crossPlatformHandler,
  route_orchestration: routeOrchestrationHandler,
  compatibility: compatibilityHandler,
  advanced_verification: advancedVerificationHandler,
  runtime_operations: runtimeOperationsHandler,
  product_workflow: productWorkflowHandler,
  administration: administrationHandler,
  performance_capacity: performanceCapacityHandler,
  resilience_dr: resilienceDrHandler,
  security_privacy: securityPrivacyHandler,
  production_readiness: productionReadinessHandler,
};

export function isDelegatedFrtSemanticHandlerKind(
  value: string,
): value is DelegatedFrtSemanticHandlerKind {
  return (delegatedFrtSemanticHandlerKinds as readonly string[]).includes(value);
}

export function executeFrtSemanticHandler(
  context: FrtSemanticHandlerContext,
): Readonly<Record<string, unknown>> {
  if (!isDelegatedFrtSemanticHandlerKind(context.handler.handlerKind)) {
    throw new Error(`No concrete FRT semantic handler is implemented for ${context.handler.handlerKind}`);
  }
  return handlers[context.handler.handlerKind](context);
}
