import { createHash } from "node:crypto";
import {
  recommendedExtensionProfiles,
  uiConversionRoute,
  uiConversionRoutes,
  uiTargetProfile,
  uiTargetProfiles,
} from "./project-profiles.js";
import { componentForRoute, renderTargetProject } from "./project-templates.js";
import type {
  GeneratedUiProject,
  UiFrameworkId,
  UiIrNode,
  UiProjectGenerationRequest,
} from "./project-types.js";

const frameworkIds = new Set<UiFrameworkId>(uiTargetProfiles().map(profile => profile.id));
const exactVersion = /^(?:[0-9]+\.)+[0-9]+(?:\([0-9]+\))?$/;
const projectName = /^[a-z][a-z0-9-]{1,47}$/;
const applicationId = /^[A-Za-z][A-Za-z0-9._-]{1,127}$/;
const packageName = /^[a-z][a-z0-9_-]{1,63}$/;
const bundleId = /^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*){2,7}$/;
const routePath = /^\/[A-Za-z0-9_./:*-]*$/;
const sha256 = /^sha256:[a-f0-9]{64}$/;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value)).digest("hex")}`;
}

function requireText(value: unknown, name: string): asserts value is string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${name} is required`);
}

function requirePattern(value: string, pattern: RegExp, name: string): void {
  if (!pattern.test(value)) throw new Error(`${name} is invalid`);
}

function validateNodeArray(
  name: string,
  nodes: readonly UiIrNode[],
  knownIds: Set<string>,
  allowEmpty: boolean,
): void {
  if (!Array.isArray(nodes) || (!allowEmpty && nodes.length === 0)) {
    throw new Error(`uiIr.${name} must contain typed nodes`);
  }
  for (const node of nodes) {
    requireText(node.id, `uiIr.${name}.id`);
    requireText(node.name, `uiIr.${name}.name`);
    requireText(node.kind, `uiIr.${name}.kind`);
    if (!Array.isArray(node.references) || !Array.isArray(node.sourceRefs)) {
      throw new Error(`uiIr.${name} references and sourceRefs must be arrays`);
    }
    if (knownIds.has(node.id)) throw new Error(`duplicate UI IR id: ${node.id}`);
    knownIds.add(node.id);
  }
}

