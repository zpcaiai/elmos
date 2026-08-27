export const MINIAPP_PLATFORMS = [
  "wechat",
  "alipay",
  "douyin",
  "xiaohongshu",
] as const;

export type MiniappPlatform = typeof MINIAPP_PLATFORMS[number];

/**
 * Source labels are deliberately more exact than a broad "web" family. A route
 * for one label never implies support for another label or version.
 */
export const MINIAPP_SOURCE_LABELS = [
  "vue2",
  "vue3",
  "react",
  "flutter",
  "h5",
  "typescript",
  "javascript",
  "taro",
  "uni-app",
  "native-miniapp",
] as const;

export type MiniappSourceLabel = typeof MINIAPP_SOURCE_LABELS[number];

export const MINIAPP_EVIDENCE_STATES = [
  "PASSED",
  "FAILED",
  "INCONCLUSIVE",
  "NOT_RUN",
] as const;

export type MiniappEvidenceState = typeof MINIAPP_EVIDENCE_STATES[number];

export interface MiniappInventoryLimits {
  readonly maxFileCount: number;
  readonly maxFileBytes: number;
  readonly maxTotalBytes: number;
}

export interface MiniappSecretReference {
  readonly name: string;
  readonly reference: string;
}

export interface MiniappConversionSource {
  /** A normalized relative path within the already-authorized workspace. */
  readonly root: string;
  /** An immutable Git revision or content revision, never a mutable branch name. */
  readonly revision: string;
  readonly snapshotDigest: string;
  readonly sourceLabel: MiniappSourceLabel;
  readonly frameworkVersion: string;
  readonly languageVersion: string;
  readonly runtimeVersion: string;
  readonly buildToolVersion: string;
}

export interface MiniappConversionTarget {
  readonly platform: MiniappPlatform;
  readonly platformVersion: string;
  readonly toolchainVersion: string;
}

export interface MiniappConversionPolicy {
  readonly priority: "fidelity" | "maintainability" | "platform-native" | "code-sharing" | "balanced";
  readonly webviewFallback: "deny" | "approval-required" | "allow";
  readonly fullPageCanvasFallback: "deny" | "approval-required";
  readonly unsupportedPolicy: "block" | "report-and-continue-noncritical" | "ask-decision";
  readonly limits: MiniappInventoryLimits;
  /** Only broker references are accepted. Secret material is never part of a request. */
  readonly secretReferences: readonly MiniappSecretReference[];
}

export interface MiniappEvidenceReference {
  readonly role: string;
  readonly uri: string;
  readonly digest: string;
  readonly state: MiniappEvidenceState;
  readonly executor: string;
  readonly verifier: string;
  readonly synthetic: boolean;
  readonly byteCount: number;
}

export interface MiniappConversionRequest {
  readonly schemaVersion: "1.0";
  readonly requestId: string;
  readonly tenantId: string;
  readonly source: MiniappConversionSource;
  readonly targets: readonly MiniappConversionTarget[];
  readonly policy: MiniappConversionPolicy;
  readonly evidence: readonly MiniappEvidenceReference[];
}

export interface MiniappInventoryInputFile {
  readonly path: string;
  /** Source bytes are supplied by the caller; discovery never opens or executes a repository. */
  readonly content: string | Uint8Array;
}

export interface MiniappInventoryInput {
  readonly schemaVersion: "1.0";
  readonly inventoryId: string;
  readonly sourceRevision: string;
  readonly sourceSnapshotDigest: string;
  readonly sourceLabelHint: MiniappSourceLabel | "auto";
  readonly limits: MiniappInventoryLimits;
  readonly files: readonly MiniappInventoryInputFile[];
}

export type MiniappInventoryFileKind =
  | "typescript"
  | "javascript"
  | "vue-sfc"
  | "dart"
  | "html"
  | "style"
  | "json-config"
  | "yaml-config"
  | "miniapp-template"
  | "asset"
  | "binary"
  | "text";

export type MiniappInventoryFileStatus = "eligible" | "binary" | "parse-error";

