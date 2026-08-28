/**
 * Human handoff: what happens to the components the engine refuses.
 *
 * A fail-closed engine with a narrow subset hands the customer a pile of
 * BLOCKED components and a placeholder that throws. That is honest, but on
 * its own it is a dead end — the migration stops at the subset boundary.
 * This module is the other half: it lets a team take those components over
 * by hand and keep working, without the tool fighting them.
 *
 * Three things have to be true for that to be safe:
 *
 *   1. **A re-run must never overwrite hand-written code.** Someone ports
 *      `Chart.vue` by hand, someone else re-runs the pipeline next week,
 *      and a week of work is gone. Marked components are skipped on write,
 *      full stop.
 *
 *   2. **A hand port must go stale loudly.** The dangerous case is not
 *      overwriting — it is the opposite. `Chart.tsx` changes upstream and
 *      the hand-written `Chart.vue` silently keeps rendering last month's
 *      behavior. Every mark records the SOURCE hash it was ported from, so
 *      a later run can say `SOURCE_CHANGED_SINCE_PORT` instead of quietly
 *      shipping a stale component.
 *
 *   3. **Human work must never be counted as engine evidence.** A
 *      manually-ported component has been through no parser, no target
 *      compiler and no SSR comparison. It is tracked separately from
 *      `converted` and can never make a run look engine-complete.
 *
 * The manifest is a plain JSON file in the destination project, so it
 * lives with the migration, diffs in review, and needs no server.
 */
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import { RouteError } from "./models";

export const HANDOFF_FILE = "handoff.json";

export type HandoffState = "UNASSIGNED" | "ASSIGNED" | "MANUALLY_PORTED";
/** Explicit ownership label used in reports and review tooling. The legacy
 * state name remains readable for backwards-compatible manifests. */
export type PortOwnership = "ENGINE_GENERATED" | "HAND_PORTED";
export const HANDOFF_EVIDENCE_ROLES = [
  "TARGET_BUILD",
  "BROWSER_OR_DEVICE",
  "PLATFORM_RUNTIME",
  "INDEPENDENT_REVIEW",
] as const;
export type HandoffEvidenceRole = typeof HANDOFF_EVIDENCE_ROLES[number];

export interface HandoffEvidenceRecord {
  role: HandoffEvidenceRole;
  status: "PASSED" | "FAILED";
  artifactPath: string;
  artifactHash: string;
  executor: string;
  verifier: string | null;
  independent: boolean;
  observedAt: string;
  note: string | null;
}

export interface HandoffEntry {
  /** Source path, relative to the source repository. The stable identity
   * of a component across runs -- target paths can move as emitters change. */
  sourcePath: string;
  /** Component identity within the source file. Null is a legacy file-wide
   * mark and remains readable; new multi-component ports should set it. */
  componentName: string | null;
  state: HandoffState;
  ownership: PortOwnership;
  assignee: string | null;
  note: string | null;
  /** Reason the engine could not convert it, carried forward so the person
   * picking it up does not have to re-derive it. */
  reasonCode: string | null;
  /** SHA-256 of the SOURCE at the moment it was marked ported. This is
   * what makes staleness detectable. */
  sourceHashAtPort: string | null;
  /** SHA-256 of the hand-written TARGET at the moment it was marked. */
  targetHashAtPort: string | null;
  /** Exact target path whose bytes were hashed. Prevents a later pipeline
   * from checking an unrelated generated path against this ownership mark. */
  targetPathAtPort: string | null;
  /** Digest-bound observations. Presence is not certification; all four
   * roles must pass and the review producer/verifier must be independent
   * before the entry can become READY_FOR_EXTERNAL_GATE. */
  evidence: HandoffEvidenceRecord[];
  markedAt: string | null;
  updatedAt: string;
}

export interface HandoffManifest {
  schemaVersion: "1.0";
  kind: "elmos.component-dialect-handoff";
  entries: HandoffEntry[];
}

/** Conditions a re-run detects on an already-ported component. Each one is
 * reported; none is silently repaired. */