export function validateUiProjectGenerationRequest(
  value: UiProjectGenerationRequest,
): UiProjectGenerationRequest {
  if (!value || typeof value !== "object") throw new Error("project request is required");
  if (value.schemaVersion !== "1.0") throw new Error("unsupported project request schemaVersion");
  requireText(value.projectName, "projectName");
  requirePattern(value.projectName, projectName, "projectName");
  requireText(value.applicationId, "applicationId");
  requirePattern(value.applicationId, applicationId, "applicationId");
  requireText(value.title, "title");
  requireText(value.packageName, "packageName");
  requirePattern(value.packageName, packageName, "packageName");
  requireText(value.bundleId, "bundleId");
  requirePattern(value.bundleId, bundleId, "bundleId");
  if (!value.source || !frameworkIds.has(value.source.framework)) {
    throw new Error("source framework is unsupported");
  }
  if (!frameworkIds.has(value.targetFramework)) throw new Error("target framework is unsupported");
  if (value.source.framework === value.targetFramework) {
    throw new Error("source and target frameworks must differ");
  }
  requireText(value.source.version, "source.version");
  requirePattern(value.source.version, exactVersion, "source.version");
  if (!["WEB", "ANDROID", "IOS", "HARMONYOS"].includes(value.source.platform)) {
    throw new Error("source.platform is unsupported");
  }
  if (!value.uiIr || value.uiIr.schemaVersion !== "1.0") {
    throw new Error("uiIr schemaVersion 1.0 is required");
  }
  requirePattern(value.uiIr.sourceSnapshotDigest, sha256, "uiIr.sourceSnapshotDigest");

  const ids = new Set<string>();
  validateNodeArray("components", value.uiIr.components, ids, false);
  validateNodeArray("routes", value.uiIr.routes, ids, false);
  validateNodeArray("views", value.uiIr.views, ids, false);
  validateNodeArray("states", value.uiIr.states, ids, false);
  validateNodeArray("actions", value.uiIr.actions, ids, false);
  validateNodeArray("effects", value.uiIr.effects, ids, false);
  validateNodeArray("forms", value.uiIr.forms, ids, false);
  validateNodeArray("bindings", value.uiIr.bindings, ids, false);
  validateNodeArray("permissions", value.uiIr.permissions, ids, false);
  validateNodeArray("resources", value.uiIr.resources, ids, false);
  validateNodeArray("designTokens", value.uiIr.designTokens, ids, false);
  validateNodeArray("accessibility", value.uiIr.accessibility, ids, false);
  validateNodeArray("nativeBoundaries", value.uiIr.nativeBoundaries, ids, true);
  validateNodeArray("unknowns", value.uiIr.unknowns, ids, true);
  for (const unknown of value.uiIr.unknowns) {
    if (!["critical", "high", "medium", "low"].includes(unknown.severity)) {
      throw new Error(`UI IR unknown severity is invalid: ${unknown.id}`);
    }
    requireText(unknown.description, `UI IR unknown description: ${unknown.id}`);
    requireText(unknown.owner, `UI IR unknown owner: ${unknown.id}`);
  }

  const paths = new Set<string>();
  const componentIds = new Set(value.uiIr.components.map(component => component.id));
  for (const route of value.uiIr.routes) {
    requireText(route.path, `route ${route.id} path`);
    requirePattern(route.path, routePath, `route ${route.id} path`);
    if (route.path.includes("..") || route.path.includes("//")) {
      throw new Error(`route ${route.id} path escapes its navigation scope`);
    }
    if (paths.has(route.path)) throw new Error(`duplicate route path: ${route.path}`);
    paths.add(route.path);
    if (!componentIds.has(route.componentId)) {
      throw new Error(`route ${route.id} references a missing component`);
    }
    if (typeof route.requiresAuth !== "boolean" || typeof route.deepLink !== "boolean") {
      throw new Error(`route ${route.id} requires typed auth and deep-link flags`);
    }
  }

  for (const group of [
    value.uiIr.routes,
    value.uiIr.views,
    value.uiIr.components,
    value.uiIr.states,
    value.uiIr.actions,
    value.uiIr.effects,
    value.uiIr.forms,
    value.uiIr.bindings,
    value.uiIr.permissions,
    value.uiIr.resources,
    value.uiIr.designTokens,
    value.uiIr.accessibility,
    value.uiIr.nativeBoundaries,
    value.uiIr.unknowns,
  ]) {
    for (const node of group) {
      for (const reference of node.references) {
        if (!ids.has(reference)) throw new Error(`UI IR reference is unresolved: ${reference}`);
      }
    }
  }
  return value;
}

function canonicalBatch32UiIr(request: UiProjectGenerationRequest): Readonly<Record<string, unknown>> {
  const node = (value: UiIrNode): Readonly<Record<string, unknown>> => ({
    id: value.id,
    kind: value.kind,
    name: value.name,
    references: value.references,
    source_refs: value.sourceRefs,
  });
  const routes = request.uiIr.routes.map(value => ({
    ...node(value),
    path: value.path,
    component_id: value.componentId,
    requires_auth: value.requiresAuth,
    deep_link: value.deepLink,
  }));
  const components = request.uiIr.components.map(value => ({
    ...node(value),
    text: value.text,
    accessibility_role: value.accessibilityRole,
  }));
  const groups = [
    request.uiIr.routes,
    request.uiIr.views,
    request.uiIr.components,
    request.uiIr.states,
    request.uiIr.actions,
    request.uiIr.effects,
    request.uiIr.forms,
    request.uiIr.bindings,
    request.uiIr.permissions,
    request.uiIr.resources,
    request.uiIr.designTokens,
    request.uiIr.accessibility,
    request.uiIr.nativeBoundaries,
  ];
  const mappedNodes = groups.flat();
  return {
    schema_version: 1,
    pack_key: request.projectName,
    source_snapshot_digest: request.uiIr.sourceSnapshotDigest,
    routes,
    views: request.uiIr.views.map(node),
    components,
    states: request.uiIr.states.map(node),
    actions: request.uiIr.actions.map(node),
    effects: request.uiIr.effects.map(node),
    forms: request.uiIr.forms.map(node),
    bindings: request.uiIr.bindings.map(node),
    permissions: request.uiIr.permissions.map(node),
    resources: request.uiIr.resources.map(node),
    design_tokens: request.uiIr.designTokens.map(node),
    accessibility: [
      ...request.uiIr.accessibility.map(node),
      ...request.uiIr.nativeBoundaries.map(node),
    ],
    source_map: mappedNodes.map(value => ({
      node_id: value.id,
      source_refs: value.sourceRefs.map(reference => ({ reference })),
    })),
    unknowns: request.uiIr.unknowns.map(value => ({
      id: value.id,
      severity: value.severity,
      description: value.description,
      owner: value.owner,
      references: value.references,
      source_refs: value.sourceRefs,
    })),
  };
}

