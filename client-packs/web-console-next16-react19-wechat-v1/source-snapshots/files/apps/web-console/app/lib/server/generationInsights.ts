import type {
  EvidenceChartStatus,
  GenerationInsights,
  GenerationTargetId,
} from "../contracts";

const digestPattern = /^[0-9a-f]{64}$/;
const idPattern = /^[a-z0-9][a-z0-9:._-]{0,199}$/;
const targetIds = new Set<GenerationTargetId>([
  "java",
  "python",
  "csharp",
  "typescript",
  "go",
  "kotlin",
  "php",
  "rust",
]);
const evidenceStatuses = [
  "PASSED",
  "FAILED",
  "NOT_RUN",
  "UNKNOWN",
  "NOT_APPLICABLE",
] as const satisfies readonly EvidenceChartStatus[];
const structureKinds = new Set([
  "repository",
  "requirements",
  "documentation",
  "deployment",
  "continuous-integration",
  "operations",
  "observability",
  "security",
  "database",
  "repository-metadata",
  "application",
  "build-manifest",
  "api-contract",
  "container",
  "test-root",
  "source-root",
  "configuration",
  "application-support",
]);
const dependencyKinds = new Set(["application", "runtime", "framework", "build-tool", "provider"]);
const dependencyVersionSources = new Set([
  "project-blueprint",
  "runtime-manifest",
  "emitter-build-manifest",
]);
const flowKinds = new Set([
  "baseline",
  "semantic-ir",
  "architecture",
  "documentation",
  "deployment",
  "evidence",
  "generated-target",
]);
const coverageIds = [
  "project-structure",
  "requirements-traceability",
  "native-target-verification",
  "direct-semantic-equivalence",
  "direct-behavior-equivalence",
] as const;

export class GenerationInsightsValidationError extends Error {
  constructor(code: string) {
    super(code);
    this.name = "GenerationInsightsValidationError";
  }
}

function invalid(code: string): never {
  throw new GenerationInsightsValidationError(code);
}

function record(value: unknown, code: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) invalid(code);
  return value as Record<string, unknown>;
}

function nonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

function safeRelativePath(value: unknown): value is string {
  if (typeof value !== "string" || value.length < 1 || value.length > 1_000) return false;
  if (value === ".") return true;
  if (value.includes("\\") || value.includes("\0") || value.startsWith("/") || value.includes("//")) {
    return false;
  }
  return value.split("/").filter(Boolean).every((part) => part !== "." && part !== "..");
}

function status(value: unknown, allowNotApplicable = true): value is EvidenceChartStatus {
  return typeof value === "string"
    && evidenceStatuses.includes(value as EvidenceChartStatus)
    && (allowNotApplicable || value !== "NOT_APPLICABLE");
}

function exactStatusCounts(value: unknown, total: number, code: string): Record<EvidenceChartStatus, number> {
  const counts = record(value, code);
  const keys = Object.keys(counts).sort();
  if (
    keys.join(",") !== [...evidenceStatuses].sort().join(",")
    || evidenceStatuses.some((item) => !nonNegativeInteger(counts[item]))
    || evidenceStatuses.reduce((sum, item) => sum + Number(counts[item]), 0) !== total
  ) invalid(code);
  return counts as Record<EvidenceChartStatus, number>;
}

