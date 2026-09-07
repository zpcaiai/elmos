/**
 * The wire types of the repository-refactoring runtime.
 *
 * These mirror the Python core's envelope exactly.  Two conventions here are
 * deliberate and load-bearing:
 *
 * * `Status` has no "unknown" member and no default.  A caller must handle
 *   `blocked` and `rejected` explicitly; there is no shape of this type in
 *   which an undecided run reads as a successful one.
 * * every "did it pass" field that the core may leave undecided is typed
 *   `boolean | null`, never `boolean`.  `null` means *not decided*, and
 *   collapsing it to `false` — or worse to `true` — is exactly the bug these
 *   types exist to prevent.
 */

/** Terminal status of one Skill invocation. */
export type Status = "succeeded" | "blocked" | "rejected" | "failed";

/** Blast radius of a change, R0 (inert) through R4 (irreversible/critical). */
export type RiskClass = "R0" | "R1" | "R2" | "R3" | "R4";

/** How a failure should be handled by the orchestrator. */
export type FailureClass =
  | "transient"
  | "retryable"
  | "terminal"
  | "approval-required"
  | "capability-missing";

/**
 * Adapter capability tiers, L0 ("nothing proven") through L4.
 *
 * There is no L5: the core's own enum stops at L4, and a type that admitted
 * one would let a host write a level the runtime rejects.
 */
export type AdapterLevel = "L0" | "L1" | "L2" | "L3" | "L4";

/** Execution outcome of a sandboxed command. `not-run` is never decisive. */
export type ExecutionStatus = "completed" | "failed" | "timeout" | "refused" | "not-run";

/** The structured error the core raises instead of a stack trace. */
export interface ContractErrorPayload {
  readonly code: string;
  readonly message: string;
  readonly details?: Readonly<Record<string, unknown>>;
}

/** The envelope every Skill returns. */
export interface HandlerEnvelope {
  readonly skill: string;
  readonly status: Status;
  readonly output: Readonly<Record<string, unknown>>;
  readonly reasons: readonly string[];
  readonly canonical_owner: string;
  readonly risk_class: RiskClass;
  readonly failure_class: FailureClass | null;
  readonly side_effects_performed: boolean;
  readonly evidence: Readonly<Record<string, unknown>>;
}

/**
 * Host-owned authority.  Kept structurally separate from a task payload,
 * because everything in here widens what the runtime may reach: a policy, a
 * filesystem root, a set of recorded executions.  A payload can never grant
 * itself any of it.
 */
export interface TrustedContext {
  readonly policy?: Readonly<Record<string, unknown>>;
  readonly policy_ref?: string;
  readonly adapter_capabilities?: Readonly<Record<string, unknown>>;
  readonly recorded_executions?: readonly Readonly<Record<string, unknown>>[];
  /** Absolute path. The runtime refuses a workspace outside this root. */
  readonly workspace_root?: string;
  readonly journal_root?: string;
  /**
   * Pins the instant the run happens, as an ISO-8601 UTC timestamp.
   *
   * Several Skills timestamp what they record — a journal entry, an approval
   * request, an incident report — so without this their output differs on
   * every call. Set it to make a run reproducible.
   *
   * It lives here, in trusted context, and not in the payload: a caller who
   * could set the time could date an approval into the past. The core rejects
   * a `now` supplied through a payload.
   */
  readonly now?: string;
}

/**
 * A file in an inline workspace snapshot.
 *
 * Exactly one of two shapes. With `content`, the file is readable text.
 * Without it, the file is described but not carried, and `content_digest` is
 * required — that is how a file the snapshot could not read is declared.
 *
 * The distinction between the two unreadable cases matters and is not
 * cosmetic: `binary: true` marks an asset that legitimately has no source
 * content (an image), while `unreadable_reason` marks source the snapshot
 * *failed* to read, which lowers coverage and lands in the inventory's
 * `unscanned` list. Declaring undecodable source as `binary` would hide it.
 */
export type WorkspaceFile = ReadableFile | UnreadFile;

export interface ReadableFile {
  readonly path: string;
  readonly content: string;
  readonly executable?: boolean;
  /** Optional; the core rejects the file if it does not match `content`. */
  readonly content_digest?: string;
}

export interface UnreadFile {
  readonly path: string;
  /** `sha256:` followed by 64 hex characters. Required for a file not carried. */
  readonly content_digest: string;
  readonly size_bytes?: number;
  /** True for an asset with no source content. Does not lower source coverage. */
  readonly binary?: boolean;
  /** Why the source could not be read, e.g. "undecodable-utf8", "too-large". */
  readonly unreadable_reason?: string;
  readonly executable?: boolean;
}

export interface WorkspacePayload {
  readonly source: "inline" | "directory";
  readonly repository_id: string;
  readonly revision: string;
  readonly files: readonly WorkspaceFile[];
}

/** Common shape of a planning-stage payload. */
export interface AnalysisPayload {
  readonly workspace: WorkspacePayload;
  readonly request?: Readonly<Record<string, unknown>>;
  readonly include?: readonly string[];
  readonly exclude?: readonly string[];
  readonly [key: string]: unknown;
}

/**
 * A gate result as the core reports it.
 *
 * `passed: null` means the gate was not decided — no executor, no evidence,
 * or an UNKNOWN predicate.  A blocking gate that is not decided fails.
 */
export interface GateResult {
  readonly gate: string;
  readonly passed: boolean | null;
  readonly blocking: boolean;
  readonly detail: string;
}

export const EXIT_CODES = {
  succeeded: 0,
  rejected: 2,
  blocked: 3,
  failed: 4,
  usage: 64,
} as const;

export type ExitCode = (typeof EXIT_CODES)[keyof typeof EXIT_CODES];

/** Map a process exit code back to a status, or `null` for a usage error. */
export function statusForExitCode(code: number): Status | null {
  switch (code) {
    case EXIT_CODES.succeeded:
      return "succeeded";
    case EXIT_CODES.rejected:
      return "rejected";
    case EXIT_CODES.blocked:
      return "blocked";
    case EXIT_CODES.failed:
      return "failed";
    default:
      return null;
  }
}