function verificationScript(target: UiFrameworkId, runtimeVersion: string): string {
  if (target === "flutter") {
    return [
      "#!/usr/bin/env bash",
      "set -euo pipefail",
      `flutter --version | grep -F "Flutter ${runtimeVersion}"`,
      "flutter pub get",
      "flutter analyze",
      "flutter test",
      "",
    ].join("\n");
  }
  if (target === "harmony-arkui") {
    return [
      "#!/usr/bin/env bash",
      "set -euo pipefail",
      'test "${ELMOS_HARMONYOS_RUNNER_PROFILE:-}" = "harmonyos-6.0.0-api20"',
      'test -x "./hvigorw" || { echo "HARMONY_HVIGOR_WRAPPER_NOT_MATERIALIZED"; exit 2; }',
      "./hvigorw clean --no-daemon",
      "./hvigorw assembleHap --mode module -p module=entry@default -p buildMode=debug --no-daemon",
      "",
    ].join("\n");
  }
  if (target === "react-native") {
    return [
      "#!/usr/bin/env bash",
      "set -euo pipefail",
      'test -f package-lock.json || { echo "PACKAGE_LOCK_NOT_MATERIALIZED"; exit 2; }',
      "npm ci",
      "npm run typecheck",
      "npm run export:web",
      'test "${ELMOS_MOBILE_DEVICE_EVIDENCE:-NOT_RUN}" != "NOT_RUN" || { echo "MOBILE_DEVICE_EVIDENCE_NOT_RUN"; exit 3; }',
      "",
    ].join("\n");
  }
  return [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    'test -f package-lock.json || { echo "PACKAGE_LOCK_NOT_MATERIALIZED"; exit 2; }',
    "npm ci",
    "npm run test",
    "npm run build",
    "",
  ].join("\n");
}

function workflow(target: UiFrameworkId, runtimeVersion: string): string {
  const labels = target === "flutter"
    ? "[self-hosted, elmos-flutter-3-44-1]"
    : target === "harmony-arkui"
      ? "[self-hosted, elmos-harmonyos-6-api20]"
      : target === "react-native"
        ? "[self-hosted, elmos-expo-57-device]"
        : "ubuntu-latest";
  const nodeSetup = ["flutter", "harmony-arkui"].includes(target)
    ? []
    : [
      "      - name: Set up exact Node.js",
      "        uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020",
      "        with:",
      `          node-version: ${runtimeVersion}`,
    ];
  return [
    "name: generated-ui-quality",
    "on:",
    "  pull_request:",
    "  workflow_dispatch:",
    "permissions:",
    "  contents: read",
    "jobs:",
    "  generated-ui:",
    `    runs-on: ${labels}`,
    "    timeout-minutes: 30",
    "    steps:",
    "      - name: Check out exact revision",
    "        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
    ...nodeSetup,
    "      - name: Verify generated project",
    "        run: bash scripts/verify.sh",
    "",
  ].join("\n");
}

