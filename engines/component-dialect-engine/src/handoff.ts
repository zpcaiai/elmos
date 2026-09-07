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

export interface HandoffEntry {
  /** Source path, relative to the source repository. The stable identity
   * of a component across runs -- target paths can move as emitters change. */
  sourcePath: string;
  /** Component declaration inside sourcePath. Null is the legacy
   * file-scoped identity used by manifests written before multi-component
   * handoffs were supported. New repository migrations always write the
   * exact component name so two declarations in one TSX file can be owned
   * independently. */
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
  /** Exact hand-written target (a file for web targets or a component
   * directory for Mini Programs), relative to the destination. */
  targetPathAtPort: string | null;
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
  /** The subset widened and the engine could now convert this component.
   * Reported, never acted on: overwriting the hand version is the human's
   * decision, not the tool's. */
  | "AUTOMATIC_CONVERSION_NOW_AVAILABLE";

export function hashContent(contents: string): string {
  return crypto.createHash("sha256").update(contents, "utf8").digest("hex");
}

export function emptyManifest(): HandoffManifest {
  return { schemaVersion: "1.0", kind: "elmos.component-dialect-handoff", entries: [] };
}

export function manifestPath(destination: string): string {
  return path.join(destination, HANDOFF_FILE);
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
    })),
  };
}

export function saveManifest(destination: string, manifest: HandoffManifest): void {
  const sorted: HandoffManifest = {
    ...manifest,
    // Sorted so the manifest diffs cleanly in review rather than churning
    // on iteration order.
    entries: [...manifest.entries].sort((a, b) =>
      a.sourcePath.localeCompare(b.sourcePath) || (a.componentName ?? "").localeCompare(b.componentName ?? ""),
    ),
  };
  fs.mkdirSync(destination, { recursive: true });
  fs.writeFileSync(manifestPath(destination), JSON.stringify(sorted, null, 2) + "\n", "utf8");
}

export function findEntry(manifest: HandoffManifest, sourcePath: string, componentName?: string): HandoffEntry | undefined {
  if (componentName !== undefined) {
    const exact = manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === componentName);
    if (exact) return exact;
    // Backwards compatibility: an old file-scoped mark still protects the
    // file. New marks never use this ambiguous identity.
    return manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === null);
  }
  return manifest.entries.find((entry) => entry.sourcePath === sourcePath);
}

export function isManuallyPorted(manifest: HandoffManifest, sourcePath: string, componentName?: string): boolean {
  return findEntry(manifest, sourcePath, componentName)?.state === "MANUALLY_PORTED";
}

function upsert(manifest: HandoffManifest, sourcePath: string, componentName: string | null): HandoffEntry {
  const existing = manifest.entries.find((entry) => entry.sourcePath === sourcePath && entry.componentName === componentName);
  if (existing) return existing;
  const created: HandoffEntry = {
    sourcePath, componentName, state: "UNASSIGNED", ownership: "ENGINE_GENERATED", assignee: null, note: null, reasonCode: null,
    sourceHashAtPort: null, targetHashAtPort: null, markedAt: null,
    targetPathAtPort: null,
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
  const manifest = loadManifest(options.destination);
  const entry = upsert(manifest, options.sourcePath, options.componentName ?? null);
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
  const sourceFile = path.join(options.repository, options.sourcePath);
  const targetFile = path.join(options.destination, options.targetPath);
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
  const entry = upsert(manifest, options.sourcePath, options.componentName ?? null);
  entry.state = "MANUALLY_PORTED";
  entry.ownership = "HAND_PORTED";
  if (options.assignee !== undefined) entry.assignee = options.assignee;
  if (options.note !== undefined) entry.note = options.note;
  entry.sourceHashAtPort = hashContent(fs.readFileSync(sourceFile, "utf8"));
  entry.targetHashAtPort = hashTarget(targetFile);
  entry.targetPathAtPort = options.targetPath;
  entry.markedAt = new Date().toISOString();
  entry.updatedAt = entry.markedAt;
  saveManifest(options.destination, manifest);
  return entry;
}

/** Release a component back to the engine. Explicit, because the next run
 * will overwrite the hand-written file. */
export function unmark(destination: string, sourcePath: string, componentName?: string): HandoffEntry {
  const manifest = loadManifest(destination);
  const entry = componentName === undefined
    ? findEntry(manifest, sourcePath)
    : manifest.entries.find((candidate) => candidate.sourcePath === sourcePath && candidate.componentName === componentName);
  if (!entry) throw new RouteError(`HANDOFF_ENTRY_NOT_FOUND: ${sourcePath}`);
  entry.state = entry.assignee ? "ASSIGNED" : "UNASSIGNED";
  entry.ownership = "ENGINE_GENERATED";
  entry.sourceHashAtPort = null;
  entry.targetHashAtPort = null;
  entry.targetPathAtPort = null;
  entry.markedAt = null;
  entry.updatedAt = new Date().toISOString();
  saveManifest(destination, manifest);
  return entry;
}

/** Stable digest for either a single target file or a Mini Program
 * four-file component directory. Relative names are included so renaming a
 * file cannot preserve the same digest accidentally. */
function hashTarget(target: string): string {
  if (!fs.statSync(target).isDirectory()) return hashContent(fs.readFileSync(target, "utf8"));
  const hash = crypto.createHash("sha256");
  const visit = (dir: string): void => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) throw new RouteError(`HANDOFF_TARGET_SYMLINK_FORBIDDEN: ${path.join(dir, entry.name)}`);
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile()) {
        hash.update(path.relative(target, full));
        hash.update("\0");
        hash.update(fs.readFileSync(full));
        hash.update("\0");
      }
    }
  };
  visit(target);
  return hash.digest("hex");
}

export interface HandoffCheck {
  sourcePath: string;
  alerts: HandoffAlert[];
  detail: string[];
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

  const targetFile = path.join(options.destination, options.targetPath);
  if (!fs.existsSync(targetFile)) {
    alerts.push("PORTED_FILE_MISSING");
    detail.push(`${entry.sourcePath} is marked MANUALLY_PORTED but ${options.targetPath} does not exist.`);
  }

  const sourceFile = path.join(options.repository, entry.sourcePath);
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

  return { sourcePath: entry.sourcePath, alerts, detail };
}

export interface HandoffSummary {
  total: number;
  unassigned: number;
  assigned: number;
  manuallyPorted: number;
  /** Ported components carrying at least one alert. Non-zero means the
   * migration has open items regardless of how the conversion counts look. */
  stale: number;
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
    byAssignee: [...byAssignee.entries()]
      .map(([assignee, count]) => ({ assignee, count }))
      .sort((a, b) => b.count - a.count || a.assignee.localeCompare(b.assignee)),
  };
}