export type HandoffAlert =
  /** The source changed after the hand port. The port is stale, and this
   * is the failure mode that actually ships wrong behavior. */
  | "SOURCE_CHANGED_SINCE_PORT"
  /** The hand-written target is gone -- so the component is now neither
   * converted nor present. */
  | "PORTED_FILE_MISSING"
  /** The protected target changed after evidence/ownership was recorded. */
  | "PORTED_TARGET_CHANGED_SINCE_MARK"
  /** The current pipeline resolved a different target path than the one
   * whose bytes were marked. */
  | "PORTED_TARGET_PATH_MISMATCH"
  /** Bound evidence bytes are missing or no longer match their digest. */
  | "PORT_EVIDENCE_MISSING_OR_CHANGED"
  /** The subset widened and the engine could now convert this component.
   * Reported, never acted on: overwriting the hand version is the human's
   * decision, not the tool's. */
  | "AUTOMATIC_CONVERSION_NOW_AVAILABLE";

export function hashContent(contents: string | Buffer): string {
  return crypto.createHash("sha256").update(contents).digest("hex");
}

export function emptyManifest(): HandoffManifest {
  return { schemaVersion: "1.0", kind: "elmos.component-dialect-handoff", entries: [] };
}

export function manifestPath(destination: string): string {
  return path.join(destination, HANDOFF_FILE);
}

function isInside(root: string, candidate: string): boolean {
  return candidate !== root && candidate.startsWith(`${root}${path.sep}`);
}

/** Resolve a user- or manifest-provided file without permitting `..`, an
 * absolute path outside the migration root, or a symlink that escapes it. */
function resolveContainedFile(
  root: string,
  suppliedPath: string,
  code: string,
  allowAbsolute = false,
): { absolutePath: string; relativePath: string } {
  if (suppliedPath.trim() === "" || suppliedPath.includes("\0")) {
    throw new RouteError(`${code}: path must be a non-empty file path`);
  }
  if (path.isAbsolute(suppliedPath) && !allowAbsolute) {
    throw new RouteError(`${code}: absolute paths are not allowed: ${suppliedPath}`);
  }
  const resolvedRoot = path.resolve(root);
  const absolutePath = path.isAbsolute(suppliedPath)
    ? path.resolve(suppliedPath)
    : path.resolve(resolvedRoot, suppliedPath);
  if (!isInside(resolvedRoot, absolutePath)) {
    throw new RouteError(`${code}: ${suppliedPath} escapes ${resolvedRoot}`);
  }
  if (fs.existsSync(absolutePath)) {
    const realRoot = fs.realpathSync(resolvedRoot);
    const realFile = fs.realpathSync(absolutePath);
    if (!isInside(realRoot, realFile)) {
      throw new RouteError(`${code}: ${suppliedPath} resolves through a symlink outside ${realRoot}`);
    }
  }
  return {
    absolutePath,
    relativePath: path.relative(resolvedRoot, absolutePath).split(path.sep).join("/"),
  };
}

export function loadManifest(destination: string): HandoffManifest {
  const file = manifestPath(destination);
  if (!fs.existsSync(file)) return emptyManifest();
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    // Refusing here is deliberate. A corrupt manifest silently replaced by
    // an empty one would drop every "do not overwrite" mark, which is
    // exactly the outcome this module exists to prevent.
    throw new RouteError(
      `HANDOFF_MANIFEST_UNREADABLE: ${file} is not valid JSON (${error instanceof Error ? error.message : String(error)}). ` +
      `Refusing to continue, because treating it as empty would silently un-protect every manually ported component.`,
    );
  }
  const manifest = parsed as Partial<HandoffManifest>;
  if (manifest.kind !== "elmos.component-dialect-handoff" || !Array.isArray(manifest.entries)) {
    throw new RouteError(`HANDOFF_MANIFEST_INVALID: ${file} is not an ELMOS handoff manifest`);
  }
  return {
    schemaVersion: "1.0",
    kind: "elmos.component-dialect-handoff",
    // Older manifests predate explicit ownership. Normalize them without
    // losing the protection mark or treating missing metadata as a port.
    entries: manifest.entries.map((entry) => ({
      ...entry,
      componentName: entry.componentName ?? null,
      ownership: entry.ownership ?? (entry.state === "MANUALLY_PORTED" ? "HAND_PORTED" : "ENGINE_GENERATED"),
      targetPathAtPort: entry.targetPathAtPort ?? null,
      evidence: Array.isArray(entry.evidence) ? entry.evidence : [],
    })),
  };
}

