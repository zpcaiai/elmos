/**
 * Regenerate `src/catalog.ts` from the Python core's committed skill catalog.
 *
 * The catalog is the one place where the two halves of this package have to
 * agree on a list of names.  Generating the TypeScript from the JSON — rather
 * than maintaining a parallel copy — means a Skill added on the Python side
 * cannot silently be missing its type here; and `test/catalog.test.ts` reads
 * the same JSON at test time, so a stale generated file fails the build
 * instead of shipping.
 *
 * Usage: pnpm run build && node dist/scripts/generate-catalog.js
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { CATALOG_RELATIVE_PATH, type CatalogDocument } from "../src/catalog-source.js";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..", "..");
const catalogPath = resolve(packageRoot, CATALOG_RELATIVE_PATH);
const outputPath = resolve(packageRoot, "src", "catalog.ts");

const document = JSON.parse(readFileSync(catalogPath, "utf8")) as CatalogDocument;
const quote = (value: string): string => JSON.stringify(value);

const header = `/**
 * GENERATED FILE — do not edit by hand.
 *
 * Produced by \`scripts/generate-catalog.ts\` from ${CATALOG_RELATIVE_PATH}.
 * \`test/catalog.test.ts\` re-reads that JSON and fails if this file has drifted,
 * so a Skill added to the Python core cannot go missing from these types.
 */

import type { AdapterLevel, RiskClass } from "./types.js";

export interface SkillSpec {
  readonly name: SkillName;
  readonly handler: string;
  readonly canonicalOwner: string;
  readonly riskClass: RiskClass;
  readonly minimumAdapterLevel: AdapterLevel;
  readonly mutating: boolean;
  /** Whether the Python core has a production handler wired for this Skill. */
  readonly implemented: boolean;
  readonly dependsOn: readonly SkillName[];
}
`;

const names = document.skills.map((skill) => skill.name);
const nameBlock = `
export const SKILL_NAMES = [
${names.map((name) => `  ${quote(name)},`).join("\n")}
] as const;

export type SkillName = (typeof SKILL_NAMES)[number];
`;

const specBlock = `
export const SKILL_SPECS: { readonly [K in SkillName]: SkillSpec } = {
${document.skills
  .map(
    (skill) => `  ${quote(skill.name)}: {
    name: ${quote(skill.name)},
    handler: ${quote(skill.handler)},
    canonicalOwner: ${quote(skill.canonical_owner)},
    riskClass: ${quote(skill.risk_class)},
    minimumAdapterLevel: ${quote(skill.minimum_adapter_level)},
    mutating: ${String(skill.mutating)},
    implemented: ${String(skill.implemented)},
    dependsOn: [${skill.depends_on.map(quote).join(", ")}],
  },`,
  )
  .join("\n")}
} as const;

export const CATALOG_VERSION = ${quote(document.package_version)};
export const CATALOG_SCHEMA_VERSION = ${quote(document.schema_version)};
export const RUNTIME_MODULE = ${quote(document.runtime_module)};
export const RUNTIME_CALLABLE = ${quote(document.runtime_callable)};

/**
 * SKILL_NAMES is *declaration* order (the catalog's own numbering), which is
 * deliberately not dependency order: \`data-schema-refactor\` is numbered 09 and
 * depends on \`human-approval-gate\`, numbered 17.  A host that scheduled in
 * declaration order would run a stage before its input existed, so the
 * dependency order is computed here rather than assumed.
 */
export function topologicalOrder(): readonly SkillName[] {
  const pending = new Map<SkillName, Set<string>>(
    SKILL_NAMES.map((name) => [name, new Set(SKILL_SPECS[name].dependsOn)]),
  );
  const ordered: SkillName[] = [];
  const placed = new Set<string>();
  while (pending.size > 0) {
    const ready = [...pending.entries()]
      .filter(([, dependencies]) => [...dependencies].every((item) => placed.has(item)))
      .map(([name]) => name)
      .sort();
    if (ready.length === 0) {
      throw new Error("skill catalog dependency graph contains a cycle");
    }
    for (const name of ready) {
      ordered.push(name);
      placed.add(name);
      pending.delete(name);
    }
  }
  return ordered;
}

/** Whether \`order\` never places a Skill before something it depends on. */
export function isDependencyOrdered(order: readonly SkillName[]): boolean {
  const seen = new Set<string>();
  for (const name of order) {
    for (const dependency of SKILL_SPECS[name].dependsOn) {
      if (!seen.has(dependency)) return false;
    }
    seen.add(name);
  }
  return true;
}

/** Skills with no production handler in the core. Empty is the goal state. */
export function pendingSkills(): readonly SkillName[] {
  return SKILL_NAMES.filter((name) => !SKILL_SPECS[name].implemented);
}
`;

writeFileSync(outputPath, `${header}${nameBlock}${specBlock}`, "utf8");
process.stdout.write(`wrote ${outputPath} (${names.length} skills)\n`);
