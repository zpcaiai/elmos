import { createHash } from "node:crypto";

import { frtTypedGapDefinition } from "./frt-typed-gap-catalog.js";

export const frtRouteStacks = [
  "Vue 2",
  "Vue 3",
  "React",
  "WeChat Mini Program",
  "ArkUI",
  "Flutter",
] as const;

export type FrtRouteStack = (typeof frtRouteStacks)[number];

export const frtRouteStackSet: ReadonlySet<string> = new Set<string>(frtRouteStacks);

export interface FrtRouteTypedGap {
  readonly code: string;
  readonly severity: "WARNING" | "ERROR" | "CRITICAL";
  readonly sourcePath: string;
  readonly message: string;
  readonly blocking: boolean;
}

export interface SourceReference {
  readonly path: string;
  readonly sha256: string;
}

/**
 * The bounded portable UI IR this route slice can carry end to end.
 *
 * Every field here must be derivable from, or checkable against, real source.
 * Growing this shape is a deliberate act: a field nothing can derive is a field
 * that will be invented downstream.
 */
export interface PortableUiIr {
  readonly schemaVersion: "1.0";
  readonly source: {
    readonly stack: FrtRouteStack;
    readonly version: string;
  };
  readonly sourceSnapshotDigest: string;
  readonly sourceRefs: readonly SourceReference[];
  readonly route: {
    readonly path: "/";
    readonly requiresAuth: false;
    readonly deepLink: true;
  };
  readonly view: {
    readonly title: string;
    readonly initialCount: number;
    readonly incrementBy: number;
    readonly buttonLabel: string;
  };
  readonly style: {
    readonly accentColor: string;
  };
  readonly accessibility: {
    readonly mainLabel: string;
    readonly buttonLabel: string;
    readonly liveRegion: "polite";
  };
  readonly capabilities: {
    readonly permissions: readonly [];
    readonly native: readonly [];
    readonly network: readonly [];
  };
}

export function sha256(value: string): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

/**
 * Report a typed gap. Severity is resolved from the catalogue, never from the
 * call site, and an unregistered code throws rather than being reported with a
 * guessed severity.
 */
export function gap(
  gaps: FrtRouteTypedGap[],
  code: string,
  sourcePath: string,
  message: string,
): void {
  const definition = frtTypedGapDefinition(code);
  gaps.push({
    code,
    sourcePath,
    message,
    severity: definition.severity,
    blocking: definition.severity !== "WARNING",
  });
}

/**
 * Cross-check a declared IR against the IR derived from the same source bytes.
 *
 * A declared IR may not assert anything the source does not say. Divergence is
 * reported field by field so the disagreement is legible, not just "invalid".
 * This is stack-neutral on purpose: every source stack that gains an extractor
 * gets the same guarantee from the same code path.
 */
export function assertDeclaredIrMatchesSource(
  declared: PortableUiIr,
  derived: PortableUiIr,
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): void {
  const comparisons: readonly (readonly [string, unknown, unknown])[] = [
    ["source.stack", declared.source.stack, derived.source.stack],
    ["source.version", declared.source.version, derived.source.version],
    ["view.title", declared.view.title, derived.view.title],
    ["view.initialCount", declared.view.initialCount, derived.view.initialCount],
    ["view.incrementBy", declared.view.incrementBy, derived.view.incrementBy],
    ["view.buttonLabel", declared.view.buttonLabel, derived.view.buttonLabel],
    ["style.accentColor", declared.style.accentColor.toUpperCase(), derived.style.accentColor.toUpperCase()],
    ["accessibility.mainLabel", declared.accessibility.mainLabel, derived.accessibility.mainLabel],
    ["accessibility.buttonLabel", declared.accessibility.buttonLabel, derived.accessibility.buttonLabel],
    ["sourceSnapshotDigest", declared.sourceSnapshotDigest, derived.sourceSnapshotDigest],
    ["sourceRefs", canonical(declared.sourceRefs), canonical(derived.sourceRefs)],
  ];
  for (const [field, declaredValue, derivedValue] of comparisons) {
    if (declaredValue === derivedValue) continue;
    gap(gaps, "FRT_DECLARED_IR_DIVERGES_FROM_SOURCE", sourcePath,
      `${field}: frt-ui-ir.json declares ${JSON.stringify(declaredValue)} but the ${derived.source.stack} source says `
      + `${JSON.stringify(derivedValue)}.`);
  }
}

export function contentAddressedSourceRefs(
  files: Readonly<Record<string, string>>,
  excluded: ReadonlySet<string>,
): readonly SourceReference[] {
  return Object.entries(files)
    .filter(([path]) => !excluded.has(path))
    .map(([path, content]) => ({ path, sha256: sha256(content) }))
    .sort((left, right) => left.path.localeCompare(right.path));
}
