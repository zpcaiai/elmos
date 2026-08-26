import type { MiniappConversionRequest, MiniappPlatform, MiniappSourceInventory } from "./miniapp-types.js";
import { validateMiniappConversionRequest } from "./miniapp-contract-validation.js";
import {
  miniappIrDigest,
  resolveMiniappRouteComponentRoots,
  validateMiniappSemanticIr,
  type MiniappAnalyzedCapability,
  type MiniappAnalyzedComponent,
  type MiniappCompatibilityClass,
  type MiniappSemanticIr,
} from "./miniapp-semantic-ir.js";

export type MiniappDecisionRisk = "low" | "medium" | "high" | "critical";

export interface MiniappPlatformDescriptor {
  readonly platform: MiniappPlatform;
  readonly profileVersion: string;
  readonly docsReviewedAt: string;
  readonly templateExtension: string;
  readonly styleExtension: string;
  readonly eventPrefix: string;
  readonly conditionPrefix: string;
  readonly loopPrefix: string;
  readonly apiNamespace: string;
  readonly projectFile: string;
  readonly officialReferences: readonly string[];
  readonly docsReviewed: true;
  readonly accountTested: false;
  readonly buildTested: false;
}

export interface MiniappCapabilityDecision {
  readonly id: string;
  readonly capabilityId: string;
  readonly capabilityName: string;
  readonly platform: MiniappPlatform;
  readonly classification: MiniappCompatibilityClass;
  readonly strategy: string;
  readonly permission: readonly string[];
  readonly backendRequired: boolean;
  readonly reviewRisk: MiniappDecisionRisk;
  readonly requiredTests: readonly string[];
  readonly rationale: string;
  readonly sourceRefs: MiniappAnalyzedCapability["sourceRefs"];
}

export interface MiniappComponentDecision {
  readonly id: string;
  readonly componentId: string;
  readonly platform: MiniappPlatform;
  readonly classification: MiniappCompatibilityClass;
  readonly targetComponent: string;
  readonly strategy: "native" | "composite" | "redesign" | "decision" | "unsupported";
  readonly preserve: readonly string[];
  readonly requiredTests: readonly string[];
  readonly sourceRefs: MiniappAnalyzedComponent["sourceRefs"];
}

export interface MiniappStateLifecycleDecision {
  readonly platform: MiniappPlatform;
  readonly states: readonly {
    readonly stateId: string;
    readonly scope: string;
    readonly targetOwner: "component-data" | "page-data" | "app-store" | "storage-port";
    readonly updateMode: "set-data" | "immutable-store";
  }[];
  readonly effects: readonly {
    readonly effectId: string;
    readonly mount: string;
    readonly cleanup: string;
    readonly asyncPolicy: "cancel-on-unload" | "none" | "blocked-unknown";
  }[];
  readonly events: readonly {
    readonly componentId: string;
    readonly sourceEvent: string;
    readonly targetEvent: string;
    readonly propagation: "preserve" | "stop" | "unknown";
  }[];
  readonly sideEffectLedger: readonly {
    readonly effectId: string;
    readonly idempotencyRequired: boolean;
    readonly rollback: string;
  }[];
}

export interface MiniappStyleDecision {
  readonly platform: MiniappPlatform;
  readonly rules: readonly {
    readonly styleId: string;
    readonly selector: string;
    readonly classification: MiniappCompatibilityClass;
    readonly declarations: Readonly<Record<string, string>>;
    readonly unitConversions: readonly string[];
    readonly unsupported: readonly string[];
  }[];
  readonly tokens: Readonly<Record<string, string>>;
  readonly safeAreaPolicy: "native-safe-area-plus-explicit-fallback";
  readonly responsivePolicy: "preserve-declared-media-and-viewport-rules";
}

export interface MiniappDependencyDecision {
  readonly dependency: string;
  readonly usageEvidence: readonly string[];
  readonly action: "retain-shared" | "replace" | "rewrite" | "backend-move" | "isolate" | "remove-with-approval" | "blocked";
  readonly replacement: string | null;
  readonly rationale: string;
  readonly licenseState: "NOT_SCANNED";
  readonly vulnerabilityState: "NOT_SCANNED";
}

export interface MiniappCommerceSocialContract {
  readonly schemaVersion: "1.0";
  readonly identity: {
    readonly clientObtainsTemporaryCodeOnly: true;
    readonly serverExchangesCredential: true;
    readonly clientSecretStorage: "FORBIDDEN";
  };
  readonly order: {
    readonly decimalMoney: true;
    readonly idempotencyKeyRequired: true;
    readonly stateMachine: readonly ["draft", "created", "paying", "paid", "cancelled", "refunding", "refunded"];
  };
  readonly payment: {
    readonly serverAuthoritative: true;
    readonly sandboxOnlyWithoutApproval: true;
    readonly callbackSignatureRequired: true;
    readonly replayProtectionRequired: true;
  };
  readonly share: {
    readonly sceneParametersValidated: true;
    readonly sensitivePayloadForbidden: true;
  };
  readonly platformAdapters: Readonly<Record<MiniappPlatform, {
    readonly state: "CONTRACT_IMPLEMENTED_EXTERNAL_ACCOUNT_NOT_RUN";
    readonly productionAuthority: "EXTERNAL_ONLY";
  }>>;
}

export interface MiniappPrivacyAudit {
  readonly schemaVersion: "1.0";
  readonly platform: MiniappPlatform;
  readonly verdict: "passed" | "blocked" | "failed" | "unknown";
  readonly dataFlows: readonly {
    readonly capability: string;
    readonly sensitive: boolean;
    readonly destination: "platform" | "backend" | "local";
    readonly consentRequired: boolean;
  }[];
  readonly permissions: readonly {
    readonly permission: string;
    readonly purpose: string;
    readonly declared: boolean;
  }[];
  readonly secretFindings: readonly string[];
  readonly findings: readonly string[];
  readonly staticAudit: "EXECUTED";
  readonly platformReview: "NOT_RUN";
}

export interface MiniappConversionPlan {
  readonly schemaVersion: "1.0";
  readonly requestId: string;
  readonly requestDigest: string;
  readonly irDigest: string;
  readonly inventoryDigest: string;
  readonly platformProfiles: readonly MiniappPlatformDescriptor[];
  readonly capabilities: readonly MiniappCapabilityDecision[];
  readonly components: readonly MiniappComponentDecision[];
  readonly stateLifecycle: readonly MiniappStateLifecycleDecision[];
  readonly styles: readonly MiniappStyleDecision[];
  readonly dependencies: readonly MiniappDependencyDecision[];
  readonly commerceSocial: MiniappCommerceSocialContract;
  readonly policyApplication: MiniappPolicyApplication;
  readonly findings: readonly {
    readonly code: string;
    readonly platform: MiniappPlatform | "all";
    readonly classification: MiniappCompatibilityClass;
    readonly blocking: boolean;
    readonly message: string;
  }[];
  readonly summary: Readonly<Record<MiniappCompatibilityClass, number>>;
  readonly deterministicDigest: string;
}

export interface MiniappPolicyApplication {
  readonly priority: MiniappConversionRequest["policy"]["priority"];
  readonly unsupportedPolicy: MiniappConversionRequest["policy"]["unsupportedPolicy"];
  readonly unresolvedClassC: "BLOCK" | "DECISION_REQUIRED" | "REPORT_NONCRITICAL";
  readonly unresolvedClassDOrE: "BLOCK";
  readonly webviewFallback: {
    readonly requested: MiniappConversionRequest["policy"]["webviewFallback"];
    readonly applied: "DENIED" | "DECISION_REQUIRED" | "ALLOW_ONLY_WITH_EXPLICIT_PLAN_FINDING";
  };
  readonly fullPageCanvasFallback: {
    readonly requested: MiniappConversionRequest["policy"]["fullPageCanvasFallback"];
    readonly applied: "DENIED" | "DECISION_REQUIRED";
  };
}

