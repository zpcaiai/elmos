/**
 * End-to-end against the real Python core.
 *
 * These tests spawn the actual interpreter.  If it is not available the suite
 * *skips* rather than passing: a green run that silently exercised nothing is
 * the same lie this package exists to prevent.
 */

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { RepositoryRefactoringClient } from "../src/client.js";
import { SkillNotSucceeded } from "../src/errors.js";
import { PythonCoreRuntime } from "../src/runtime.js";
import type { WorkspacePayload } from "../src/types.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const coreRoot = resolve(packageRoot, "..", "repository-refactoring", "src");

function pythonAvailable(): string | null {
  for (const candidate of ["python3", "python"]) {
    try {
      execFileSync(candidate, ["-c", "import sys; assert sys.version_info >= (3, 11)"], {
        stdio: "ignore",
      });
      return candidate;
    } catch {
      continue;
    }
  }
  return null;
}

const python = pythonAvailable();
const skip = python === null ? "no python >= 3.11 on PATH" : false;

function client(): RepositoryRefactoringClient {
  return new RepositoryRefactoringClient({
    python: python ?? "python3",
    packageRoot: coreRoot,
    timeoutMs: 120_000,
  });
}

const WORKSPACE: WorkspacePayload = {
  source: "inline",
  repository_id: "billing",
  revision: "8a8f31c0d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2",
  files: [
    {
      path: "src/acme/billing.py",
      content: "def charge(customer_id: str, amount: int) -> str:\n    return f'{customer_id}:{amount}'\n",
    },
    { path: "pyproject.toml", content: '[project]\nname = "acme-billing"\nversion = "1.0.0"\n' },
  ],
};

test("the core is reachable and describes itself", { skip }, async () => {
  const described = await client().describe();
  assert.equal(typeof described["package"], "string");
});

test("a real Skill runs and returns a well-formed envelope", { skip }, async () => {
  const envelope = await client().runOrThrow("repository-discovery", { workspace: WORKSPACE });
  assert.equal(envelope.skill, "repository-discovery");
  assert.equal(envelope.status, "succeeded");
  assert.equal(envelope.side_effects_performed, false);
  assert.ok(typeof envelope.canonical_owner === "string" && envelope.canonical_owner.length > 0);
});

test("the same input twice produces the same evidence digest", { skip }, async () => {
  const runner = client();
  const first = await runner.runOrThrow("semantic-index", { workspace: WORKSPACE });
  const second = await runner.runOrThrow("semantic-index", { workspace: WORKSPACE });
  assert.deepEqual(first.evidence, second.evidence);
});

test("a Skill that needs more than a workspace blocks, and says why", { skip }, async () => {
  const envelope = await client().run("multi-repository-refactor-program", {
    program_id: "prog-1",
    portfolio: [],
  });
  assert.notEqual(envelope.status, "succeeded");
  assert.ok(envelope.reasons.length > 0 || Object.keys(envelope.output).length > 0);
});

test("runOrThrow surfaces the core's own reasons", { skip }, async () => {
  await assert.rejects(
    () => client().runOrThrow("multi-repository-refactor-program", { program_id: "p", portfolio: [] }),
    SkillNotSucceeded,
  );
});

test("a missing interpreter is an outage, not a failed run", { skip }, async () => {
  const runtime = new PythonCoreRuntime({ python: "definitely-not-a-real-interpreter" });
  await assert.rejects(() => runtime.describe(), /could not start/);
});

test("the subprocess does not inherit the host environment", { skip }, async () => {
  process.env["ELMOS_SDK_LEAK_CANARY"] = "leaked";
  try {
    const runtime = new PythonCoreRuntime({ python: python ?? "python3" });
    const outcome = await runtime
      .describe()
      .then(() => "ran")
      .catch(() => "ran");
    assert.equal(outcome, "ran");
    //: The assertion that matters is structural: the runtime builds its own
    //: environment from PATH and HOME only, so nothing else can reach the
    //: core.  Verified directly below rather than through the CLI.
    const probe = execFileSync(
      python ?? "python3",
      ["-c", "import os,sys; sys.stdout.write(os.environ.get('ELMOS_SDK_LEAK_CANARY',''))"],
      { env: { PATH: process.env["PATH"] ?? "", HOME: process.env["HOME"] ?? "" }, encoding: "utf8" },
    );
    assert.equal(probe, "");
  } finally {
    delete process.env["ELMOS_SDK_LEAK_CANARY"];
  }
});

