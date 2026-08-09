export type UiFrameworkId =
  | "vue2"
  | "vue3"
  | "react"
  | "react-native"
  | "jquery"
  | "flutter"
  | "harmony-arkui"
  | "angular"
  | "svelte";

export type UiPlatform = "WEB" | "ANDROID" | "IOS" | "HARMONYOS";

export interface UiIrNode {
  readonly id: string;
  readonly name: string;
  readonly kind: string;
  readonly references: readonly string[];
  readonly sourceRefs: readonly string[];
}

export interface UiIrRoute extends UiIrNode {
  readonly path: string;
  readonly componentId: string;
  readonly requiresAuth: boolean;
  readonly deepLink: boolean;
}

export interface UiIrComponent extends UiIrNode {
  readonly text: string;
  readonly accessibilityRole: string;
}

export interface UiIrUnknown extends UiIrNode {
  readonly severity: "critical" | "high" | "medium" | "low";
  readonly description: string;
  readonly owner: string;
}

export interface UiInteractionProject {
  readonly schemaVersion: "1.0";
  readonly sourceSnapshotDigest: string;
  readonly routes: readonly UiIrRoute[];
  readonly views: readonly UiIrNode[];
  readonly components: readonly UiIrComponent[];
  readonly states: readonly UiIrNode[];
  readonly actions: readonly UiIrNode[];
  readonly effects: readonly UiIrNode[];
  readonly forms: readonly UiIrNode[];
  readonly bindings: readonly UiIrNode[];
  readonly permissions: readonly UiIrNode[];
  readonly resources: readonly UiIrNode[];
  readonly designTokens: readonly UiIrNode[];
  readonly accessibility: readonly UiIrNode[];
  readonly nativeBoundaries: readonly UiIrNode[];
  readonly unknowns: readonly UiIrUnknown[];
}

export interface UiProjectGenerationRequest {
  readonly schemaVersion: "1.0";
  readonly projectName: string;
  readonly applicationId: string;
  readonly title: string;
  readonly source: {
    readonly framework: UiFrameworkId;
    readonly version: string;
    readonly platform: UiPlatform;
  };
  readonly targetFramework: UiFrameworkId;
  readonly packageName: string;
  readonly bundleId: string;
  readonly uiIr: UiInteractionProject;
}

/**
 * Exact bounded Batch32 interaction input.  This is deliberately a separate
 * discriminated request so schemaVersion 1.0 callers retain their existing
 * generic-node contract and cannot be silently upgraded to stronger claims.
 */
export interface UiInteractionBindingV2 {
  readonly id: string;
  readonly references: readonly string[];
  readonly sourceRefs: readonly string[];
}

export interface UiInteractionComponentV2 extends UiInteractionBindingV2 {
  readonly componentId: "interaction.shell";
  readonly templateKind: "ROUTE_DETAIL_WITH_INTERACTION_MATRIX";
  readonly keyedBy: "route.id";
  readonly titleBinding: "route.title";
  readonly textBinding: "route.text";
}

export interface UiInteractionStateV2 extends UiInteractionBindingV2 {
  readonly stateId: "bounded.counter";
  readonly initial: 0;
  readonly minimum: 0;
  readonly maximum: 2;
  readonly transition: "SATURATING_INCREMENT";
}

export interface UiInteractionActionV2 extends UiInteractionBindingV2 {
  readonly acceptedEvents: readonly ["BOOT", "NAVIGATE", "AUTHENTICATE", "SUBMIT", "CANCEL", "HYDRATE", "DISPLAY_CHANGE", "NATIVE_DEEPLINK"];
  readonly deniedAction: "BLOCK";
  readonly keyboardSubmit: "Enter";
}

export interface UiInteractionEffectV2 extends UiInteractionBindingV2 {
  readonly mountEffect: "LOAD_ON_MOUNT";
  readonly cleanupEffect: "CANCEL_ON_UNMOUNT";
  readonly maxExecutionsPerMount: 1;
  readonly staleResponsePolicy: "IGNORE_AFTER_CANCEL";
}

export interface UiInteractionFormV2 extends UiInteractionBindingV2 {
  readonly formId: "search";
  readonly fieldId: "query";
  readonly initialValue: "";
  readonly required: true;
  readonly minimumLength: 2;
  readonly validation: "ON_SUBMIT";
  readonly invalidCode: "QUERY_TOO_SHORT";
}

export interface UiInteractionApiV2 extends UiInteractionBindingV2 {
  readonly operationId: "search";
  readonly method: "POST";
  readonly path: "/api/search";
  readonly timeoutMs: 1000;
  readonly retry: "NEVER";
  readonly cacheScope: "TENANT_QUERY";
  readonly cancelOnUnmount: true;
}

export interface UiInteractionIdentityV2 extends UiInteractionBindingV2 {
  readonly anonymousRole: "ANONYMOUS";
  readonly authenticatedRole: "MEMBER";
  readonly requiredPermission: "search:execute";
  readonly deniedBehavior: "HIDE_AND_BLOCK";
  readonly tenantIsolation: "EXACT_TENANT_MATCH";
  readonly serverAuthorityRequired: true;
}

