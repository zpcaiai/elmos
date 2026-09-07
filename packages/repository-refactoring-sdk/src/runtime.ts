/**
 * The transport between this shell and the deterministic Python core.
 *
 * The core is invoked as a subprocess with one JSON document on stdin and one
 * JSON document on stdout.  That boundary is deliberate:
 *
 * * the core owns every decision; this module adds no policy of its own and
 *   never edits a payload on the way through;
 * * the process is spawned with a scrubbed environment and no shell, so a
 *   payload value cannot become a command;
 * * the exit code and the envelope's status are cross-checked.  If they
 *   disagree, that is a broken runtime, not a result to act on, and it raises
 *   rather than resolving to whichever looks better.
 */

import { spawn } from "node:child_process";

import { ContractViolation, RuntimeUnavailable } from "./errors.js";
import type { HandlerEnvelope, TrustedContext } from "./types.js";
import { statusForExitCode } from "./types.js";

export interface CoreRuntimeOptions {
  /** Interpreter to run. Default `python3`. */
  readonly python?: string;
  /**
   * Directory containing the `elmos_repository_refactoring` package, prepended
   * to `PYTHONPATH`.  Omit when the package is installed in the interpreter.
   */
  readonly packageRoot?: string;
  /** Working directory of the subprocess. Default: the current one. */
  readonly cwd?: string;
  /** Hard ceiling in milliseconds. Default 900_000, matching the core's own. */
  readonly timeoutMs?: number;
  /** Maximum stdout bytes to accept. Default 64 MiB. */
  readonly maxOutputBytes?: number;
  /**
   * Extra environment for the subprocess.  The base environment is *not*
   * inherited: only PATH, HOME and these entries are passed, so a stray
   * credential in the host environment does not reach a refactoring run.
   */
  readonly environment?: Readonly<Record<string, string>>;
}

const DEFAULT_TIMEOUT_MS = 900_000;
const DEFAULT_MAX_OUTPUT = 64 * 1024 * 1024;

export interface CoreRuntime {
  run(
    skill: string,
    payload: Readonly<Record<string, unknown>>,
    trustedContext?: TrustedContext,
  ): Promise<HandlerEnvelope>;
  describe(): Promise<Readonly<Record<string, unknown>>>;
}

interface ProcessOutcome {
  readonly code: number;
  readonly stdout: string;
  readonly stderr: string;
}

export class PythonCoreRuntime implements CoreRuntime {
  readonly #python: string;
  readonly #cwd: string | undefined;
  readonly #timeoutMs: number;
  readonly #maxOutputBytes: number;
  readonly #env: Record<string, string>;

  constructor(options: CoreRuntimeOptions = {}) {
    this.#python = options.python ?? "python3";
    this.#cwd = options.cwd;
    this.#timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.#maxOutputBytes = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT;
    const base: Record<string, string> = {
      PATH: process.env["PATH"] ?? "/usr/bin:/bin",
      HOME: process.env["HOME"] ?? "/tmp",
      PYTHONHASHSEED: "0",
      PYTHONDONTWRITEBYTECODE: "1",
    };
    if (options.packageRoot !== undefined) base["PYTHONPATH"] = options.packageRoot;
    this.#env = { ...base, ...(options.environment ?? {}) };
  }