function readme(request: UiProjectGenerationRequest, obligations: readonly string[]): string {
  return [
    `# ${request.title}`,
    "",
    `This project was generated from typed UI Interaction IR for the directional route \`${request.source.framework}@${request.source.version} -> ${request.targetFramework}\`.`,
    "",
    "## Generated scope",
    "",
    "- Exact target profile, build configuration, application shell, routes, accessibility semantics, UI IR snapshot, CI workflow, and fail-closed verification script.",
    "- Source business behavior was not executed by the static generator.",
    "- Dependency lock resolution, target build/startup, browser or device journeys, visual parity, accessibility review, holdout execution, signing, and release remain `NOT_RUN`.",
    "",
    "## Next commands",
    "",
    "For npm targets, materialize an exact lock without lifecycle scripts:",
    "",
    "```bash",
    "npm install --package-lock-only --ignore-scripts --no-audit --no-fund",
    "bash scripts/verify.sh",
    "```",
    "",
    "Flutter and HarmonyOS targets require their exact declared SDK Runner. The verification script fails closed when that Runner or required evidence is absent.",
    "",
    "## Open obligations",
    "",
    ...obligations.map(item => `- ${item}`),
    "",
  ].join("\n");
}

function commonFiles(
  request: UiProjectGenerationRequest,
  projectId: string,
  obligations: readonly string[],
): Record<string, string> {
  const profile = uiTargetProfile(request.targetFramework);
  return {
    ".editorconfig": [
      "root = true",
      "[*]",
      "charset = utf-8",
      "end_of_line = lf",
      "insert_final_newline = true",
      "indent_style = space",
      "indent_size = 2",
      "trim_trailing_whitespace = true",
      "",
    ].join("\n"),
    ".gitignore": [
      "node_modules/",
      ".elmos-npm-cache/",
      "dist/",
      "build/",
      ".dart_tool/",
      ".flutter-plugins*",
      ".idea/",
      ".deveco/",
      "oh_modules/",
      "*.hap",
      "*.app",
      ".env",
      ".env.*",
      "!.env.example",
      "",
    ].join("\n"),
    ".env.example": "PUBLIC_API_BASE_URL=http://127.0.0.1:8080\n",
    "README.md": readme(request, obligations),
    "ui-ir/model.json": `${JSON.stringify(canonicalBatch32UiIr(request), null, 2)}\n`,
    "target-profile/profile.json": `${JSON.stringify(profile, null, 2)}\n`,
    "conversion/route.json": `${JSON.stringify(uiConversionRoute(request.source.framework, request.targetFramework), null, 2)}\n`,
    "conversion/obligations.json": `${JSON.stringify({ schemaVersion: "1.0", projectId, obligations }, null, 2)}\n`,
    "scripts/verify.sh": verificationScript(request.targetFramework, profile.runtimeVersion),
    ".github/workflows/generated-ui-quality.yml": workflow(
      request.targetFramework,
      profile.nodeVersion ?? profile.runtimeVersion,
    ),
  };
}

function obligations(request: UiProjectGenerationRequest): readonly string[] {
  const result = [
    "Resolve and review an immutable dependency lock with an approved network and supply-chain policy.",
    "Build and start the generated target with the exact target profile.",
    "Replay route, state, action, effect, form, API, permission, localization, error, and business contracts.",
    "Run keyboard/focus or native accessibility, semantic-tree, contrast, zoom/text-scale, and assistive-technology checks.",
    "Capture approved visual baselines without automatic updates or widened masks.",
    "Run physically separate negative, holdout, and representative journey corpora.",
    "Bind raw runtime evidence to the exact source snapshot, target artifact, environment, executor, and independent verifier.",
  ];
  if (request.uiIr.unknowns.length > 0) {
    result.push("Resolve every critical or high UI IR unknown; unknown behavior cannot pass through permissive fallbacks.");
  }
  if (request.uiIr.routes.some(route => route.requiresAuth)) {
    result.push("Implement and independently verify identity, tenant, authorization, session expiry, and permission-denied journeys.");
  }
  if (request.uiIr.routes.some(route => route.deepLink)) {
    result.push("Verify every declared deep link from cold start, warm start, background, invalid input, and unsupported-version states.");
  }
  if (["react-native", "flutter", "harmony-arkui"].includes(request.targetFramework)) {
    result.push("Verify lifecycle, background/foreground, process death, offline replay, secure storage, permissions, signing, upgrade, rollback, and real-device behavior.");
  }
  if (["vue2", "jquery"].includes(request.targetFramework)) {
    result.push("Obtain explicit legacy-target approval, maintenance owner, security exception, and dated exit criteria.");
  }
  if (request.targetFramework === "vue3") {
    result.push("Vue Router declaration compatibility sets exactOptionalPropertyTypes=false; preserve optional-versus-undefined API semantics with explicit domain tests.");
  }
  return result;
}