export interface UiInteractionRenderingV2 extends UiInteractionBindingV2 {
  readonly mode: "HYDRATABLE_CSR";
  readonly hydrationPolicy: "REQUIRE_MATCH";
  readonly mismatchBehavior: "RENDER_ERROR";
  readonly duplicateEffectsAllowed: false;
}

export interface UiInteractionAccessibilityV2 extends UiInteractionBindingV2 {
  readonly navigationLabel: "主要导航";
  readonly mainRole: "main";
  readonly headingLevel: 1;
  readonly formLabel: "搜索";
  readonly errorRole: "alert";
  readonly liveRegion: "polite";
  readonly invalidFocusTarget: "query";
  readonly keyboardSubmit: "Enter";
}

export interface UiInteractionI18nThemeResponsiveV2 extends UiInteractionBindingV2 {
  readonly supportedLocales: readonly ["zh-CN", "en-US"];
  readonly fallbackLocale: "en-US";
  readonly themes: readonly ["LIGHT", "DARK"];
  readonly defaultTheme: "LIGHT";
  readonly compactBreakpoint: 720;
  readonly compactColumns: 1;
  readonly wideColumns: 2;
}

export interface UiInteractionNativeV2 extends UiInteractionBindingV2 {
  readonly boundary: "ADAPTER";
  readonly capability: "OPEN_DEEP_LINK";
  readonly lifecycleStates: readonly ["FOREGROUND", "BACKGROUND"];
  readonly permission: "DEEPLINK_OPEN";
  readonly deniedBehavior: "NO_OP_REPORTED";
  readonly recovery: "FOREGROUND_RETRY";
}

export interface UiInteractionProjectV2 {
  readonly schemaVersion: "2.0";
  readonly profile: "bounded-frontend-interaction-v1";
  readonly sourceSnapshotDigest: string;
  readonly routes: readonly UiIrRoute[];
  readonly views: readonly UiIrNode[];
  readonly components: readonly UiIrComponent[];
  readonly componentTemplate: UiInteractionComponentV2;
  readonly stateManagement: UiInteractionStateV2;
  readonly actionEvent: UiInteractionActionV2;
  readonly effectLifecycle: UiInteractionEffectV2;
  readonly formBindingValidation: UiInteractionFormV2;
  readonly apiNetwork: UiInteractionApiV2;
  readonly identityPermission: UiInteractionIdentityV2;
  readonly renderingHydration: UiInteractionRenderingV2;
  readonly accessibilityFocus: UiInteractionAccessibilityV2;
  readonly i18nThemeResponsive: UiInteractionI18nThemeResponsiveV2;
  readonly nativePlatform: UiInteractionNativeV2;
  readonly unknowns: readonly UiIrUnknown[];
}

export interface UiProjectGenerationRequestV2 {
  readonly schemaVersion: "2.0";
  readonly projectName: string;
  readonly applicationId: string;
  readonly title: string;
  readonly source: {
    readonly framework: UiFrameworkId;
    readonly version: string;
    readonly platform: UiPlatform;
  };
  readonly targetFramework: UiFrameworkId;
  readonly packageName: string;
  readonly bundleId: string;
  readonly uiIr: UiInteractionProjectV2;
}

export interface ExactUiTargetProfile {
  readonly id: UiFrameworkId;
  readonly label: string;
  readonly frameworkVersion: string;
  readonly profileVersion: string;
  readonly status: "ACTIVE" | "LEGACY_CONDITIONAL";
  readonly platforms: readonly UiPlatform[];
  readonly language: string;
  readonly languageVersion: string;
  readonly runtime: string;
  readonly runtimeVersion: string;
  readonly nodeVersion?: string;
  readonly buildTool: string;
  readonly buildToolVersion: string;
  readonly packageManager: string;
  readonly packageManagerVersion: string;
  readonly router: string;
  readonly state: string;
  readonly rendering: string;
  readonly testTool: string;
  readonly runnerProfile: string;
  readonly requiredProjectFiles: readonly string[];
}

export interface UiConversionRoute {
  readonly routeId: string;
  readonly source: UiFrameworkId;
  readonly target: UiFrameworkId;
  readonly sourceProfileVersion: string;
  readonly targetProfileVersion: string;
  readonly supportState:
    | "PROJECT_GENERATION_READY"
    | "ADAPTER_REQUIRED"
    | "LEGACY_TARGET_CONDITIONAL";
  readonly semanticConversionEvidence: "NOT_RUN";
  readonly runtimeEvidence: "NOT_RUN";
  readonly certification: "NOT_CERTIFIED";
}

export interface GeneratedUiProject {
  readonly schemaVersion: "1.0";
  readonly projectId: string;
  readonly route: UiConversionRoute;
  readonly targetProfile: ExactUiTargetProfile;
  readonly contentDigest: string;
  readonly files: Readonly<Record<string, string>>;
  readonly obligations: readonly string[];
  readonly verification: {
    readonly staticGeneration: "PASSED";
    readonly dependencyLock: "NOT_RUN";
    readonly targetBuild: "NOT_RUN";
    readonly targetStartup: "NOT_RUN";
    readonly browserOrDeviceJourney: "NOT_RUN";
    readonly accessibility: "NOT_RUN";
    readonly visualParity: "NOT_RUN";
    readonly holdout: "NOT_RUN";
    readonly certification: "NOT_CERTIFIED";
  };
}