export function saveManifest(destination: string, manifest: HandoffManifest): void {
  const sorted: HandoffManifest = {
    ...manifest,
    // Sorted so the manifest diffs cleanly in review rather than churning
    // on iteration order.
    entries: [...manifest.entries].sort((a, b) =>
      a.sourcePath.localeCompare(b.sourcePath)
        || (a.componentName ?? "").localeCompare(b.componentName ?? "")),
  };
  fs.mkdirSync(destination, { recursive: true });
  fs.writeFileSync(manifestPath(destination), JSON.stringify(sorted, null, 2) + "\n", "utf8");
}

export function findEntry(manifest: HandoffManifest, sourcePath: string, componentName?: string): HandoffEntry | undefined {
  if (componentName !== undefined) {
    return manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === componentName)
      ?? manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === null);
  }
  return manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === null)
    ?? manifest.entries.find((entry) => entry.sourcePath === sourcePath);
}

export function isManuallyPorted(manifest: HandoffManifest, sourcePath: string): boolean {
  return findEntry(manifest, sourcePath)?.state === "MANUALLY_PORTED";
}

function upsert(manifest: HandoffManifest, sourcePath: string, componentName: string | null = null): HandoffEntry {
  const existing = manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === componentName);
  if (existing) return existing;
  const created: HandoffEntry = {
    sourcePath, componentName, state: "UNASSIGNED", ownership: "ENGINE_GENERATED", assignee: null, note: null, reasonCode: null,
    sourceHashAtPort: null, targetHashAtPort: null, targetPathAtPort: null, evidence: [], markedAt: null,
    updatedAt: new Date().toISOString(),
  };
  manifest.entries.push(created);
  return created;
}

export interface AssignOptions {
  destination: string;
  sourcePath: string;
  componentName?: string;
  assignee: string;
  note?: string;
}

/** Assign a blocked component to a person. Assignment alone changes
 * nothing about writes -- only `markPorted` protects a file. */
export function assign(options: AssignOptions): HandoffEntry {
  const sourcePath = resolveContainedFile(options.destination, options.sourcePath, "HANDOFF_SOURCE_PATH_INVALID").relativePath;
  const manifest = loadManifest(options.destination);
  const entry = upsert(manifest, sourcePath, options.componentName ?? null);
  if (entry.state === "MANUALLY_PORTED") {
    throw new RouteError(
      `HANDOFF_ALREADY_PORTED: ${options.sourcePath} is already marked MANUALLY_PORTED. ` +
      `Reassigning would clear the source hash that makes staleness detectable; unmark it first if that is intended.`,
    );
  }
  entry.state = "ASSIGNED";
  entry.assignee = options.assignee;
  if (options.note !== undefined) entry.note = options.note;
  entry.updatedAt = new Date().toISOString();
  saveManifest(options.destination, manifest);
  return entry;
}

export interface MarkPortedOptions {
  destination: string;
  /** Source repository, needed to hash the source this port was made from. */
  repository: string;
  sourcePath: string;
  componentName?: string;
  /** Hand-written target, relative to the destination. */
  targetPath: string;
  assignee?: string;
  note?: string;
}

/**
 * Record that a human has ported this component by hand.
 *
 * Both files must exist. Marking a port whose target is absent would
 * create a protection entry guarding nothing, and would make a later run
 * skip writing a placeholder for a component that has no implementation at
 * all -- strictly worse than leaving it blocked.
 */
