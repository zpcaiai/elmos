export type Framework = "ANGULARJS" | "ANGULAR" | "VUE2" | "VUE3" | "REACT" | "JQUERY" | "UNKNOWN";
export type PackageManager = "NPM" | "YARN_CLASSIC" | "YARN_MODERN" | "PNPM" | "BOWER" | "MIXED" | "UNKNOWN";
export type ClientPlatform = "WEB" | "DESKTOP" | "ANDROID" | "IOS";

export type FrontendState =
  | "DISCOVERY"
  | "BASELINE_CAPTURING"
  | "TARGET_PLANNING"
  | "DESIGN_SYSTEM_PREPARING"
  | "COMPATIBILITY_LAYER_BUILDING"
  | "ROUTE_MIGRATING"
  | "COMPONENT_MIGRATING"
  | "STATE_MIGRATING"
  | "CONTRACT_VALIDATING"
  | "VISUAL_VALIDATING"
  | "ACCESSIBILITY_VALIDATING"
  | "CLIENT_PERFORMANCE_VALIDATING"
  | "INTERNAL_RELEASE"
  | "CANARY_RELEASE"
  | "PROGRESSIVE_CUTOVER"
  | "STABILITY_HOLD"
  | "LEGACY_CLIENT_READ_ONLY"
  | "DECOMMISSIONED";

export type FrontendExceptionState =
  | "FRONTEND_BUILD_UNREPRODUCIBLE"
  | "ROUTE_INVENTORY_INCOMPLETE"
  | "DYNAMIC_COMPONENT_UNRESOLVED"
  | "VISUAL_BASELINE_UNSTABLE"
  | "ACCESSIBILITY_REGRESSION"
  | "AUTH_FLOW_REGRESSION"
  | "BFF_CONTRACT_BREAKING"
  | "CLIENT_STORAGE_INCOMPATIBLE"
  | "OFFLINE_SYNC_REGRESSION"
  | "DESKTOP_INTEGRATION_BLOCKER"
  | "MOBILE_STORE_BLOCKER"
  | "CUTOVER_PAUSED";

const stateOrder: readonly FrontendState[] = [
  "DISCOVERY", "BASELINE_CAPTURING", "TARGET_PLANNING", "DESIGN_SYSTEM_PREPARING",
  "COMPATIBILITY_LAYER_BUILDING", "ROUTE_MIGRATING", "COMPONENT_MIGRATING",
  "STATE_MIGRATING", "CONTRACT_VALIDATING", "VISUAL_VALIDATING",
  "ACCESSIBILITY_VALIDATING", "CLIENT_PERFORMANCE_VALIDATING", "INTERNAL_RELEASE",
  "CANARY_RELEASE", "PROGRESSIVE_CUTOVER", "STABILITY_HOLD",
  "LEGACY_CLIENT_READ_ONLY", "DECOMMISSIONED"
];

export function advanceFrontendState(current: FrontendState, requested: FrontendState): FrontendState {
  const currentIndex = stateOrder.indexOf(current);
  const requestedIndex = stateOrder.indexOf(requested);
  if (requestedIndex !== currentIndex + 1) {
    throw new Error(`frontend state must advance exactly one stage: ${current} -> ${requested}`);
  }
  return requested;
}

export interface Finding {
  readonly code: string;
  readonly severity: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  readonly path: string;
  readonly evidence: string;
}

export interface WorkspaceInventory {
  readonly snapshotId: string;
  readonly packageManager: PackageManager;
  readonly lockfiles: readonly string[];
  readonly frameworks: readonly Framework[];
  readonly buildTools: readonly string[];
  readonly platforms: readonly ClientPlatform[];
  readonly entryPoints: readonly string[];
  readonly findings: readonly Finding[];
}

export interface RouteNode {
  readonly routeId: string;
  readonly applicationId: string;
  readonly path: string;
  readonly routeType: string;
  readonly componentIds: readonly string[];
  readonly requiredPermissions: readonly string[];
  readonly confidence: number;
}

export interface ComponentNode {
  readonly componentId: string;
  readonly framework: Framework;
  readonly sourcePath: string;
  readonly stateKinds: readonly string[];
  readonly eventKinds: readonly string[];
}

export interface UiSemanticGraph {
  readonly routes: readonly RouteNode[];
  readonly components: readonly ComponentNode[];
  readonly findings: readonly Finding[];
}

export type MigrationMode =
  | "BEHAVIOR_PRESERVING_MODERNIZATION"
  | "DESIGN_SYSTEM_ADOPTION"
  | "UX_REDESIGN"
  | "CLIENT_REPLATFORM";

export interface TargetProfile {
  readonly mode: MigrationMode;
  readonly targetFramework: string;
  readonly targetVersion: string;
  readonly browserProfileRef: string;
  readonly accessibilityTarget: string;
  readonly approvedBy?: string;
}

export interface MigrationStep {
  readonly stepId: string;
  readonly type: string;
  readonly dependsOn: readonly string[];
  readonly automatic: boolean;
  readonly requiredRunner: string;
  readonly acceptanceGates: readonly string[];
}

export interface FrontendMigrationPlan {
  readonly strategy: string;
  readonly steps: readonly MigrationStep[];
  readonly blockers: readonly string[];
}