function sameSet(left: Set<string>, right: Set<string>): boolean {
  return left.size === right.size && [...left].every((item) => right.has(item));
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const item = record(value, "GENERATION_INSIGHTS_CANONICAL_JSON_INVALID");
  return `{${Object.keys(item).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson(item[key])}`).join(",")}}`;
}

export function generationInsightsEqual(left: unknown, right: unknown): boolean {
  return canonicalJson(left) === canonicalJson(right);
}

function validateProjectStructure(
  value: unknown,
  project: Record<string, unknown>,
): Set<GenerationTargetId> {
  const graph = record(value, "GENERATION_PROJECT_STRUCTURE_INVALID");
  const graphProject = record(graph.project, "GENERATION_PROJECT_STRUCTURE_PROJECT_INVALID");
  if (
    graph.schema_version !== "1.0.0"
    || graph.graph_kind !== "elmos.project-structure"
    || graphProject.id !== project.id
    || graphProject.name !== project.name
    || graphProject.repository_mode !== "polyglot-monorepo"
    || graphProject.approved_payload_sha256 !== project.approved_payload_sha256
    || !Array.isArray(graph.nodes)
    || graph.nodes.length < 2
    || graph.nodes.length > 256
    || !Array.isArray(graph.edges)
    || graph.edges.length < 1
    || graph.edges.length > 512
  ) invalid("GENERATION_PROJECT_STRUCTURE_INVALID");
  const nodeIds = new Set<string>();
  const languages = new Set<GenerationTargetId>();
  let repositoryNode: Record<string, unknown> | undefined;
  for (const rawNode of graph.nodes) {
    const node = record(rawNode, "GENERATION_PROJECT_STRUCTURE_NODE_INVALID");
    if (
      typeof node.id !== "string"
      || !idPattern.test(node.id)
      || nodeIds.has(node.id)
      || typeof node.kind !== "string"
      || !structureKinds.has(node.kind)
      || !safeRelativePath(node.path)
      || typeof node.label !== "string"
      || node.label.length < 1
      || node.label.length > 200
      || node.ownership !== "managed"
      || !nonNegativeInteger(node.file_count)
      || node.status !== "REPRESENTED"
    ) invalid("GENERATION_PROJECT_STRUCTURE_NODE_INVALID");
    nodeIds.add(node.id);
    if (node.kind === "repository") {
      if (
        repositoryNode !== undefined
        || node.id !== "repository"
        || node.path !== "."
        || node.file_count < 1
      ) invalid("GENERATION_PROJECT_STRUCTURE_REPOSITORY_INVALID");
      repositoryNode = node;
    }
    if (node.kind === "application") {
      if (
        typeof node.language !== "string"
        || !targetIds.has(node.language as GenerationTargetId)
        || languages.has(node.language as GenerationTargetId)
        || node.id !== `app:${node.language}`
        || typeof node.framework !== "string"
        || typeof node.runtime !== "string"
        || node.file_count < 1
      ) invalid("GENERATION_PROJECT_STRUCTURE_APPLICATION_INVALID");
      languages.add(node.language as GenerationTargetId);
    }
  }
  if (repositoryNode === undefined || languages.size < 1) {
    invalid("GENERATION_PROJECT_STRUCTURE_COVERAGE_INVALID");
  }
  const seenEdges = new Set<string>();
  const reachableEdges = new Map<string, Set<string>>();
  for (const rawEdge of graph.edges) {
    const edge = record(rawEdge, "GENERATION_PROJECT_STRUCTURE_EDGE_INVALID");
    if (
      typeof edge.from !== "string"
      || typeof edge.to !== "string"
      || !nodeIds.has(edge.from)
      || !nodeIds.has(edge.to)
      || edge.from === edge.to
      || edge.type !== "contains"
    ) invalid("GENERATION_PROJECT_STRUCTURE_EDGE_INVALID");
    const edgeKey = `${edge.from}\0${edge.to}\0${edge.type}`;
    if (seenEdges.has(edgeKey)) invalid("GENERATION_PROJECT_STRUCTURE_EDGE_DUPLICATED");
    seenEdges.add(edgeKey);
    const targets = reachableEdges.get(edge.from) ?? new Set<string>();
    targets.add(edge.to);
    reachableEdges.set(edge.from, targets);
  }
  const reachable = new Set<string>(["repository"]);
  const pending = ["repository"];
  while (pending.length > 0) {
    const source = pending.pop() as string;
    for (const target of reachableEdges.get(source) ?? []) {
      if (reachable.has(target)) continue;
      reachable.add(target);
      pending.push(target);
    }
  }
  if (!sameSet(reachable, nodeIds)) invalid("GENERATION_PROJECT_STRUCTURE_GRAPH_NOT_CLOSED");
  const coverage = record(graph.coverage, "GENERATION_PROJECT_STRUCTURE_COVERAGE_INVALID");
  if (
    coverage.scope !== "managed-generated-artifacts"
    || !nonNegativeInteger(coverage.managed_file_count)
    || coverage.managed_file_count < 1
    || coverage.classified_file_count !== coverage.managed_file_count
    || coverage.managed_file_count !== repositoryNode.file_count
    || coverage.declared_application_count !== languages.size
    || coverage.represented_application_count !== languages.size
    || !Array.isArray(coverage.unclassified_paths)
    || coverage.unclassified_paths.length !== 0
    || coverage.status !== "PASSED"
  ) invalid("GENERATION_PROJECT_STRUCTURE_COVERAGE_INVALID");
  return languages;
}

function validateDeclaredDependencies(
  value: unknown,
  project: Record<string, unknown>,
  languages: Set<GenerationTargetId>,
): void {
  const graph = record(value, "GENERATION_DECLARED_DEPENDENCIES_INVALID");
  if (
    graph.schema_version !== "1.0.0"
    || graph.graph_kind !== "elmos.declared-dependency-graph"
    || graph.project_id !== project.id
    || !Array.isArray(graph.nodes)
    || graph.nodes.length < languages.size * 4
    || graph.nodes.length > 64
    || !Array.isArray(graph.edges)
    || graph.edges.length < languages.size * 3
    || graph.edges.length > 128
    || graph.complete !== false
    || !Array.isArray(graph.issues)
    || !graph.issues.includes("NATIVE_TRANSITIVE_RESOLUTION_NOT_RUN")
  ) invalid("GENERATION_DECLARED_DEPENDENCIES_INVALID");
  const resolution = record(graph.resolution, "GENERATION_DECLARED_DEPENDENCY_RESOLUTION_INVALID");
  if (
    resolution.status !== "NOT_RUN"
    || !Array.isArray(resolution.resolved_graph_refs)
    || resolution.resolved_graph_refs.length !== 0
  ) invalid("GENERATION_DECLARED_DEPENDENCY_RESOLUTION_INVALID");
  const nodeIds = new Set<string>();
  const appLanguages = new Set<GenerationTargetId>();
  const requiredNodeIds = new Map<GenerationTargetId, Map<string, string>>();
  for (const rawNode of graph.nodes) {
    const node = record(rawNode, "GENERATION_DECLARED_DEPENDENCY_NODE_INVALID");
    if (
      typeof node.id !== "string"
      || !idPattern.test(node.id)
      || nodeIds.has(node.id)
      || typeof node.kind !== "string"
      || !dependencyKinds.has(node.kind)
      || typeof node.coordinate !== "string"
      || node.coordinate.length < 1
      || !dependencyVersionSources.has(String(node.version_source))
    ) invalid("GENERATION_DECLARED_DEPENDENCY_NODE_INVALID");
    nodeIds.add(node.id);
    const expectedVersionSource = node.kind === "framework"
      ? "emitter-build-manifest"
      : ["build-tool", "provider"].includes(node.kind)
        ? "runtime-manifest"
        : "project-blueprint";
    if (node.version_source !== expectedVersionSource) {
      invalid("GENERATION_DECLARED_DEPENDENCY_VERSION_SOURCE_INVALID");
    }
    if (node.kind === "provider") {
      if (!node.id.startsWith("provider:")) {
        invalid("GENERATION_DECLARED_DEPENDENCY_PROVIDER_INVALID");
      }
      continue;
    }
    const parts = node.id.split(":");
    const expectedPrefix = node.kind === "application" ? "app" : node.kind;
    const language = parts[1] as GenerationTargetId;
    if (
      parts[0] !== expectedPrefix
      || (node.kind === "application" ? parts.length !== 2 : parts.length < 3)
      || !targetIds.has(language)
      || !languages.has(language)
    ) invalid("GENERATION_DECLARED_DEPENDENCY_LANGUAGE_BINDING_INVALID");
    const byKind = requiredNodeIds.get(language) ?? new Map<string, string>();
    if (byKind.has(node.kind)) invalid("GENERATION_DECLARED_DEPENDENCY_ROLE_DUPLICATED");
    byKind.set(node.kind, node.id);
    requiredNodeIds.set(language, byKind);
    if (node.kind === "application") {
      if (appLanguages.has(language)) invalid("GENERATION_DECLARED_DEPENDENCY_APPLICATION_INVALID");
      appLanguages.add(language);
    }
  }
  if (!sameSet(new Set(appLanguages), new Set(languages))) {
    invalid("GENERATION_DECLARED_DEPENDENCY_COVERAGE_INVALID");
  }
  const requiredRoles = ["application", "runtime", "framework", "build-tool"];
  for (const language of languages) {
    const byKind = requiredNodeIds.get(language);
    if (!byKind || requiredRoles.some((kind) => !byKind.has(kind))) {
      invalid("GENERATION_DECLARED_DEPENDENCY_ROLE_COVERAGE_INVALID");
    }
  }
  const seenEdges = new Set<string>();
  for (const rawEdge of graph.edges) {
    const edge = record(rawEdge, "GENERATION_DECLARED_DEPENDENCY_EDGE_INVALID");
    if (
      typeof edge.from !== "string"
      || typeof edge.to !== "string"
      || !nodeIds.has(edge.from)
      || !nodeIds.has(edge.to)
      || edge.from === edge.to
      || !["requires", "uses", "builds-with", "persists-to"].includes(String(edge.type))
      || !["runtime", "application", "build"].includes(String(edge.scope))
      || edge.evidence_status !== "DECLARED"
    ) invalid("GENERATION_DECLARED_DEPENDENCY_EDGE_INVALID");
    const edgeKey = `${edge.from}\0${edge.to}\0${edge.type}\0${edge.scope}`;
    if (seenEdges.has(edgeKey)) invalid("GENERATION_DECLARED_DEPENDENCY_EDGE_DUPLICATED");
    seenEdges.add(edgeKey);
  }
  for (const language of languages) {
    const byKind = requiredNodeIds.get(language) as Map<string, string>;
    const app = byKind.get("application") as string;
    for (const [kind, type, scope] of [
      ["runtime", "requires", "runtime"],
      ["framework", "uses", "application"],
      ["build-tool", "builds-with", "build"],
    ]) {
      const expected = `${app}\0${String(byKind.get(kind))}\0${type}\0${scope}`;
      if (!seenEdges.has(expected)) {
        invalid("GENERATION_DECLARED_DEPENDENCY_EDGE_COVERAGE_INVALID");
      }
    }
  }
}

function validateFlowGraph(value: unknown, languages: Set<GenerationTargetId>): void {
  const graph = record(value, "GENERATION_INSIGHT_FLOW_INVALID");
  if (
    graph.graph_kind !== "project-synthesis-insight-graph"
    || !Array.isArray(graph.nodes)
    || graph.nodes.length !== graph.node_count
    || graph.nodes.length !== languages.size + 6
    || !Array.isArray(graph.edges)
    || graph.edges.length !== graph.edge_count
    || graph.target_count !== languages.size
  ) invalid("GENERATION_INSIGHT_FLOW_INVALID");
  const nodeIds = new Set<string>();
  const targetLanguages = new Set<GenerationTargetId>();
  for (const rawNode of graph.nodes) {
    const node = record(rawNode, "GENERATION_INSIGHT_FLOW_NODE_INVALID");
    if (
      typeof node.id !== "string"
      || !idPattern.test(node.id)
      || nodeIds.has(node.id)
      || typeof node.label !== "string"
      || !safeRelativePath(node.path)
      || typeof node.kind !== "string"
      || !flowKinds.has(node.kind)
      || !status(node.status, false)
    ) invalid("GENERATION_INSIGHT_FLOW_NODE_INVALID");
    nodeIds.add(node.id);
    if (node.kind === "generated-target") {
      if (
        typeof node.language !== "string"
        || !targetIds.has(node.language as GenerationTargetId)
        || targetLanguages.has(node.language as GenerationTargetId)
      ) invalid("GENERATION_INSIGHT_FLOW_TARGET_INVALID");
      targetLanguages.add(node.language as GenerationTargetId);
    }
  }
  if (!sameSet(new Set(targetLanguages), new Set(languages))) {
    invalid("GENERATION_INSIGHT_FLOW_COVERAGE_INVALID");
  }
  const seenEdges = new Set<string>();
  for (const rawEdge of graph.edges) {
    const edge = record(rawEdge, "GENERATION_INSIGHT_FLOW_EDGE_INVALID");
    if (
      typeof edge.from !== "string"
      || typeof edge.to !== "string"
      || !nodeIds.has(edge.from)
      || !nodeIds.has(edge.to)
      || edge.from === edge.to
      || !["normalizes", "plans", "documents", "configures", "generates", "requires-verification"]
        .includes(String(edge.relation))
    ) invalid("GENERATION_INSIGHT_FLOW_EDGE_INVALID");
    const edgeKey = `${edge.from}\0${edge.to}\0${edge.relation}`;
    if (seenEdges.has(edgeKey)) invalid("GENERATION_INSIGHT_FLOW_EDGE_DUPLICATED");
    seenEdges.add(edgeKey);
  }
}

function validateSemantic(value: unknown): number {
  const semantic = record(value, "GENERATION_SEMANTIC_INSIGHTS_INVALID");
  if (
    semantic.relation !== "APPROVED_REQUIREMENTS_TO_GENERATED_TARGETS"
    || semantic.mapping_status !== "PASSED"
    || semantic.equivalence_status !== "NOT_RUN"
    || !Array.isArray(semantic.subjects)
    || semantic.subjects.length !== 7
    || !nonNegativeInteger(semantic.source_subject_count)
    || !nonNegativeInteger(semantic.mapped_subject_count)
    || semantic.source_subject_count !== semantic.mapped_subject_count
    || !Array.isArray(semantic.limitations)
    || semantic.limitations.length < 2
  ) invalid("GENERATION_SEMANTIC_INSIGHTS_INVALID");
  const subjectIds = new Set<string>();
  let sourceCount = 0;
  let mappedCount = 0;
  for (const rawSubject of semantic.subjects) {
    const subject = record(rawSubject, "GENERATION_SEMANTIC_SUBJECT_INVALID");
    if (
      typeof subject.id !== "string"
      || !idPattern.test(subject.id)
      || subjectIds.has(subject.id)
      || typeof subject.label !== "string"
      || !nonNegativeInteger(subject.source_count)
      || !nonNegativeInteger(subject.mapped_count)
      || subject.mapped_count !== subject.source_count
      || subject.mapping_status !== "PASSED"
      || subject.semantic_equivalence_status !== "NOT_RUN"
      || subject.evidence_strength !== "HASH_BOUND_TRACEABILITY"
    ) invalid("GENERATION_SEMANTIC_SUBJECT_INVALID");
    subjectIds.add(subject.id);
    sourceCount += subject.source_count;
    mappedCount += subject.mapped_count;
  }
  if (sourceCount !== semantic.source_subject_count || mappedCount !== semantic.mapped_subject_count) {
    invalid("GENERATION_SEMANTIC_COUNTS_INVALID");
  }
  return semantic.subjects.length;
}

function validateBehavior(
  value: unknown,
  languages: Set<GenerationTargetId>,
  stage: "GENERATED" | "VERIFIED",
): { status: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">; passedTargets: number } {
  const behavior = record(value, "GENERATION_BEHAVIOR_INSIGHTS_INVALID");
  if (
    behavior.profile !== "native-build-test-startup-v1"
    || !status(behavior.status, false)
    || !Array.isArray(behavior.targets)
    || behavior.targets.length !== languages.size
    || !Array.isArray(behavior.cross_target_matrix)
    || behavior.cross_target_matrix.length !== languages.size ** 2
    || !Array.isArray(behavior.limitations)
    || behavior.limitations.length < 2
  ) invalid("GENERATION_BEHAVIOR_INSIGHTS_INVALID");
  const targetLanguages = new Set<GenerationTargetId>();
  const targetStatuses: EvidenceChartStatus[] = [];
  for (const rawTarget of behavior.targets) {
    const target = record(rawTarget, "GENERATION_BEHAVIOR_TARGET_INVALID");
    if (
      typeof target.language !== "string"
      || !targetIds.has(target.language as GenerationTargetId)
      || !languages.has(target.language as GenerationTargetId)
      || targetLanguages.has(target.language as GenerationTargetId)
      || !status(target.status, false)
      || !status(target.exact_toolchain_status, false)
      || !status(target.startup_status, false)
    ) invalid("GENERATION_BEHAVIOR_TARGET_INVALID");
    const build = record(target.build_analysis, "GENERATION_BEHAVIOR_BUILD_ANALYSIS_INVALID");
    if (!nonNegativeInteger(build.total) || build.total > 100) {
      invalid("GENERATION_BEHAVIOR_BUILD_ANALYSIS_INVALID");
    }
    const buildCounts = exactStatusCounts(
      build.status_counts,
      build.total,
      "GENERATION_BEHAVIOR_BUILD_STATUS_COUNTS_INVALID",
    );
    if (buildCounts.NOT_APPLICABLE !== 0) {
      invalid("GENERATION_BEHAVIOR_BUILD_STATUS_COUNTS_INVALID");
    }
    const buildStatus = buildCounts.FAILED > 0
      ? "FAILED"
      : buildCounts.UNKNOWN > 0
        ? "UNKNOWN"
        : build.total === 0 || buildCounts.NOT_RUN > 0
          ? "NOT_RUN"
          : buildCounts.PASSED === build.total
            ? "PASSED"
            : "UNKNOWN";
    const expectedTargetStatus = [target.exact_toolchain_status, buildStatus, target.startup_status]
      .includes("FAILED")
      ? "FAILED"
      : target.exact_toolchain_status === "PASSED"
        && buildStatus === "PASSED"
        && target.startup_status === "PASSED"
        ? "PASSED"
        : [target.exact_toolchain_status, buildStatus, target.startup_status].includes("UNKNOWN")
          ? "UNKNOWN"
          : "NOT_RUN";
    if (target.status !== expectedTargetStatus) {
      invalid("GENERATION_BEHAVIOR_TARGET_STATUS_CONTRADICTORY");
    }
    if (
      stage === "GENERATED"
      && (target.status !== "NOT_RUN"
        || target.exact_toolchain_status !== "NOT_RUN"
        || target.startup_status !== "NOT_RUN"
        || build.total !== 0)
    ) invalid("GENERATION_BEHAVIOR_GENERATED_CLAIM_INVALID");
    targetLanguages.add(target.language as GenerationTargetId);
    targetStatuses.push(target.status);
  }
  if (!sameSet(new Set(targetLanguages), new Set(languages))) {
    invalid("GENERATION_BEHAVIOR_TARGET_COVERAGE_INVALID");
  }
  const pairs = new Set<string>();
  for (const rawCell of behavior.cross_target_matrix) {
    const cell = record(rawCell, "GENERATION_BEHAVIOR_PAIR_INVALID");
    if (
      typeof cell.source !== "string"
      || typeof cell.target !== "string"
      || !languages.has(cell.source as GenerationTargetId)
      || !languages.has(cell.target as GenerationTargetId)
    ) invalid("GENERATION_BEHAVIOR_PAIR_INVALID");
    const pair = `${cell.source}->${cell.target}`;
    if (pairs.has(pair)) invalid("GENERATION_BEHAVIOR_PAIR_DUPLICATED");
    pairs.add(pair);
    const diagonal = cell.source === cell.target;
    if (
      cell.semantic_status !== (diagonal ? "NOT_APPLICABLE" : "NOT_RUN")
      || cell.behavior_status !== (diagonal ? "NOT_APPLICABLE" : "NOT_RUN")
      || cell.reason !== (diagonal
        ? "SAME_TARGET"
        : "DIRECT_PAIRWISE_SOURCE_TARGET_COMPARISON_NOT_EXECUTED")
    ) invalid("GENERATION_BEHAVIOR_PAIR_CLAIM_INVALID");
  }
  const expectedStatus = targetStatuses.includes("FAILED")
    ? "FAILED"
    : targetStatuses.length > 0 && targetStatuses.every((item) => item === "PASSED")
      ? "PASSED"
      : targetStatuses.includes("UNKNOWN")
        ? "UNKNOWN"
        : "NOT_RUN";
  if (behavior.status !== expectedStatus) invalid("GENERATION_BEHAVIOR_STATUS_CONTRADICTORY");
  return {
    status: expectedStatus,
    passedTargets: targetStatuses.filter((item) => item === "PASSED").length,
  };
}

function validateCoverage(
  value: unknown,
  targetCount: number,
  semanticDimensionCount: number,
  behaviorStatus: Exclude<EvidenceChartStatus, "NOT_APPLICABLE">,
  passedTargets: number,
): void {
  if (!Array.isArray(value) || value.length !== coverageIds.length) {
    invalid("GENERATION_INSIGHT_COVERAGE_INVALID");
  }
  const dimensions = new Map<string, Record<string, unknown>>();
  for (const rawDimension of value) {
    const dimension = record(rawDimension, "GENERATION_INSIGHT_COVERAGE_DIMENSION_INVALID");
    if (
      typeof dimension.id !== "string"
      || !coverageIds.includes(dimension.id as typeof coverageIds[number])
      || dimensions.has(dimension.id)
      || typeof dimension.label !== "string"
      || !status(dimension.status, false)
      || !nonNegativeInteger(dimension.passed)
      || !nonNegativeInteger(dimension.total)
      || dimension.passed > dimension.total
    ) invalid("GENERATION_INSIGHT_COVERAGE_DIMENSION_INVALID");
    dimensions.set(dimension.id, dimension);
  }
  const pairs = targetCount * (targetCount - 1);
  const structure = dimensions.get("project-structure");
  const trace = dimensions.get("requirements-traceability");
  const native = dimensions.get("native-target-verification");
  const semantic = dimensions.get("direct-semantic-equivalence");
  const behavior = dimensions.get("direct-behavior-equivalence");
  if (
    structure?.status !== "PASSED" || structure.passed !== 1 || structure.total !== 1
    || trace?.status !== "PASSED"
    || trace.passed !== semanticDimensionCount
    || trace.total !== semanticDimensionCount
    || native?.status !== behaviorStatus
    || native.passed !== passedTargets
    || native.total !== targetCount
    || semantic?.status !== "NOT_RUN" || semantic.passed !== 0 || semantic.total !== pairs
    || behavior?.status !== "NOT_RUN" || behavior.passed !== 0 || behavior.total !== pairs
  ) invalid("GENERATION_INSIGHT_COVERAGE_CONTRADICTORY");
}

export function validateGenerationInsights(
  value: unknown,
  expectedStage?: "GENERATED" | "VERIFIED",
): GenerationInsights {
  const insights = record(value, "GENERATION_INSIGHTS_INVALID");
  if (
    insights.schema_version !== "1.0.0"
    || insights.kind !== "elmos.project-generation-insights"
    || !["GENERATED", "VERIFIED"].includes(String(insights.stage))
    || (expectedStage !== undefined && insights.stage !== expectedStage)
    || insights.claim_ceiling !== "LOCAL_ENGINEERING_EVIDENCE"
    || insights.external_verification_status !== "NOT_RUN"
    || insights.certification_status !== "NOT_CERTIFIED"
  ) invalid("GENERATION_INSIGHTS_INVALID");
  const project = record(insights.project, "GENERATION_INSIGHTS_PROJECT_INVALID");
  if (
    typeof project.id !== "string"
    || project.id.length < 1
    || typeof project.name !== "string"
    || project.name.length < 1
    || typeof project.request_sha256 !== "string"
    || !digestPattern.test(project.request_sha256)
    || typeof project.approved_payload_sha256 !== "string"
    || !digestPattern.test(project.approved_payload_sha256)
  ) invalid("GENERATION_INSIGHTS_PROJECT_INVALID");
  const languages = validateProjectStructure(insights.project_structure, project);
  validateDeclaredDependencies(insights.declared_dependencies, project, languages);
  validateFlowGraph(insights.structure, languages);
  const semanticDimensionCount = validateSemantic(insights.semantic);
  const stage = insights.stage as "GENERATED" | "VERIFIED";
  const behavior = validateBehavior(insights.behavior, languages, stage);
  validateCoverage(
    insights.coverage,
    languages.size,
    semanticDimensionCount,
    behavior.status,
    behavior.passedTargets,
  );
  if (
    (stage === "GENERATED" && insights.verification_status !== undefined)
    || (stage === "VERIFIED"
      && !["PASSED", "PARTIAL", "FAILED"].includes(String(insights.verification_status)))
  ) invalid("GENERATION_INSIGHTS_VERIFICATION_STATUS_INVALID");
  return insights as GenerationInsights;
}

export function validateVerifiedInsightProjection(
  generatedValue: unknown,
  verifiedValue: unknown,
): GenerationInsights {
  const generated = validateGenerationInsights(generatedValue, "GENERATED");
  const verified = validateGenerationInsights(verifiedValue, "VERIFIED");
  for (const field of [
    "project",
    "claim_ceiling",
    "project_structure",
    "declared_dependencies",
    "structure",
    "semantic",
    "external_verification_status",
    "certification_status",
  ] as const) {
    if (!generationInsightsEqual(generated[field], verified[field])) {
      invalid("GENERATION_VERIFIED_INSIGHTS_PROJECTION_INVALID");
    }
  }
  const generatedBehavior = generated.behavior;
  const verifiedBehavior = verified.behavior;
  if (
    generatedBehavior.profile !== verifiedBehavior.profile
    || !generationInsightsEqual(
      generatedBehavior.cross_target_matrix,
      verifiedBehavior.cross_target_matrix,
    )
    || !generationInsightsEqual(generatedBehavior.limitations, verifiedBehavior.limitations)
  ) invalid("GENERATION_VERIFIED_BEHAVIOR_PROJECTION_INVALID");
  if (
    generatedBehavior.targets.length !== verifiedBehavior.targets.length
    || generatedBehavior.targets.some(
      (target, index) => target.language !== verifiedBehavior.targets[index]?.language,
    )
  ) invalid("GENERATION_VERIFIED_BEHAVIOR_TARGET_IDENTITY_DRIFTED");
  for (const dimension of verified.coverage) {
    const generatedDimension = generated.coverage.find((item) => item.id === dimension.id);
    if (dimension.id === "native-target-verification") {
      if (
        generatedDimension?.id !== dimension.id
        || generatedDimension.label !== dimension.label
        || generatedDimension.total !== dimension.total
      ) invalid("GENERATION_VERIFIED_NATIVE_COVERAGE_IDENTITY_DRIFTED");
      continue;
    }
    if (!generationInsightsEqual(generatedDimension, dimension)) {
      invalid("GENERATION_VERIFIED_COVERAGE_PROJECTION_INVALID");
    }
  }
  return verified;
}