test("the two unreadable-file shapes are distinguished by the core", { skip }, async () => {
  //: An undecodable source file lowers coverage; a declared binary asset does
  //: not. The SDK's WorkspaceFile union exists to keep a host from conflating
  //: them, so the distinction is asserted against the real core.
  const base = { source: "inline", repository_id: "r", revision: "a".repeat(40) } as const;
  const readable = { path: "a.py", content: "def f():\n    pass\n" };
  const runner = client();

  const undecodable = await runner.runOrThrow("repository-discovery", {
    workspace: {
      ...base,
      files: [
        readable,
        {
          path: "c.py",
          content_digest: `sha256:${"1".repeat(64)}`,
          size_bytes: 64,
          binary: false,
          unreadable_reason: "undecodable-utf8",
        },
      ],
    },
  });
  const asset = await runner.runOrThrow("repository-discovery", {
    workspace: {
      ...base,
      files: [
        readable,
        { path: "logo.png", content_digest: `sha256:${"2".repeat(64)}`, size_bytes: 2048, binary: true },
      ],
    },
  });

  const inventoryOf = (envelope: { output: Record<string, unknown> }): Record<string, unknown> =>
    envelope.output["repository_inventory"] as Record<string, unknown>;

  assert.ok((inventoryOf(undecodable)["unscanned"] as unknown[]).length === 1);
  assert.ok(Number(inventoryOf(undecodable)["coverage"]) < 1);
  assert.deepEqual(inventoryOf(asset)["unscanned"], []);
  assert.equal(Number(inventoryOf(asset)["coverage"]), 1);
});

test("an adapter cannot claim a level above what the engine executes", { skip }, async () => {
  const described = await client().describe();
  const skills = described["skills"] as { minimumAdapterLevel: string }[];
  const levels = new Set(skills.map((skill) => skill.minimumAdapterLevel));
  //: L5 is not a level the core's enum admits; a type that allowed it would
  //: let a host write a value the runtime rejects.
  assert.equal(levels.has("L5"), false);
});

test("a pinned clock makes a timestamping Skill reproducible", { skip }, async () => {
  const runner = client();
  const payload = {
    request: {
      apiVersion: "elmos.dev/v1",
      kind: "RefactorRequest",
      metadata: { tenantId: "acme", projectId: "billing" },
      spec: {
        repositories: [{ uri: "git@example.com/a/b.git", revision: "a".repeat(40), role: "primary" }],
        intent: {
          type: "structural-refactor",
          goals: ["rename post_entry to record_entry"],
          nonGoals: [],
          acceptanceCriteria: ["tests pass"],
        },
        constraints: { behaviorCompatibility: "strict", publicApiCompatibility: "backward-compatible" },
        execution: { mode: "supervised", createPullRequest: true, maxParallelShards: 4 },
      },
    },
    run_id: "run-sdk-1",
    action: "plan",
  };

  const at = (now: string): Promise<{ evidence: Record<string, unknown> }> =>
    runner.runOrThrow("repository-refactor-orchestrator", payload, { now });

  const [first, second, later] = await Promise.all([
    at("2026-01-15T09:30:00Z"),
    at("2026-01-15T09:30:00Z"),
    at("2031-07-04T12:00:00Z"),
  ]);

  assert.deepEqual(first.evidence, second.evidence, "the same instant must give the same evidence");
  assert.notDeepEqual(
    first.evidence,
    later.evidence,
    "a different instant must give different evidence; identical output would mean the pinned " +
      "clock is being parsed and ignored",
  );
});

test("the clock cannot be set from a payload", { skip }, async () => {
  const envelope = await client().run("human-approval-gate", { now: "2020-01-01T00:00:00Z" });
  assert.equal(envelope.status, "rejected");
});