export function markPorted(options: MarkPortedOptions): HandoffEntry {
  const source = resolveContainedFile(options.repository, options.sourcePath, "HANDOFF_SOURCE_PATH_INVALID");
  const target = resolveContainedFile(options.destination, options.targetPath, "HANDOFF_TARGET_PATH_INVALID");
  const sourceFile = source.absolutePath;
  const targetFile = target.absolutePath;
  if (!fs.existsSync(sourceFile)) {
    throw new RouteError(`HANDOFF_SOURCE_NOT_FOUND: ${sourceFile}`);
  }
  if (!fs.existsSync(targetFile)) {
    throw new RouteError(
      `HANDOFF_TARGET_NOT_FOUND: ${targetFile}. Write the hand-ported component first -- ` +
      `marking a port with no file would protect nothing and suppress the placeholder that warns it is missing.`,
    );
  }

  const manifest = loadManifest(options.destination);
  const entry = upsert(manifest, source.relativePath, options.componentName ?? null);
  entry.state = "MANUALLY_PORTED";
  entry.ownership = "HAND_PORTED";
  if (options.assignee !== undefined) entry.assignee = options.assignee;
  if (options.note !== undefined) entry.note = options.note;
  entry.sourceHashAtPort = hashContent(fs.readFileSync(sourceFile, "utf8"));
  entry.targetHashAtPort = hashContent(fs.readFileSync(targetFile, "utf8"));
  entry.targetPathAtPort = target.relativePath;
  // A new mark binds different source/target bytes. Prior observations can
  // no longer apply, even when the path stayed the same.
  entry.evidence = [];
  entry.markedAt = new Date().toISOString();
  entry.updatedAt = entry.markedAt;
  saveManifest(options.destination, manifest);
  return entry;
}

/** Release a component back to the engine. Explicit, because the next run
 * will overwrite the hand-written file. */
export function unmark(destination: string, sourcePath: string, componentName?: string): HandoffEntry {
  const normalizedSourcePath = resolveContainedFile(destination, sourcePath, "HANDOFF_SOURCE_PATH_INVALID").relativePath;
  const manifest = loadManifest(destination);
  const entry = findEntry(manifest, normalizedSourcePath, componentName);
  if (!entry) throw new RouteError(`HANDOFF_ENTRY_NOT_FOUND: ${normalizedSourcePath}`);
  entry.state = entry.assignee ? "ASSIGNED" : "UNASSIGNED";
  entry.ownership = "ENGINE_GENERATED";
  entry.sourceHashAtPort = null;
  entry.targetHashAtPort = null;
  entry.targetPathAtPort = null;
  entry.evidence = [];
  entry.markedAt = null;
  entry.updatedAt = new Date().toISOString();
  saveManifest(destination, manifest);
  return entry;
}

export interface HandoffCheck {
  sourcePath: string;
  componentName: string | null;
  alerts: HandoffAlert[];
  detail: string[];
  evidenceState: "EVIDENCE_PENDING" | "EVIDENCE_FAILED" | "READY_FOR_EXTERNAL_GATE";
}

/**
 * Check a manually-ported component at run time.
 *
 * `engineCouldConvertNow` is passed in rather than recomputed here so the
 * caller stays the single place that decides convertibility.
 */
