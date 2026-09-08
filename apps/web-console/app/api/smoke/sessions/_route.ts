import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../lib/server/generationRunner";
import { withBusinessAudit } from "../../../lib/server/operationsProxy";
import { authorizeSmoke, createSmokeSession } from "../../../lib/server/smokeLeaseRunner";
import { BoundedJsonError, readBoundedJson } from "../../../lib/server/boundedJson";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "SMOKE_SESSION_CREATE",
        businessLine: "RUNNABLE_SMOKE",
        route: "/api/smoke/sessions",
        target: "smoke-session",
      },
      () => create(request),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function create(request: NextRequest) {
  try {
    const context = authorizeSmoke(request);
    const body = await readBoundedJson(request, 4 * 1024);
    return NextResponse.json(await createSmokeSession(context, body), { status: 202 });
  } catch (error) {
    const status = error instanceof GenerationRunnerError || error instanceof BoundedJsonError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "SMOKE_SESSION_REQUEST_INVALID";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
