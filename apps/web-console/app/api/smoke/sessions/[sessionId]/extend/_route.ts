import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import { withBusinessAudit } from "../../../../../lib/server/operationsProxy";
import { authorizeSmoke, extendSmokeSession } from "../../../../../lib/server/smokeLeaseRunner";
import { BoundedJsonError, readBoundedJson } from "../../../../../lib/server/boundedJson";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  try {
    return await withBusinessAudit(
      request,
      {
        // Extension beyond the free quota is a metered, attributable decision:
        // it is audited even when the run itself never leaves the workstation.
        action: "SMOKE_SESSION_EXTEND",
        businessLine: "RUNNABLE_SMOKE",
        route: "/api/smoke/sessions/:id/extend",
        target: "smoke-session",
      },
      () => extend(request, context),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function extend(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  try {
    const authorized = authorizeSmoke(request);
    const { sessionId } = await context.params;
    const body = await readBoundedJson(request, 4 * 1024);
    return NextResponse.json(await extendSmokeSession(authorized, sessionId, body));
  } catch (error) {
    const status = error instanceof GenerationRunnerError || error instanceof BoundedJsonError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "SMOKE_EXTENSION_INVALID";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
