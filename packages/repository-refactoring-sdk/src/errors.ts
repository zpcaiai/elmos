/** Typed failures the SDK raises, each carrying the core's own reasons. */

import type { ContractErrorPayload, FailureClass, HandlerEnvelope, Status } from "./types.js";

/** Base class so a caller can catch everything this SDK throws in one clause. */
export class RepositoryRefactoringError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/**
 * The run finished with a non-successful status.
 *
 * Thrown only by `runOrThrow`.  `run` returns the envelope, because a blocked
 * result is information, not an exception — the reasons are the point.
 */
export class SkillNotSucceeded extends RepositoryRefactoringError {
  readonly envelope: HandlerEnvelope;

  constructor(envelope: HandlerEnvelope) {
    const reasons = envelope.reasons.length > 0 ? `: ${envelope.reasons.join("; ")}` : "";
    super(`skill '${envelope.skill}' ${envelope.status}${reasons}`);
    this.envelope = envelope;
  }

  get status(): Status {
    return this.envelope.status;
  }

  get failureClass(): FailureClass | null {
    return this.envelope.failure_class;
  }

  get reasons(): readonly string[] {
    return this.envelope.reasons;
  }

  /** Whether the orchestrator may retry this unchanged. */
  get retryable(): boolean {
    return this.failureClass === "transient" || this.failureClass === "retryable";
  }
}

/** The core rejected the input before doing any work. */
export class ContractViolation extends RepositoryRefactoringError {
  readonly code: string;
  readonly details: Readonly<Record<string, unknown>>;

  constructor(payload: ContractErrorPayload) {
    super(`${payload.code}: ${payload.message}`);
    this.code = payload.code;
    this.details = payload.details ?? {};
  }
}

/** The core could not be started, or produced something that is not an envelope. */
export class RuntimeUnavailable extends RepositoryRefactoringError {
  /** The underlying failure, when there was one. `Error.cause`, narrowed. */
  override readonly cause: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.cause = cause;
  }
}
