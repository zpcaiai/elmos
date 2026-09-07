import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import { authorizeSmoke, smokeSessionEvidence } from "../../../../../lib/server/smokeLeaseRunner";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  try {
    const authorized = authorizeSmoke(request);
    const { sessionId } = await context.params;
    // Evidence outlives the lease: the services are gone, the record is not.
    return NextResponse.json(await smokeSessionEvidence(authorized, sessionId));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "SMOKE_EVIDENCE_UNAVAILABLE";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
