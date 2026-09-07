/**
 * The typed entry point: a Skill name in, an envelope out.
 *
 * The client adds three things to the raw transport and nothing else:
 *
 * * the Skill name is checked against the generated catalog *before* the
 *   subprocess starts, so a typo is a `ContractViolation` here rather than a
 *   round trip;
 * * a Skill the core has not implemented is refused up front with the same
 *   error the core would return, instead of being dispatched hopefully;
 * * `runOrThrow` distinguishes "did not succeed" from "could not run", which
 *   are different decisions for a caller: one is an answer, the other is an
 *   outage.
 *
 * It deliberately does *not* retry, cache, or reinterpret a result.  Retry
 * policy belongs to the orchestrator, which can see the failure class.
 */

import { SKILL_NAMES, SKILL_SPECS, type SkillName } from "./catalog.js";
import { ContractViolation, SkillNotSucceeded } from "./errors.js";
import { type CoreRuntime, type CoreRuntimeOptions, PythonCoreRuntime } from "./runtime.js";
import type { GateResult, HandlerEnvelope, RiskClass, TrustedContext } from "./types.js";

export interface ClientOptions extends CoreRuntimeOptions {
  /** Applied to every call unless the call supplies its own. */
  readonly trustedContext?: TrustedContext;
  /** Inject a different transport; used by tests and by in-process hosts. */
  readonly runtime?: CoreRuntime;
}

export class RepositoryRefactoringClient {
  readonly #runtime: CoreRuntime;
  readonly #defaultContext: TrustedContext | undefined;

  constructor(options: ClientOptions = {}) {
    const { trustedContext, runtime, ...runtimeOptions } = options;
    this.#runtime = runtime ?? new PythonCoreRuntime(runtimeOptions);
    this.#defaultContext = trustedContext;
  }

  /** Every Skill, in the catalog's own declaration order. */
  get skills(): readonly SkillName[] {
    return SKILL_NAMES;
  }

  /**
   * Run one Skill.  Returns the envelope whatever the status: a `blocked`
   * result is the answer to the question that was asked, and its `reasons`
   * are the useful part.
   */
  async run(
    skill: SkillName,
    payload: Readonly<Record<string, unknown>> = {},
    trustedContext?: TrustedContext,
  ): Promise<HandlerEnvelope> {
    const spec = SKILL_SPECS[skill];
    if (spec === undefined) {
      throw new ContractViolation({
        code: "unknown_skill",
        message: `'${String(skill)}' is not in the catalog`,
        details: { known: [...SKILL_NAMES] },
      });
    }
    if (!spec.implemented) {
      throw new ContractViolation({
        code: "handler_not_implemented",
        message:
          `'${skill}' has no production handler in this build of the core; ` +
          "it fails closed rather than returning an unearned success",
        details: { skill },
      });
    }
    return this.#runtime.run(skill, payload, trustedContext ?? this.#defaultContext);
  }

  /** Run, and throw unless the status is `succeeded`. */
  async runOrThrow(
    skill: SkillName,
    payload: Readonly<Record<string, unknown>> = {},
    trustedContext?: TrustedContext,
  ): Promise<HandlerEnvelope> {
    const envelope = await this.run(skill, payload, trustedContext);
    if (envelope.status !== "succeeded") throw new SkillNotSucceeded(envelope);
    return envelope;
  }

  /** What the core reports about itself: version, coverage, risk per Skill. */
  async describe(): Promise<Readonly<Record<string, unknown>>> {
    return this.#runtime.describe();
  }

  /**
   * Run several Skills in the order given, stopping at the first one that
   * does not succeed.  Use `topologicalOrder()` if the caller needs an order
   * that respects declared dependencies.
   *
   * Stopping is the point: continuing past a blocked stage would feed a later
   * stage an input that was never adjudicated.
   */
  async runSequence(
    steps: readonly {
      readonly skill: SkillName;
      readonly payload?: Readonly<Record<string, unknown>>;
    }[],
    trustedContext?: TrustedContext,
  ): Promise<readonly HandlerEnvelope[]> {
    const results: HandlerEnvelope[] = [];
    for (const step of steps) {
      const envelope = await this.run(step.skill, step.payload ?? {}, trustedContext);
      results.push(envelope);
      if (envelope.status !== "succeeded") break;
    }
    return results;
  }
}

/** Read the gate results out of a verification envelope, undecided included. */
export function gateResults(envelope: HandlerEnvelope): readonly GateResult[] {
  const raw = envelope.output["gates"];
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item): GateResult[] => {
    if (typeof item !== "object" || item === null) return [];
    const record = item as Record<string, unknown>;
    const passed = record["passed"];
    return [
      {
        gate: typeof record["gate"] === "string" ? record["gate"] : "",
        //: `undefined` and a missing key both mean *undecided*, and both map
        //: to null.  Only an explicit boolean is a decision.
        passed: typeof passed === "boolean" ? passed : null,
        blocking: record["blocking"] !== false,
        detail: typeof record["detail"] === "string" ? record["detail"] : "",
      },
    ];
  });
}

/** Gates that block and were not decided. These fail; they do not pass. */
export function undecidedBlockingGates(envelope: HandlerEnvelope): readonly GateResult[] {
  return gateResults(envelope).filter((gate) => gate.blocking && gate.passed === null);
}

/** Whether a risk class needs a human decision under the enterprise default. */
export function requiresApproval(risk: RiskClass): boolean {
  return risk === "R2" || risk === "R3" || risk === "R4";
}