  async run(
    skill: string,
    payload: Readonly<Record<string, unknown>>,
    trustedContext?: TrustedContext,
  ): Promise<HandlerEnvelope> {
    const envelope: Record<string, unknown> = { payload };
    if (trustedContext !== undefined) envelope["trustedContext"] = trustedContext;
    const outcome = await this.#spawn(
      ["-m", "elmos_repository_refactoring.cli", "run", skill, "--envelope", "-", "--compact"],
      JSON.stringify(envelope),
    );
    if (outcome.code === 64) {
      throw new RuntimeUnavailable(
        `the core rejected the invocation itself (exit 64): ${outcome.stderr.trim()}`,
      );
    }
    const parsed = this.#parse(outcome);
    if ("error" in parsed && typeof parsed["error"] === "object" && parsed["error"] !== null) {
      throw new ContractViolation(parsed["error"] as never);
    }
    const result = asEnvelope(parsed);
    const expected = statusForExitCode(outcome.code);
    if (expected !== null && expected !== result.status) {
      //: A runtime whose exit code and envelope disagree cannot be trusted to
      //: have adjudicated anything; picking one of the two would be guessing.
      throw new RuntimeUnavailable(
        `the core exited ${outcome.code} (${expected}) but reported '${result.status}'`,
      );
    }
    return result;
  }

  async describe(): Promise<Readonly<Record<string, unknown>>> {
    const outcome = await this.#spawn(["-m", "elmos_repository_refactoring.cli", "describe"], "");
    return this.#parse(outcome);
  }

  #parse(outcome: ProcessOutcome): Record<string, unknown> {
    const text = outcome.stdout.trim() || outcome.stderr.trim();
    if (text === "") {
      throw new RuntimeUnavailable(`the core produced no output (exit ${outcome.code})`);
    }
    try {
      const value: unknown = JSON.parse(text);
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new RuntimeUnavailable("the core produced JSON that is not an object");
      }
      return value as Record<string, unknown>;
    } catch (cause) {
      if (cause instanceof RuntimeUnavailable) throw cause;
      throw new RuntimeUnavailable(
        `the core produced output that is not JSON (exit ${outcome.code})`,
        cause,
      );
    }
  }

  #spawn(argv: readonly string[], stdin: string): Promise<ProcessOutcome> {
    return new Promise<ProcessOutcome>((resolve, reject) => {
      const child = spawn(this.#python, [...argv], {
        //: No shell: argv is passed through verbatim, so nothing in a payload
        //: can be interpreted as a command.
        shell: false,
        env: this.#env,
        ...(this.#cwd === undefined ? {} : { cwd: this.#cwd }),
        stdio: ["pipe", "pipe", "pipe"],
      });

      let stdout = "";
      let stderr = "";
      let bytes = 0;
      let settled = false;

      const finish = (outcome: ProcessOutcome): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(outcome);
      };
      const fail = (error: Error): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        child.kill("SIGKILL");
        reject(error);
      };

      const timer = setTimeout(() => {
        fail(new RuntimeUnavailable(`the core did not finish within ${this.#timeoutMs}ms`));
      }, this.#timeoutMs);
      timer.unref?.();

      child.stdout.setEncoding("utf8");
      child.stdout.on("data", (chunk: string) => {
        bytes += Buffer.byteLength(chunk, "utf8");
        if (bytes > this.#maxOutputBytes) {
          fail(new RuntimeUnavailable(`the core produced more than ${this.#maxOutputBytes} bytes`));
          return;
        }
        stdout += chunk;
      });
      child.stderr.setEncoding("utf8");
      child.stderr.on("data", (chunk: string) => {
        stderr += chunk;
      });
      child.on("error", (error) => {
        fail(new RuntimeUnavailable(`could not start '${this.#python}'`, error));
      });
      child.on("close", (code) => {
        finish({ code: code ?? 4, stdout, stderr });
      });

      child.stdin.on("error", () => {
        //: The child may exit before reading stdin (a rejected Skill name, for
        //: instance).  That is a normal EPIPE, not a transport failure; the
        //: exit code and stderr still carry the answer.
      });
      child.stdin.end(stdin, "utf8");
    });
  }
}

const STATUSES = new Set(["succeeded", "blocked", "rejected", "failed"]);

/** Validate that a parsed object really is an envelope before typing it as one. */
export function asEnvelope(value: Record<string, unknown>): HandlerEnvelope {
  const status = value["status"];
  if (typeof status !== "string" || !STATUSES.has(status)) {
    throw new RuntimeUnavailable(`the core returned an unknown status ${JSON.stringify(status)}`);
  }
  const reasons = Array.isArray(value["reasons"]) ? (value["reasons"] as unknown[]) : [];
  return {
    skill: typeof value["skill"] === "string" ? value["skill"] : "",
    status: status as HandlerEnvelope["status"],
    output: isRecord(value["output"]) ? value["output"] : {},
    reasons: reasons.filter((item): item is string => typeof item === "string"),
    canonical_owner:
      typeof value["canonical_owner"] === "string" ? value["canonical_owner"] : "",
    risk_class: (typeof value["risk_class"] === "string"
      ? value["risk_class"]
      : "R0") as HandlerEnvelope["risk_class"],
    failure_class: (typeof value["failure_class"] === "string"
      ? value["failure_class"]
      : null) as HandlerEnvelope["failure_class"],
    side_effects_performed: value["side_effects_performed"] === true,
    evidence: isRecord(value["evidence"]) ? value["evidence"] : {},
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
