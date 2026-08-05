import { NextRequest, NextResponse } from "next/server";

import {
  FrtEngineProxyError,
  completeFrtConsoleRun,
  transitionFrtConsoleRun,
} from "../../../../../lib/server/frtEngineProxy";

const transitions = new Set(["claim", "cancel", "retry"]);
const operations = new Set([...transitions, "complete"]);
const maximumTransitionBytes = 2_048;
const maximumCompletionBytes = 256 * 1024;

function expectedVersionOf(body: unknown): number {
  if (!body || typeof body !== "object" || Array.isArray(body)
    || !Object.hasOwn(body, "expectedVersion")
    || !Number.isInteger((body as { expectedVersion?: unknown }).expectedVersion)
    || (body as { expectedVersion: number }).expectedVersion < 0) {
    throw new FrtEngineProxyError(400, "FRT_RUN_TRANSITION_INVALID");
  }
  return (body as { expectedVersion: number }).expectedVersion;
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ runId: string; operation: string }> },
) {
  try {
    const { runId, operation } = await context.params;
    if (!/^[a-f0-9]{24}$/.test(runId) || !operations.has(operation)) {
      throw new FrtEngineProxyError(400, "FRT_RUN_TRANSITION_INVALID");
    }
    const completing = operation === "complete";
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf8") > (completing ? maximumCompletionBytes : maximumTransitionBytes)) {
      throw new FrtEngineProxyError(413, "REQUEST_TOO_LARGE");
    }
    let body: unknown;
    try {
      body = JSON.parse(raw) as unknown;
    } catch {
      throw new FrtEngineProxyError(400, "FRT_RUN_TRANSITION_INVALID");
    }
    const expectedVersion = expectedVersionOf(body);

    if (!completing) {
      // A transition carries no payload beyond the optimistic-concurrency version.
      if (Object.keys(body as object).length !== 1) {
        throw new FrtEngineProxyError(400, "FRT_RUN_TRANSITION_INVALID");
      }
      const result = await transitionFrtConsoleRun(
        request,
        runId,
        operation as "claim" | "cancel" | "retry",
        expectedVersion,
      );
      return NextResponse.json(result.body, {
        status: result.status,
        headers: { "cache-control": "private, no-store" },
      });
    }

    const keys = Object.keys(body as object);
    if (keys.length !== 2 || !keys.includes("completion")) {
      throw new FrtEngineProxyError(400, "FRT_RUN_TRANSITION_INVALID");
    }
    const result = await completeFrtConsoleRun(
      request,
      runId,
      expectedVersion,
      (body as { completion: unknown }).completion,
    );
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { "cache-control": "private, no-store" },
    });
  } catch (error) {
    const status = error instanceof FrtEngineProxyError ? error.status : 400;
    const reason = error instanceof FrtEngineProxyError ? error.code : "FRT_CONSOLE_REQUEST_REJECTED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