const descriptors: Readonly<Record<MiniappPlatform, MiniappPlatformDescriptor>> = {
  wechat: {
    platform: "wechat",
    profileVersion: "2026-08-20.1",
    docsReviewedAt: "2026-08-20",
    templateExtension: ".wxml",
    styleExtension: ".wxss",
    eventPrefix: "bind",
    conditionPrefix: "wx:",
    loopPrefix: "wx:",
    apiNamespace: "wx",
    projectFile: "project.config.json",
    officialReferences: [
      "https://developers.weixin.qq.com/miniprogram/dev/framework/",
      "https://developers.weixin.qq.com/miniprogram/dev/devtools/ci.html",
    ],
    docsReviewed: true,
    accountTested: false,
    buildTested: false,
  },
  alipay: {
    platform: "alipay",
    profileVersion: "2026-08-20.1",
    docsReviewedAt: "2026-08-20",
    templateExtension: ".axml",
    styleExtension: ".acss",
    eventPrefix: "on",
    conditionPrefix: "a:",
    loopPrefix: "a:",
    apiNamespace: "my",
    projectFile: "mini.project.json",
    officialReferences: [
      "https://opendocs.alipay.com/mini",
      "https://opendocs.alipay.com/mini/02qh1f",
    ],
    docsReviewed: true,
    accountTested: false,
    buildTested: false,
  },
  douyin: {
    platform: "douyin",
    profileVersion: "2026-08-20.1",
    docsReviewedAt: "2026-08-20",
    templateExtension: ".ttml",
    styleExtension: ".ttss",
    eventPrefix: "bind",
    conditionPrefix: "tt:",
    loopPrefix: "tt:",
    apiNamespace: "tt",
    projectFile: "project.config.json",
    officialReferences: [
      "https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/",
      "https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/framework/general-configuration/",
    ],
    docsReviewed: true,
    accountTested: false,
    buildTested: false,
  },
  xiaohongshu: {
    platform: "xiaohongshu",
    profileVersion: "2026-08-20.1",
    docsReviewedAt: "2026-08-20",
    templateExtension: ".xhsml",
    styleExtension: ".css",
    eventPrefix: "bind",
    conditionPrefix: "xhs:",
    loopPrefix: "xhs:",
    apiNamespace: "xhs",
    projectFile: "project.config.json",
    officialReferences: [
      "https://miniapp.xiaohongshu.com/doc/DC923374",
      "https://miniapp.xiaohongshu.com/doc/DC626355",
    ],
    docsReviewed: true,
    accountTested: false,
    buildTested: false,
  },
};

const nativeComponent: Readonly<Record<string, string>> = {
  button: "button",
  "form-control": "input",
  media: "image",
  list: "scroll-view",
  navigation: "navigator",
  text: "text",
  container: "view",
  "view-component": "view",
  "route-outlet": "view",
};

const supportedSourceFrameworkVersions: Readonly<Record<MiniappConversionRequest["source"]["sourceLabel"], readonly string[]>> = {
  vue2: ["2.7.16"],
  vue3: ["3.5.39"],
  react: ["19.2.0", "19.2.7"],
  flutter: [],
  h5: [],
  typescript: ["5.9.2"],
  javascript: [],
  taro: ["4.1.0"],
  "uni-app": ["3.0.0"],
  "native-miniapp": [],
};

const frameworkDependencyByLabel: Readonly<Partial<Record<MiniappConversionRequest["source"]["sourceLabel"], string>>> = {
  vue2: "vue",
  vue3: "vue",
  react: "react",
  taro: "@tarojs/taro",
  "uni-app": "@dcloudio/uni-app",
  typescript: "typescript",
  flutter: "flutter",
};

const languageDependencyByLabel: Readonly<Partial<Record<MiniappConversionRequest["source"]["sourceLabel"], string>>> = {
  vue2: "typescript",
  vue3: "typescript",
  react: "typescript",
  typescript: "typescript",
  taro: "typescript",
  "uni-app": "typescript",
};

const supportedTargetTuples: Readonly<Record<MiniappPlatform, readonly string[]>> = {
  wechat: ["3.9.1|1.06.2504010"],
  alipay: ["2.10.2|3.9.4"],
  douyin: [],
  xiaohongshu: [],
};

const sensitiveCapabilityPermissions: Readonly<Record<string, readonly string[]>> = {
  address: ["address-data"],
  authorize: ["platform-authorization-scope"],
  location: ["user-location"],
  camera: ["camera"],
  album: ["photo-album"],
  media: ["media-selection"],
  microphone: ["microphone"],
  record: ["microphone"],
  contact: ["contacts"],
  bluetooth: ["bluetooth"],
  clipboard: ["clipboard"],
  biometric: ["biometric-authentication"],
  health: ["health-data"],
  invoice: ["invoice-data"],
  motion: ["motion-sensor"],
  scan: ["camera"],
  setting: ["platform-settings"],
  phone: ["phone-number"],
  login: ["account-login"],
  payment: ["merchant-account", "platform-payment-capability"],
  pay: ["merchant-account", "platform-payment-capability"],
  user: ["user-profile"],
};

export function miniappPlatformDescriptor(platform: MiniappPlatform): MiniappPlatformDescriptor {
  return descriptors[platform];
}

function capabilityClass(capability: MiniappAnalyzedCapability): MiniappCompatibilityClass {
  const value = capability.name.toLowerCase();
  if (value.includes("browser.") || value.includes("serviceworker") || value.includes("shadowdom")) return "C";
  if (value.includes("platformchannel")) return "D";
  if (capability.sensitive) return "D";
  if (/payment|pay|refund|phone|location|camera|album|user|login/.test(value)) return "D";
  if (/network|storage|navigation/.test(value)) return "B";
  return "B";
}

function permissionFor(capability: MiniappAnalyzedCapability): readonly string[] {
  const value = capability.name.toLowerCase();
  const result = new Set<string>();
  for (const [signal, permissions] of Object.entries(sensitiveCapabilityPermissions)) {
    if (value.includes(signal)) permissions.forEach(item => result.add(item));
  }
  return [...result].sort();
}

export function resolveMiniappCapabilities(
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
): readonly MiniappCapabilityDecision[] {
  return request.targets.flatMap(target => ir.capabilities.map(capability => {
    const classification = capabilityClass(capability);
    const permission = permissionFor(capability);
    const highRisk = classification === "D" || capability.sensitive;
    return {
      id: `capability.${target.platform}.${capability.id}`,
      capabilityId: capability.id,
      capabilityName: capability.name,
      platform: target.platform,
      classification,
      strategy: classification === "B" ? "platform-port-adapter"
        : classification === "C" ? "explicit-redesign-plan"
          : classification === "D" ? "owner-and-account-decision-required"
            : classification === "E" ? "unsupported-blocking"
              : "native-equivalent",
      permission,
      backendRequired: /network|login|payment|pay|refund/.test(capability.name.toLowerCase()),
      reviewRisk: highRisk ? "high" as const : "medium" as const,
      requiredTests: [
        "happy-path",
        ...(permission.length ? ["permission-denied", "consent-revoked"] : []),
        ...(/network|payment|pay/.test(capability.name.toLowerCase()) ? ["timeout", "duplicate-replay"] : []),
      ],
      rationale: `${capability.name} is planned against requested tuple ${target.platform}/${target.platformVersion}; account, installed toolchain and official runtime evidence remain NOT_RUN.`,
      sourceRefs: capability.sourceRefs,
    } satisfies MiniappCapabilityDecision;
  })).sort((left, right) => left.id.localeCompare(right.id, "en-US"));
}

