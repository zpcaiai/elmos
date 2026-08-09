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