export function checkPortedEntry(
  entry: HandoffEntry,
  options: { repository: string; destination: string; targetPath: string; engineCouldConvertNow: boolean },
): HandoffCheck {
  const alerts: HandoffAlert[] = [];
  const detail: string[] = [];

  const target = resolveContainedFile(options.destination, options.targetPath, "HANDOFF_TARGET_PATH_INVALID");
  const targetFile = target.absolutePath;
  if (entry.targetPathAtPort !== null && entry.targetPathAtPort !== target.relativePath) {
    alerts.push("PORTED_TARGET_PATH_MISMATCH");
    detail.push(
      `${entry.sourcePath} was marked against ${entry.targetPathAtPort}, but this run resolved ${target.relativePath}. ` +
      "The ownership mark cannot be transferred to another path implicitly.",
    );
  }
  if (!fs.existsSync(targetFile)) {
    alerts.push("PORTED_FILE_MISSING");
    detail.push(`${entry.sourcePath} is marked MANUALLY_PORTED but ${target.relativePath} does not exist.`);
  } else if (entry.targetHashAtPort !== null) {
    const currentTarget = hashContent(fs.readFileSync(targetFile, "utf8"));
    if (currentTarget !== entry.targetHashAtPort) {
      alerts.push("PORTED_TARGET_CHANGED_SINCE_MARK");
      detail.push(
        `${target.relativePath} changed after the HAND_PORTED mark. Re-mark it to bind the new target bytes and ` +
        "invalidate evidence collected for the previous implementation.",
      );
    }
  }

  const sourceFile = resolveContainedFile(options.repository, entry.sourcePath, "HANDOFF_SOURCE_PATH_INVALID").absolutePath;
  if (entry.sourceHashAtPort !== null && fs.existsSync(sourceFile)) {
    const current = hashContent(fs.readFileSync(sourceFile, "utf8"));
    if (current !== entry.sourceHashAtPort) {
      alerts.push("SOURCE_CHANGED_SINCE_PORT");
      detail.push(
        `${entry.sourcePath} changed since it was hand-ported on ${entry.markedAt}. ` +
        `The hand-written component is stale and is NOT being updated automatically.`,
      );
    }
  }

  if (options.engineCouldConvertNow) {
    alerts.push("AUTOMATIC_CONVERSION_NOW_AVAILABLE");
    detail.push(
      `${entry.sourcePath} is now inside certified-component-v1 and could be converted automatically. ` +
      `The hand-written version was kept; unmark it to let the engine take over.`,
    );
  }

  let evidenceInvalid = false;
  for (const record of entry.evidence) {
    const artifactFile = resolveContainedFile(
      options.destination,
      record.artifactPath,
      "HANDOFF_EVIDENCE_PATH_INVALID",
      true,
    ).absolutePath;
    if (!fs.existsSync(artifactFile)
      || hashContent(fs.readFileSync(artifactFile)) !== record.artifactHash) {
      evidenceInvalid = true;
      alerts.push("PORT_EVIDENCE_MISSING_OR_CHANGED");
      detail.push(`${record.role} evidence ${record.artifactPath} is missing or no longer matches its bound digest.`);
    }
  }
  const evidenceByRole = new Map(entry.evidence.map((record) => [record.role, record]));
  const missingRoles = HANDOFF_EVIDENCE_ROLES.filter((role) => evidenceByRole.get(role)?.status !== "PASSED");
  const failed = entry.evidence.some((record) => record.status === "FAILED") || evidenceInvalid;
  const independent = evidenceByRole.get("INDEPENDENT_REVIEW");
  const independentValid = independent !== undefined && independent.status === "PASSED"
    && independent.independent && independent.verifier !== null && independent.verifier !== independent.executor;
  const evidenceState = failed || independent !== undefined && !independentValid
    ? "EVIDENCE_FAILED" as const
    : missingRoles.length === 0 && independentValid
      ? "READY_FOR_EXTERNAL_GATE" as const
      : "EVIDENCE_PENDING" as const;
  if (missingRoles.length > 0) detail.push(`HAND_PORTED evidence still required: ${missingRoles.join(", ")}.`);

  return { sourcePath: entry.sourcePath, componentName: entry.componentName, alerts: [...new Set(alerts)], detail, evidenceState };
}

export interface BindHandoffEvidenceOptions {
  destination: string;
  sourcePath: string;
  componentName?: string;
  role: HandoffEvidenceRole;
  status: "PASSED" | "FAILED";
  artifactPath: string;
  executor: string;
  verifier?: string;
  independent?: boolean;
  note?: string;
}

/** Bind real artifact bytes to one hand port. This records evidence but can
 * never produce certification. Independent review must name a distinct
 * verifier; self-review fails closed. */
