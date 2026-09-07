export interface VisualEnvironment {
  readonly imageDigest: string;
  readonly browserVersion: string;
  readonly operatingSystem: string;
  readonly fontHash: string;
  readonly viewport: string;
  readonly locale: string;
  readonly timezone: string;
  readonly fixtureHash: string;
}

export type VisualStatus = "VISUAL_MATCH" | "WITHIN_THRESHOLD" | "EXPECTED_APPROVED_CHANGE" | "REGRESSION" | "UNSTABLE_BASELINE" | "NOT_COMPARABLE";

export function evaluateVisualDifference(
  baseline: VisualEnvironment | undefined,
  target: VisualEnvironment | undefined,
  differenceRatio: number | undefined,
  threshold: number,
  approvedTargetDesign: boolean
): VisualStatus {
  if (!baseline || !target || differenceRatio === undefined) return "NOT_COMPARABLE";
  if (differenceRatio < 0 || threshold < 0) throw new Error("visual ratios must be non-negative");
  if (JSON.stringify(baseline) !== JSON.stringify(target)) return "UNSTABLE_BASELINE";
  if (differenceRatio === 0) return "VISUAL_MATCH";
  if (approvedTargetDesign) return "EXPECTED_APPROVED_CHANGE";
  return differenceRatio <= threshold ? "WITHIN_THRESHOLD" : "REGRESSION";
}

export type AccessibilityStatus = "VIOLATION" | "NEEDS_REVIEW" | "PASS_AUTOMATED" | "PASS_MANUAL" | "NOT_APPLICABLE" | "ACCEPTED_EXCEPTION";

export interface AccessibilityEvidence {
  readonly automatedViolations: number;
  readonly automatedIncomplete: number;
  readonly keyboardPassed?: boolean;
  readonly focusPassed?: boolean;
  readonly screenReaderPassed?: boolean;
  readonly manualEvidenceRefs?: readonly string[];
}

export function evaluateAccessibility(evidence: AccessibilityEvidence): AccessibilityStatus {
  if (evidence.automatedViolations < 0 || evidence.automatedIncomplete < 0) throw new Error("invalid accessibility counts");
  if (evidence.automatedViolations > 0 || evidence.keyboardPassed === false || evidence.focusPassed === false || evidence.screenReaderPassed === false) return "VIOLATION";
  if (evidence.automatedIncomplete > 0 || evidence.keyboardPassed !== true || evidence.focusPassed !== true
      || evidence.screenReaderPassed !== true || !evidence.manualEvidenceRefs?.length) return "NEEDS_REVIEW";
  return "PASS_MANUAL";
}