export function mapMiniappComponents(
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
): readonly MiniappComponentDecision[] {
  return request.targets.flatMap(target => ir.components.map(component => {
    const targetComponent = nativeComponent[component.semanticRole] ?? "view";
    const unresolved = !Object.hasOwn(nativeComponent, component.semanticRole);
    const classification: MiniappCompatibilityClass = unresolved ? "C" : "A";
    return {
      id: `component.${target.platform}.${component.id}`,
      componentId: component.id,
      platform: target.platform,
      classification,
      targetComponent,
      strategy: unresolved ? "decision" : "native",
      preserve: ["props", "events", "children", "focus-order", "accessible-name"],
      requiredTests: ["render", "interaction", "accessibility-tree", "source-trace"],
      sourceRefs: component.sourceRefs,
    } satisfies MiniappComponentDecision;
  })).sort((left, right) => left.id.localeCompare(right.id, "en-US"));
}

function targetEvent(platform: MiniappPlatform, sourceEvent: string): string {
  const normalized = sourceEvent
    .replace(/^@|^v-on:/, "")
    .replace(/^(?:bind|catch|capture-bind|capture-catch)/, "")
    .replace(/^on(?=[A-Z])/, "")
    .toLowerCase();
  const event = normalized === "click" ? "tap" : normalized;
  return platform === "alipay" ? `on${event[0]?.toUpperCase() ?? ""}${event.slice(1)}` : `bind${event}`;
}

export function lowerMiniappStateLifecycle(
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
): readonly MiniappStateLifecycleDecision[] {
  return request.targets.map(target => ({
    platform: target.platform,
    states: ir.states.map(state => ({
      stateId: state.id,
      scope: state.scope,
      targetOwner: state.scope === "persistent" ? "storage-port" as const
        : state.scope === "application" ? "app-store" as const
          : state.scope === "page" ? "page-data" as const
            : "component-data" as const,
      updateMode: state.scope === "application" ? "immutable-store" as const : "set-data" as const,
    })),
    effects: ir.effects.map(effect => ({
      effectId: effect.id,
      mount: effect.trigger,
      cleanup: effect.cleanup,
      asyncPolicy: effect.asynchronous
        ? effect.cleanup === "present" ? "cancel-on-unload" as const : "blocked-unknown" as const
        : "none" as const,
    })),
    events: ir.components.flatMap(component => component.events.map(event => ({
      componentId: component.id,
      sourceEvent: event,
      targetEvent: targetEvent(target.platform, event),
      propagation: event.startsWith("catch") ? "stop" as const : "preserve" as const,
    }))),
    sideEffectLedger: ir.effects.map(effect => ({
      effectId: effect.id,
      idempotencyRequired: effect.asynchronous,
      rollback: effect.asynchronous ? "cancel-request-and-ignore-stale-response" : "restore-previous-state",
    })),
  }));
}

function lowerUnit(property: string, value: string): { value: string; conversion?: string; unsupported?: string } {
  if (/^-?\d+(?:\.\d+)?px$/.test(value) && !["border-width", "outline-width"].includes(property)) {
    const numeric = Number(value.slice(0, -2));
    return { value: `${numeric * 2}rpx`, conversion: `${value}->${numeric * 2}rpx` };
  }
  if (/(?:^|[^A-Za-z])[-+]?\d*\.?\d+(?:vh|vw)(?:$|[^A-Za-z])/u.test(value)) {
    return { value, unsupported: `${property}:${value}:requires-device-matrix` };
  }
  return { value };
}

const portableMiniappCssProperties = new Set([
  "align-content", "align-items", "align-self", "background", "background-color",
  "border", "border-bottom", "border-bottom-color", "border-bottom-left-radius",
  "border-bottom-right-radius", "border-bottom-style", "border-bottom-width", "border-color",
  "border-left", "border-left-color", "border-left-style", "border-left-width", "border-radius",
  "border-right", "border-right-color", "border-right-style", "border-right-width", "border-style",
  "border-top", "border-top-color", "border-top-left-radius", "border-top-right-radius",
  "border-top-style", "border-top-width", "border-width", "box-sizing", "color", "display",
  "flex", "flex-basis", "flex-direction", "flex-grow", "flex-shrink", "flex-wrap", "font",
  "font-family", "font-size", "font-style", "font-weight", "height", "justify-content",
  "line-height", "margin", "margin-bottom", "margin-left", "margin-right", "margin-top",
  "max-height", "max-width", "min-height", "min-width", "opacity", "padding", "padding-bottom",
  "padding-left", "padding-right", "padding-top", "position", "text-align", "text-decoration",
  "text-overflow", "transform", "transform-origin", "white-space", "width", "z-index",
]);

const miniappCssCapabilityMatrix: Readonly<Record<MiniappPlatform, ReadonlySet<string>>> = {
  wechat: portableMiniappCssProperties,
  alipay: portableMiniappCssProperties,
  douyin: portableMiniappCssProperties,
  xiaohongshu: portableMiniappCssProperties,
};

const sourceTagToMiniappTag: Readonly<Record<string, string>> = {
  article: "view",
  block: "view",
  button: "button",
  div: "view",
  flatlist: "scroll-view",
  footer: "view",
  form: "view",
  h1: "text",
  h2: "text",
  h3: "text",
  h4: "text",
  h5: "text",
  h6: "text",
  header: "view",
  image: "image",
  img: "image",
  input: "input",
  label: "text",
  li: "view",
  list: "scroll-view",
  main: "view",
  nav: "navigator",
  navigator: "navigator",
  ol: "view",
  outlet: "view",
  p: "text",
  page: "page",
  picker: "input",
  "router-view": "view",
  routerview: "view",
  "scroll-view": "scroll-view",
  scrollview: "scroll-view",
  section: "view",
  select: "input",
  span: "text",
  text: "text",
  textarea: "input",
  ul: "view",
  video: "image",
  view: "view",
};