export function generateUiProject(request: UiProjectGenerationRequest): GeneratedUiProject {
  const valid = validateUiProjectGenerationRequest(request);
  const profile = uiTargetProfile(valid.targetFramework);
  const route = uiConversionRoute(valid.source.framework, valid.targetFramework);
  const projectId = createHash("sha256").update(canonical(valid)).digest("hex").slice(0, 24);
  const openObligations = obligations(valid);
  const renderedRoutes = valid.uiIr.routes.map(item => {
    const component = componentForRoute(valid.uiIr.components, item);
    return { ...item, title: component.name, text: component.text };
  });
  const targetFiles = renderTargetProject({
    request: valid,
    profile,
    safeProjectName: valid.projectName,
    routes: renderedRoutes,
  });
  const files: Record<string, string> = {
    ...targetFiles,
    ...commonFiles(valid, projectId, openObligations),
  };
  if (!["flutter", "harmony-arkui"].includes(valid.targetFramework)) {
    files[".npmrc"] = "save-exact=true\npackage-lock=true\nengine-strict=true\nfund=false\naudit=true\n";
    files[".nvmrc"] = `${profile.nodeVersion ?? profile.runtimeVersion}\n`;
  }
  if (valid.targetFramework === "flutter") {
    files[".fvmrc"] = `${JSON.stringify({ flutter: profile.frameworkVersion }, null, 2)}\n`;
  }
  if (valid.targetFramework === "harmony-arkui") {
    files[".elmos-harmony-runner.json"] = `${JSON.stringify({
      schemaVersion: "1.0",
      sdk: profile.runtimeVersion,
      apiLevel: 20,
      runnerProfile: "harmonyos-6.0.0-api20",
      signing: "NOT_RUN",
      deviceEvidence: "NOT_RUN",
    }, null, 2)}\n`;
  }

  for (const required of profile.requiredProjectFiles) {
    if (!(required in files)) throw new Error(`target template omitted required file: ${required}`);
  }
  const contentDigest = digest(files);
  files["elmos.ui-migration.json"] = `${JSON.stringify({
    schemaVersion: "1.0",
    projectId,
    direction: route,
    targetProfile: profile,
    digestScope: "all generated files except elmos.ui-migration.json",
    contentDigest,
    ownership: {
      generated: Object.keys(files).sort(),
      generatedOnce: [".env.example"],
      protected: [],
      manual: [],
    },
    verification: {
      dependencyLock: "NOT_RUN",
      targetBuild: "NOT_RUN",
      targetStartup: "NOT_RUN",
      browserOrDeviceJourney: "NOT_RUN",
      accessibility: "NOT_RUN",
      visualParity: "NOT_RUN",
      holdout: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    },
  }, null, 2)}\n`;
  return {
    schemaVersion: "1.0",
    projectId,
    route,
    targetProfile: profile,
    contentDigest,
    files,
    obligations: openObligations,
    verification: {
      staticGeneration: "PASSED",
      dependencyLock: "NOT_RUN",
      targetBuild: "NOT_RUN",
      targetStartup: "NOT_RUN",
      browserOrDeviceJourney: "NOT_RUN",
      accessibility: "NOT_RUN",
      visualParity: "NOT_RUN",
      holdout: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    },
  };
}

export function uiProjectGenerationCapabilities(): Readonly<Record<string, unknown>> {
  return {
    schemaVersion: "1.0",
    exactTargetProfiles: uiTargetProfiles(),
    directedRoutes: uiConversionRoutes(),
    directedRouteCount: uiConversionRoutes().length,
    recommendedExtensions: recommendedExtensionProfiles,
    generation: "STATIC_PROJECT_AND_CONFIGURATION_READY",
    dependencyLock: "NOT_RUN",
    customerCodeExecution: false,
    runtimeEvidence: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
}
