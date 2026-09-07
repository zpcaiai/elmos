import { readFileSync } from "node:fs";

import {
  validateFrtBatchPlanRequest,
  validateFrtRunCompletionRequest,
  validateFrtRunTransitionRequest,
  validateFrtSkillRunRequest,
} from "./frt-contract-validation.js";
import { frtRuntime } from "./frt-runtime.js";
import type { FrtBatchPlanRequest, FrtSkillRunRequest } from "./frt-types.js";

function option(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function inputPath(): string {
  const value = option("--request");
  if (!value) throw new Error("--request <json-file> is required");
  return value;
}

function required(name: string): string {
  const value = option(name);
  if (!value) throw new Error(`${name} <value> is required`);
  return value;
}

function jsonFile(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

function print(value: unknown): void {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function main(): number {
  const command = process.argv[2];
  if (command === "catalog") {
    print(frtRuntime.catalog(option("--batch"), option("--query")));
    return 0;
  }
  if (command === "routes") {
    print({ directedRouteCount: frtRuntime.routes().length, routes: frtRuntime.routes() });
    return 0;
  }
  if (command === "batch-plan") {
    const result = frtRuntime.planBatch(
      validateFrtBatchPlanRequest(jsonFile(inputPath())) as FrtBatchPlanRequest,
    );
    print(result);
    return result.state === "READY" ? 0 : 3;
  }
  if (["claim", "heartbeat", "cancel", "retry", "complete"].includes(command ?? "")) {
    const scope = {
      organizationId: required("--organization"),
      tenantId: required("--tenant"),
      workspaceId: required("--workspace"),
      projectId: required("--project"),
      accountId: required("--account"),
      environmentId: required("--environment"),
      releaseId: required("--release"),
    };
    const runId = required("--run");
    const actor = required("--actor");
    const body = jsonFile(inputPath());
    const result = command === "complete"
      ? (() => {
        const parsed = validateFrtRunCompletionRequest(body);
        return frtRuntime.complete(scope, runId, parsed.expectedVersion, actor, parsed.completion);
      })()
      : (() => {
        const parsed = validateFrtRunTransitionRequest(body);
        const transition = command === "claim"
          ? frtRuntime.claim
          : command === "heartbeat" ? frtRuntime.heartbeat
          : command === "cancel" ? frtRuntime.cancel : frtRuntime.retry;
        return transition.call(frtRuntime, scope, runId, parsed.expectedVersion, actor);
      })();
    if (!result) throw new Error("run not found");
    print(result);
    return result.state === "SUCCEEDED" || result.state === "RUNNING" || result.state === "QUEUED"
      ? 0
      : result.state === "BLOCKED" ? 3 : 2;
  }
  if (["plan", "analyze", "execute", "verify"].includes(command ?? "")) {
    const request = validateFrtSkillRunRequest(jsonFile(inputPath())) as FrtSkillRunRequest;
    const expectedAction = command!.toLocaleUpperCase("en-US");
    if (request.action !== expectedAction) {
      throw new Error(`request action must be ${expectedAction}`);
    }
    const result = frtRuntime.run(request);
    print(result);
    return result.state === "SUCCEEDED" ? 0 : result.state === "BLOCKED" ? 3 : 2;
  }
  throw new Error("usage: frt-cli <catalog|routes|batch-plan|plan|analyze|execute|verify|claim|heartbeat|cancel|retry|complete> [--request file] [--batch G01] [--query text] [--organization id --tenant id --workspace id --project id --account id --environment id --release id --run id --actor id]");
}

try {
  process.exitCode = main();
} catch {
  process.stderr.write("FRT_CLI_REQUEST_REJECTED\n");
  process.exitCode = 2;
}