function lowerMiniappSelector(selector: string): { value: string; unsupported?: string } {
  let unsupported: string | undefined;
  const value = selector.replace(
    /(^|[,\s>+~])([A-Za-z][A-Za-z0-9-]*)(?=[.#,\s>+~]|$)/gu,
    (match, prefix: string, rawTag: string) => {
      const targetTag = sourceTagToMiniappTag[rawTag.toLowerCase()];
      if (targetTag === undefined) {
        unsupported ??= `${selector}:tag-selector-${rawTag}-has-no-native-equivalent`;
        return match;
      }
      return `${prefix}${targetTag}`;
    },
  );
  return unsupported === undefined ? { value } : { value, unsupported };
}

function unsupportedMiniappCssCapability(
  platform: MiniappPlatform,
  property: string,
  value: string,
): string | undefined {
  if (!miniappCssCapabilityMatrix[platform].has(property)) {
    return `${property}:platform-css-capability-unbound`;
  }
  if (property === "display" && !/^(?:block|flex|inline|inline-block|none)$/iu.test(value.trim())) {
    return `${property}:${value}:display-mode-not-portable`;
  }
  if (property === "position" && !/^(?:absolute|relative|static)$/iu.test(value.trim())) {
    return `${property}:${value}:position-mode-not-portable`;
  }
  if (/\b(?:url|var)\s*\(/iu.test(value)) {
    return `${property}:${value}:external-or-custom-value-not-materialized`;
  }
  return undefined;
}

export function lowerMiniappStyles(
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
): readonly MiniappStyleDecision[] {
  return request.targets.map(target => ({
    platform: target.platform,
    rules: ir.styles.map(style => {
      const lowered: Record<string, string> = {};
      const conversions: string[] = [];
      const unsupported: string[] = [];
      const selector = lowerMiniappSelector(style.selector);
      if (selector.unsupported) unsupported.push(selector.unsupported);
      if (style.responsive) unsupported.push(`${style.selector}:nested-responsive-rule-requires-css-ast`);
      for (const [property, raw] of Object.entries(style.declarations).sort(([a], [b]) => a.localeCompare(b, "en-US"))) {
        const unsupportedCapability = unsupportedMiniappCssCapability(target.platform, property, raw);
        if (unsupportedCapability) {
          unsupported.push(unsupportedCapability);
          continue;
        }
        const decision = lowerUnit(property, raw);
        if (!decision.unsupported) lowered[property] = decision.value;
        if (decision.conversion) conversions.push(decision.conversion);
        if (decision.unsupported) unsupported.push(decision.unsupported);
      }
      return {
        styleId: style.id,
        selector: selector.value,
        classification: unsupported.length ? "C" as const : "A" as const,
        declarations: lowered,
        unitConversions: conversions,
        unsupported,
      };
    }),
    tokens: Object.fromEntries(ir.styles.flatMap(style => Object.entries(style.declarations)
      .filter(([property]) => /color|font|spacing|radius/.test(property))
      .map(([property, value]): [string, string] => [`${style.id}.${property}`, value]))
      .sort(([a], [b]) => a.localeCompare(b, "en-US"))),
    safeAreaPolicy: "native-safe-area-plus-explicit-fallback",
    responsivePolicy: "preserve-declared-media-and-viewport-rules",
  }));
}

const sourceOnlyPackages = new Set([
  "vue", "vue-router", "pinia", "vuex", "react", "react-dom", "react-router", "react-router-dom",
  "redux", "@reduxjs/toolkit", "zustand", "mobx", "flutter", "typescript", "@tarojs/taro", "@dcloudio/uni-app",
]);
const sourceBuildPackages = new Set(["vite", "webpack", "react-scripts", "@vue/cli-service", "@tarojs/cli", "@dcloudio/vite-plugin-uni"]);

export function planMiniappDependencies(
  ir: MiniappSemanticIr,
  inventory?: MiniappSourceInventory,
): readonly MiniappDependencyDecision[] {
  return ir.dependencies.map(dependency => {
    const sourceOnly = sourceOnlyPackages.has(dependency)
      || dependency.startsWith("@vue/")
      || dependency.startsWith("@tarojs/")
      || dependency.startsWith("@dcloudio/");
    const browserOnly = /dom|browser|service-worker|webpack|vite/.test(dependency);
    const usageRefs = ir.dependencyUsage[dependency] ?? [];
    const declared = inventory?.dependencies.find(item => item.name === dependency);
    const locked = inventory?.lockedDependencies.find(item => item.name === dependency);
    const buildOnly = declared?.scope === "dev" && (dependency === "typescript" || sourceBuildPackages.has(dependency));
    const manifestEvidence = buildOnly && locked
      ? [`${declared.sourcePath}:declared-${declared.scope}`, `${locked.sourcePath}:locked-${locked.version}`]
      : [];
    const unresolved = (usageRefs.length === 0 && manifestEvidence.length === 0) || (!sourceOnly && !browserOnly && !buildOnly);
    return {
      dependency,
      usageEvidence: [...usageRefs.map(ref => `${ref.path}:${ref.startLine}:${ref.startColumn}`), ...manifestEvidence],
      action: unresolved ? "blocked" as const : sourceOnly || buildOnly ? "rewrite" as const : browserOnly ? "replace" as const : "retain-shared" as const,
      replacement: unresolved ? null : sourceOnly || buildOnly ? "semantic-ir-native-generation" : browserOnly ? "platform-adapter-or-native-api" : null,
      rationale: usageRefs.length === 0 && manifestEvidence.length === 0
        ? "The dependency is declared but no exact source import/call-site evidence was recovered."
        : buildOnly
          ? "The source-only compiler/build dependency is declared and lock-resolved; it is not shipped into the native miniapp target."
        : sourceOnly
        ? "Source framework runtime is not shipped into a native miniapp target."
        : browserOnly
          ? "Browser/build-tool behavior needs a target capability decision."
          : "No generated target dependency or verified shared-domain boundary exists; migration is blocked.",
      licenseState: "NOT_SCANNED" as const,
      vulnerabilityState: "NOT_SCANNED" as const,
    };
  });
}

function classPolicyBlocks(
  classification: MiniappCompatibilityClass,
  request: MiniappConversionRequest,
): boolean {
  if (classification === "D" || classification === "E") return true;
  if (classification !== "C") return false;
  return request.policy.unsupportedPolicy !== "report-and-continue-noncritical";
}

function policyApplication(request: MiniappConversionRequest): MiniappPolicyApplication {
  return {
    priority: request.policy.priority,
    unsupportedPolicy: request.policy.unsupportedPolicy,
    unresolvedClassC: request.policy.unsupportedPolicy === "block"
      ? "BLOCK"
      : request.policy.unsupportedPolicy === "ask-decision"
        ? "DECISION_REQUIRED"
        : "REPORT_NONCRITICAL",
    unresolvedClassDOrE: "BLOCK",
    webviewFallback: {
      requested: request.policy.webviewFallback,
      applied: request.policy.webviewFallback === "deny"
        ? "DENIED"
        : request.policy.webviewFallback === "approval-required"
          ? "DECISION_REQUIRED"
          : "ALLOW_ONLY_WITH_EXPLICIT_PLAN_FINDING",
    },
    fullPageCanvasFallback: {
      requested: request.policy.fullPageCanvasFallback,
      applied: request.policy.fullPageCanvasFallback === "deny" ? "DENIED" : "DECISION_REQUIRED",
    },
  };
}

function routeComponentResolved(ir: MiniappSemanticIr, route: MiniappSemanticIr["routes"][number]): boolean {
  return resolveMiniappRouteComponentRoots(ir.components, route).length === 1;
}

const windowsReservedRouteSegment = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/iu;

export function exactMiniappTargetRoutePath(routePath: string): string | null {
  if (routePath === "/") return "index";
  if (!/^\/(?:[A-Za-z0-9_-]+)(?:\/[A-Za-z0-9_-]+)*$/u.test(routePath)) return null;
  const segments = routePath.slice(1).split("/");
  if (segments.some(segment => segment.length > 255 || windowsReservedRouteSegment.test(segment))) return null;
  return segments.join("/");
}

function applicationShellAmbiguity(ir: MiniappSemanticIr): string | null {
  const outlets = ir.components.filter(component => component.semanticRole === "route-outlet");
  if (outlets.length === 0) return null;
  const paths = new Set(outlets.flatMap(component => component.sourceRefs.map(ref => ref.path)));
  if (outlets.length !== 1 || paths.size !== 1) {
    return `${outlets.length} route outlets across ${paths.size} source modules cannot be assigned to one bounded application shell.`;
  }
  const shellPath = [...paths][0]!;
  const candidates = ir.components.filter(component => component.sourceRefs.some(ref => ref.path === shellPath)
    && component.semanticRole !== "non-render-metadata");
  const childIds = new Set(candidates.flatMap(component => component.children));
  const roots = candidates.filter(component => component.semanticRole !== "route-outlet" && !childIds.has(component.id));
  return roots.length === 1
    ? null
    : `${shellPath} has ${roots.length} independent rendered shell roots around its route outlet; exactly one is required.`;
}

const emittedStaticAttributes = new Set([
  "class", "className", "id", "role", "aria-label", "tabindex", "tabIndex", "name", "placeholder",
  "disabled",
]);

function normalizedDirectiveExpression(value: string): string {
  return value.trim().replace(/^\{\{/u, "").replace(/\}\}$/u, "").replace(/[\s()]/gu, "");
}

function supportedInteractionAttribute(
  component: MiniappAnalyzedComponent,
  name: string,
  value: string,
  interaction: MiniappSemanticIr["interactions"][number] | undefined,
): boolean {
  if (!interaction) return false;
  if (name === "required") {
    return value === "true" && component.id === interaction.inputComponentId;
  }
  if (name === "v-model") return component.id === interaction.inputComponentId;
  if (/^(?:@|v-on:|on|bind|catch)/u.test(name)) {
    return component.id === interaction.submitComponentId
      && component.eventBindings.some(binding => ["click", "tap"].includes(binding.event)
        && binding.handler === interaction.submitHandler
        && binding.modifiers.length === 0);
  }
  if (/^(?:v-for|wx:for|a:for|tt:for|xhs:for|wx:for-item|a:for-item|tt:for-item|xhs:for-item|wx:for-index|a:for-index|tt:for-index|xhs:for-index)$/u.test(name)) {
    return component.id === interaction.listComponentId;
  }
  if ([":key", "v-bind:key", "wx:key", "a:key", "tt:key", "xhs:key"].includes(name)) {
    if (component.id !== interaction.listComponentId || !component.collectionBinding) return false;
    const item = component.collectionBinding.itemAlias;
    const index = component.collectionBinding.indexAlias ?? "index";
    const normalized = normalizedDirectiveExpression(value);
    const templateKey = "`" + "${" + item + "}-${" + index + "}`";
    return normalized === index || normalized === `${item}+'-'+${index}` || normalized === `${item}+\"-\"+${index}`
      || normalized === templateKey;
  }
  if ([":disabled", "v-bind:disabled"].includes(name) && component.id === interaction.submitComponentId) {
    return normalizedDirectiveExpression(value) === `!${interaction.draftState}.trim`;
  }
  return false;
}

export function miniappCommerceSocialContract(): MiniappCommerceSocialContract {
  const adapter = {
    state: "CONTRACT_IMPLEMENTED_EXTERNAL_ACCOUNT_NOT_RUN" as const,
    productionAuthority: "EXTERNAL_ONLY" as const,
  };
  return {
    schemaVersion: "1.0",
    identity: { clientObtainsTemporaryCodeOnly: true, serverExchangesCredential: true, clientSecretStorage: "FORBIDDEN" },
    order: {
      decimalMoney: true,
      idempotencyKeyRequired: true,
      stateMachine: ["draft", "created", "paying", "paid", "cancelled", "refunding", "refunded"],
    },
    payment: { serverAuthoritative: true, sandboxOnlyWithoutApproval: true, callbackSignatureRequired: true, replayProtectionRequired: true },
    share: { sceneParametersValidated: true, sensitivePayloadForbidden: true },
    platformAdapters: { wechat: adapter, alipay: adapter, douyin: adapter, xiaohongshu: adapter },
  };
}

export function auditMiniappPrivacy(
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
  sourceFiles: Readonly<Record<string, string>>,
): readonly MiniappPrivacyAudit[] {
  const secretFindings = Object.entries(sourceFiles).flatMap(([path, content]) => {
    const patterns = [
      /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
      /(?:appsecret|client_secret|private_key|refresh_token)\s*[:=]\s*["'][^"']{8,}/i,
    ];
    return patterns.some(pattern => pattern.test(content)) ? [path] : [];
  }).sort();
  return request.targets.map(target => {
    const decisions = resolveMiniappCapabilities(ir, { ...request, targets: [target] });
    const permissions = [...new Set(decisions.flatMap(item => item.permission))].sort();
    const findings = [
      ...ir.unknowns.filter(item => item.severity === "critical" || item.severity === "error").map(item => item.code),
      ...(permissions.length > 0 ? ["PLATFORM_PERMISSION_AND_DISCLOSURE_EXTERNAL_REVIEW_NOT_RUN"] : []),
    ];
    return {
      schemaVersion: "1.0",
      platform: target.platform,
      verdict: secretFindings.length > 0 ? "failed" as const : findings.length > 0 ? "blocked" as const : "unknown" as const,
      dataFlows: ir.capabilities.map(capability => ({
        capability: capability.name,
        sensitive: capability.sensitive,
        destination: /network|login|payment|pay/.test(capability.name.toLowerCase()) ? "backend" as const
          : capability.name.includes("storage") ? "local" as const
            : "platform" as const,
        consentRequired: capability.sensitive,
      })),
      permissions: permissions.map(permission => ({
        permission,
        purpose: `Required by resolved capability for ${target.platform}`,
        declared: false,
      })),
      secretFindings,
      findings,
      staticAudit: "EXECUTED",
      platformReview: "NOT_RUN",
    };
  });
}

export function planMiniappConversion(
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
): MiniappConversionPlan {
  request = validateMiniappConversionRequest(request);
  validateMiniappSemanticIr(ir, inventory);
  if (
    ir.source.label !== request.source.sourceLabel
    || ir.source.frameworkVersion !== request.source.frameworkVersion
    || ir.source.snapshotDigest !== request.source.snapshotDigest
    || ir.source.revision !== request.source.revision
  ) {
    throw new Error("miniapp IR source tuple does not match the conversion request");
  }
  if (
    inventory.sourceRevision !== request.source.revision
    || inventory.sourceSnapshotDigest !== request.source.snapshotDigest
    || inventory.fileSetDigest !== request.source.snapshotDigest
    || inventory.selectedSourceLabel !== request.source.sourceLabel
  ) {
    throw new Error("miniapp inventory source tuple does not match the conversion request");
  }
  const capabilities = resolveMiniappCapabilities(ir, request);
  const components = mapMiniappComponents(ir, request);
  const stateLifecycle = lowerMiniappStateLifecycle(ir, request);
  const styles = lowerMiniappStyles(ir, request);
  const dependencies = planMiniappDependencies(ir, inventory);
  const coveredComponentIds = new Set(ir.interactions.flatMap(interaction => [
    interaction.inputComponentId,
    interaction.submitComponentId,
    interaction.listComponentId,
  ]));
  const componentFindings = components.flatMap(decision => {
    const component = ir.components.find(item => item.id === decision.componentId);
    if (!component) return [];
    const unresolved: Array<{ code: string; message: string }> = [];
    const interaction = ir.interactions.find(item => [item.inputComponentId, item.submitComponentId, item.listComponentId].includes(component.id));
    if (decision.strategy === "decision") {
      unresolved.push({
        code: "MINIAPP_CUSTOM_COMPONENT_UNRESOLVED",
        message: `${component.sourceTag} has no registered native or generated component implementation.`,
      });
    }
    if (component.semanticRole === "view-component" && component.children.length === 0) {
      unresolved.push({
        code: "MINIAPP_COMPONENT_BODY_UNRESOLVED",
        message: `${component.name} was recognized as a component declaration, but no exact render/template root is connected to it.`,
      });
    }
    if (component.eventBindings.length > 0 && !coveredComponentIds.has(component.id)) {
      unresolved.push({
        code: "MINIAPP_EVENT_BEHAVIOR_UNRESOLVED",
        message: `${component.sourceTag} event binding(s) ${component.eventBindings.map(item => `${item.event}:${item.handler}`).join(",")} are not represented by an executable interaction.`,
      });
    }
    if (component.modelBinding && !coveredComponentIds.has(component.id)) {
      unresolved.push({
        code: "MINIAPP_MODEL_BINDING_UNRESOLVED",
        message: `${component.sourceTag} model ${component.modelBinding} is not represented by an executable interaction.`,
      });
    }
    if (component.collectionBinding && !coveredComponentIds.has(component.id)) {
      unresolved.push({
        code: "MINIAPP_COLLECTION_BINDING_UNRESOLVED",
        message: `${component.sourceTag} collection ${component.collectionBinding.collection} is not represented by an executable interaction.`,
      });
    }
    if (component.collectionBinding && coveredComponentIds.has(component.id)
      && normalizedDirectiveExpression(component.collectionBinding.valueExpression) !== component.collectionBinding.itemAlias) {
      unresolved.push({
        code: "MINIAPP_COLLECTION_VALUE_EXPRESSION_UNRESOLVED",
        message: `${component.sourceTag} renders ${component.collectionBinding.valueExpression}; the bounded append-only interaction only proves direct ${component.collectionBinding.itemAlias} rendering.`,
      });
    }
    const conditionalDirectives = Object.entries(component.attributes)
      .filter(([name]) => /^(?:v-if|v-else-if|v-else|v-show|wx:if|wx:elif|wx:else|a:if|a:elif|a:else|tt:if|tt:elif|tt:else|xhs:if|xhs:elif|xhs:else)$/u.test(name))
      .map(([name, value]) => `${name}=${value}`);
    if (conditionalDirectives.length > 0) {
      unresolved.push({
        code: "MINIAPP_CONDITIONAL_RENDERING_UNRESOLVED",
        message: `${component.sourceTag} conditional directive(s) ${conditionalDirectives.join(",")} are not represented by an executable branch.`,
      });
    }
    if (/\{\{[\s\S]*\}\}/u.test(component.textContent) && !coveredComponentIds.has(component.id)) {
      unresolved.push({
        code: "MINIAPP_DYNAMIC_TEXT_BINDING_UNRESOLVED",
        message: `${component.sourceTag} dynamic text ${component.textContent} is not represented by an executable state binding.`,
      });
    }
    const unresolvedDynamicAttributes = Object.entries(component.attributes)
      .filter(([name, value]) => /^(?::|v-bind:)/u.test(name) || /\{\{[\s\S]*\}\}/u.test(value))
      .filter(([name]) => !(coveredComponentIds.has(component.id) && [":key", "v-bind:key", ":disabled", "v-bind:disabled"].includes(name)))
      .map(([name, value]) => `${name}=${value}`);
    if (unresolvedDynamicAttributes.length > 0) {
      unresolved.push({
        code: "MINIAPP_DYNAMIC_ATTRIBUTE_BINDING_UNRESOLVED",
        message: `${component.sourceTag} dynamic attribute(s) ${unresolvedDynamicAttributes.join(",")} are not represented by an executable state binding.`,
      });
    }
    const resourceAttributes = Object.entries(component.attributes)
      .filter(([name, value]) => ["src", ":src", "href", ":href", "poster", ":poster"].includes(name) && value.trim())
      .map(([name, value]) => `${name}=${value}`);
    if (resourceAttributes.length > 0) {
      unresolved.push({
        code: "MINIAPP_RESOURCE_BINDING_UNRESOLVED",
        message: `${component.sourceTag} resource binding(s) ${resourceAttributes.join(",")} have not been copied or adapted.`,
      });
    }
    const unsupportedAttributes = Object.entries(component.attributes)
      .filter(([name, value]) => !emittedStaticAttributes.has(name)
        && !supportedInteractionAttribute(component, name, value, interaction))
      .map(([name, value]) => `${name}=${value}`);
    if (unsupportedAttributes.length > 0) {
      unresolved.push({
        code: "MINIAPP_SOURCE_ATTRIBUTE_UNSUPPORTED",
        message: `${component.sourceTag} attribute(s) ${unsupportedAttributes.join(",")} are neither emitted nor represented by an executable interaction.`,
      });
    }
    if (["form", "textarea", "select", "picker", "video"].includes(component.sourceTag.toLowerCase())) {
      unresolved.push({
        code: "MINIAPP_SOURCE_CONTROL_TAG_UNSUPPORTED",
        message: `${component.sourceTag} has submit, value, selection, validation or media semantics that are not implemented by the bounded generator.`,
      });
    }
    return unresolved.map(item => ({
      ...item,
      platform: decision.platform,
      classification: "C" as const,
      blocking: true,
    }));
  });
  const dependencyFindings = dependencies.filter(item => item.action === "blocked").flatMap(item => request.targets.map(target => ({
    code: "MINIAPP_DEPENDENCY_ADAPTER_NOT_WIRED",
    platform: target.platform,
    classification: "C" as const,
    blocking: true,
    message: `${item.dependency}: ${item.rationale}`,
  })));
  const coveredStateIds = new Set(ir.interactions.flatMap(interaction => [interaction.draftStateId, interaction.collectionStateId]));
  const stateFindings = request.targets.flatMap(target => ir.states.flatMap(state => {
    if (state.scope === "persistent") {
      return [{
        code: "MINIAPP_PERSISTENT_STATE_NOT_WIRED",
        platform: target.platform,
        classification: "C" as const,
        blocking: true,
        message: `${state.name} requires an explicit storage schema, hydration, conflict and failure contract.`,
      }];
    }
    if (!coveredStateIds.has(state.id)) {
      return [{
        code: "MINIAPP_STATE_TRANSITION_UNRESOLVED",
        platform: target.platform,
        classification: "C" as const,
        blocking: true,
        message: `${state.name}/${state.scope} is not consumed by an executable, source-resolved interaction.`,
      }];
    }
    return [];
  }));
  const structuralFrameworkEffects = new Set([
    "vue.create-app",
    "vue.app.mount",
    "vue.app.use.router",
    "vue.app.use.pinia",
    "pinia.create",
    "vue-router.create-router",
    "vue-router.history.web-root",
  ]);
  const structuralEffects = ir.effects.filter(effect => structuralFrameworkEffects.has(effect.name));
  const structuralFrameworkFindings: readonly {
    readonly code: string;
    readonly platform: MiniappPlatform | "all";
    readonly classification: MiniappCompatibilityClass;
    readonly blocking: boolean;
    readonly message: string;
  }[] = (() => {
    const findings: Array<{
      readonly code: string;
      readonly platform: MiniappPlatform | "all";
      readonly classification: MiniappCompatibilityClass;
      readonly blocking: boolean;
      readonly message: string;
    }> = [];
    const add = (message: string): void => {
      findings.push({
        code: "MINIAPP_FRAMEWORK_BOOTSTRAP_UNRESOLVED",
        platform: "all",
        classification: "D",
        blocking: true,
        message,
      });
    };
    const byName = (name: string) => structuralEffects.filter(effect => effect.name === name);
    const unique = (name: string) => {
      const matches = byName(name);
      if (matches.length > 1) add(`${name} must have exactly one trace-bound structural effect; found ${matches.length}.`);
      return matches[0];
    };
    for (const effect of structuralEffects) {
      const validTrigger = effect.name === "vue.create-app" && effect.trigger === "application-bootstrap"
        || effect.name === "vue.app.mount" && effect.trigger === "native-application-entry"
        || effect.name === "vue.app.use.router" && effect.trigger === "application-plugin-install"
        || effect.name === "vue.app.use.pinia" && effect.trigger === "application-plugin-install"
        || effect.name === "pinia.create" && effect.trigger === "application-state-provider"
        || effect.name === "vue-router.create-router" && effect.trigger === "application-router"
        || effect.name === "vue-router.history.web-root" && effect.trigger === "native-page-stack";
      if (!validTrigger || !effect.instanceId) add(`${effect.name} is missing its exact synchronous trigger or instance binding.`);
      if (effect.asynchronous) add(`${effect.name} cannot be asynchronous in the application bootstrap contract.`);
    }
    const app = unique("vue.create-app");
    const mount = unique("vue.app.mount");
    if (app && !mount) add("createApp has no matching app.mount effect.");
    if (mount && !app) add("app.mount has no matching createApp effect.");
    if (app && mount && app.instanceId !== mount.instanceId) add("createApp and app.mount do not reference the same app instance.");
    const router = unique("vue-router.create-router");
    const history = unique("vue-router.history.web-root");
    if (router && (!history || router.relatedInstanceId !== history.instanceId)) add("createRouter must reference the exact createWebHistory(\"/\") instance.");
    if (history && !router) add("createWebHistory(\"/\") is not consumed by one createRouter effect.");
    const pinia = unique("pinia.create");
    const useRouter = unique("vue.app.use.router");
    const usePinia = unique("vue.app.use.pinia");
    if (useRouter && (!router || useRouter.relatedInstanceId !== router.instanceId)) add("app.use(router) must reference the exact createRouter instance.");
    if (usePinia && (!pinia || usePinia.relatedInstanceId !== pinia.instanceId)) add("app.use(pinia) must reference the exact createPinia instance.");
    if ((pinia && !usePinia) || (usePinia && !pinia)) add("createPinia and app.use(pinia) must form one complete application-state-provider trace.");
    return findings;
  })();
  const effectFindings = request.targets.flatMap(target => [
    ...ir.effects.filter(effect => !structuralFrameworkEffects.has(effect.name)).map(effect => ({
      code: "MINIAPP_EFFECT_NOT_WIRED",
      platform: target.platform,
      classification: "C" as const,
      blocking: true,
      message: `${effect.name}/${effect.trigger} is represented in the plan but has no generated lifecycle implementation.`,
    })),
    ...structuralFrameworkFindings.map(finding => ({ ...finding, platform: target.platform })),
  ]);
  const unmaterializedAssetPaths = [...new Set([
    ...(inventory?.assets ?? []),
    ...(inventory?.files.filter(file => file.status === "binary").map(file => file.path) ?? []),
  ])].sort((left, right) => left.localeCompare(right, "en-US"));
  const assetFindings = request.targets.flatMap(target => unmaterializedAssetPaths.map(assetPath => {
    const inventoryFile = inventory?.files.find(file => file.path === assetPath);
    return {
      code: "MINIAPP_ASSET_NOT_MATERIALIZED",
      platform: target.platform,
      classification: "C" as const,
      blocking: true,
      message: `${assetPath}${inventoryFile ? ` (${inventoryFile.digest})` : ""} is inventoried but has no typed IR node, rewritten reference, or generated target artifact.`,
    };
  }));
  const sourceVersions = supportedSourceFrameworkVersions[request.source.sourceLabel];
  const frameworkDependency = frameworkDependencyByLabel[request.source.sourceLabel];
  const declaredFrameworkVersion = frameworkDependency
    ? inventory?.dependencies.find(item => item.name === frameworkDependency && item.scope === "direct")?.version
    : undefined;
  const lockedFrameworkVersion = frameworkDependency
    ? inventory?.lockedDependencies.find(item => item.name === frameworkDependency)?.version
    : undefined;
  const languageDependency = languageDependencyByLabel[request.source.sourceLabel];
  const declaredLanguageVersion = languageDependency
    ? inventory?.dependencies.find(item => item.name === languageDependency)?.version
    : undefined;
  const lockedLanguageVersion = languageDependency
    ? inventory?.lockedDependencies.find(item => item.name === languageDependency)?.version
    : undefined;
  const declaredRuntimeVersion = inventory?.declaredRuntimes.find(item => item.runtime === "node")?.version;
  const declaredBuildTools = inventory?.dependencies.filter(item => sourceBuildPackages.has(item.name)) ?? [];
  const lockedBuildTools = declaredBuildTools.flatMap(item => {
    const locked = inventory?.lockedDependencies.find(candidate => candidate.name === item.name);
    return locked ? [{ name: item.name, declared: item.version, locked: locked.version }] : [];
  });
  const versionFindings = [
    ...(!sourceVersions.includes(request.source.frameworkVersion) ? [{
      code: "MINIAPP_SOURCE_VERSION_TUPLE_UNSUPPORTED",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `${request.source.sourceLabel}/${request.source.frameworkVersion} is not bound to parser profile ${sourceVersions.join("|") || "NONE"}.`,
    }] : []),
    ...(frameworkDependency && !lockedFrameworkVersion ? [{
      code: "MINIAPP_SOURCE_VERSION_LOCK_EVIDENCE_MISSING",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `${frameworkDependency}@${declaredFrameworkVersion ?? "missing"} has no parsed package-lock resolution bound to source bytes.`,
    }] : []),
    ...(declaredFrameworkVersion && declaredFrameworkVersion !== request.source.frameworkVersion ? [{
      code: "MINIAPP_SOURCE_VERSION_MANIFEST_MISMATCH",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `request ${request.source.frameworkVersion} does not match source manifest ${frameworkDependency}@${declaredFrameworkVersion}.`,
    }] : []),
    ...(lockedFrameworkVersion && lockedFrameworkVersion !== request.source.frameworkVersion ? [{
      code: "MINIAPP_SOURCE_VERSION_BINDING_MISMATCH",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `request ${request.source.frameworkVersion} does not match locked inventory ${frameworkDependency}@${lockedFrameworkVersion}.`,
    }] : []),
    ...(!languageDependency ? [{
      code: "MINIAPP_SOURCE_LANGUAGE_PROFILE_UNSUPPORTED",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `${request.source.sourceLabel}/${request.source.languageVersion} has no exact source-language profile bound to this analyzer.`,
    }] : []),
    ...(languageDependency && !lockedLanguageVersion ? [{
      code: "MINIAPP_SOURCE_LANGUAGE_LOCK_EVIDENCE_MISSING",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `${languageDependency}@${declaredLanguageVersion ?? "missing"} has no package-lock resolution for requested language ${request.source.languageVersion}.`,
    }] : []),
    ...(declaredLanguageVersion && declaredLanguageVersion !== request.source.languageVersion ? [{
      code: "MINIAPP_SOURCE_LANGUAGE_MANIFEST_MISMATCH",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `request language ${request.source.languageVersion} does not match manifest ${languageDependency}@${declaredLanguageVersion}.`,
    }] : []),
    ...(lockedLanguageVersion && lockedLanguageVersion !== request.source.languageVersion ? [{
      code: "MINIAPP_SOURCE_LANGUAGE_LOCK_MISMATCH",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `request language ${request.source.languageVersion} does not match lock ${languageDependency}@${lockedLanguageVersion}.`,
    }] : []),
    ...(!declaredRuntimeVersion ? [{
      code: "MINIAPP_SOURCE_RUNTIME_DECLARATION_MISSING",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `requested source runtime ${request.source.runtimeVersion} has no exact package.json engines.node declaration; installed source runtime execution remains NOT_RUN.`,
    }] : declaredRuntimeVersion !== request.source.runtimeVersion ? [{
      code: "MINIAPP_SOURCE_RUNTIME_MANIFEST_MISMATCH",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `request runtime ${request.source.runtimeVersion} does not match manifest engines.node ${declaredRuntimeVersion}.`,
    }] : []),
    ...(declaredBuildTools.length !== 1 || lockedBuildTools.length !== 1 ? [{
      code: "MINIAPP_SOURCE_BUILD_TOOL_BINDING_MISSING_OR_AMBIGUOUS",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `requested build tool ${request.source.buildToolVersion} requires exactly one known manifest dependency and package-lock resolution; found ${declaredBuildTools.length}/${lockedBuildTools.length}.`,
    }] : []),
    ...(lockedBuildTools.length === 1 && (lockedBuildTools[0]!.declared !== request.source.buildToolVersion
      || lockedBuildTools[0]!.locked !== request.source.buildToolVersion) ? [{
      code: "MINIAPP_SOURCE_BUILD_TOOL_VERSION_MISMATCH",
      platform: "all" as const,
      classification: "D" as const,
      blocking: true,
      message: `request build tool ${request.source.buildToolVersion} does not match ${lockedBuildTools[0]!.name} manifest/lock ${lockedBuildTools[0]!.declared}/${lockedBuildTools[0]!.locked}.`,
    }] : []),
    ...request.targets.filter(target => !supportedTargetTuples[target.platform].includes(`${target.platformVersion}|${target.toolchainVersion}`)).map(target => ({
      code: "MINIAPP_TARGET_VERSION_TUPLE_UNSUPPORTED",
      platform: target.platform,
      classification: "D" as const,
      blocking: true,
      message: `${target.platform}/${target.platformVersion}/${target.toolchainVersion} is not bound to generator profile ${miniappPlatformDescriptor(target.platform).profileVersion}.`,
    })),
  ];
  const routePathKeys = new Map<string, string[]>();
  for (const route of ir.routes) {
    const targetPath = exactMiniappTargetRoutePath(route.path);
    if (targetPath === null) continue;
    const key = targetPath.normalize("NFC").toLowerCase();
    routePathKeys.set(key, [...(routePathKeys.get(key) ?? []), route.path]);
  }
  const collidingRoutePaths = new Set([...routePathKeys.entries()]
    .filter(([, sourcePaths]) => sourcePaths.length > 1)
    .map(([key]) => key));
  const routePathFindings = request.targets.flatMap(target => ir.routes.flatMap(route => {
    const targetPath = exactMiniappTargetRoutePath(route.path);
    if (targetPath === null) {
      return [{
        code: "MINIAPP_ROUTE_PATH_NOT_LOSSLESS",
        platform: target.platform,
        classification: "D" as const,
        blocking: true,
        message: `${route.path} cannot be materialized as an exact native page path without normalization or character loss.`,
      }];
    }
    if (collidingRoutePaths.has(targetPath.normalize("NFC").toLowerCase())) {
      return [{
        code: "MINIAPP_ROUTE_PATH_COLLISION",
        platform: target.platform,
        classification: "D" as const,
        blocking: true,
        message: `${route.path} collides with another native page path under case-insensitive materialization.`,
      }];
    }
    return [];
  }));
  const emptyRouteFindings = ir.routes.length === 0
    ? request.targets.map(target => ({
      code: "MINIAPP_ROUTE_MANIFEST_EMPTY",
      platform: target.platform,
      classification: "D" as const,
      blocking: true,
      message: "No source route or uniquely traceable application root was recovered; an empty native page manifest cannot be treated as a generated candidate.",
    }))
    : [];
  const shellAmbiguity = applicationShellAmbiguity(ir);
  const findings = [
    ...ir.unknowns.map(item => ({
      code: item.code,
      platform: "all" as const,
      classification: item.classification,
      blocking: item.blocking || item.classification === "C" || classPolicyBlocks(item.classification, request),
      message: item.message,
    })),
    ...capabilities.map(item => ({
      code: item.classification === "D" || item.classification === "E"
        ? `MINIAPP_CAPABILITY_${item.classification}`
        : "MINIAPP_CAPABILITY_ADAPTER_NOT_WIRED",
      platform: item.platform,
      classification: item.classification === "A" || item.classification === "B" ? "C" as const : item.classification,
      blocking: true,
      message: `${item.capabilityName}: ${item.rationale}`,
    })),
    ...componentFindings,
    ...dependencyFindings,
    ...stateFindings,
    ...effectFindings,
    ...assetFindings,
    ...versionFindings,
    ...routePathFindings,
    ...emptyRouteFindings,
    ...(shellAmbiguity ? request.targets.map(target => ({
      code: "MINIAPP_APPLICATION_SHELL_AMBIGUOUS",
      platform: target.platform,
      classification: "D" as const,
      blocking: true,
      message: shellAmbiguity,
    })) : []),
    ...request.targets.flatMap(target => ir.routes.flatMap(route => [
      ...(!routeComponentResolved(ir, route) ? [{
        code: "MINIAPP_ROUTE_COMPONENT_UNRESOLVED",
        platform: target.platform,
        classification: "D" as const,
        blocking: true,
        message: `${route.path} component ${route.component}${route.componentModule ? ` from ${route.componentModule}` : ""} is not bound to one unique source component root.`,
      }] : []),
      ...(route.guards.length > 0 ? [{
        code: "MINIAPP_ROUTE_GUARD_UNRESOLVED",
        platform: target.platform,
        classification: "D" as const,
        blocking: true,
        message: `${route.path} guard(s) ${route.guards.join(",")} are not lowered into a target authorization/page-stack contract.`,
      }] : []),
      ...(route.parameters.length > 0 ? [{
        code: "MINIAPP_ROUTE_PARAMETER_UNRESOLVED",
        platform: target.platform,
        classification: "C" as const,
        blocking: true,
        message: `${route.path} parameter(s) ${route.parameters.join(",")} are not lowered into a target deep-link contract.`,
      }] : []),
    ])),
    ...(ir.components.length > 64 ? request.targets.map(target => ({
      code: "MINIAPP_COMPONENT_LIMIT_EXCEEDED",
      platform: target.platform,
      classification: "D" as const,
      blocking: true,
      message: `${ir.components.length} components exceed the bounded generator limit of 64.`,
    })) : []),
    ...styles.flatMap(item => item.rules.filter(rule => rule.classification !== "A").map(rule => ({
      code: "MINIAPP_STYLE_REDESIGN_REQUIRED",
      platform: item.platform,
      classification: rule.classification,
      // The bounded generator intentionally omits unsupported declarations.
      // Such a candidate cannot be locally closed even when policy permits a
      // noncritical report-and-continue workflow.
      blocking: true,
      message: `${rule.selector}: ${rule.unsupported.join(",")}`,
    }))),
  ].sort((left, right) => `${left.platform}:${left.code}:${left.message}`.localeCompare(`${right.platform}:${right.code}:${right.message}`, "en-US"));
  const allClasses: MiniappCompatibilityClass[] = [
    ...capabilities.map(item => item.classification),
    ...components.map(item => item.classification),
    ...findings.map(item => item.classification),
  ];
  const summary: Record<MiniappCompatibilityClass, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 };
  for (const value of allClasses) summary[value] += 1;
  const base = {
    schemaVersion: "1.0" as const,
    requestId: request.requestId,
    requestDigest: miniappIrDigest(request),
    irDigest: ir.deterministicDigest,
    inventoryDigest: miniappIrDigest(inventory),
    platformProfiles: request.targets.map(target => miniappPlatformDescriptor(target.platform)),
    capabilities,
    components,
    stateLifecycle,
    styles,
    dependencies,
    commerceSocial: miniappCommerceSocialContract(),
    policyApplication: policyApplication(request),
    findings,
    summary,
  };
  return { ...base, deterministicDigest: miniappIrDigest(base) };
}

export function validateMiniappConversionPlan(
  plan: MiniappConversionPlan,
  ir: MiniappSemanticIr,
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
): MiniappConversionPlan {
  const normalizedRequest = validateMiniappConversionRequest(request);
  const { deterministicDigest: suppliedDigest, ...body } = plan;
  if (suppliedDigest !== miniappIrDigest(body)) {
    throw new Error("miniapp plan deterministic digest does not match its content");
  }
  if (plan.inventoryDigest !== miniappIrDigest(inventory)) {
    throw new Error("miniapp plan does not belong to the exact source inventory");
  }
  const expected = planMiniappConversion(ir, normalizedRequest, inventory);
  if (plan.deterministicDigest !== expected.deterministicDigest) {
    throw new Error("miniapp plan does not match its canonical semantic reconstruction");
  }
  return plan;
}
