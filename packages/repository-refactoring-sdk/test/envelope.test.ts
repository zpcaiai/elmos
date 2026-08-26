import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RepositoryRefactoringClient,
  gateResults,
  requiresApproval,
  undecidedBlockingGates,
} from "../src/client.js";
import { ContractViolation, RuntimeUnavailable, SkillNotSucceeded } from "../src/errors.js";
import { asEnvelope } from "../src/runtime.js";
import type { CoreRuntime } from "../src/runtime.js";
import { EXIT_CODES, statusForExitCode, type HandlerEnvelope } from "../src/types.js";

function envelope(overrides: Partial<HandlerEnvelope> = {}): HandlerEnvelope {
  return {
    skill: "semantic-index",
    status: "succeeded",
    output: {},
    reasons: [],
    canonical_owner: "canonical.elmos.semantic-index",
    risk_class: "R0",
    failure_class: null,
    side_effects_performed: false,
    evidence: {},
    ...overrides,
  };
}

class StubRuntime implements CoreRuntime {
  calls: { skill: string; payload: unknown; context: unknown }[] = [];
  constructor(private readonly result: HandlerEnvelope) {}
  async run(
    skill: string,
    payload: Readonly<Record<string, unknown>>,
    trustedContext?: unknown,
  ): Promise<HandlerEnvelope> {
    this.calls.push({ skill, payload, context: trustedContext });
    return this.result;
  }
  async describe(): Promise<Readonly<Record<string, unknown>>> {
    return { skills: [] };
  }
}

test("exit codes map to statuses, and 64 maps to no status at all", () => {
  assert.equal(statusForExitCode(EXIT_CODES.succeeded), "succeeded");
  assert.equal(statusForExitCode(EXIT_CODES.blocked), "blocked");
  assert.equal(statusForExitCode(EXIT_CODES.rejected), "rejected");
  assert.equal(statusForExitCode(EXIT_CODES.failed), "failed");
  assert.equal(statusForExitCode(EXIT_CODES.usage), null);
});

test("an unknown status is a broken runtime, not a result", () => {
  assert.throws(() => asEnvelope({ status: "probably-fine" }), RuntimeUnavailable);
});

test("a blocked run is returned, not thrown, so the reasons survive", async () => {
  const blocked = envelope({
    status: "blocked",
    reasons: ["gate 'security-scan' was not decided"],
    failure_class: "approval-required",
  });
  const client = new RepositoryRefactoringClient({ runtime: new StubRuntime(blocked) });
  const result = await client.run("semantic-index");
  assert.equal(result.status, "blocked");
  assert.deepEqual([...result.reasons], ["gate 'security-scan' was not decided"]);
});

test("runOrThrow reports the failure class so a caller can tell retryable from final", async () => {
  const blocked = envelope({ status: "blocked", failure_class: "approval-required" });
  const client = new RepositoryRefactoringClient({ runtime: new StubRuntime(blocked) });
  await assert.rejects(
    () => client.runOrThrow("semantic-index"),
    (error: unknown) => {
      assert.ok(error instanceof SkillNotSucceeded);
      assert.equal(error.status, "blocked");
      assert.equal(error.retryable, false);
      return true;
    },
  );
});

test("an unknown Skill never reaches the subprocess", async () => {
  const client = new RepositoryRefactoringClient({ runtime: new StubRuntime(envelope()) });
  await assert.rejects(
    // @ts-expect-error — the point of the test is the runtime check behind the type.
    () => client.run("not-a-skill"),
    ContractViolation,
  );
});

test("a sequence stops at the first non-success", async () => {
  const blocked = envelope({ status: "blocked" });
  const runtime = new StubRuntime(blocked);
  const client = new RepositoryRefactoringClient({ runtime });
  const results = await client.runSequence([
    { skill: "repository-discovery" },
    { skill: "semantic-index" },
    { skill: "recipe-synthesis" },
  ]);
  assert.equal(results.length, 1);
  assert.equal(runtime.calls.length, 1);
});

test("an undecided gate reads as null, never as false", () => {
  const withGates = envelope({
    output: {
      gates: [
        { gate: "full-tests", passed: true, blocking: true, detail: "" },
        { gate: "security-scan", blocking: true, detail: "no evidence was produced" },
        { gate: "lint", passed: false, blocking: false, detail: "" },
      ],
    },
  });
  const gates = gateResults(withGates);
  assert.equal(gates[1]?.passed, null);
  assert.equal(gates[2]?.passed, false);
  const undecided = undecidedBlockingGates(withGates);
  assert.deepEqual(undecided.map((gate) => gate.gate), ["security-scan"]);
});

test("R2 and above need a human", () => {
  assert.equal(requiresApproval("R1"), false);
  assert.equal(requiresApproval("R2"), true);
  assert.equal(requiresApproval("R4"), true);
});