export function assessAngularJsWatch(source: string): "BEHAVIOR_TEST_REQUIRED" | "SAFE_CANDIDATE" {
  const watches = [...source.matchAll(/\$watch\s*\(/g)].length;
  return watches > 1 || /\$digest|\$apply|\$broadcast|\$emit/.test(source) ? "BEHAVIOR_TEST_REQUIRED" : "SAFE_CANDIDATE";
}

export function assessVueCompat(source: string): "ELIGIBLE" | "PARTIAL" | "INELIGIBLE" {
  if (/(?:_vnode|componentOptions|functionalContext|elm)[.\]]/.test(source)) return "INELIGIBLE";
  if (/render\s*\(|Vue\.extend|\$on\s*\(/.test(source)) return "PARTIAL";
  return "ELIGIBLE";
}

export type ReactClassDecision = "SAFE_FUNCTION_CONVERSION" | "FUNCTION_WITH_EFFECT" | "FUNCTION_WITH_LAYOUT_EFFECT" | "KEEP_ERROR_BOUNDARY_CLASS" | "MANUAL_REDESIGN";

export function classifyReactClass(source: string): ReactClassDecision {
  if (/componentDidCatch|getDerivedStateFromError/.test(source)) return "KEEP_ERROR_BOUNDARY_CLASS";
  if (/getSnapshotBeforeUpdate/.test(source)) return "MANUAL_REDESIGN";
  if (/getBoundingClientRect|scrollHeight|offsetWidth/.test(source)) return "FUNCTION_WITH_LAYOUT_EFFECT";
  if (/componentDidMount|componentDidUpdate|componentWillUnmount/.test(source)) return "FUNCTION_WITH_EFFECT";
  return "SAFE_FUNCTION_CONVERSION";
}

export function assessDomOwnership(source: string): "CONFLICT" | "ISOLATED" {
  const frameworkOwns = /ReactDOM|createRoot|createApp\s*\(|@Component/.test(source);
  const jqueryMutates = /\$\s*\([^)]*\)\.(?:html|append|remove|replaceWith)\s*\(/.test(source);
  return frameworkOwns && jqueryMutates ? "CONFLICT" : "ISOLATED";
}

export function jqueryUpgradePath(fromMajor: number, toMajor: number): readonly string[] {
  if (fromMajor < 1 || toMajor < fromMajor || toMajor > 4) throw new Error("unsupported jQuery version path");
  const path: string[] = [];
  if (fromMajor <= 2 && toMajor >= 3) path.push("MIGRATE_1", "JQUERY_3", "MIGRATE_3");
  if (toMajor >= 4) path.push("JQUERY_4", "MIGRATE_4", "REMOVE_MIGRATE");
  return path;
}

export function assessElectronSecurity(source: string): readonly string[] {
  const findings: string[] = [];
  if (/nodeIntegration\s*:\s*true/.test(source)) findings.push("ELECTRON_NODE_INTEGRATION");
  if (!/contextIsolation\s*:\s*true/.test(source)) findings.push("ELECTRON_CONTEXT_ISOLATION_DISABLED");
  if (/ipcMain\.on\s*\([^)]*(?:exec|shell|command)/s.test(source) || /child_process|exec\s*\(/.test(source)) findings.push("ELECTRON_IPC_UNVALIDATED");
  return findings;
}

export function assessDesktopWebReplacement(capabilities: readonly string[]): "FEASIBLE" | "DEVICE_CAPABILITY_BLOCKER" {
  const native = new Set(["SERIAL_PORT", "PRINTER", "SMART_CARD", "COM", "SCANNER", "NATIVE_LIBRARY"]);
  return capabilities.some(value => native.has(value)) ? "DEVICE_CAPABILITY_BLOCKER" : "FEASIBLE";
}

export interface ClientCompatibility {
  readonly activeClientVersions: readonly string[];
  readonly supportedClientVersions: readonly string[];
  readonly removedFields: readonly string[];
  readonly adapterAvailable: boolean;
}

export function evaluateClientCompatibility(value: ClientCompatibility): "SUPPORTED" | "SUPPORTED_WITH_ADAPTER" | "BLOCKED" {
  const unsupported = value.activeClientVersions.filter(version => !value.supportedClientVersions.includes(version));
  if (unsupported.length === 0 && value.removedFields.length === 0) return "SUPPORTED";
  return value.adapterAvailable ? "SUPPORTED_WITH_ADAPTER" : "BLOCKED";
}

export function validateOfflineReplay(operationIds: readonly string[], idempotencyEnforced: boolean): "PASS" | "DUPLICATE_RISK" {
  const duplicate = new Set(operationIds).size !== operationIds.length;
  return duplicate && !idempotencyEnforced ? "DUPLICATE_RISK" : "PASS";
}

export function validateDeepLinks(oldRoutes: readonly string[], targetRoutes: readonly string[], redirects: Readonly<Record<string, string>>): readonly string[] {
  return oldRoutes.filter(route => !targetRoutes.includes(route) && !redirects[route]);
}

export function assessServiceWorkerRelease(oldChunks: readonly string[], retainedChunks: readonly string[], reloadStrategy: boolean): "SAFE" | "CHUNK_404_RISK" {
  return oldChunks.every(chunk => retainedChunks.includes(chunk)) || reloadStrategy ? "SAFE" : "CHUNK_404_RISK";
}

export function assessBffResponsibilities(responsibilities: readonly string[]): "ADAPTER_BOUNDARY" | "BFF_BUSINESS_LOGIC_LEAK" {
  const forbidden = new Set(["PRICE_CALCULATION", "DISCOUNT_RULE", "TRANSACTION_OWNER", "CROSS_DOMAIN_TRANSACTION"]);
  return responsibilities.some(value => forbidden.has(value)) ? "BFF_BUSINESS_LOGIC_LEAK" : "ADAPTER_BOUNDARY";
}

export function mapDesignComponent(compatibility: "FULL" | "PARTIAL" | "REQUIRES_ADAPTER" | "REQUIRES_REDESIGN" | "NO_EQUIVALENT", approvedBy?: string): "AUTOMATIC" | "ADAPTER" | "HUMAN_DESIGN_REQUIRED" {
  if (compatibility === "FULL") return "AUTOMATIC";
  if (compatibility === "PARTIAL" || compatibility === "REQUIRES_ADAPTER") return "ADAPTER";
  if (!approvedBy?.trim()) return "HUMAN_DESIGN_REQUIRED";
  return "ADAPTER";
}

export interface CutoverEvidence {
  readonly requestedStage: "INTERNAL" | "CANARY" | "PROGRESSIVE" | "FULL" | "DECOMMISSION";
  readonly currentStage: "NONE" | "INTERNAL" | "CANARY" | "PROGRESSIVE" | "FULL";
  readonly webPassed: boolean;
  readonly desktopPassed: boolean;
  readonly androidPassed: boolean;
  readonly iosPassed: boolean;
  readonly bffPassed: boolean;
  readonly backendPassed: boolean;
  readonly usageEvidenceRefs: readonly string[];
  readonly approvedBy?: string;
}

export function evaluateClientCutover(evidence: CutoverEvidence): "PROMOTE" | "HOLD" | "HUMAN_REVIEW" | "BLOCKED" {
  const order = ["NONE", "INTERNAL", "CANARY", "PROGRESSIVE", "FULL", "DECOMMISSION"] as const;
  if (order.indexOf(evidence.requestedStage) !== order.indexOf(evidence.currentStage) + 1) return "BLOCKED";
  if (![evidence.webPassed, evidence.desktopPassed, evidence.androidPassed, evidence.iosPassed, evidence.bffPassed, evidence.backendPassed].every(Boolean)) return "HOLD";
  if (!evidence.usageEvidenceRefs.length) return "HOLD";
  if ((evidence.requestedStage === "FULL" || evidence.requestedStage === "DECOMMISSION") && !evidence.approvedBy?.trim()) return "HUMAN_REVIEW";
  return "PROMOTE";
}