export function bindHandoffEvidence(options: BindHandoffEvidenceOptions): HandoffEntry {
  if (!(HANDOFF_EVIDENCE_ROLES as readonly string[]).includes(options.role)) {
    throw new RouteError(`HANDOFF_EVIDENCE_ROLE_INVALID: ${options.role}`);
  }
  if (options.executor.trim() === "") throw new RouteError("HANDOFF_EVIDENCE_EXECUTOR_REQUIRED");
  if (options.role === "INDEPENDENT_REVIEW"
    && (!options.independent || options.verifier === undefined || options.verifier === options.executor)) {
    throw new RouteError("HANDOFF_INDEPENDENT_REVIEW_INVALID: verifier must be present, independent and distinct from executor");
  }
  const sourcePath = resolveContainedFile(options.destination, options.sourcePath, "HANDOFF_SOURCE_PATH_INVALID").relativePath;
  const manifest = loadManifest(options.destination);
  const entry = findEntry(manifest, sourcePath, options.componentName);
  if (entry === undefined || entry.state !== "MANUALLY_PORTED") {
    throw new RouteError(`HANDOFF_NOT_PORTED: ${options.sourcePath}`);
  }
  const artifact = resolveContainedFile(
    options.destination,
    options.artifactPath,
    "HANDOFF_EVIDENCE_PATH_INVALID",
    true,
  );
  const artifactFile = artifact.absolutePath;
  if (!fs.existsSync(artifactFile) || !fs.statSync(artifactFile).isFile()) {
    throw new RouteError(`HANDOFF_EVIDENCE_NOT_FOUND: ${artifactFile}`);
  }
  const record: HandoffEvidenceRecord = {
    role: options.role,
    status: options.status,
    artifactPath: artifact.relativePath,
    artifactHash: hashContent(fs.readFileSync(artifactFile)),
    executor: options.executor,
    verifier: options.verifier ?? null,
    independent: options.independent === true,
    observedAt: new Date().toISOString(),
    note: options.note ?? null,
  };
  entry.evidence = [...entry.evidence.filter((item) => item.role !== options.role), record]
    .sort((left, right) => left.role.localeCompare(right.role));
  entry.updatedAt = record.observedAt;
  saveManifest(options.destination, manifest);
  return entry;
}

export interface HandoffSummary {
  total: number;
  unassigned: number;
  assigned: number;
  manuallyPorted: number;
  /** Ported components carrying at least one alert. Non-zero means the
   * migration has open items regardless of how the conversion counts look. */
  stale: number;
  evidencePending: number;
  evidenceFailed: number;
  readyForExternalGate: number;
  byAssignee: { assignee: string; count: number }[];
}

export function summarize(manifest: HandoffManifest, checks: HandoffCheck[]): HandoffSummary {
  const counts = { UNASSIGNED: 0, ASSIGNED: 0, MANUALLY_PORTED: 0 };
  const byAssignee = new Map<string, number>();
  for (const entry of manifest.entries) {
    counts[entry.state] += 1;
    if (entry.assignee) byAssignee.set(entry.assignee, (byAssignee.get(entry.assignee) ?? 0) + 1);
  }
  return {
    total: manifest.entries.length,
    unassigned: counts.UNASSIGNED,
    assigned: counts.ASSIGNED,
    manuallyPorted: counts.MANUALLY_PORTED,
    stale: checks.filter((c) => c.alerts.some((a) => a !== "AUTOMATIC_CONVERSION_NOW_AVAILABLE")).length,
    evidencePending: checks.filter((check) => check.evidenceState === "EVIDENCE_PENDING").length,
    evidenceFailed: checks.filter((check) => check.evidenceState === "EVIDENCE_FAILED").length,
    readyForExternalGate: checks.filter((check) => check.evidenceState === "READY_FOR_EXTERNAL_GATE").length,
    byAssignee: [...byAssignee.entries()]
      .map(([assignee, count]) => ({ assignee, count }))
      .sort((a, b) => b.count - a.count || a.assignee.localeCompare(b.assignee)),
  };
}