export interface MiniappInventoryFile {
  readonly path: string;
  readonly digest: string;
  readonly byteCount: number;
  readonly kind: MiniappInventoryFileKind;
  readonly status: MiniappInventoryFileStatus;
  readonly reason?: string;
}

export type MiniappFrameworkSignalKind =
  | "manifest-dependency"
  | "language-config"
  | "platform-config"
  | "file-extension"
  | "source-import"
  | "entrypoint";

export interface MiniappFrameworkSignal {
  readonly sourceLabel: MiniappSourceLabel;
  readonly kind: MiniappFrameworkSignalKind;
  readonly path: string;
  readonly detail: string;
  readonly weight: number;
}

export interface MiniappFrameworkCandidate {
  readonly sourceLabel: MiniappSourceLabel;
  readonly confidence: number;
  readonly evidence: readonly MiniappFrameworkSignal[];
}

export interface MiniappFrameworkConflict {
  readonly sourceLabels: readonly MiniappSourceLabel[];
  readonly reason: string;
  readonly blocking: true;
}

export interface MiniappDependencyEvidence {
  readonly name: string;
  readonly version: string;
  readonly scope: "direct" | "dev";
  readonly sourcePath: string;
}

export interface MiniappLockedDependencyEvidence {
  readonly name: string;
  readonly version: string;
  readonly sourcePath: string;
  readonly sourceDigest: string;
  readonly packageManager: "npm" | "pnpm";
}

export interface MiniappDeclaredRuntimeEvidence {
  readonly runtime: "node";
  readonly version: string;
  readonly sourcePath: string;
  readonly sourceDigest: string;
  readonly evidenceKind: "manifest-declaration";
}

export type MiniappConfigurationKind = "package-json" | "package-lock" | "pnpm-lock" | "pubspec" | "app-config";

export interface MiniappConfigurationEvidence {
  readonly kind: MiniappConfigurationKind;
  readonly path: string;
  readonly digest: string;
  readonly parsed: boolean;
  readonly signals: readonly string[];
  readonly error?: string;
}

export interface MiniappInventoryCoverage {
  readonly totalFiles: number;
  readonly eligibleFiles: number;
  readonly processedFiles: number;
  readonly configurationFiles: number;
  readonly parsedConfigurationFiles: number;
  readonly ratio: number;
}

export interface MiniappInventoryFinding {
  readonly code:
    | "MINIAPP_FRAMEWORK_NOT_DETECTED"
    | "MINIAPP_FRAMEWORK_CONFLICT"
    | "MINIAPP_FRAMEWORK_HINT_MISMATCH"
    | "MINIAPP_SOURCE_FILE_UNSUPPORTED"
    | "MINIAPP_SOURCE_FILE_UNCLASSIFIED"
    | "MINIAPP_CONFIG_PARSE_ERROR";
  readonly severity: "WARNING" | "ERROR";
  readonly message: string;
  readonly paths: readonly string[];
  readonly blocking: boolean;
}

export interface MiniappSourceInventory {
  readonly schemaVersion: "1.0";
  readonly inventoryId: string;
  readonly sourceRevision: string;
  readonly sourceSnapshotDigest: string;
  readonly fileSetDigest: string;
  readonly files: readonly MiniappInventoryFile[];
  readonly frameworkCandidates: readonly MiniappFrameworkCandidate[];
  readonly selectedSourceLabel: MiniappSourceLabel | null;
  readonly frameworkConflicts: readonly MiniappFrameworkConflict[];
  readonly dependencies: readonly MiniappDependencyEvidence[];
  readonly lockedDependencies: readonly MiniappLockedDependencyEvidence[];
  readonly declaredRuntimes: readonly MiniappDeclaredRuntimeEvidence[];
  readonly configurationEvidence: readonly MiniappConfigurationEvidence[];
  readonly entrypoints: readonly string[];
  readonly routes: readonly string[];
  readonly components: readonly string[];
  readonly stores: readonly string[];
  readonly assets: readonly string[];
  readonly platformApiSignals: readonly string[];
  readonly coverage: MiniappInventoryCoverage;
  readonly findings: readonly MiniappInventoryFinding[];
}
