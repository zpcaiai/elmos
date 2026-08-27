/**
 * GENERATED FILE — do not edit by hand.
 *
 * Produced by `scripts/generate-catalog.ts` from ../repository-refactoring/config/skill-catalog.json.
 * `test/catalog.test.ts` re-reads that JSON and fails if this file has drifted,
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

export const SKILL_NAMES = [
  "repository-refactor-orchestrator",
  "repository-discovery",
  "build-graph-and-environment",
  "semantic-index",
  "refactor-intent-compiler",
  "change-impact-analysis",
  "recipe-synthesis",
  "deterministic-transform-executor",
  "cross-language-contract-refactor",
  "data-schema-refactor",
  "distributed-system-refactor",
  "test-and-verification",
  "bounded-auto-repair",
  "canary-rollout",
  "rollback-and-recovery",
  "evidence-and-audit",
  "recipe-learning-registry",
  "human-approval-gate",
  "performance-preservation",
  "security-preservation",
  "api-compatibility",
  "multi-repository-refactor-program",
  "ui-and-client-refactor",
] as const;

export type SkillName = (typeof SKILL_NAMES)[number];

export const SKILL_SPECS: { readonly [K in SkillName]: SkillSpec } = {
  "repository-refactor-orchestrator": {
    name: "repository-refactor-orchestrator",
    handler: "repository_refactor_orchestrator",
    canonicalOwner: "canonical.elmos.durable-runtime",
    riskClass: "R3",
    minimumAdapterLevel: "L0",
    mutating: false,
    implemented: true,
    dependsOn: [],
  },
  "repository-discovery": {
    name: "repository-discovery",
    handler: "repository_discovery",
    canonicalOwner: "canonical.elmos.repository-snapshot",
    riskClass: "R0",
    minimumAdapterLevel: "L0",
    mutating: false,
    implemented: true,
    dependsOn: [],
  },
  "build-graph-and-environment": {
    name: "build-graph-and-environment",
    handler: "build_graph_and_environment",
    canonicalOwner: "canonical.elmos.build-graph",
    riskClass: "R2",
    minimumAdapterLevel: "L1",
    mutating: false,
    implemented: true,
    dependsOn: ["repository-discovery"],
  },
  "semantic-index": {
    name: "semantic-index",
    handler: "semantic_index",
    canonicalOwner: "canonical.elmos.semantic-index",
    riskClass: "R0",
    minimumAdapterLevel: "L1",
    mutating: false,
    implemented: true,
    dependsOn: ["repository-discovery", "build-graph-and-environment"],
  },
  "refactor-intent-compiler": {
    name: "refactor-intent-compiler",
    handler: "refactor_intent_compiler",
    canonicalOwner: "canonical.elmos.intent-baseline",
    riskClass: "R0",
    minimumAdapterLevel: "L0",
    mutating: false,
    implemented: true,
    dependsOn: ["semantic-index"],
  },
  "change-impact-analysis": {
    name: "change-impact-analysis",
    handler: "change_impact_analysis",
    canonicalOwner: "canonical.elmos.impact-graph",
    riskClass: "R0",
    minimumAdapterLevel: "L2",
    mutating: false,
    implemented: true,
    dependsOn: ["semantic-index", "refactor-intent-compiler"],
  },
  "recipe-synthesis": {
    name: "recipe-synthesis",
    handler: "recipe_synthesis",
    canonicalOwner: "canonical.elmos.recipe-registry",
    riskClass: "R2",
    minimumAdapterLevel: "L2",
    mutating: false,
    implemented: true,
    dependsOn: ["refactor-intent-compiler", "change-impact-analysis"],
  },
  "deterministic-transform-executor": {
    name: "deterministic-transform-executor",
    handler: "deterministic_transform_executor",
    canonicalOwner: "canonical.elmos.transform-runtime",
    riskClass: "R3",
    minimumAdapterLevel: "L2",
    mutating: true,
    implemented: true,
    dependsOn: ["recipe-synthesis"],
  },
  "cross-language-contract-refactor": {
    name: "cross-language-contract-refactor",
    handler: "cross_language_contract_refactor",
    canonicalOwner: "canonical.elmos.contract-registry",
    riskClass: "R3",
    minimumAdapterLevel: "L3",
    mutating: true,
    implemented: true,
    dependsOn: ["change-impact-analysis", "deterministic-transform-executor", "api-compatibility"],
  },
  "data-schema-refactor": {
    name: "data-schema-refactor",
    handler: "data_schema_refactor",
    canonicalOwner: "canonical.elmos.data-migration",
    riskClass: "R4",
    minimumAdapterLevel: "L3",
    mutating: true,
    implemented: true,
    dependsOn: ["change-impact-analysis", "human-approval-gate", "rollback-and-recovery"],
  },
  "distributed-system-refactor": {
    name: "distributed-system-refactor",
    handler: "distributed_system_refactor",
    canonicalOwner: "canonical.elmos.service-topology",
    riskClass: "R4",
    minimumAdapterLevel: "L3",
    mutating: true,
    implemented: true,
    dependsOn: ["cross-language-contract-refactor", "data-schema-refactor", "performance-preservation"],
  },
  "test-and-verification": {
    name: "test-and-verification",
    handler: "test_and_verification",
    canonicalOwner: "canonical.elmos.verification",
    riskClass: "R3",
    minimumAdapterLevel: "L2",
    mutating: false,
    implemented: true,
    dependsOn: ["deterministic-transform-executor"],
  },
  "bounded-auto-repair": {
    name: "bounded-auto-repair",
    handler: "bounded_auto_repair",
    canonicalOwner: "canonical.elmos.transform-runtime",
    riskClass: "R3",
    minimumAdapterLevel: "L2",
    mutating: true,
    implemented: true,
    dependsOn: ["test-and-verification"],
  },
  "canary-rollout": {
    name: "canary-rollout",
    handler: "canary_rollout",
    canonicalOwner: "canonical.elmos.release-control",
    riskClass: "R4",
    minimumAdapterLevel: "L3",
    mutating: true,
    implemented: true,
    dependsOn: ["test-and-verification", "human-approval-gate"],
  },
  "rollback-and-recovery": {
    name: "rollback-and-recovery",
    handler: "rollback_and_recovery",
    canonicalOwner: "canonical.elmos.durable-runtime",
    riskClass: "R4",
    minimumAdapterLevel: "L1",
    mutating: true,
    implemented: true,
    dependsOn: ["repository-refactor-orchestrator"],
  },
  "evidence-and-audit": {
    name: "evidence-and-audit",
    handler: "evidence_and_audit",
    canonicalOwner: "canonical.elmos.evidence-store",
    riskClass: "R0",
    minimumAdapterLevel: "L0",
    mutating: false,
    implemented: true,
    dependsOn: [],
  },
  "recipe-learning-registry": {
    name: "recipe-learning-registry",
    handler: "recipe_learning_registry",
    canonicalOwner: "canonical.elmos.recipe-registry",
    riskClass: "R3",
    minimumAdapterLevel: "L0",
    mutating: false,
    implemented: true,
    dependsOn: ["evidence-and-audit"],
  },
  "human-approval-gate": {
    name: "human-approval-gate",
    handler: "human_approval_gate",
    canonicalOwner: "canonical.elmos.identity-policy",
    riskClass: "R4",
    minimumAdapterLevel: "L0",
    mutating: false,
    implemented: true,
    dependsOn: [],
  },
  "performance-preservation": {
    name: "performance-preservation",
    handler: "performance_preservation",
    canonicalOwner: "canonical.elmos.verification",
    riskClass: "R3",
    minimumAdapterLevel: "L2",
    mutating: false,
    implemented: true,
    dependsOn: ["build-graph-and-environment", "test-and-verification"],
  },
  "security-preservation": {
    name: "security-preservation",
    handler: "security_preservation",
    canonicalOwner: "canonical.elmos.security-control",
    riskClass: "R4",
    minimumAdapterLevel: "L2",
    mutating: false,
    implemented: true,
    dependsOn: ["test-and-verification"],
  },
  "api-compatibility": {
    name: "api-compatibility",
    handler: "api_compatibility",
    canonicalOwner: "canonical.elmos.contract-registry",
    riskClass: "R3",
    minimumAdapterLevel: "L2",
    mutating: false,
    implemented: true,
    dependsOn: ["semantic-index"],
  },
  "multi-repository-refactor-program": {
    name: "multi-repository-refactor-program",
    handler: "multi_repository_refactor_program",
    canonicalOwner: "canonical.elmos.durable-runtime",
    riskClass: "R4",
    minimumAdapterLevel: "L3",
    mutating: false,
    implemented: true,
    dependsOn: ["repository-refactor-orchestrator", "cross-language-contract-refactor", "canary-rollout"],
  },
  "ui-and-client-refactor": {
    name: "ui-and-client-refactor",
    handler: "ui_and_client_refactor",
    canonicalOwner: "canonical.elmos.client-platform",
    riskClass: "R3",
    minimumAdapterLevel: "L2",
    mutating: true,
    implemented: true,
    dependsOn: ["semantic-index", "api-compatibility", "test-and-verification"],
  },
} as const;

export const CATALOG_VERSION = "1.0.0";
export const CATALOG_SCHEMA_VERSION = "elmos.repository-refactoring.skill-catalog.v1";
export const RUNTIME_MODULE = "elmos_repository_refactoring.runtime";
export const RUNTIME_CALLABLE = "dispatch";

/**
 * SKILL_NAMES is *declaration* order (the catalog's own numbering), which is
 * deliberately not dependency order: `data-schema-refactor` is numbered 09 and
 * depends on `human-approval-gate`, numbered 17.  A host that scheduled in
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

/** Whether `order` never places a Skill before something it depends on. */
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
