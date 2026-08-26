/**
 * `@elmos/repository-refactoring-sdk` — a typed shell over the deterministic
 * repository-refactoring core.
 *
 * The core (Python, zero third-party dependencies) owns every decision:
 * parsing, indexing, planning, transformation, adjudication and evidence.
 * This package adds types, a transport, and typed errors — no policy, no
 * retries, and no reinterpretation of a result.
 */

export {
  RepositoryRefactoringClient,
  gateResults,
  requiresApproval,
  undecidedBlockingGates,
  type ClientOptions,
} from "./client.js";
export {
  CATALOG_SCHEMA_VERSION,
  CATALOG_VERSION,
  RUNTIME_CALLABLE,
  RUNTIME_MODULE,
  SKILL_NAMES,
  SKILL_SPECS,
  isDependencyOrdered,
  pendingSkills,
  topologicalOrder,
  type SkillName,
  type SkillSpec,
} from "./catalog.js";
export {
  ContractViolation,
  RepositoryRefactoringError,
  RuntimeUnavailable,
  SkillNotSucceeded,
} from "./errors.js";
export {
  PythonCoreRuntime,
  asEnvelope,
  type CoreRuntime,
  type CoreRuntimeOptions,
} from "./runtime.js";
export {
  EXIT_CODES,
  statusForExitCode,
  type AdapterLevel,
  type AnalysisPayload,
  type ContractErrorPayload,
  type ExecutionStatus,
  type ExitCode,
  type FailureClass,
  type GateResult,
  type HandlerEnvelope,
  type RiskClass,
  type Status,
  type TrustedContext,
  type ReadableFile,
  type UnreadFile,
  type WorkspaceFile,
  type WorkspacePayload,
} from "./types.js";
